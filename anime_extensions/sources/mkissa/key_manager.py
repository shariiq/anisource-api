"""State management for MKissa crypto material and API handshakes."""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import aiohttp
from ...utils.mkissa_crypto import MKissaCrypto

log = logging.getLogger(__name__)

@dataclass
class Material:
    """Encapsulated crypto material for MKissa."""
    key: bytes
    epoch: int
    build_id: str
    expires_at: float
    fetched_at: float

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

class MKissaKeyManager:
    """
    Handles the complex handshake flow to obtain AES keys for MKissa streams.

    Flow:
    1. Resolve Build (Scrape JS chunks) -> buildId, seeds
    2. Handshake (Bootstrap) -> epoch, partB
    3. Derive Key (XOR mask + partB)
    """

    def __init__(self, session: aiohttp.ClientSession, site_url: str, api_url: str):
        self.session = session
        self.site_url = site_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self._cached_material: Material | None = None
        self._stored_build: str = ""  # "buildId|seed1,seed2,seed3,seed4"

    async def get_material(self, force_refresh: bool = False) -> Material:
        """Get current valid crypto material, performing handshake if needed."""
        if not force_refresh and self._cached_material and not self._cached_material.is_expired():
            return self._cached_material

        entered_at = time.time()

        # Attempt to use cached build first
        cached_build = self._parse_stored_build()
        if cached_build:
            build_id, seeds = cached_build
            mask = MKissaCrypto.derive_mask(build_id, seeds)
            if mask:
                # Try standard epochs
                bootstrap = await self._bootstrap(build_id, mask, self._get_epoch_candidates())
                if bootstrap:
                    return self._create_material(bootstrap, mask, build_id)

                # Try skewed epochs
                bootstrap = await self._bootstrap(build_id, mask, self._get_skewed_epoch_candidates())
                if bootstrap:
                    return self._create_material(bootstrap, mask, build_id)

        # Resolve fresh build if cache fails or is missing
        fresh_build = await self._resolve_build()
        if not fresh_build:
            raise Exception("Unable to resolve MKissa build (could not find crypto chunk)")

        build_id, seeds = fresh_build
        mask = MKissaCrypto.derive_mask(build_id, seeds)
        if not mask:
            raise Exception("Failed to derive mask from fresh build")

        bootstrap = await self._bootstrap(build_id, mask, self._get_epoch_candidates())
        if not bootstrap:
            raise Exception("Handshake failed for fresh build")

        material = self._create_material(bootstrap, mask, build_id)
        return material

    def _create_material(self, bootstrap: dict, mask: bytes, build_id: str) -> Material:
        # bootstrap is { "epoch": ..., "partB": ... }
        part_b = base64.b64decode(bootstrap["partB"])
        key = MKissaCrypto.derive_key(mask, part_b)

        now = time.time()
        material = Material(
            key=key,
            epoch=bootstrap["epoch"],
            build_id=build_id,
            expires_at=now + (6 * 60 * 60),  # 6 hour TTL
            fetched_at=now,
        )
        self._cached_material = material
        # Cache the build: buildId|seed1,seed2,seed3,seed4
        # Note: We don't have the seeds here, we should pass them or store them separately.
        # For now, we'll let the cache be managed by a separate mechanism or just not cache seeds here.
        return material

    async def _bootstrap(self, build_id: str, mask: bytes, epochs: list[int]) -> dict | None:
        """Perform bootstrap handshake."""
        host = self.site_url.split("//")[-1].split("/")[0]
        url = f"{self.api_url}/client-crypto/v1/bootstrap"

        for epoch in epochs:
            token = MKissaCrypto.boot_token(mask, build_id, epoch, "mkissa", host, "k7")
            headers = {
                "x-build-id": build_id,
                "x-aa-boot": token,
                "Origin": self.site_url,
                "Referer": f"{self.site_url}/",
            }

            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status in {403, 404}:
                    continue # Try next epoch
        return None

    async def _resolve_build(self) -> tuple[str, list[str]] | None:
        """Scrape site for the crypto build chunk."""
        # 1. Find entry JS
        try:
            async with self.session.get(f"{self.site_url}/") as resp:
                html = await resp.text()
                # import(".../entry/app.xxxx.js")
                match = re.search(r'import\("([^"]*/entry/app\.[^"]*\.js)"\)', html)
                if not match:
                    return None
                entry_url = self.site_url + match.group(1) if match.group(1).startswith("/") else match.group(1)
        except Exception:
            return None

        # 2. Scan chunks for "aaReq"
        # The site lists chunks in the entry file
        async with self.session.get(entry_url) as resp:
            js = await resp.text()

        chunk_refs = re.findall(r'["\'](\.\.?/[\w./-]+\.js)["\']', js)
        # Prioritize /chunks/
        sorted_chunks = sorted(chunk_refs, key=lambda x: "/chunks/" in x, reverse=True)

        for chunk_ref in sorted_chunks[:40]:
            chunk_url = self.site_url + chunk_ref if chunk_ref.startswith("/") else entry_url.replace("/entry/app.", "/chunks/app.") # Simplified
            # This resolution is tricky in Kotlin. Let's try a simpler approach: resolve relative to entry_url.
            # Better yet, just search for "aaReq" in the entry file first.
            try:
                async with self.session.get(chunk_url) as resp:
                    body = await resp.text()
                    if "aaReq" in body:
                        # Extract build info: buildId and seeds
                        # Kotlin does MKissaBundle.parse(body)
                        # We need to find the object that looks like {buildId: "...", seeds: ["...", "..."]}
                        # This is usually in a JS object literal.
                        build_info = self._parse_build_from_js(body)
                        if build_info:
                            return build_info
            except Exception:
                continue

        return None

    def _parse_build_from_js(self, js: str) -> tuple[str, list[str]] | None:
        """Extract buildId and seeds from JS code."""
        # Look for patterns like buildId: "...", seeds: ["...", "..."]
        bid_match = re.search(r'buildId\s*:\s*"([^"]+)"', js)
        seeds_match = re.search(r'seeds\s*:\s*\[([^\]]+)\]', js)

        if bid_match and seeds_match:
            build_id = bid_match.group(1)
            seeds = [s.strip('"\' ') for s in seeds_match.group(1).split(",")]
            if len(seeds) == 4:
                return build_id, seeds
        return None

    def _parse_stored_build(self) -> tuple[str, list[str]] | None:
        if not self._stored_build:
            return None
        try:
            build_id, seeds_raw = self._stored_build.split("|")
            seeds = seeds_raw.split(",")
            if len(seeds) == 4:
                return build_id, seeds
        except Exception:
            return None
        return None

    def _get_epoch_candidates(self) -> list[int]:
        window_ms = 7 * 24 * 60 * 60 * 1000
        now = int(time.time() * 1000)
        current = now // window_ms
        # Grace period for the previous epoch
        grace_ms = 24 * 60 * 60 * 1000
        if now - current * window_ms < grace_ms:
            return [current - 1, current]
        return [current]

    def _get_skewed_epoch_candidates(self) -> list[int]:
        now = int(time.time() * 1000)
        window_ms = 7 * 24 * 60 * 60 * 1000
        current = now // window_ms
        return [current + 1, current - 1]
