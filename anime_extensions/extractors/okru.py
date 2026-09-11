"""Okru (Ok.ru / Odnoklassniki) video extractor."""

from __future__ import annotations

import html
import json
import logging
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from ..core.errors import ExtractorError
from ..core.extractor import Extractor
from ..core.models import Stream
from ..core.registry import register_extractor

if TYPE_CHECKING:
    pass

from ..utils.m3u8 import parse_m3u8_streams

log = logging.getLogger(__name__)


@register_extractor(r"ok\.ru|okru|odnoklassniki\.ru")
class OkruExtractor(Extractor):
    """Extractor for Ok.ru (Odnoklassniki) video hosting."""

    name = "Okru"

    # Quality name to resolution mapping from Kotlin OkruExtractor
    QUALITY_MAP = {
        "ultra": "2160p",
        "quad": "1440p",
        "full": "1080p",
        "hd": "720p",
        "sd": "480p",
        "low": "360p",
        "lowest": "240p",
        "mobile": "144p",
    }

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from Okru embed URL."""
        label_prefix = kwargs.get("label_prefix", "")

        session = self.context.http.session
        if not session:
            raise ExtractorError("Okru: runtime HTTP client is not started")

        # Normalize URL
        if not url.startswith("http"):
            url = f"https:{url}" if url.startswith("//") else f"https://{url}"

        try:
            # Fetch embed page
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise ExtractorError(f"Okru: failed to fetch page, status {resp.status}")
                text = await resp.text(errors="replace")

            # Parse data-options attribute
            soup = BeautifulSoup(text, "html.parser")
            options_div = soup.find("div", {"data-options": True})
            if not options_div:
                log.warning("Okru: no data-options div found")
                return []

            options_raw = options_div.get("data-options", "")
            if not isinstance(options_raw, str) or not options_raw:
                return []

            # HTML unescape
            options_unescaped = html.unescape(options_raw)

            # Try parsing as JSON
            try:
                options = json.loads(options_unescaped)
            except json.JSONDecodeError:
                log.warning("Okru: failed to parse data-options as JSON")
                return []

            flashvars = options.get("flashvars", {})
            if not flashvars:
                log.warning("Okru: no flashvars in data-options")
                return []

            streams: list[Stream] = []

            # HLS case
            hls_url = flashvars.get("hls_url") or flashvars.get("ondemandHls")
            if hls_url:
                # Decode escaped URL
                hls_url = hls_url.replace("\\u0026", "&").replace("\\/", "/")
                if not hls_url.startswith("http"):
                    log.warning("Okru: invalid HLS URL")
                    return []

                async with session.get(hls_url) as hls_resp:
                    if hls_resp.status == 200:
                        hls_text = await hls_resp.text(errors="replace")
                        parsed_streams = parse_m3u8_streams(
                            hls_text,
                            hls_url,
                            referer=url,
                            label_prefix=label_prefix or "Okru",
                        )
                        streams.extend(parsed_streams)
                        return streams

            # DASH case (return manifest URL directly since we don't have a DASH parser)
            dash_url = flashvars.get("dash_url") or flashvars.get("ondemandDash")
            if dash_url:
                dash_url = dash_url.replace("\\u0026", "&").replace("\\/", "/")
                if dash_url.startswith("http"):
                    quality = f"{label_prefix} - DASH" if label_prefix else "Okru - DASH"
                    streams.append(
                        Stream(
                            url=dash_url,
                            quality=quality,
                            headers={"Referer": url},
                            is_hls=False,
                        )
                    )
                    return streams

            # Direct videos case
            metadata_raw = flashvars.get("metadata")
            if not metadata_raw:
                log.warning("Okru: no metadata in flashvars")
                return []

            # Metadata is often double-encoded JSON
            if isinstance(metadata_raw, str):
                try:
                    metadata = json.loads(metadata_raw)
                except json.JSONDecodeError:
                    log.warning("Okru: failed to parse metadata JSON")
                    return []
            else:
                metadata = metadata_raw

            videos = metadata.get("videos", [])
            if not isinstance(videos, list):
                return []

            for video in videos:
                if not isinstance(video, dict):
                    continue

                video_url = video.get("url")
                if not video_url or not video_url.startswith("http"):
                    continue

                name = video.get("name", "").lower()
                quality_label = self.QUALITY_MAP.get(name, name or "auto")

                final_label = (
                    f"{label_prefix} - {quality_label}"
                    if label_prefix
                    else f"Okru - {quality_label}"
                )

                streams.append(
                    Stream(
                        url=video_url,
                        quality=final_label,
                        headers={"Referer": url},
                        is_hls=False,
                    )
                )

            return streams

        except Exception as e:
            log.warning("Okru extraction failed for %s: %s", url, e)
            return []
