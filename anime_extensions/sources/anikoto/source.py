"""Anikoto source implementation."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from selectolax.parser import HTMLParser

from ...core.errors import ExtractorError
from ...core.metadata import SourceCapability, SourceMetadata
from ...core.source import Source
from ...models import Anime, Episode, Page, Server, Stream
from ...utils.crypto import vrf_encrypt

if TYPE_CHECKING:
    from ...core.runtime import ExtensionContext

log = logging.getLogger(__name__)
_EPISODE_SUFFIX_RE = re.compile(r"/(?:ep-\d+|episode/\d+)$")


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
        tree = HTMLParser(html)
        animes: list[Anime] = []

        for item in tree.css("div.ani.items > div.item"):
            name_a = item.css_first("a.name")
            if not name_a:
                continue

            href = name_a.attributes.get("href", "")
            url_path = _EPISODE_SUFFIX_RE.sub("", href.split("?")[0])
            img = item.css_first("div.poster img")
            animes.append(
                Anime(
                    id=url_path.split("/watch/")[-1] if "/watch/" in url_path else url_path,
                    title=name_a.attributes.get("data-jp", "").strip() or name_a.text(strip=True),
                    url=url_path,
                    thumbnail=(
                        (img.attributes.get("data-src") or img.attributes.get("src", ""))
                        if img
                        else ""
                    ),
                )
            )

        return animes, bool(tree.css("ul.pagination > li.active ~ li"))

    # === Details & Episodes ===

    async def get_details(self, anime_id: str) -> Anime:
        """Get full anime details."""
        clean_id = anime_id.split("#")[0].strip("/")
        anime_path = f"/watch/{clean_id}" if not clean_id.startswith("watch/") else f"/{clean_id}"

        tree = HTMLParser(await self._request(f"{self.base_url}{anime_path}"))

        # Title - prefer Japanese title from data-jp attribute
        title_elem = tree.css_first("h1.title, h2.title")
        title = (
            title_elem.attributes.get("data-jp", "").strip() or title_elem.text(strip=True)
            if title_elem
            else ""
        )

        # Internal ID - get from watch-main div or rating div
        watch_main = tree.css_first("div#watch-main[data-id]")
        internal_id = watch_main.attributes.get("data-id", "") if watch_main else ""

        # Thumbnail
        img = tree.css_first("div.poster img, img.thumbnail")
        thumbnail = (img.attributes.get("data-src") or img.attributes.get("src", "")) if img else ""

        # Parse metadata from bmeta div
        genres: list[str] = []
        studios: list[str] = []
        status_text = ""
        score: float | None = None

        if bmeta := tree.css_first("div.bmeta"):
            for div in bmeta.css("div.meta > div"):
                text = div.text(separator=" ", strip=True)
                if "Genres:" in text:
                    genres = [a.text(strip=True) for a in div.css("span a")]
                elif "Studios:" in text:
                    studios = [a.text(strip=True) for a in div.css("span a")]
                elif "Status:" in text and (span := div.css_first("span")):
                    status_text = span.text(strip=True).lower()
                elif ("MAL:" in text or "Scores" in text) and (span := div.css_first("span")):
                    with contextlib.suppress(ValueError):
                        score = float(span.text(strip=True).split()[0])

        # Determine status
        anime_status = "unknown"
        if "ongoing" in status_text or "currently airing" in status_text:
            anime_status = "ongoing"
        elif "finished" in status_text or "completed" in status_text:
            anime_status = "completed"

        # Description
        synopsis_elem = tree.css_first("div.synopsis div.content")
        description = synopsis_elem.text(strip=True) if synopsis_elem else ""

        # Alternative titles
        alt_titles = (
            [title_elem.attributes.get("data-jp", "").strip()]
            if title_elem and title_elem.attributes.get("data-jp")
            else []
        )

        if alt_container := tree.css_first("div.names.font-italic"):
            for name in alt_container.text(strip=True).split(";"):
                if (clean := name.strip()) and clean not in alt_titles:
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

        tree = HTMLParser(html_result)
        episodes: list[Episode] = []
        clean_path = _EPISODE_SUFFIX_RE.sub("", anime_path)

        for a in tree.css("div.episodes ul > li > a"):
            ep_num = a.attributes.get("data-num", "")
            ep_ids = a.attributes.get("data-ids", "")
            if not ep_num and not ep_ids:
                continue

            # Title
            parent = a.parent
            title_span = parent.css_first("span.d-title") if parent else None
            title = title_span.text(strip=True) if title_span else ""

            if not title and parent and parent.attributes.get("title"):
                title = (
                    parent.attributes.get("title", "")
                    .split("Release:")[0]
                    .split("Softsub")[0]
                    .strip()
                )

            if not title:
                title = f"Episode {ep_num}"

            # Sub/Dub
            has_sub = a.attributes.get("data-sub") == "1"
            has_dub = a.attributes.get("data-dub") == "1"

            # Filler
            is_filler = "filler" in a.attributes.get("class", "").split()

            # Release date
            released_at = None
            timestamp = a.attributes.get("data-timestamp", "")
            if timestamp and timestamp.isdigit():
                with contextlib.suppress(ValueError, OSError):
                    released_at = datetime.fromtimestamp(int(timestamp))

            # Build episode ID
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

        tree = HTMLParser(html_result)
        servers: list[Server] = []

        for type_div in tree.css("div.servers > div.type"):
            # Get video type
            label = type_div.css_first("label")
            label_text = label.text(strip=True).lower() if label else ""
            video_type = self._resolve_video_type(label_text)

            for li in type_div.css("li"):
                if "download-icon" in li.attributes.get("class", "").split():
                    continue

                server_id = li.attributes.get("data-link-id", "")
                server_name = li.text(strip=True)

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
