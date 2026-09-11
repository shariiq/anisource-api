"""Streamlare video extractor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from ..core.errors import ExtractorError
from ..core.extractor import Extractor
from ..core.models import Stream
from ..core.registry import register_extractor
from ..utils.m3u8 import parse_m3u8_streams

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


@register_extractor(r"streamlare\.com|slwatch\.co")
class StreamlareExtractor(Extractor):
    """Extractor for Streamlare video hosting."""

    name = "Streamlare"

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from Streamlare embed URL."""
        label_prefix = kwargs.get("label_prefix", "")

        session = self.context.http.session
        if not session:
            raise ExtractorError("Streamlare: runtime HTTP client is not started")

        parsed = urlparse(url)
        path_segments = [s for s in parsed.path.split("/") if s]
        if not path_segments:
            log.warning("Streamlare: could not parse video ID from %s", url)
            return []

        video_id = path_segments[-1]

        try:
            api_url = "https://slwatch.co/api/video/stream/get"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": url,
            }
            payload = {"id": video_id}

            async with session.post(api_url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise ExtractorError(
                        f"Streamlare: API request failed with status {resp.status}"
                    )
                data = await resp.json()

            if not isinstance(data, dict):
                return []

            result = data.get("result", {})
            if not isinstance(result, dict):
                return []

            stream_type = result.get("type", "")
            streams: list[Stream] = []

            if stream_type == "hls":
                master_url = result.get("file", "")
                if master_url:
                    master_url = master_url.replace("\\/", "/")
                    async with session.get(master_url, headers=headers) as hls_resp:
                        if hls_resp.status == 200:
                            hls_text = await hls_resp.text(errors="replace")
                            return parse_m3u8_streams(
                                hls_text,
                                master_url,
                                referer=url,
                                label_prefix=label_prefix or "Streamlare",
                            )
            else:
                # Direct links by label
                for label, info in result.items():
                    if not isinstance(info, dict):
                        continue
                    file_url = info.get("file")
                    if not file_url or not isinstance(file_url, str):
                        continue

                    # Often file_url is an API link that redirects or provides direct video
                    final_video_url = file_url
                    try:
                        async with session.post(
                            file_url, headers=headers, allow_redirects=True
                        ) as file_resp:
                            if file_resp.status == 200:
                                final_video_url = str(file_resp.url)
                    except Exception:
                        pass

                    quality_str = (
                        f"{label_prefix} - {label}" if label_prefix else f"Streamlare - {label}"
                    )
                    streams.append(
                        Stream(
                            url=final_video_url,
                            quality=quality_str,
                            headers=headers,
                            is_hls=False,
                        )
                    )

            return streams

        except Exception as e:
            log.warning("Streamlare extraction failed for %s: %s", url, e)
            return []
