"""AniWaves source implementation."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..base import BaseSource
from ..extractors.byse import ByseExtractor
from ..extractors.dood import DoodExtractor
from ..extractors.echovideo import EchoVideoExtractor
from ..models import Anime, Episode, Server, Stream
from ..utils.crypto import vrf_encrypt

log = logging.getLogger(__name__)


class AniWaves(BaseSource):
    """AniWaves anime source."""

    name = "AniWaves"
    id = "aniwaves"
    base_url = "https://aniwaves.ru"

    DOMAINS = [
        "aniwaves.ru",
    ]

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )

    HOSTER_LABELS = {
        "vidplay": "Vidplay",
        "byfms": "BYFMS",
        "dghg": "DGHG",
        "mycloud": "MyCloud",
        "datsav": "DatSaV",
    }

    def __init__(self, *, domain: str | None = None, session: Any = None) -> None:
        super().__init__(session=session)
        if domain:
            self.base_url = f"https://{domain}"
        self._headers["User-Agent"] = self.USER_AGENT

        # Extractors share our session once created
        self._dood: DoodExtractor | None = None
        self._byse: ByseExtractor | None = None
        self._echovideo: EchoVideoExtractor | None = None

    async def _get_dood(self) -> DoodExtractor:
        if self._dood is None:
            session = await self._ensure_session()
            self._dood = DoodExtractor(session=session)
        return self._dood

    async def _get_byse(self) -> ByseExtractor:
        if self._byse is None:
            session = await self._ensure_session()
            self._byse = ByseExtractor(session=session)
        return self._byse

    async def _get_echovideo(self) -> EchoVideoExtractor:
        if self._echovideo is None:
            session = await self._ensure_session()
            self._echovideo = EchoVideoExtractor(session=session)
        return self._echovideo

    # === Listing Methods ===

    async def get_popular(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch popular/trending anime."""
        url = f"{self.base_url}/trending/page/{page}"
        status, html = await self._request(url)
        return self._parse_listing(html)

    async def get_latest(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch latest updated anime."""
        url = f"{self.base_url}/filter"
        params = {"sort_by": "last_updated", "page": page}
        status, html = await self._request(url, params=params)
        return self._parse_listing(html)

    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        """Search anime by query."""
        # Handle tag queries (#tag -> /tags/tag-slug)
        if query.startswith("#"):
            slug = query[1:].strip().lower().replace(" ", "-")
            slug = re.sub(r"[^a-z0-9-]", "", slug)
            tag_page = "" if page == 1 else f"/page/{page}"
            url = f"{self.base_url}/tags/{slug}{tag_page}"
            status, html = await self._request(url)
            return self._parse_listing(html)

        params = {"keyword": query, "page": page}
        url = f"{self.base_url}/filter"
        status, html = await self._request(url, params=params)
        return self._parse_listing(html)

    def _parse_listing(self, html: str) -> tuple[list[Anime], bool]:
        """Parse anime listing page."""
        soup = BeautifulSoup(html, "html.parser")
        animes: list[Anime] = []

        for item in soup.select("div.ani.items > div.item"):
            name_a = item.select_one("a.name, a.d-title")
            if not name_a:
                continue

            href = name_a.get("href", "")
            url_path = re.sub(r"/(?:ep-\d+|episode/\d+)$", "", href.split("?")[0])

            # Prefer Japanese title
            title = name_a.get("data-jp", "").strip() or name_a.get_text(strip=True)

            thumbnail = ""
            img = item.select_one("div.poster img, img")
            if img:
                thumbnail = img.get("data-src") or img.get("src", "")

            anime_id = url_path.split("/watch/")[-1] if "/watch/" in url_path else url_path

            animes.append(Anime(
                id=anime_id,
                title=title,
                url=url_path,
                thumbnail=thumbnail,
            ))

        # Check pagination
        has_next = len(soup.select("nav > ul.pagination > li.active ~ li")) > 0

        return animes, has_next

    # === Details & Episodes ===

    async def get_details(self, anime_id: str) -> Anime:
        """Get full anime details."""
        clean_id = anime_id.split("#")[0].strip("/")
        if not clean_id.startswith("watch/"):
            anime_path = f"/watch/{clean_id}"
        else:
            anime_path = f"/{clean_id}"

        url = f"{self.base_url}{anime_path}"
        status, html = await self._request(url)
        soup = BeautifulSoup(html, "html.parser")

        # Title
        title_elem = soup.select_one("h1.title, h2.title")
        title = ""
        if title_elem:
            title = title_elem.get("data-jp", "").strip() or title_elem.get_text(strip=True)

        # Internal ID
        internal_id = ""
        watch_main = soup.select_one("#watch-main[data-id]")
        if watch_main:
            internal_id = watch_main.get("data-id", "")

        # Thumbnail
        thumbnail = ""
        img = soup.select_one("#w-info div.poster img")
        if img:
            thumbnail = img.get("data-src") or img.get("src", "")

        # Parse metadata
        genres: list[str] = []
        studios: list[str] = []
        status_text = ""
        score: float | None = None

        # Genres
        genre_divs = soup.select("div:-soup-contains(Genres) > span > a")
        if not genre_divs:
            for div in soup.select("div.bmeta div.meta > div"):
                if "Genres" in div.get_text():
                    genres = [a.get_text(strip=True) for a in div.select("span a")]
                    break
        else:
            genres = [a.get_text(strip=True) for a in genre_divs]

        # Studios
        studio_divs = soup.select("div:-soup-contains(Studios) > span > a")
        if studio_divs:
            studios = [a.get_text(strip=True) for a in studio_divs]

        # Status
        status_div = soup.select_one("div:-soup-contains(Status) > span")
        if status_div:
            status_text = status_div.get_text(strip=True).lower()

        # MAL Score
        for div in soup.select("div.bmeta div.meta > div"):
            text = div.get_text()
            if "Scores" in text or "MAL" in text:
                span = div.select_one("span")
                if span:
                    score_text = span.get_text(strip=True).split()[0]
                    try:
                        score = float(score_text)
                    except ValueError:
                        pass
                break

        # Determine status
        anime_status = "unknown"
        if "ongoing" in status_text or "currently" in status_text or "airing" in status_text:
            anime_status = "ongoing"
        elif "finished" in status_text or "completed" in status_text:
            anime_status = "completed"

        # Description
        synopsis_elem = soup.select_one("div.shorting.film-description div.content")
        description = synopsis_elem.get_text(strip=True) if synopsis_elem else ""

        # Alternative titles
        alt_titles: list[str] = []
        if title_elem and title_elem.get("data-jp"):
            alt_titles.append(title_elem.get("data-jp").strip())

        alt_container = soup.select_one("div.names.font-italic")
        if alt_container:
            for name in alt_container.get_text(strip=True).split(","):
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

        status, data = await self._get_json(ajax_url, headers=headers, params={"vrf": vrf})
        if status != 200 or not isinstance(data, dict):
            return []

        html_result = data.get("result", "")
        if not html_result:
            return []

        soup = BeautifulSoup(html_result, "html.parser")
        episodes: list[Episode] = []

        for a in soup.select("div.episodes ul li a"):
            ep_num = a.get("data-num", "")
            ep_ids = a.get("data-ids", "")
            if not ep_num and not ep_ids:
                continue

            # Scanlator flags
            has_sub = a.get("data-sub") == "1"
            has_dub = a.get("data-dub") == "1"

            # Title from parent
            parent = a.parent
            title = ""
            if parent:
                title_span = parent.select_one("span.d-title")
                if title_span:
                    title = title_span.get_text(strip=True)

                if not title and parent.get("title"):
                    release_title = parent.get("title")
                    title = release_title.split("Release:")[0].split("Softsub")[0].strip()

            if not title:
                title = f"Episode {ep_num}"

            # Build episode ID
            clean_path = re.sub(r"/(?:ep-\d+|episode/\d+)$", "", anime_path)
            ep_id = f"{ep_ids}&epurl={clean_path}/episode/{ep_num}"

            try:
                ep_number = float(ep_num)
            except ValueError:
                ep_number = 0.0

            episodes.append(Episode(
                id=ep_id,
                number=ep_number,
                title=title,
                has_sub=has_sub,
                has_dub=has_dub,
            ))

        return list(reversed(episodes))

    # === Servers & Streams ===

    async def get_servers(self, episode_id: str) -> list[Server]:
        """Get available video servers."""
        if "&epurl=" not in episode_id:
            return []

        ids, epurl = episode_id.split("&epurl=", 1)
        epurl = epurl.split("&", 1)[0]

        ajax_url = f"{self.base_url}/ajax/server/list?servers={ids}"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{epurl}",
            "X-Requested-With": "XMLHttpRequest",
        }

        status, data = await self._get_json(ajax_url, headers=headers)
        if status != 200 or not isinstance(data, dict):
            return []

        html_result = data.get("result", "")
        if not html_result:
            return []

        soup = BeautifulSoup(html_result, "html.parser")
        servers: list[Server] = []

        for type_div in soup.select("div.servers div.type[data-type]"):
            label = type_div.get("data-type", "").lower()
            video_type = self._resolve_video_type(label)

            for li in type_div.select("li"):
                server_id = li.get("data-link-id", "")
                raw_name = li.get_text(strip=True)

                if not server_id or not raw_name:
                    continue

                server_name = self._normalize_server_name(raw_name)

                servers.append(Server(
                    id=server_id,
                    name=server_name,
                    type=video_type,
                ))

        return servers

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Extract video streams from a server.

        Args:
            episode_id: The episode identifier
            server_id: The server identifier (data-link-id)
        """
        # Get embed URL
        embed_url = await self._get_embed_url(server_id, episode_id)
        if not embed_url:
            return []

        # Build label prefix from server metadata
        label_prefix = ""

        # Route to appropriate extractor (matching Kotlin order: dood first, then byse, else echo)
        embed_lower = embed_url.lower()

        if "dood" in embed_lower or "myvidplay" in embed_lower:
            return await self._extract_from_dood(embed_url, label_prefix)

        if any(x in embed_lower for x in ["gn1r5n", "byfms", "filemoon"]):
            return await self._extract_from_byse(embed_url, label_prefix, episode_id)

        return await self._extract_from_echovideo(embed_url, label_prefix)

    async def _get_embed_url(self, server_id: str, episode_id: str) -> str | None:
        """Get embed URL from server ID."""
        if not server_id:
            return None

        # Extract episode URL for referer
        ep_url = ""
        if "&epurl=" in episode_id:
            for part in episode_id.split("&"):
                if part.startswith("epurl="):
                    ep_url = part.split("=", 1)[1]
                    break

        ajax_url = f"{self.base_url}/ajax/sources"
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{ep_url}",
            "X-Requested-With": "XMLHttpRequest",
        }

        params = {"id": server_id, "asi": "0", "autoPlay": "0"}

        status, data = await self._get_json(ajax_url, headers=headers, params=params)
        if status != 200 or not isinstance(data, dict):
            return None

        result = data.get("result", {})
        if isinstance(result, dict):
            return result.get("url")
        return None

    async def _extract_from_echovideo(self, embed_url: str, label_prefix: str) -> list[Stream]:
        """Extract from Vidplay/MyCloud/DatSaV (EchoVideo family)."""
        try:
            extractor = await self._get_echovideo()
            return await extractor.extract(embed_url, label_prefix=label_prefix)
        except Exception as e:
            log.warning("EchoVideo extraction failed for %s: %s", embed_url, e)
            return []

    async def _extract_from_dood(self, embed_url: str, label_prefix: str) -> list[Stream]:
        """Extract from Doodstream."""
        try:
            extractor = await self._get_dood()
            return await extractor.extract(
                embed_url,
                quality_prefix=label_prefix,
            )
        except Exception as e:
            log.warning("Dood extraction failed for %s: %s", embed_url, e)
            return []

    async def _extract_from_byse(self, embed_url: str, label_prefix: str, episode_id: str) -> list[Stream]:
        """Extract from BYFMS/Filemoon (Byse system)."""
        # Build ep URL for referer
        ep_url = ""
        if "&epurl=" in episode_id:
            for part in episode_id.split("&"):
                if part.startswith("epurl="):
                    ep_url = part.split("=", 1)[1]
                    break

        try:
            extractor = await self._get_byse()
            return await extractor.extract(
                embed_url,
                embed_parent=f"{self.base_url}{ep_url}",
                embed_origin=self.base_url,
                label_prefix=label_prefix,
            )
        except Exception as e:
            log.warning("Byse extraction failed for %s: %s", embed_url, e)
            return []

    def _resolve_video_type(self, label: str) -> str:
        """Resolve video type from label."""
        if label == "dub":
            return "dub"
        elif label in ("ssub", "soft sub"):
            return "soft-sub"
        return "sub"

    def _normalize_server_name(self, raw_name: str) -> str:
        """Normalize server name to standard form."""
        lower = raw_name.lower()
        return self.HOSTER_LABELS.get(lower, raw_name.capitalize())
