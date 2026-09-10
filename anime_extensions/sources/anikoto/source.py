"""Anikoto source implementation."""

from __future__ import annotations

import base64
import contextlib
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from ...base import BaseSource
from ...models import Anime, Episode, Server, Stream, Subtitle
from ...utils.crypto import vrf_encrypt

# === Anikoto Source ===


class Anikoto(BaseSource):
    """Anikoto anime source."""

    name = "Anikoto"
    id = "anikoto"
    base_url = "https://anikototv.to"

    DOMAINS = [
        "anikototv.to",
        "anikoto.bz",
        "anikoto.cz",
        "anikoto.me",
        "anikoto.net",
        "anikototv.se",
    ]

    def __init__(self, *, domain: str | None = None, session: Any = None) -> None:
        super().__init__(session=session)
        if domain:
            self.base_url = f"https://{domain}"

    # === Listing Methods ===

    async def get_popular(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch popular anime."""
        url = f"{self.base_url}/most-viewed/"
        html = await self._request(url, params={"page": page})
        return self._parse_listing(html)

    async def get_latest(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch latest updated anime."""
        url = f"{self.base_url}/latest-updated/"
        html = await self._request(url, params={"page": page})
        return self._parse_listing(html)

    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        """Search anime by query."""
        params = {
            "keyword": query,
            "page": page,
            "vrf": vrf_encrypt(query),
        }
        url = f"{self.base_url}/filter"
        html = await self._request(url, params=params)
        return self._parse_listing(html)

    def _parse_listing(self, html: str) -> tuple[list[Anime], bool]:
        """Parse anime listing page."""
        soup = BeautifulSoup(html, "html.parser")
        animes = []

        for item in soup.select("div.ani.items > div.item"):
            name_a = item.select_one("a.name")
            if not name_a:
                continue

            href = name_a.get("href", "")
            url_path = re.sub(r"/ep-\d+$", "", href.split("?")[0])

            title = name_a.get_text(strip=True)
            jp_title = name_a.get("data-jp", "").strip()
            final_title = jp_title or title

            thumbnail = ""
            img = item.select_one("div.poster img")
            if img:
                thumbnail = img.get("data-src") or img.get("src", "")

            anime_id = url_path.split("/watch/")[-1] if "/watch/" in url_path else url_path

            animes.append(
                Anime(
                    id=anime_id,
                    title=final_title,
                    url=url_path,
                    thumbnail=thumbnail,
                )
            )

        # Check pagination
        pagination = soup.select_one("ul.pagination")
        has_next = False
        if pagination:
            lis = pagination.select("li")
            active_found = False
            for li in lis:
                if "active" in (li.get("class") or []):
                    active_found = True
                elif active_found:
                    has_next = True
                    break

        return animes, has_next

    # === Details & Episodes ===

    async def get_details(self, anime_id: str) -> Anime:
        """Get full anime details."""
        clean_id = anime_id.split("#")[0].strip("/")
        anime_path = f"/watch/{clean_id}" if not clean_id.startswith("watch/") else f"/{clean_id}"

        url = f"{self.base_url}{anime_path}"
        html = await self._request(url)
        soup = BeautifulSoup(html, "html.parser")

        # Title - prefer Japanese title from data-jp attribute
        title_elem = soup.select_one("h1.title, h2.title")
        title = ""
        if title_elem:
            title = title_elem.get("data-jp", "").strip() or title_elem.get_text(strip=True)

        # Internal ID - get from watch-main div or rating div
        internal_id = ""
        watch_main = soup.select_one("div#watch-main[data-id]")
        if watch_main:
            internal_id = watch_main.get("data-id", "")

        # Thumbnail
        thumbnail = ""
        img = soup.select_one("div.poster img, img.thumbnail")
        if img:
            thumbnail = img.get("data-src") or img.get("src", "")

        # Parse metadata from bmeta div
        genres = []
        studios = []
        status_text = ""
        score = None

        bmeta = soup.select_one("div.bmeta")
        if bmeta:
            # Genres
            genre_div = None
            for div in bmeta.select("div.meta > div"):
                if "Genres:" in div.get_text():
                    genre_div = div
                    break
            if genre_div:
                genres = [a.get_text(strip=True) for a in genre_div.select("span a")]

            # Studios
            studio_div = None
            for div in bmeta.select("div.meta > div"):
                if "Studios:" in div.get_text():
                    studio_div = div
                    break
            if studio_div:
                studios = [a.get_text(strip=True) for a in studio_div.select("span a")]

            # Status
            status_div = None
            for div in bmeta.select("div.meta > div"):
                if "Status:" in div.get_text():
                    status_div = div
                    break
            if status_div:
                status_text = (
                    status_div.select_one("span").get_text(strip=True).lower()
                    if status_div.select_one("span")
                    else ""
                )

            # MAL Score
            mal_div = None
            for div in bmeta.select("div.meta > div"):
                if "MAL:" in div.get_text():
                    mal_div = div
                    break
            if mal_div:
                span = mal_div.select_one("span")
                if span:
                    with contextlib.suppress(ValueError):
                        score = float(span.get_text(strip=True))

        # Determine status
        anime_status = "unknown"
        if "ongoing" in status_text or "currently airing" in status_text:
            anime_status = "ongoing"
        elif "finished" in status_text or "completed" in status_text:
            anime_status = "completed"

        # Description
        synopsis_elem = soup.select_one("div.synopsis div.content")
        description = synopsis_elem.get_text(strip=True) if synopsis_elem else ""

        # Alternative titles
        alt_titles = []
        if title_elem and title_elem.get("data-jp"):
            alt_titles.append(title_elem.get("data-jp").strip())

        alt_container = soup.select_one("div.names.font-italic")
        if alt_container:
            for name in alt_container.get_text(strip=True).split(";"):
                clean = name.strip()
                if clean and clean not in alt_titles:
                    alt_titles.append(clean)

        return Anime(
            id=internal_id or anime_path,
            title=title,
            url=f"{anime_path}#{internal_id}" if internal_id else anime_path,
            thumbnail=thumbnail,
            description=description,
            genres=genres,
            studios=studios,
            alternative_titles=alt_titles,
            status=anime_status,
            score=score,
        )

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        """Get episode list."""
        if "#" in anime_id:
            anime_path, internal_id = anime_id.split("#", 1)
        else:
            # Get details to fetch internal ID
            details = await self.get_details(anime_id)
            internal_id = details.id
            anime_path = details.url.split("#")[0]

        if not internal_id:
            return []

        vrf = vrf_encrypt(internal_id)
        ajax_url = f"{self.base_url}/ajax/episode/list/{internal_id}"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{anime_path}",
            "X-Requested-With": "XMLHttpRequest",
        }

        data = await self._get_json(ajax_url, headers=headers, params={"vrf": vrf})
        if not isinstance(data, dict):
            return []

        html_result = data.get("result", "")
        if not html_result:
            return []

        soup = BeautifulSoup(html_result, "html.parser")
        episodes = []

        for a in soup.select("div.episodes ul > li > a"):
            ep_num = a.get("data-num", "")
            ep_ids = a.get("data-ids", "")
            if not ep_num and not ep_ids:
                continue

            # Title
            parent = a.parent
            title_span = parent.select_one("span.d-title") if parent else None
            title = title_span.get_text(strip=True) if title_span else ""

            if not title and parent and parent.get("title"):
                title = parent.get("title").split("Release:")[0].split("Softsub")[0].strip()

            if not title:
                title = f"Episode {ep_num}"

            # Sub/Dub
            has_sub = a.get("data-sub") == "1"
            has_dub = a.get("data-dub") == "1"

            # Filler
            is_filler = "filler" in (a.get("class") or [])

            # Release date
            released_at = None
            timestamp = a.get("data-timestamp", "")
            if timestamp and timestamp.isdigit():
                with contextlib.suppress(ValueError, OSError):
                    released_at = datetime.fromtimestamp(int(timestamp))

            # Build episode ID
            clean_path = re.sub(r"/ep-\d+$", "", anime_path)
            ep_id = f"{ep_ids}&epurl={clean_path}/ep-{ep_num}"

            try:
                ep_number = float(ep_num)
            except ValueError:
                ep_number = 0.0

            episodes.append(
                Episode(
                    id=ep_id,
                    number=ep_number,
                    title=title,
                    is_filler=is_filler,
                    has_sub=has_sub,
                    has_dub=has_dub,
                    released_at=released_at,
                )
            )

        return list(reversed(episodes))

    # === Servers & Streams ===

    async def get_servers(self, episode_id: str) -> list[Server]:
        """Get available video servers."""
        parts = episode_id.split("&")
        if not parts:
            return []

        ids = parts[0]
        epurl = ""
        for part in parts:
            if part.startswith("epurl="):
                epurl = part.split("=", 1)[1]
                break

        ajax_url = f"{self.base_url}/ajax/server/list"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{epurl}",
            "X-Requested-With": "XMLHttpRequest",
        }

        data = await self._get_json(ajax_url, headers=headers, params={"servers": ids})
        if not isinstance(data, dict):
            return []

        html_result = data.get("result", "")
        if not html_result:
            return []

        soup = BeautifulSoup(html_result, "html.parser")
        servers = []

        for type_div in soup.select("div.servers > div.type"):
            # Get video type
            label = type_div.select_one("label")
            label_text = label.get_text(strip=True).lower() if label else ""
            video_type = self._resolve_video_type(label_text)

            for li in type_div.select("li"):
                if "download-icon" in (li.get("class") or []):
                    continue

                server_id = li.get("data-link-id", "")
                server_name = li.get_text(strip=True)

                if server_id and server_name:
                    servers.append(
                        Server(
                            id=server_id,
                            name=server_name,
                            type=video_type,
                        )
                    )

        return servers

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Extract video streams from a server.

        Args:
            episode_id: The episode identifier (needed for referer)
            server_id: The server identifier to extract streams from
        """
        # Extract episode URL for referer
        ep_url = ""
        if "&epurl=" in episode_id:
            for part in episode_id.split("&"):
                if part.startswith("epurl="):
                    ep_url = part.split("=", 1)[1]
                    break

        embed_url = await self._get_embed_link(server_id, ep_url)
        if not embed_url:
            return []

        # Route to appropriate extractor based on URL pattern
        if "mewcdn.online/player/plyr.php" in embed_url:
            return await self._extract_from_mewcdn(embed_url, server_id)
        elif embed_url.endswith(".m3u8") or (".m3u8" in embed_url and "/stream/" not in embed_url):
            return await self._extract_direct_m3u8(embed_url, server_id)
        else:
            return await self._extract_from_player(embed_url, server_id, ep_url)

    async def _get_embed_link(self, server_id: str, ep_url: str) -> str | None:
        """Get embed URL from server ID."""
        if not server_id:
            return None

        # If it's already a full URL, return it directly
        if server_id.startswith("http"):
            return server_id

        ajax_url = f"{self.base_url}/ajax/server"
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{ep_url}",
            "X-Requested-With": "XMLHttpRequest",
        }

        data = await self._get_json(ajax_url, headers=headers, params={"get": server_id})
        if not isinstance(data, dict):
            return None

        result = data.get("result", {})
        if isinstance(result, dict):
            return result.get("url")
        return None

    async def _extract_from_player(
        self,
        embed_url: str,
        server_id: str,
        ep_url: str,
    ) -> list[Stream]:
        """Extract streams from a generic player page."""
        from urllib.parse import urlparse

        host = urlparse(embed_url).netloc
        headers = {
            "Referer": f"{self.base_url}/",
        }

        body = await self._request(embed_url, headers=headers)
        if not body:
            return []

        # Try to find data-id for API extraction
        data_id_match = re.search(r'data-id="([^"]+)"', body)
        if data_id_match:
            data_id = data_id_match.group(1)
            return await self._fetch_sources_from_api(data_id, host, embed_url, server_id)

        # Try to find iframe src
        iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', body)
        if iframe_match:
            iframe_src = self._resolve_url(iframe_match.group(1), embed_url)
            return await self._extract_from_player(iframe_src, server_id, ep_url)

        # Try to find direct m3u8
        m3u8_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', body)
        if m3u8_match:
            return await self._extract_direct_m3u8(
                m3u8_match.group(0), server_id, f"https://{host}/"
            )

        # Try JS variable patterns
        js_m3u8_match = re.search(
            r"""(?:var|let|const)\s+\w+\s*=\s*["']([^"']*(?:\.m3u8|/stream/)[^"']*)["']"""
            r"""|(?:file|source|url|src)\s*[:=]\s*["']([^"']*(?:\.m3u8|/stream/)[^"']*)["']""",
            body,
        )
        if js_m3u8_match:
            js_url = js_m3u8_match.group(1) or js_m3u8_match.group(2)
            if js_url:
                resolved_url = self._resolve_url(js_url, embed_url)
                if ".m3u8" in resolved_url or "/stream/" in resolved_url:
                    try:
                        return await self._fetch_sources_from_page(
                            resolved_url, server_id, f"https://{host}/"
                        )
                    except Exception:
                        return await self._extract_direct_m3u8(
                            resolved_url, server_id, f"https://{host}/"
                        )

        return []

    async def _fetch_sources_from_api(
        self,
        data_id: str,
        host: str,
        embed_url: str,
        server_id: str,
    ) -> list[Stream]:
        """Fetch sources from the getSources/getSourcesNew API."""
        # Determine stream type from URL path
        path_segments = embed_url.split("/")
        stream_type = ""
        if path_segments[-1] in ("sub", "dub", "hsub"):
            stream_type = path_segments[-1]

        api_headers = {
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": embed_url,
            "Origin": f"https://{host}",
        }

        # Try getSources first
        data = None

        api_url = f"https://{host}/stream/getSources?id={data_id}&id={data_id}&type={stream_type}&type={stream_type}"
        try:
            resp_data = await self._get_json(api_url, headers=api_headers)
            if isinstance(resp_data, dict):
                src = resp_data.get("sources")
                # Valid if it's a dict with file or a valid list/string URL
                if (
                    (isinstance(src, dict) and src.get("file"))
                    or (isinstance(src, list) and src and str(src[0]).startswith("http"))
                    or (isinstance(src, str) and src.startswith("http"))
                ):
                    data = resp_data
        except Exception:
            data = None

        # Fall back to getSourcesNew
        if data is None:
            api_url = f"https://{host}/stream/getSourcesNew?id={data_id}&id={data_id}&type={stream_type}&type={stream_type}"
            try:
                resp_data = await self._get_json(api_url, headers=api_headers)
                if isinstance(resp_data, dict):
                    data = resp_data
            except Exception:
                data = None

        if not data:
            return []

        sources = data.get("sources", "")
        if not sources:
            return []

        # Handle sources as dict with "file" key or as direct string
        m3u8_url = ""
        if isinstance(sources, dict):
            m3u8_url = sources.get("file", "")
        elif isinstance(sources, str):
            m3u8_url = sources

        if not m3u8_url or not m3u8_url.startswith("http"):
            return []

        # Extract subtitles
        subtitles = []
        tracks = data.get("tracks", []) or []
        for track in tracks:
            if isinstance(track, dict) and track.get("kind") == "captions":
                subtitles.append(
                    Subtitle(
                        url=track.get("file", ""),
                        label=track.get("label", ""),
                        language=track.get("label", ""),
                    )
                )

        # Parse m3u8 for qualities
        return await self._parse_m3u8(m3u8_url, server_id, f"https://{host}/", subtitles)

    async def _fetch_sources_from_page(
        self,
        url: str,
        server_id: str,
        referer: str,
    ) -> list[Stream]:
        """Fetch sources from a page that may contain m3u8."""
        headers = {"Referer": referer}
        body = await self._request(url, headers=headers)

        if not body:
            raise Exception("Page fetch failed")

        # Check if it's directly an m3u8
        if body.lstrip().startswith("#EXTM3U"):
            return await self._extract_direct_m3u8(url, server_id, referer)

        # Try to find m3u8 in body
        m3u8_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', body)
        if m3u8_match:
            return await self._extract_direct_m3u8(m3u8_match.group(0), server_id, referer)

        raise Exception("No m3u8 found in page")

    async def _extract_direct_m3u8(
        self,
        m3u8_url: str,
        server_id: str,
        referer: str,
    ) -> list[Stream]:
        """Extract streams from a direct m3u8 URL."""
        return await self._parse_m3u8(m3u8_url, server_id, referer, [])

    async def _extract_from_mewcdn(
        self,
        embed_url: str,
        server_id: str,
    ) -> list[Stream]:
        """Extract from Mewcdn player."""
        # Extract fragment from URL
        fragment = ""
        if "#" in embed_url:
            fragment = embed_url.split("#", 1)[1]

        if not fragment:
            return []

        # Decode fragment from base64
        try:
            raw_m3u8 = base64.b64decode(fragment).decode("utf-8").strip()
        except Exception:
            return []

        if not raw_m3u8.startswith("http"):
            return []

        # Fetch page to get host map
        headers = {"Referer": f"{self.base_url}/"}

        try:
            body = await self._request(embed_url, headers=headers)
        except Exception:
            body = ""

        host_map = {}
        if body:
            host_map = self._parse_host_map(body)

        # Apply host map
        m3u8_url = self._apply_host_map(raw_m3u8, host_map)

        return await self._parse_m3u8(m3u8_url, server_id, "https://mewcdn.online/", [])

    def _parse_host_map(self, html: str) -> dict[str, str]:
        """Parse HOST_MAP from player page."""
        map_match = re.search(r"var HOST_MAP\s*=\s*\{([^}]+)\}", html)
        if not map_match:
            return {}

        entries = re.findall(r"'([^']+)'\s*:\s*'([^']+)'", map_match.group(1))
        return dict(entries)

    def _apply_host_map(self, url: str, host_map: dict[str, str]) -> str:
        """Apply host map to URL."""
        result = url
        for origin, proxy in host_map.items():
            if origin in result:
                result = result.replace(origin, proxy)
                break
        return result

    async def _parse_m3u8(
        self,
        m3u8_url: str,
        server_id: str,
        referer: str,
        subtitles: list[Subtitle],
    ) -> list[Stream]:
        """Parse m3u8 playlist and extract stream URLs with qualities."""
        from urllib.parse import urljoin

        headers = {
            "Referer": referer,
        }

        try:
            body = await self._request(m3u8_url, headers=headers)
        except Exception:
            return []

        streams = []
        base_url = m3u8_url.rsplit("/", 1)[0] + "/"

        if not body.lstrip().startswith("#EXTM3U"):
            return []

        lines = body.split("\n")
        if not any(line.lstrip().startswith("#EXT-X-STREAM-INF:") for line in lines):
            return [
                Stream(
                    url=m3u8_url,
                    quality="HLS",
                    headers={"Referer": referer},
                    subtitles=subtitles,
                )
            ]

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXT-X-STREAM-INF:"):
                # Parse quality info
                quality = "Unknown"
                resolution_match = re.search(r"RESOLUTION=(\d+x\d+)", line)
                if resolution_match:
                    resolution = resolution_match.group(1)
                    height = resolution.split("x")[1]
                    quality = f"{height}p"

                # Get bandwidth for additional quality info
                re.search(r"BANDWIDTH=(\d+)", line)

                i += 1
                if i < len(lines):
                    stream_url = lines[i].strip()
                    if stream_url:
                        # Resolve relative URLs
                        if not stream_url.startswith("http"):
                            stream_url = urljoin(base_url, stream_url)

                        # Determine codec/type from bandwidth
                        if "dub" in server_id.lower() or "dub" in str(server_id).lower():
                            pass

                        streams.append(
                            Stream(
                                url=stream_url,
                                quality=quality,
                                headers={"Referer": referer},
                                subtitles=subtitles,
                            )
                        )
            i += 1

        return streams

    def _resolve_url(self, url: str, base: str) -> str:
        """Resolve relative URL against base."""
        if url.startswith("http"):
            return url

        from urllib.parse import urljoin

        return urljoin(base, url)

    def _resolve_video_type(self, label_text: str) -> str:
        """Resolve video type from label."""
        if "dub" in label_text:
            return "dub"
        elif "h-sub" in label_text or "hsub" in label_text:
            return "h-sub"
        return "sub"
