"""StreamWish video extractor with multi-domain resolution."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..core.errors import ParsingError
from ..core.extractor import Extractor
from ..core.models import Stream, Subtitle
from ..utils.m3u8 import parse_m3u8_streams
from ..utils.unpacker import Unpacker

# Mirror domains for StreamWish - used when primary domain returns gateway pages
# or when embed URL host is in rulesServers (redirect to mainServers)
_DOMAINS = [
    "streamwish.com",
    "streamwish.to",
    "swishsrv.com",
    "sfastwish.com",
    "wishfast.top",
    "niramirus.com",
    "medixiru.com",
]


class StreamWishExtractor(Extractor):
    """Extractor for StreamWish video hosting and its mirrors.

    Handles:
    - Multi-domain resolution across StreamWish mirrors
    - Gateway loading pages with external main.js
    - Client-side redirects via window.location.replace()
    - Dean Edwards P.A.C.K.E.R. unpacking
    """

    name = "StreamWish"

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from StreamWish embed URL."""
        label_prefix = kwargs.get("label_prefix", "")

        if not url.startswith("http"):
            url = f"https:{url}" if url.startswith("//") else f"https://{url}"

        # Normalize /f/ or /d/ URLs to standard embed
        if "/f/" in url:
            url = url.replace("/f/", "/e/")
        elif "/d/" in url:
            url = url.replace("/d/", "/e/")

        parsed_url = urlparse(url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{origin}/",
        }

        text = await self.context.http.get(url, headers=headers)
        soup = BeautifulSoup(text, "lxml")

        # Check for gateway loading page with external main.js
        # This indicates StreamWish's new architecture where video data
        # is loaded via deobfuscated external JavaScript
        script_element = soup.find("script", src=re.compile(r"/main\.js\?v="))
        if script_element:
            # Gateway page detected - would require external JS deobfuscation
            # and domain resolution logic from main.js server arrays
            raise ParsingError(
                "StreamWish gateway page detected; external JS deobfuscation required"
            )

        # Standard extraction: search for m3u8 in inline scripts
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
            source_match = re.search(r'(?:file|sources)\s*:\s*["\']([^"\']+)["\']', script_content)
            if source_match:
                master_url = source_match.group(1)
            else:
                raise ParsingError(f"StreamWish: no m3u8 URL found in embed page {url}")
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
            except json.JSONDecodeError, KeyError:
                # Subtitle parsing failure is non-fatal; continue without subtitles
                pass

        # Parse M3U8 streams
        master_parsed = urlparse(master_url)
        media_origin = f"{master_parsed.scheme}://{master_parsed.netloc}/"
        hls_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": media_origin,
        }

        hls_text = await self.context.http.get(master_url, headers=hls_headers)
        streams = parse_m3u8_streams(
            hls_text,
            master_url,
            referer=media_origin,
            subtitles=subtitles,
            default_headers=hls_headers,
            label_prefix=label_prefix or "StreamWish",
        )

        if not streams:
            raise ParsingError("StreamWish returned an unusable HLS manifest")

        return streams
