"""WolfStream video extractor."""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ..core.errors import HttpError, ParsingError
from ..core.extractor import Extractor
from ..models import Stream

log = logging.getLogger(__name__)


class WolfStreamExtractor(Extractor):
    """Extractor for WolfStream."""

    name = "WolfStream"

    _SOURCES_REGEX = re.compile(r"sources\s*:\s*(.+?\]),", re.DOTALL)
    _URLS_REGEX = re.compile(r"file\s*:\s*[\"'](.*?)[\"']")

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        session = self.context.http
        prefix = kwargs.get("label_prefix", "")

        try:
            html = await session.get(url)
        except HttpError as e:
            log.warning("WolfStream request failed: %s", e)
            raise

        doc = BeautifulSoup(html, "lxml")
        script_text = ""

        # Find script containing sources
        for script in doc.find_all("script"):
            text = script.string
            if text and "sources" in text:
                script_text = text
                break

        if not script_text:
            raise ParsingError(f"WolfStream: no script containing sources found in {url}")

        sources_match = self._SOURCES_REGEX.search(script_text)
        if not sources_match:
            raise ParsingError(f"WolfStream: no sources array matched in script for {url}")

        sources_str = sources_match.group(1)
        video_urls = [
            m.group(1) for m in self._URLS_REGEX.finditer(sources_str) if m.group(1).strip()
        ]

        if not video_urls:
            raise ParsingError(f"WolfStream: no video URLs found in sources for {url}")

        streams: list[Stream] = []
        for v_url in video_urls:
            quality_label = f"{prefix} WolfStream" if prefix else "WolfStream"
            streams.append(
                Stream(
                    url=v_url,
                    quality=quality_label.strip(),
                    # Native app doesn't specify extra headers for playing WolfStream mp4 files,
                    # but typically standard Referer is given by player architecture
                    headers={"Referer": url},
                    is_hls=".m3u8" in v_url,
                )
            )

        return streams
