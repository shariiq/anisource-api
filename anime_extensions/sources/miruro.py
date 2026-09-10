"""Miruro.tv anime source with encrypted pipe API and vault stream proxying.

Miruro communicates with its own backend via an obfuscated pipe API
(`/api/secure/pipe?e=...`). Responses are XOR-decrypted and GZIP-decompressed.
HLS streams are wrapped through Miruro's ultracloud.cc vault proxies to
bypass CDN CORS/header gating.

Ported from the Kotlin extension `Miruro.kt` / `MiruroExtractor.kt`.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from ..base import BaseSource
from ..models import Anime, Episode, Server, Stream, Subtitle
from ..utils.crypto import (
    miruro_build_pipe_url,
    miruro_build_proxied_url,
    miruro_decrypt_pipe,
)

log = logging.getLogger(__name__)


# ── Provider aliases (Kotlin: KNOWN_DISPLAY_NAMES) ───────────────────────────

_PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "kiwi": "AnimePahe",
    "bee": "Anikoto",
    "hop": "Zoro",
    "ally": "9Anime",
    "duck": "AnimeDuck",
    "fox": "AnimeFox",
    "ant": "AnimeKai",
    "owl": "AnimeOwl",
}

# Sub-type display order for scanlator labels (Kotlin: SUB_TYPE_DISPLAY_ORDER)
_SUB_TYPE_DISPLAY_ORDER = ["sub", "dub", "ssub", "h-sub"]
_SCANLATOR_SUB_TYPES = {"sub", "dub", "ssub", "h-sub"}

# AniList status string → normalised status
_STATUS_MAP: dict[str, str] = {
    "RELEASING": "ongoing",
    "FINISHED": "completed",
    "CANCELLED": "cancelled",
    "NOT_YET_RELEASED": "upcoming",
}


def _provider_display_name(alias: str) -> str:
    """Return a human-readable provider name for the given alias."""
    return _PROVIDER_DISPLAY_NAMES.get(alias, alias.capitalize())


def _format_sub_type_label(sub_type: str) -> str:
    """Format sub-type string for display in the scanlator field."""
    return {"sub": "Sub", "dub": "Dub", "ssub": "Soft Sub", "h-sub": "Hard Sub"}.get(
        sub_type, sub_type.capitalize()
    )


class Miruro(BaseSource):
    """Miruro.tv anime source.

    Uses Miruro's proprietary encrypted pipe API as the primary data source.
    All browse, search, details, episode, and stream calls go through
    `/api/secure/pipe?e={base64url-encoded-payload}` with XOR+GZIP response
    decryption.

    Stream URLs are wrapped through `vault01/02.ultracloud.cc` using an
    FNV-1a-based proxy selected deterministically per episode. This mirrors
    the browser frontend's behaviour and bypasses direct-fetch 403s from
    upstream CDNs (e.g. kwik.cx, owocdn.top).

    Limitations:
    - No AniList GraphQL fallback (pipe API only; empty on pipe failure).
    - No Cloudflare cookie-farming warm-up (may 403 on some CDNs).
    - No multi-provider episode merging; a single preferred provider is used.
    - Embed-type streams (MegaCloud, RapidCloud) are skipped; HLS only.
    """

    name = "Miruro.tv"
    id = "miruro"
    base_url = "https://www.miruro.tv"

    DOMAINS = ["miruro.tv", "miruro.to", "miruro.bz", "miruro.com"]

    # Default provider preference order (mirrors Kotlin providerOrder logic)
    DEFAULT_PROVIDER_ORDER = ["kiwi", "bee", "hop", "ally"]

    def __init__(
        self,
        *,
        domain: str | None = None,
        session: Any = None,
        preferred_provider: str = "kiwi",
        preferred_sub_type: str = "sub",
    ) -> None:
        super().__init__(session=session)
        if domain:
            self.base_url = f"https://{domain}"
        self.preferred_provider = preferred_provider
        self.preferred_sub_type = preferred_sub_type

    # ── Pipe API ─────────────────────────────────────────────────────────────

    async def _pipe_get(
        self,
        path: str,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an encrypted GET request to the pipe API and return parsed JSON.

        Builds the obfuscated URL, fetches it, then decrypts the response
        body with XOR + GZIP (when `x-obfuscated: 2` semantics apply).
        On any error returns an empty dict to let callers degrade gracefully.
        """
        url = miruro_build_pipe_url(self.base_url, path, "GET", query)
        try:
            session = await self._ensure_session()
            async with session.get(url, headers=self._headers) as resp:
                raw_body = await resp.text(errors="replace")
                obfuscated = resp.headers.get("x-obfuscated", "2")
                status = resp.status
        except Exception as exc:
            log.warning("Miruro pipe GET %s failed: %s", path, exc)
            return {}

        if status != 200:
            log.warning("Miruro pipe GET %s returned HTTP %s", path, status)
            return {}

        try:
            decrypted = miruro_decrypt_pipe(raw_body, obfuscated)
        except Exception as exc:
            log.warning("Miruro pipe decrypt failed for %s: %s", path, exc)
            return {}

        if not decrypted.strip():
            return {}

        try:
            return json.loads(decrypted)
        except json.JSONDecodeError as exc:
            log.warning("Miruro pipe JSON parse failed for %s: %s", path, exc)
            return {}

    # ── Listing ──────────────────────────────────────────────────────────────

    async def get_popular(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch trending anime (TRENDING_DESC, RELEASING)."""
        data = await self._pipe_get(
            "search/browse",
            {
                "type": "ANIME",
                "status": "RELEASING",
                "sort": "TRENDING_DESC",
                "page": page,
                "perPage": 20,
            },
        )
        return self._parse_media_list(data), self._has_next_page(data, 20)

    async def get_latest(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch recently updated anime (UPDATED_AT_DESC, RELEASING)."""
        data = await self._pipe_get(
            "search/browse",
            {
                "type": "ANIME",
                "status": "RELEASING",
                "sort": "UPDATED_AT_DESC",
                "page": page,
                "perPage": 20,
            },
        )
        return self._parse_media_list(data), self._has_next_page(data, 20)

    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        """Search anime by text query or AniList ID prefix (`miruro:<id>`).

        Prefix queries (`miruro:154587`) go directly to `info/<id>` for a
        quick single-title lookup with full metadata.
        """
        if query.startswith("miruro:"):
            anilist_id = query.removeprefix("miruro:").strip()
            data = await self._pipe_get(f"info/{anilist_id}")
            media = data.get("media") or data
            if not isinstance(media, dict) or not media:
                return [], False
            return [self._parse_anime(media, full=True)], False

        data = await self._pipe_get(
            "search",
            {
                "type": "ANIME",
                "q": query,
                "sort": "SEARCH_MATCH",
                "limit": 20,
                "offset": (page - 1) * 20,
            },
        )
        return self._parse_media_list(data), self._has_next_page(data, 20)

    # ── Details ───────────────────────────────────────────────────────────────

    async def get_details(self, anime_id: str) -> Anime:
        """Get full metadata for a single anime by its AniList id."""
        data = await self._pipe_get(f"info/{anime_id}")
        media = data.get("media") or data
        if not isinstance(media, dict):
            media = {}
        return self._parse_anime(media, full=True)

    # ── Episodes ──────────────────────────────────────────────────────────────

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        """Get episode list for a given AniList id.

        Selects the preferred provider (default: `kiwi` = AnimePahe), falls
        back through DEFAULT_PROVIDER_ORDER, then any available provider.
        Each episode's ID is a JSON string encoding the episode id, provider,
        preferred sub-type, available sub-type map, and the anilist id; this
        compact envelope is decoded by `get_streams` without an extra network
        call.
        """
        data = await self._pipe_get("episodes", {"anilistId": anime_id})
        providers: dict[str, Any] = data.get("providers") or {}
        if not providers:
            log.warning("Miruro: no providers in episodes response for %s", anime_id)
            return []

        provider_key = self._select_provider(providers)
        if not provider_key:
            return []

        provider_data: dict[str, Any] = providers.get(provider_key) or {}
        episodes_obj: dict[str, Any] = provider_data.get("episodes") or {}
        if not episodes_obj:
            return []

        # Build cross-provider subType map: episode_number → {subType → episode_id}
        all_sub_type_ids: dict[float, dict[str, str]] = {}
        all_ep_meta: dict[float, tuple[float, str]] = {}

        for sub_type, ep_array in episodes_obj.items():
            if not isinstance(ep_array, list):
                continue
            for ep in ep_array:
                number = float(ep.get("number") or 0)
                ep_id = ep.get("id") or ""
                title = ep.get("title") or ""
                if number not in all_sub_type_ids:
                    all_sub_type_ids[number] = {}
                    all_ep_meta[number] = (number, title)
                all_sub_type_ids[number][sub_type] = ep_id

        episodes: list[Episode] = []
        for number in sorted(all_sub_type_ids):
            sub_type_ids = all_sub_type_ids[number]
            raw_number, title = all_ep_meta[number]

            default_sub_type = self._select_sub_type(sub_type_ids)
            episode_id = sub_type_ids.get(default_sub_type) or ""

            id_envelope = json.dumps(
                {
                    "episodeId": episode_id,
                    "provider": provider_key,
                    "defaultSubType": default_sub_type,
                    "subTypes": sub_type_ids,
                    "anilistId": anime_id,
                },
                separators=(",", ":"),
            )

            has_sub = "sub" in sub_type_ids
            has_dub = "dub" in sub_type_ids
            scanlator = self._build_scanlator(provider_key, sub_type_ids)

            episodes.append(
                Episode(
                    id=id_envelope,
                    number=raw_number,
                    title=title if title else f"Episode {int(number)}",
                    has_sub=has_sub,
                    has_dub=has_dub,
                    scanlator=scanlator,
                )
            )

        # Descending episode order (newest first) matches Kotlin default
        episodes.sort(key=lambda e: e.number, reverse=True)
        return episodes

    # ── Servers ───────────────────────────────────────────────────────────────

    async def get_servers(self, episode_id: str) -> list[Server]:
        """Derive pseudo-servers from the episode ID envelope.

        Miruro doesn't expose discrete streaming servers; instead the pipe
        `sources` call returns streams directly. We surface each available
        sub-type (sub/dub/ssub/h-sub) as a separate synthetic server so
        callers can choose which sub-type to load.
        """
        try:
            ep_data: dict[str, Any] = json.loads(episode_id)
        except (json.JSONDecodeError, TypeError):
            return []

        sub_types: dict[str, str] = ep_data.get("subTypes") or {}
        provider_key: str = ep_data.get("provider") or "unknown"
        provider_name = _provider_display_name(provider_key)

        servers: list[Server] = []
        for sub_type in _SUB_TYPE_DISPLAY_ORDER:
            if sub_type in sub_types:
                servers.append(
                    Server(
                        id=sub_type,
                        name=f"{provider_name} ({_format_sub_type_label(sub_type)})",
                        type=sub_type,
                    )
                )

        # Fall back: any sub-types not in the display order
        seen = set(_SUB_TYPE_DISPLAY_ORDER)
        for sub_type in sub_types:
            if sub_type not in seen:
                servers.append(
                    Server(
                        id=sub_type,
                        name=f"{provider_name} ({_format_sub_type_label(sub_type)})",
                        type=sub_type,
                    )
                )

        return servers

    # ── Streams ───────────────────────────────────────────────────────────────

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Extract playable streams for the given episode and sub-type server.

        `server_id` is the sub-type string (e.g. `"sub"`, `"dub"`) returned
        by `get_servers`. The episode envelope is decoded to determine the
        upstream episode id and provider; the pipe `sources` endpoint returns
        HLS streams and subtitle tracks. Each HLS URL is wrapped through
        vault01/02.ultracloud.cc before being returned.

        Embed-type streams are skipped (Android-only MegaCloud/RapidCloud
        extractors are not available in the Python port).
        """
        try:
            ep_data: dict[str, Any] = json.loads(episode_id)
        except (json.JSONDecodeError, TypeError):
            log.warning("Miruro get_streams: invalid episode_id JSON")
            return []

        # Allow the caller to override the sub-type via server_id
        sub_types: dict[str, str] = ep_data.get("subTypes") or {}
        effective_sub_type = (
            server_id if server_id in sub_types else ep_data.get("defaultSubType") or "sub"
        )
        effective_episode_id = sub_types.get(effective_sub_type) or ep_data.get("episodeId") or ""

        provider_key: str = ep_data.get("provider") or ""
        anilist_id: str = str(ep_data.get("anilistId") or "")

        data = await self._pipe_get(
            "sources",
            {
                "episodeId": effective_episode_id,
                "provider": provider_key,
                "category": effective_sub_type,
            },
        )

        if not data:
            return []

        streams_data: list[dict[str, Any]] = data.get("streams") or []
        subtitles_data: list[dict[str, Any]] = data.get("subtitles") or []

        subtitles = [
            Subtitle(
                url=sub.get("url") or "",
                label=sub.get("label") or sub.get("language") or "",
                language=sub.get("language") or "",
            )
            for sub in subtitles_data
            if sub.get("url")
        ]

        provider_name = _provider_display_name(provider_key)
        sub_type_label = _format_sub_type_label(effective_sub_type)
        proxy_seed = f"{effective_episode_id}|{anilist_id}"
        referer = f"{self.base_url.rstrip('/')}/"

        streams: list[Stream] = []
        for stream_data in streams_data:
            stream_type = (stream_data.get("type") or "").lower()
            stream_url = stream_data.get("url") or ""

            if not stream_url or stream_type == "embed":
                # Embed streams require Android-only extractors; skip in MVP.
                continue

            if stream_type != "hls":
                continue

            quality = stream_data.get("quality") or "unknown"
            codec = stream_data.get("codec") or ""
            audio = stream_data.get("audio") or ""
            resolution: dict[str, int] = stream_data.get("resolution") or {}
            width = resolution.get("width") or 0
            height = resolution.get("height") or 0

            # Build quality label matching Kotlin's buildString block
            parts = [f"{provider_name} - {quality}p {sub_type_label}"]
            if width and height:
                parts.append(f"{width}x{height}")
            if codec:
                parts.append(codec)
            if audio:
                parts.append(audio)
            parts.append("HLS")
            quality_label = " ".join(parts)

            # Use stream's advertised referer (e.g. kwik.cx) for proxy hint;
            # fall back to kwik.cx default matching Kotlin KWIK_DEFAULT_REFERER.
            stream_referer = (stream_data.get("referer") or "").strip() or "https://kwik.cx/"

            proxied_url = miruro_build_proxied_url(
                stream_url=stream_url,
                referer=stream_referer,
                proxy_seed=proxy_seed,
            )

            streams.append(
                Stream(
                    url=proxied_url,
                    quality=quality_label,
                    headers={"Referer": referer},
                    subtitles=subtitles,
                    is_hls=True,
                )
            )

        return streams

    # ── Parsing helpers ───────────────────────────────────────────────────────

    def _parse_media_list(self, data: dict[str, Any]) -> list[Anime]:
        """Parse a `media` array or root array from a pipe browse/search response."""
        if isinstance(data, list):
            media_array = data
        else:
            media_array = data.get("media") or []
            if not isinstance(media_array, list):
                # Some endpoints return the media object directly with an `id` field
                if isinstance(media_array, dict) and media_array.get("id"):
                    return [self._parse_anime(media_array)]
                return []
        return [self._parse_anime(m) for m in media_array if isinstance(m, dict)]

    def _parse_anime(self, media: dict[str, Any], full: bool = False) -> Anime:
        """Parse a single AniList-style media object into an `Anime` model."""
        anime_id = str(media.get("id") or "")

        title_obj: dict[str, str] = media.get("title") or {}
        title = (
            title_obj.get("userPreferred")
            or title_obj.get("romaji")
            or title_obj.get("english")
            or title_obj.get("native")
            or "Unknown"
        )

        cover_obj: dict[str, str] = media.get("coverImage") or {}
        thumbnail = (
            cover_obj.get("extraLarge")
            or cover_obj.get("large")
            or cover_obj.get("medium")
            or media.get("bannerImage")
            or ""
        )

        if not full:
            return Anime(id=anime_id, title=title, url=anime_id, thumbnail=thumbnail)

        # Full metadata for details view
        description = media.get("description") or ""
        genres: list[str] = media.get("genres") or []

        studios_obj: dict[str, Any] = media.get("studios") or {}
        studios: list[str] = [
            edge["node"]["name"]
            for edge in (studios_obj.get("edges") or [])
            if isinstance(edge, dict)
            and edge.get("isMain")
            and isinstance(edge.get("node"), dict)
            and edge["node"].get("name")
        ]

        raw_status: str = (media.get("status") or "").upper()
        status = _STATUS_MAP.get(raw_status, "unknown")

        score_raw = media.get("averageScore") or media.get("meanScore")
        score: float | None = None
        if score_raw is not None:
            with contextlib.suppress(ValueError, TypeError):
                score = float(score_raw) / 10.0  # AniList returns 0–100

        return Anime(
            id=anime_id,
            title=title,
            url=anime_id,
            thumbnail=thumbnail,
            description=description,
            genres=genres if isinstance(genres, list) else [],
            studios=studios,
            status=status,
            score=score,
        )

    def _has_next_page(self, data: dict[str, Any], per_page: int) -> bool:
        """Check for a next page using pageInfo or array length heuristic."""
        if not isinstance(data, dict):
            return False
        page_info: dict[str, Any] = data.get("pageInfo") or {}
        if "hasNextPage" in page_info:
            return bool(page_info["hasNextPage"])
        media_array = data.get("media") or []
        if isinstance(media_array, list):
            return len(media_array) >= per_page
        return False

    def _select_provider(self, providers: dict[str, Any]) -> str | None:
        """Select the best available provider from the response.

        Priority:
        1. User's preferred provider if it has episodes.
        2. Any provider in DEFAULT_PROVIDER_ORDER that has episodes.
        3. First available provider with episodes.
        """

        def has_episodes(key: str) -> bool:
            p = providers.get(key)
            return isinstance(p, dict) and bool(p.get("episodes"))

        if has_episodes(self.preferred_provider):
            return self.preferred_provider

        for key in self.DEFAULT_PROVIDER_ORDER:
            if key != self.preferred_provider and has_episodes(key):
                return key

        return next((k for k in providers if has_episodes(k)), None)

    def _select_sub_type(self, sub_type_ids: dict[str, str]) -> str:
        """Select the default sub-type for an episode.

        Priority: preferred_sub_type → display order → any available.
        """
        if self.preferred_sub_type in sub_type_ids:
            return self.preferred_sub_type
        for sub_type in _SUB_TYPE_DISPLAY_ORDER:
            if sub_type in sub_type_ids:
                return sub_type
        return next(iter(sub_type_ids), "sub")

    def _build_scanlator(self, provider_key: str, sub_type_ids: dict[str, str]) -> str:
        """Build the scanlator label: '<Provider> • Sub, Dub'."""
        available_labels = [
            _format_sub_type_label(st)
            for st in _SUB_TYPE_DISPLAY_ORDER
            if st in sub_type_ids and st in _SCANLATOR_SUB_TYPES
        ]
        extras = [
            _format_sub_type_label(st)
            for st in sub_type_ids
            if st not in set(_SUB_TYPE_DISPLAY_ORDER) and st in _SCANLATOR_SUB_TYPES
        ]
        all_labels = available_labels + extras
        label_str = ", ".join(all_labels) if all_labels else ""
        provider_name = _provider_display_name(provider_key)
        return f"{provider_name} • {label_str}" if label_str else provider_name
