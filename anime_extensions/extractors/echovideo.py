"""EchoVideo (Vidplay, MyCloud, DatSaV) video extractor."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from ..base import BaseExtractor
from ..models import Stream, Subtitle
from ..utils.m3u8 import parse_m3u8_streams

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)

DATSAV_QUALITY_LABELS = {
    "FHD": "1080p",
    "HD": "720p",
    "HQ": "480p",
    "SD": "360p",
}


class EchoVideoExtractor(BaseExtractor):
    """Extractor for Vidplay / MyCloud / DatSaV (play.echovideo.ru family)."""

    async def extract(
        self,
        embed_url: str,
        *,
        label_prefix: str = "",
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from EchoVideo embed URL."""
        session = await self._ensure_session()
        parsed = urlparse(embed_url)
        host = parsed.netloc

        path_segments = [s for s in parsed.path.split("/") if s]
        if not path_segments:
            return []

        video_id = path_segments[-1]
        base_embed = embed_url.rsplit("/", 1)[0]
        sources_url = f"{base_embed}/getSources?id={video_id}"

        headers = {
            "Accept": "*/*",
            "Referer": embed_url,
            "User-Agent": USER_AGENT,
        }

        async with session.get(sources_url, headers=headers) as resp:
            if resp.status != 200:
                # Fall back to getSourcesNew if the endpoint returns nothing or error
                sources_url = f"{base_embed}/getSourcesNew?id={video_id}"
                async with session.get(sources_url, headers=headers) as resp2:
                    if resp2.status != 200:
                        return []
                    data = await resp2.json(content_type=None)
            else:
                data = await resp.json(content_type=None)

        if not isinstance(data, dict):
            return []

        # Parse Subtitles
        subtitles: list[Subtitle] = []
        raw_tracks = data.get("tracks") or data.get("subtitles") or []
        for track in raw_tracks:
            if isinstance(track, dict):
                sub_url = track.get("file") or track.get("url")
                sub_label = track.get("label") or track.get("lang") or "Subtitle"
                kind = track.get("kind", "captions")
                if (
                    sub_url
                    and sub_url.startswith("http")
                    and kind.lower() in ["captions", "subtitles"]
                ):
                    subtitles.append(Subtitle(url=sub_url, label=sub_label))

        video_referer = f"https://{host}/"
        video_headers = {
            "Referer": video_referer,
            "User-Agent": USER_AGENT,
        }

        sources = data.get("sources")
        if not sources:
            return []

        # Case 1: Quality-keyed direct files (DatSaV) -> dict of {quality: [urls]}
        if isinstance(sources, dict) and "qualityFiles" in sources:
            quality_files = sources.get("qualityFiles", {})
            if isinstance(quality_files, dict) and quality_files:
                streams: list[Stream] = []
                for quality, urls in quality_files.items():
                    url_list = urls if isinstance(urls, list) else [urls]
                    qual_name = DATSAV_QUALITY_LABELS.get(quality, quality)
                    full_label = f"{label_prefix} - {qual_name}" if label_prefix else qual_name
                    for u in url_list:
                        if u and u.startswith("http"):
                            streams.append(
                                Stream(
                                    url=u,
                                    quality=full_label,
                                    headers=video_headers,
                                    subtitles=subtitles,
                                    is_hls=".m3u8" in u,
                                )
                            )
                return streams

        # Extract master playlist URL from various JSON shapes
        m3u8_url: str | None = None
        if isinstance(sources, dict):
            m3u8_url = sources.get("file") or sources.get("url")
        elif isinstance(sources, str):
            m3u8_url = sources
        elif isinstance(sources, list) and sources:
            first = sources[0]
            if isinstance(first, str):
                m3u8_url = first
            elif isinstance(first, dict):
                m3u8_url = first.get("file") or first.get("url")

        if not m3u8_url or not m3u8_url.startswith("http"):
            return []

        # Fetch and parse the m3u8 playlist
        try:
            async with session.get(m3u8_url, headers=video_headers) as hls_resp:
                if hls_resp.status == 200:
                    hls_text = await hls_resp.text(errors="replace")
                    return parse_m3u8_streams(
                        hls_text,
                        m3u8_url,
                        referer=video_referer,
                        subtitles=subtitles,
                        default_headers=video_headers,
                        label_prefix=label_prefix,
                    )
        except Exception as e:
            log.warning("Failed to parse EchoVideo playlist: %s", e)

        full_label = f"{label_prefix} - auto" if label_prefix else "auto"
        return [
            Stream(
                url=m3u8_url,
                quality=full_label,
                headers=video_headers,
                subtitles=subtitles,
                is_hls=True,
            )
        ]
