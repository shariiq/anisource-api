"""State management for MKissa crypto material and API handshakes."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp

from ...exceptions import CryptoError
from ...utils.mkissa_crypto import MKissaCrypto
from .bundle import BuildInfo, MKissaBundle, MKissaConfig

log = logging.getLogger(__name__)

_ANIME_LANE = "k7"
_BOOTSTRAP_PATH = "/client-crypto/v1/bootstrap"
_CRYPTO_CHUNK_MARKER = "aaReq"
_ENTRY_PATTERN = re.compile(r'import\("([^"]*/entry/app\.[^"]*\.js)"\)')
_CHUNK_PATTERN = re.compile(r'["\'](\.\.?/[\w./-]+\.js)["\']')
_MATERIAL_TTL_SECONDS = 6 * 60 * 60
_MAX_BUILD_CHUNKS = 40
_BUILD_CHUNK_BATCH = 4


@dataclass(frozen=True, slots=True)
class Material:
    """Crypto material for one MKissa frontend build."""

    key: bytes
    epoch: int
    build_id: str
    config: MKissaConfig | None
    expires_at: float
    fetched_at: float

    def is_expired(self) -> bool:
        """Return whether this material has passed its six-hour lifetime."""
        return time.time() >= self.expires_at


class MKissaKeyManager:
    """Resolve frontend build data and manage MKissa's crypto handshake."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None,
        site_url: str,
        api_url: str,
        *,
        session_factory: Callable[[], Awaitable[aiohttp.ClientSession]] | None = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self.site_url = site_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self._cached_material: Material | None = None
        self._stored_build: BuildInfo | None = None
        self._material_lock = asyncio.Lock()

    async def get_material(self, force_refresh: bool = False) -> Material:
        """Return valid material, sharing refresh work across concurrent callers."""
        entered_at = time.time()
        if not force_refresh and self._is_cache_valid():
            return self._cached_material  # type: ignore[return-value]

        async with self._material_lock:
            cached = self._cached_material
            if cached is not None and (
                cached.fetched_at > entered_at or (not force_refresh and not cached.is_expired())
            ):
                return cached

            handshake = await self._handshake()
            if handshake is None:
                raise CryptoError("Unable to obtain MKissa crypto material")

            build_id, seeds, mask, bootstrap, config = handshake
            try:
                part_b = base64.b64decode(bootstrap["partB"], validate=True)
                epoch = int(bootstrap["epoch"])
            except (KeyError, TypeError, ValueError, binascii.Error) as error:
                raise CryptoError("Invalid MKissa bootstrap response") from error
            if len(part_b) < 32:
                raise CryptoError("Invalid MKissa bootstrap key fragment")

            self._stored_build = BuildInfo(build_id, seeds, config)
            now = time.time()
            material = Material(
                key=MKissaCrypto.derive_key(mask, part_b),
                epoch=epoch,
                build_id=build_id,
                config=config,
                expires_at=now + _MATERIAL_TTL_SECONDS,
                fetched_at=now,
            )
            self._cached_material = material
            return material

    def invalidate(self) -> None:
        """Discard cached key material without discarding the frontend build."""
        self._cached_material = None

    def invalidate_build(self) -> None:
        """Discard both key material and the cached frontend build."""
        self._stored_build = None
        self._cached_material = None

    @staticmethod
    def is_crypto_error(body: str) -> bool:
        """Return whether a GraphQL response reports an AA crypto failure."""
        try:
            errors = json.loads(body).get("errors", [])
        except (json.JSONDecodeError, AttributeError):
            return False
        return any(
            isinstance(error, dict)
            and str((error.get("extensions") or {}).get("code", "")).startswith("AA_CRYPTO")
            for error in errors
        )

    @staticmethod
    def api_error_message(body: str) -> str | None:
        """Return a useful non-crypto GraphQL error message, when present."""
        if MKissaKeyManager.is_crypto_error(body):
            return None
        try:
            errors = json.loads(body).get("errors", [])
        except (json.JSONDecodeError, AttributeError):
            return None
        for error in errors:
            if not isinstance(error, dict) or not error.get("message"):
                continue
            message = str(error["message"])
            if message == "NEED_CAPTCHA":
                return (
                    "MKissa is rate limiting this network (NEED_CAPTCHA). "
                    "Browsing still works; streams should return after a while."
                )
            return f"MKissa: {message}"
        return None

    def _is_cache_valid(self) -> bool:
        return self._cached_material is not None and not self._cached_material.is_expired()

    async def _handshake(
        self,
    ) -> tuple[str, tuple[str, ...], bytes, dict[str, object], MKissaConfig | None] | None:
        cached = self._stored_build
        if cached is not None:
            mask = self._derive_mask(cached)
            if mask is not None:
                bootstrap, stale = await self._bootstrap(
                    cached.build_id, mask, self._get_epoch_candidates(), cached.config
                )
                if bootstrap is not None:
                    return cached.build_id, cached.seeds, mask, bootstrap, cached.config
                if not stale:
                    return None
                bootstrap, _ = await self._bootstrap(
                    cached.build_id, mask, self._get_skewed_epoch_candidates(), cached.config
                )
                if bootstrap is not None:
                    return cached.build_id, cached.seeds, mask, bootstrap, cached.config

        fresh = await self._resolve_build()
        if fresh is None:
            return None
        mask = self._derive_mask(fresh)
        if mask is None:
            return None
        bootstrap, _ = await self._bootstrap(
            fresh.build_id, mask, self._get_epoch_candidates(), fresh.config
        )
        if bootstrap is None:
            return None
        return fresh.build_id, fresh.seeds, mask, bootstrap, fresh.config

    @staticmethod
    def _derive_mask(build: BuildInfo) -> bytes | None:
        config = build.config
        if config is None:
            return MKissaCrypto.derive_mask(build.build_id, list(build.seeds))
        return MKissaCrypto.derive_mask(
            build.build_id,
            list(build.seeds),
            salt_mul=config.salt_mul,
            salt_add=config.salt_add,
            frag_mul=config.frag_mul,
            frag_add=config.frag_add,
        )

    async def _bootstrap(
        self,
        build_id: str,
        mask: bytes,
        epochs: list[int],
        config: MKissaConfig | None,
    ) -> tuple[dict[str, object] | None, bool]:
        session = await self._ensure_session()
        host = urlparse(self.site_url).hostname or ""
        url = f"{self.api_url}{_BOOTSTRAP_PATH}"
        params = {"buildId": build_id, "k": _ANIME_LANE}
        saw_stale = False

        for epoch in epochs:
            headers = {
                "x-build-id": build_id,
                "x-aa-boot": MKissaCrypto.boot_token(
                    mask,
                    build_id,
                    epoch,
                    "mkissa",
                    host,
                    _ANIME_LANE,
                    boot_prefix=config.boot_prefix if config else "FD0xZhgI:",
                    join_char=config.join_char if config else ".",
                    parts=config.parts if config else None,
                ),
                "Origin": self.site_url,
                "Referer": f"{self.site_url}/",
            }
            try:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status < 200 or response.status >= 300:
                        saw_stale = saw_stale or response.status in {403, 404}
                        continue
                    data = await response.json(content_type=None)
            except (TimeoutError, aiohttp.ClientError, ValueError):
                return None, False
            if not isinstance(data, dict):
                continue
            lane = data.get("k")
            if lane is not None and lane != _ANIME_LANE:
                continue
            return data, False
        return None, saw_stale

    async def _resolve_build(self) -> BuildInfo | None:
        session = await self._ensure_session()
        try:
            async with session.get(f"{self.site_url}/") as response:
                if response.status < 200 or response.status >= 300:
                    return None
                html = await response.text(errors="replace")
            entry_match = _ENTRY_PATTERN.search(html)
            if entry_match is None:
                return None
            entry_url = urljoin(f"{self.site_url}/", entry_match.group(1))
            async with session.get(entry_url) as response:
                if response.status < 200 or response.status >= 300:
                    return None
                app_js = await response.text(errors="replace")
        except (TimeoutError, aiohttp.ClientError):
            return None

        chunk_references = sorted(
            dict.fromkeys(_CHUNK_PATTERN.findall(app_js)),
            key=lambda reference: "/chunks/" not in reference,
        )[:_MAX_BUILD_CHUNKS]

        for index in range(0, len(chunk_references), _BUILD_CHUNK_BATCH):
            batch = chunk_references[index : index + _BUILD_CHUNK_BATCH]
            results = await asyncio.gather(
                *(self._parse_chunk(urljoin(entry_url, reference)) for reference in batch),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BuildInfo):
                    return result
        return None

    async def _parse_chunk(self, url: str) -> BuildInfo | None:
        session = await self._ensure_session()
        async with session.get(url) as response:
            if response.status < 200 or response.status >= 300:
                return None
            body = await response.text(errors="replace")
        if _CRYPTO_CHUNK_MARKER not in body:
            return None
        return MKissaBundle.parse(body)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        session = self._session
        if session is not None and not session.closed:
            return session
        if self._session_factory is None:
            raise CryptoError("MKissa key manager has no active HTTP session")
        session = await self._session_factory()
        self._session = session
        return session

    @staticmethod
    def _get_epoch_candidates() -> list[int]:
        window_ms = 7 * 24 * 60 * 60 * 1000
        now = int(time.time() * 1000)
        current = now // window_ms
        grace_ms = 24 * 60 * 60 * 1000
        if now - current * window_ms < grace_ms:
            return [current - 1, current]
        return [current]

    @staticmethod
    def _get_skewed_epoch_candidates() -> list[int]:
        window_ms = 7 * 24 * 60 * 60 * 1000
        current = int(time.time() * 1000) // window_ms
        return [current + 1, current - 1]
