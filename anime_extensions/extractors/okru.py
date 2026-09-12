"""Okru (Ok.ru / Odnoklassniki) video extractor."""

from __future__ import annotations

import html
import json
from typing import Any

from bs4 import BeautifulSoup

from ..core.errors import ParsingError
from ..core.extractor import Extractor
from ..core.models import Stream
from ..utils.m3u8 import parse_m3u8_streams


class OkruExtractor(Extractor):
    """Extractor for Ok.ru (Odnoklassniki) video hosting."""

    name = "Okru"

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

    async def extract(self, url: str, **kwargs: Any) -> list[Stream]:
        """Extract streams from an Okru embed URL."""
        label_prefix = kwargs.get("label_prefix", "")
        if not url.startswith("http"):
            url = f"https:{url}" if url.startswith("//") else f"https://{url}"

        # Ok.ru's certificate chain is incomplete on some supported runtimes.
        # Keep the exception host-scoped rather than weakening the shared client.
        text = await self.context.http.get(url, ssl=False)
        soup = BeautifulSoup(text, "html.parser")
        options_div = soup.find("div", {"data-options": True})
        if options_div is None:
            raise ParsingError("Okru response did not contain video options")

        options_raw = options_div.get("data-options", "")
        if not isinstance(options_raw, str) or not options_raw:
            raise ParsingError("Okru response contained empty video options")

        try:
            options = json.loads(html.unescape(options_raw))
        except json.JSONDecodeError as exc:
            raise ParsingError("Okru returned malformed video options") from exc

        flashvars = options.get("flashvars")
        if not isinstance(flashvars, dict):
            raise ParsingError("Okru video options did not contain flashvars")

        hls_url = flashvars.get("hls_url") or flashvars.get("ondemandHls")
        if isinstance(hls_url, str) and hls_url:
            hls_url = hls_url.replace("\\u0026", "&").replace("\\/", "/")
            if not hls_url.startswith("http"):
                raise ParsingError("Okru returned an invalid HLS URL")
            hls_text = await self.context.http.get(hls_url, headers={"Referer": url}, ssl=False)
            streams = parse_m3u8_streams(
                hls_text,
                hls_url,
                referer=url,
                label_prefix=label_prefix or "Okru",
            )
            if not streams:
                raise ParsingError("Okru returned an unusable HLS manifest")
            return streams

        dash_url = flashvars.get("dash_url") or flashvars.get("ondemandDash")
        if isinstance(dash_url, str) and dash_url:
            dash_url = dash_url.replace("\\u0026", "&").replace("\\/", "/")
            if not dash_url.startswith("http"):
                raise ParsingError("Okru returned an invalid DASH URL")
            quality = f"{label_prefix} - DASH" if label_prefix else "Okru - DASH"
            return [
                Stream(
                    url=dash_url,
                    quality=quality,
                    headers={"Referer": url},
                    is_hls=False,
                )
            ]

        metadata_raw = flashvars.get("metadata")
        if not metadata_raw:
            raise ParsingError("Okru flashvars did not contain playback metadata")
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError as exc:
                raise ParsingError("Okru returned malformed playback metadata") from exc
        elif isinstance(metadata_raw, dict):
            metadata = metadata_raw
        else:
            raise ParsingError("Okru returned invalid playback metadata")

        videos = metadata.get("videos")
        if not isinstance(videos, list):
            raise ParsingError("Okru playback metadata did not contain videos")

        streams: list[Stream] = []
        for video in videos:
            if not isinstance(video, dict):
                continue
            video_url = video.get("url")
            if not isinstance(video_url, str) or not video_url.startswith("http"):
                continue
            name = str(video.get("name", "")).lower()
            quality_label = self.QUALITY_MAP.get(name, name or "auto")
            final_label = (
                f"{label_prefix} - {quality_label}" if label_prefix else f"Okru - {quality_label}"
            )
            streams.append(
                Stream(
                    url=video_url,
                    quality=final_label,
                    headers={"Referer": url},
                    is_hls=False,
                )
            )

        if not streams:
            raise ParsingError("Okru playback metadata did not contain usable streams")
        return streams
