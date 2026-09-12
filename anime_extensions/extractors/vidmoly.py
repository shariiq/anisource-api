"""VidMoly video extractor."""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ..core.errors import HttpError, ParsingError
from ..core.extractor import Extractor
from ..models import Stream
from ..utils.m3u8 import parse_m3u8_streams

log = logging.getLogger(__name__)


class VidMolyExtractor(Extractor):
    """Extractor for VidMoly."""

    name = "VidMoly"
    BASE_URL = "https://vidmoly.biz"
    _HOST_REGEX = re.compile(r"^https?://(?:www\.)?[^/]+/")
    _SOURCES_REGEX = re.compile(r"sources\s*:\s*(\[[^\]]+\]),")
    _URLS_REGEX = re.compile(r"file\s*:\s*[\"'](.*?)[\"']")

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        session = self.context.http
        prefix = kwargs.get("label_prefix", "")

        fixed_url = url
        if not fixed_url.lower().startswith(self.BASE_URL):
            fixed_url = self._HOST_REGEX.sub(f"{self.BASE_URL}/", fixed_url, count=1)

        headers = {
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
        }

        try:
            html = await session.get(fixed_url, headers=headers)
        except HttpError as e:
            log.warning("VidMoly request failed: %s", e)
            raise

        doc = BeautifulSoup(html, "lxml")
        script_text = ""
        for s in doc.find_all("script"):
            if s.string and "sources" in s.string:
                script_text = s.string
                break

        if not script_text:
            raise ParsingError(f"VidMoly: no script containing sources found in {fixed_url}")

        sources_match = self._SOURCES_REGEX.search(script_text)
        if not sources_match:
            raise ParsingError(f"VidMoly: no sources array matched in script for {fixed_url}")

        sources_str = sources_match.group(1)
        video_urls = [
            m.group(1) for m in self._URLS_REGEX.finditer(sources_str) if m.group(1).strip()
        ]

        if not video_urls:
            raise ParsingError(f"VidMoly: no video URLs extracted from sources in {fixed_url}")

        streams: list[Stream] = []
        for v_url in video_urls:
            try:
                playlist_text = await session.get(v_url, headers=headers)
                v_streams = parse_m3u8_streams(
                    playlist_text,
                    v_url,
                    referer=f"{self.BASE_URL}/",
                    default_headers=headers,
                    label_prefix=prefix if prefix else "VidMoly",
                )
                streams.extend(v_streams)
            except HttpError:
                raise

        return streams
