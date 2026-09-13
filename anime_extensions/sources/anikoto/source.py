"""Anikoto source implementation."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from ...core.errors import ExtractorError
from ...core.metadata import SourceCapability, SourceMetadata
from ...core.source import Source
from ...models import Anime, Episode, Page, Server, Stream
from ...utils.crypto import vrf_encrypt

if TYPE_CHECKING:
    from ...core.runtime import ExtensionContext

log = logging.getLogger(__name__)


class Anikoto(Source):
    """Anikoto anime source."""

    metadata = SourceMetadata(
        id="anikoto",
        name="Anikoto",
        base_url="https://anikototv.to",
        capabilities=frozenset(
            {
                SourceCapability.POPULAR,
                SourceCapability.LATEST,
                SourceCapability.SEARCH,
                SourceCapability.DETAILS,
                SourceCapability.EPISODES,
                SourceCapability.SERVERS,
                SourceCapability.STREAMS,
            }
        ),
        domains=(
            "anikototv.to",
            "anikoto.bz",
            "anikoto.cz",
            "anikoto.me",
            "anikoto.net",
            "anikototv.se",
        ),
    )
    id = metadata.id
    base_url = metadata.base_url

    def __init__(self, context: ExtensionContext, *, domain: str | None = None) -> None:
        """Bind the source to an explicit runtime context."""
        super().__init__(context)
        if domain:
            self.base_url = f"https://{domain}"

    async def _request(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Fetch source content through the runtime-owned HTTP client."""
        return await self.context.http.get(url, headers=headers, params=params)

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Fetch source JSON through the runtime-owned HTTP client."""
        return await self.context.http.get_json(url, headers=headers, params=params)

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        """Fetch popular anime."""
        url = f"{self.base_url}/most-viewed/"
        html = await self._request(url, params={"page": page})
        items, has_next = self._parse_listing(html)
        return Page(items=items, page=page, has_next=has_next)

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        """Fetch latest updated anime."""
        url = f"{self.base_url}/latest-updated/"
        html = await self._request(url, params={"page": page})
        items, has_next = self._parse_listing(html)
        return Page(items=items, page=page, has_next=has_next)

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        """Search anime by query."""
        params = {
            "keyword": query,
            "page": page,
            "vrf": vrf_encrypt(query),
        }
        url = f"{self.base_url}/filter"
        html = await self._request(url, params=params)
        items, has_next = self._parse_listing(html)
        return Page(items=items, page=page, has_next=has_next)

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

    @staticmethod
    def _episode_url_from_id(episode_id: str) -> str:
        """Extract the source-relative episode URL encoded in an episode ID."""
        marker = "&epurl="
        if marker not in episode_id:
            return ""
        return episode_id.split(marker, 1)[1].split("&", 1)[0]

    async def get_servers(self, episode_id: str) -> list[Server]:
        """Get available video servers."""
        if not episode_id:
            return []

        ids = episode_id.split("&", 1)[0]
        epurl = self._episode_url_from_id(episode_id)

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
        ep_url = self._episode_url_from_id(episode_id)
        embed_url = await self._get_embed_link(server_id, ep_url)
        if not embed_url:
            return []

        if embed_url.endswith(".m3u8") or (".m3u8" in embed_url and "/stream/" not in embed_url):
            return [
                Stream(
                    url=embed_url,
                    quality="auto",
                    headers={"Referer": f"{self.base_url}/"},
                    is_hls=True,
                )
            ]

        try:
            extractor_cls = self.context.extractors.resolve(embed_url)
            extractor = extractor_cls(self.context)
        except ExtractorError:
            log.warning(f"Anikoto: Unable to resolve extractor for {embed_url}")
            return []

        return await extractor.extract(
            embed_url,
            quality_prefix="",
            external_subs=[],
        )

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

    def _resolve_video_type(self, label_text: str) -> str:
        """Resolve video type from label."""
        if "dub" in label_text:
            return "dub"
        elif "h-sub" in label_text or "hsub" in label_text:
            return "h-sub"
        return "sub"
