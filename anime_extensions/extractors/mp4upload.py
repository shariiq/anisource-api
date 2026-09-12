"""Mp4Upload video extractor."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from ..core.errors import ExtractorError
from ..core.extractor import Extractor
from ..models import Stream
from ..utils.unpacker import Unpacker

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class Mp4UploadExtractor(Extractor):
    """Extractor for Mp4Upload video hosting."""

    name = "Mp4Upload"

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from Mp4Upload embed URL."""
        label_prefix = kwargs.get("label_prefix", "")

        session = self.context.http.session
        if not session:
            raise ExtractorError("Mp4Upload: runtime HTTP client is not started")

        # Normalize URL to embed format
        if not url.startswith("http"):
            url = f"https://{url}"
        if "mp4upload.com" in url and "/embed-" not in url:
            # Convert direct links to embed links
            video_id_match = re.search(r"mp4upload\.com/([a-zA-Z0-9]+)", url)
            if video_id_match:
                url = f"https://www.mp4upload.com/embed-{video_id_match.group(1)}.html"

        try:
            # Fetch embed page with referer
            headers = {
                "Referer": "https://mp4upload.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    raise ExtractorError(f"Mp4Upload: failed to fetch page, status {resp.status}")
                text = await resp.text(errors="replace")

            # Check if script is packed
            script_text = text
            if Unpacker.is_packed(text):
                script_text = Unpacker.unpack(text)

            # Extract video URL from player.src or src: expression
            # Patterns: player.src = "url" or player.src({src:"url"}) or src: "url"
            video_url = None
            url_patterns = [
                r'player\.src\s*=\s*["\']([^"\']+)["\']',
                r'player\.src\s*=\s*{\s*src:\s*["\']([^"\']+)["\']',
                r'src:\s*["\']([^"\']+)["\']',
                r'file:\s*["\']([^"\']+)["\']',
            ]

            for pattern in url_patterns:
                match = re.search(pattern, script_text)
                if match:
                    video_url = match.group(1)
                    break

            if not video_url or not video_url.startswith("http"):
                log.warning("Mp4Upload: could not extract video URL from %s", url)
                return []

            # Extract resolution/quality
            quality = "auto"
            height_match = re.search(r"\bHEIGHT=(\d+)", script_text)
            if height_match:
                quality = f"{height_match.group(1)}p"
            else:
                # Try finding resolution in URL or other parts
                res_match = re.search(r"(\d{3,4})p", script_text)
                if res_match:
                    quality = f"{res_match.group(1)}p"

            final_label = (
                f"{label_prefix} - {quality}" if label_prefix else f"Mp4Upload - {quality}"
            )

            # Determine if HLS
            is_hls = ".m3u8" in video_url

            return [
                Stream(
                    url=video_url,
                    quality=final_label,
                    headers={"Referer": "https://mp4upload.com/"},
                    is_hls=is_hls,
                )
            ]

        except Exception as e:
            log.warning("Mp4Upload extraction failed for %s: %s", url, e)
            return []
