"""StreamWish video extractor."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..core.errors import ExtractorError
from ..core.extractor import Extractor
from ..core.models import Stream, Subtitle
from ..core.registry import register_extractor
from ..utils.m3u8 import parse_m3u8_streams
from ..utils.unpacker import Unpacker

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


@register_extractor(
    r"streamwish\.\w+|wish\w*\.\w+|sw\w*\.\w+|niramirus\.\w+|medixiru\.\w+|streamwish"
)
class StreamWishExtractor(Extractor):
    """Extractor for StreamWish video hosting and its mirrors."""

    name = "StreamWish"

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from StreamWish embed URL."""
        label_prefix = kwargs.get("label_prefix", "")

        session = self.context.http.session
        if not session:
            raise ExtractorError("StreamWish: runtime HTTP client is not started")

        if not url.startswith("http"):
            url = f"https:{url}" if url.startswith("//") else f"https://{url}"

        # Normalize /f/ or /d/ URLs to standard embed
        if "/f/" in url:
            url = url.replace("/f/", "/e/")
        elif "/d/" in url:
            url = url.replace("/d/", "/e/")

        parsed_url = urlparse(url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"{origin}/",
            }
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    raise ExtractorError(f"StreamWish: failed to fetch page, status {resp.status}")
                text = await resp.text(errors="replace")

            soup = BeautifulSoup(text, "html.parser")
            scripts = soup.find_all("script")

            script_content = ""
            for script in scripts:
                content = script.string or script.get_text() or ""
                if "m3u8" in content or "eval(function(p,a,c" in content:
                    if Unpacker.is_packed(content):
                        script_content = Unpacker.unpack(content)
                    else:
                        script_content = content
                    if "m3u8" in script_content:
                        break

            if not script_content:
                # Check raw page text if not found in isolated script tags
                script_content = Unpacker.unpack(text) if Unpacker.is_packed(text) else text

            # Extract m3u8 master URL
            m3u8_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', script_content)
            if not m3u8_match:
                # Try finding sources or file property
                source_match = re.search(
                    r'(?:file|sources)\s*:\s*["\']([^"\']+)["\']', script_content
                )
                if source_match:
                    master_url = source_match.group(1)
                else:
                    log.warning("StreamWish: no m3u8 URL found in %s", url)
                    return []
            else:
                master_url = m3u8_match.group(0)

            # Extract subtitles if present
            subtitles: list[Subtitle] = []
            tracks_match = re.search(r"tracks\s*:\s*(\[[^\]]+\])", script_content)
            if tracks_match:
                try:
                    fixed_tracks = re.sub(
                        r'(?<!")([a-zA-Z0-9_]+)(?!")\s*:', r'"\1":', tracks_match.group(1)
                    )
                    tracks_data = json.loads(fixed_tracks)
                    for track in tracks_data:
                        if isinstance(track, dict) and track.get("kind", "").lower() in (
                            "captions",
                            "subtitles",
                        ):
                            track_file = track.get("file")
                            if track_file and track_file.startswith("http"):
                                subtitles.append(
                                    Subtitle(
                                        url=track_file,
                                        label=track.get("label", "Unknown"),
                                    )
                                )
                except Exception as e:
                    log.debug("StreamWish: subtitle parsing failed: %s", e)

            # Parse M3U8 streams
            master_parsed = urlparse(master_url)
            media_origin = f"{master_parsed.scheme}://{master_parsed.netloc}/"
            hls_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": media_origin,
            }

            async with session.get(master_url, headers=hls_headers) as hls_resp:
                if hls_resp.status == 200:
                    hls_text = await hls_resp.text(errors="replace")
                    return parse_m3u8_streams(
                        hls_text,
                        master_url,
                        referer=media_origin,
                        subtitles=subtitles,
                        default_headers=hls_headers,
                        label_prefix=label_prefix or "StreamWish",
                    )

            # Fallback
            prefix = f"{label_prefix} - auto" if label_prefix else "StreamWish - auto"
            return [
                Stream(
                    url=master_url,
                    quality=prefix,
                    headers=hls_headers,
                    subtitles=subtitles,
                    is_hls=True,
                )
            ]

        except Exception as e:
            log.warning("StreamWish extraction failed for %s: %s", url, e)
            return []
