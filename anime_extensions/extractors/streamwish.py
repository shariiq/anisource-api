"""StreamWish video extractor."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..core.errors import HttpError, ParsingError
from ..core.extractor import Extractor
from ..core.registry import register_extractor
from ..models import Stream, Subtitle
from ..utils.m3u8 import parse_m3u8_streams
from ..utils.unpacker import unpack_packer

log = logging.getLogger(__name__)


@register_extractor(r"streamwish|swdyu|niramirus|medixiru")
class StreamWishExtractor(Extractor):
    """Extractor for StreamWish and its domains."""

    name = "StreamWish"

    _M3U8_REGEX = re.compile(r"https[^\"]*m3u8[^\"]*")
    _FIX_TRACKS_REGEX = re.compile(r"(?<=[,\[\s])(file|kind|label)(?=\s*:)")
    _DOMAINS = ["streamwish.com", "niramirus.com", "medixiru.com"]
    _DMCA_REGEX = re.compile(r"dmca\s*=\s*\[(.*?)]", re.DOTALL)
    _MAIN_REGEX = re.compile(r"main\s*=\s*\[(.*?)]", re.DOTALL)
    _RULES_REGEX = re.compile(r"rules\s*=\s*\[(.*?)]", re.DOTALL)

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        session = self.context.http
        prefix = kwargs.get("label_prefix", "")
        headers = dict(kwargs.get("headers", {}))

        video_id = self._get_embed_id(url)
        is_absolute = video_id.startswith("http://") or video_id.startswith("https://")
        domains_to_try = [""] if is_absolute else self._DOMAINS

        for domain in domains_to_try:
            full_url = video_id if is_absolute else f"https://{domain}/e/{video_id}"

            try:
                html = await session.get(full_url, headers=headers)
            except HttpError:
                if is_absolute:
                    return []
                continue

            if not html.strip():
                raise ParsingError(f"StreamWish returned blank content for {full_url}")

            doc = BeautifulSoup(html, "html.parser")

            # Check for main.js redirect logic
            script_element = doc.select_one('body > script[src*="/main.js"]')
            if script_element:
                try:
                    script_url = script_element.get("src")
                    if script_url and not script_url.startswith("http"):
                        parsed = urlparse(full_url)
                        script_url = f"{parsed.scheme}://{parsed.netloc}{script_url}"

                    script_content = await session.get(script_url, headers=headers)

                    dmca_servers = self._extract_server_list(self._DMCA_REGEX, script_content)
                    main_servers = self._extract_server_list(self._MAIN_REGEX, script_content)
                    rules_servers = self._extract_server_list(self._RULES_REGEX, script_content)

                    embed_host = urlparse(full_url).netloc
                    if embed_host in rules_servers and main_servers:
                        destination = main_servers[0]
                    elif dmca_servers:
                        destination = dmca_servers[0]
                    else:
                        destination = None

                    if destination:
                        parsed_url = urlparse(full_url)
                        redirected_url = f"{parsed_url.scheme}://{destination}{parsed_url.path}"
                        if parsed_url.query:
                            redirected_url += f"?{parsed_url.query}"

                        html = await session.get(
                            self._get_embed_url(redirected_url), headers=headers
                        )
                        doc = BeautifulSoup(html, "html.parser")
                except Exception as e:
                    log.warning("StreamWish main.js redirect failed: %s", e)

            script_text = ""
            for s in doc.find_all("script"):
                if s.string and "m3u8" in s.string:
                    script_text = s.string
                    break

            if not script_text:
                if is_absolute:
                    raise ParsingError(f"StreamWish: no m3u8 script found in {full_url}")
                continue

            if "eval(function(p,a,c" in script_text:
                unpacked = unpack_packer(script_text)
                if unpacked:
                    script_text = unpacked

            m3u8_match = self._M3U8_REGEX.search(script_text)
            if not m3u8_match:
                if is_absolute:
                    raise ParsingError(f"StreamWish: no m3u8 URL found in script for {full_url}")
                continue

            master_url = m3u8_match.group(0).replace(r"\/", "/")
            subtitles: list[Subtitle] = self._extract_subtitles(script_text)

            parsed_host = urlparse(master_url).netloc
            req_host = urlparse(full_url).netloc
            referer = f"https://{parsed_host}/" if parsed_host else f"https://{req_host}/"

            req_headers = dict(headers)
            req_headers["Referer"] = referer

            try:
                playlist_text = await session.get(master_url, headers=req_headers)
            except HttpError:
                if is_absolute:
                    raise
                continue

            return parse_m3u8_streams(
                playlist_text,
                master_url,
                referer=referer,
                subtitles=subtitles,
                default_headers=req_headers,
                label_prefix=prefix if prefix else "StreamWish",
            )

        return []

    def _extract_server_list(self, regex: re.Pattern[str], script: str) -> list[str]:
        match = regex.search(script)
        if not match:
            return []

        servers_str = match.group(1)
        servers = []
        for part in servers_str.split(","):
            cleaned = part.strip().strip('"').strip("'")
            if cleaned:
                servers.append(cleaned)
        return servers

    def _get_embed_url(self, url: str) -> str:
        if "/f/" in url:
            video_id = url.split("/f/", 1)[1].split("/")[0].split("?")[0]
            return f"https://streamwish.com/{video_id}"
        return url

    def _get_embed_id(self, url: str) -> str:
        match = re.search(r".*/[efd]/([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        return url

    def _extract_subtitles(self, script: str) -> list[Subtitle]:
        try:
            if "tracks" not in script:
                return []

            sub_str = script.split("tracks", 1)[1].split("[", 1)[1].split("]", 1)[0]
            if not sub_str.strip():
                return []

            def repl(m: re.Match[str]) -> str:
                return f'"{m.group(1)}"'

            fixed = self._FIX_TRACKS_REGEX.sub(repl, sub_str)
            data = json.loads(f"[{fixed}]")

            subs: list[Subtitle] = []
            for item in data:
                if isinstance(item, dict) and item.get("kind", "").lower() == "captions":
                    subs.append(Subtitle(url=item.get("file", ""), label=item.get("label", "")))
            return subs
        except Exception as e:
            log.warning("Failed to parse StreamWish subtitles: %s", e)
            return []
