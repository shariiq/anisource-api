"""Vtube video extractor."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..core.errors import HttpError, ParsingError
from ..core.extractor import Extractor
from ..core.registry import register_extractor
from ..models import Stream
from ..utils.m3u8 import parse_m3u8_streams
from ..utils.unpacker import unpack_packer

log = logging.getLogger(__name__)


@register_extractor(r"vtbe|vtube")
class VtubeExtractor(Extractor):
    """Extractor for Vtube."""

    name = "Vtube"

    _SOURCES_REGEX = re.compile(r"sources\s*:\s*(.+?\]),", re.DOTALL)
    _URLS_REGEX = re.compile(r"file\s*:\s*[\"'](.*?)[\"']")

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        session = self.context.http
        prefix = kwargs.get("label_prefix", "")
        base_url = kwargs.get("base_url", "")

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Host": urlparse(url).netloc,
            "Referer": f"{base_url}/" if base_url else url,
        }

        try:
            html = await session.get(url, headers=headers)
        except HttpError as e:
            log.warning("Vtube request failed: %s", e)
            raise

        doc = BeautifulSoup(html, "html.parser")
        unpacked: str | None = None

        for script in doc.find_all("script"):
            text = script.string
            if not text:
                continue

            # Only look at player source scripts containing m3u8 or sources
            if "m3u8" not in text and "sources" not in text:
                continue

            if "function(p,a,c,k,e,d)" in text:
                unpacked = unpack_packer(text)
                if unpacked:
                    break
            else:
                unpacked = text
                break

        if not unpacked:
            raise ParsingError(f"Vtube: could not find valid player script in {url}")

        sources_match = self._SOURCES_REGEX.search(unpacked)
        if not sources_match:
            raise ParsingError(f"Vtube: no sources matched in player script for {url}")

        sources_str = sources_match.group(1)
        video_urls = [
            m.group(1) for m in self._URLS_REGEX.finditer(sources_str) if m.group(1).strip()
        ]

        if not video_urls:
            raise ParsingError(f"Vtube: no video URLs found in sources for {url}")

        streams: list[Stream] = []
        for v_url in video_urls:
            try:
                playlist_text = await session.get(v_url, headers={"Referer": url})
                v_streams = parse_m3u8_streams(
                    playlist_text,
                    v_url,
                    referer=url,
                    default_headers={"Referer": url},
                    label_prefix=prefix if prefix else "Vtube",
                )
                streams.extend(v_streams)
            except HttpError:
                raise

        return streams
