"""AniWaves source implementation."""

from __future__ import annotations

import contextlib
import logging
import re
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from ...core.errors import ExtractorError
from ...core.metadata import SourceCapability, SourceMetadata
from ...core.registry import register_source
from ...core.source import Source
from ...models import Anime, Episode, Server, Stream
from ...utils.crypto import vrf_encrypt

if TYPE_CHECKING:
    from ...core.runtime import SourceContext

log = logging.getLogger(__name__)


@register_source
class AniWaves(Source):
    """AniWaves anime source."""

    metadata = SourceMetadata(
        id="aniwaves",
        name="AniWaves",
        base_url="https://aniwaves.ru",
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
        domains=("aniwaves.ru",),
    )
    id = metadata.id
    base_url = metadata.base_url

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

    def __init__(self, context: SourceContext, *, domain: str | None = None) -> None:
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
        request_headers = {"User-Agent": self.USER_AGENT}
        if headers:
            request_headers.update(headers)
        return await self.context.http.get(url, headers=request_headers, params=params)

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Fetch source JSON through the runtime-owned HTTP client."""
        request_headers = {"User-Agent": self.USER_AGENT}
        if headers:
            request_headers.update(headers)
        return await self.context.http.get_json(url, headers=request_headers, params=params)

    async def get_popular(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch popular/trending anime."""
        return self._parse_listing(await self._request(f"{self.base_url}/trending/page/{page}"))

    async def get_latest(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch latest updated anime."""
        return self._parse_listing(
            await self._request(
                f"{self.base_url}/filter", params={"sort_by": "last_updated", "page": page}
            )
        )

    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        """Search anime by query."""
        if query.startswith("#"):
            slug = re.sub(r"[^a-z0-9-]", "", query[1:].strip().lower().replace(" ", "-"))
            suffix = "" if page == 1 else f"/page/{page}"
            return self._parse_listing(await self._request(f"{self.base_url}/tags/{slug}{suffix}"))
        return self._parse_listing(
            await self._request(f"{self.base_url}/filter", params={"keyword": query, "page": page})
        )

    def _parse_listing(self, html: str) -> tuple[list[Anime], bool]:
        """Parse an anime listing page."""
        soup = BeautifulSoup(html, "html.parser")
        animes: list[Anime] = []
        for item in soup.select("div.ani.items > div.item"):
            name_a = item.select_one("a.name, a.d-title")
            if not name_a:
                continue
            url_path = re.sub(r"/(?:ep-\d+|episode/\d+)$", "", name_a.get("href", "").split("?")[0])
            img = item.select_one("div.poster img, img")
            animes.append(
                Anime(
                    id=url_path.split("/watch/")[-1] if "/watch/" in url_path else url_path,
                    title=name_a.get("data-jp", "").strip() or name_a.get_text(strip=True),
                    url=f"{self.base_url}{url_path}",
                    thumbnail=(img.get("data-src") or img.get("src", "")) if img else "",
                )
            )
        return animes, bool(soup.select("nav > ul.pagination > li.active ~ li"))

    async def get_details(self, anime_id: str) -> Anime:
        """Get full anime details."""
        clean_id = anime_id.split("#")[0].strip("/")
        anime_path = f"/watch/{clean_id}" if not clean_id.startswith("watch/") else f"/{clean_id}"
        soup = BeautifulSoup(await self._request(f"{self.base_url}{anime_path}"), "html.parser")
        title_elem = soup.select_one("h1.title, h2.title")
        title = (
            title_elem.get("data-jp", "").strip() or title_elem.get_text(strip=True)
            if title_elem
            else ""
        )
        watch_main = soup.select_one("#watch-main[data-id]")
        internal_id = watch_main.get("data-id", "") if watch_main else ""
        img = soup.select_one("#w-info div.poster img")
        thumbnail = (img.get("data-src") or img.get("src", "")) if img else ""
        genres: list[str] = []
        studios: list[str] = []
        status_text = ""
        score: float | None = None
        for div in soup.select("div.bmeta div.meta > div"):
            text = div.get_text()
            if "Genres" in text:
                genres = [a.get_text(strip=True) for a in div.select("span a")]
            elif "Studios" in text:
                studios = [a.get_text(strip=True) for a in div.select("span a")]
            elif "Status" in text and (span := div.select_one("span")):
                status_text = span.get_text(strip=True).lower()
            elif ("Scores" in text or "MAL" in text) and (span := div.select_one("span")):
                with contextlib.suppress(ValueError):
                    score = float(span.get_text(strip=True).split()[0])
        status = (
            "ongoing"
            if any(x in status_text for x in ("ongoing", "currently", "airing"))
            else "completed"
            if any(x in status_text for x in ("finished", "completed"))
            else "unknown"
        )
        synopsis = soup.select_one("div.shorting.film-description div.content")
        alt_titles = (
            [title_elem.get("data-jp").strip()] if title_elem and title_elem.get("data-jp") else []
        )
        if alt_container := soup.select_one("div.names.font-italic"):
            for name in alt_container.get_text(strip=True).split(","):
                if (clean := name.strip()) and clean not in alt_titles:
                    alt_titles.append(clean)
        return Anime(
            id=internal_id or anime_path,
            title=title,
            url=f"{anime_path}#{internal_id}" if internal_id else anime_path,
            thumbnail=thumbnail,
            description=synopsis.get_text(strip=True) if synopsis else "",
            genres=genres,
            studios=studios,
            alternative_titles=alt_titles,
            status=status,
            score=score,
        )

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        """Get episode list."""
        if "#" in anime_id:
            anime_path, internal_id = anime_id.split("#", 1)
        else:
            details = await self.get_details(anime_id)
            internal_id, anime_path = details.id, details.url.split("#")[0]
        if not internal_id:
            return []
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{anime_path}",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = await self._get_json(
            f"{self.base_url}/ajax/episode/list/{internal_id}",
            headers=headers,
            params={"vrf": vrf_encrypt(internal_id)},
        )
        if not isinstance(data, dict) or not (html_result := data.get("result", "")):
            return []
        episodes: list[Episode] = []
        for anchor in BeautifulSoup(html_result, "html.parser").select("div.episodes ul li a"):
            ep_num, ep_ids = anchor.get("data-num", ""), anchor.get("data-ids", "")
            if not ep_num and not ep_ids:
                continue
            parent = anchor.parent
            title_span = parent.select_one("span.d-title") if parent else None
            title = title_span.get_text(strip=True) if title_span else ""
            if not title and parent and parent.get("title"):
                title = parent.get("title").split("Release:")[0].split("Softsub")[0].strip()
            try:
                ep_number = float(ep_num)
            except ValueError:
                ep_number = 0.0
            path = re.sub(r"/(?:ep-\d+|episode/\d+)$", "", anime_path)
            episodes.append(
                Episode(
                    id=f"{ep_ids}&epurl={path}/episode/{ep_num}",
                    number=ep_number,
                    title=title or f"Episode {ep_num}",
                    has_sub=anchor.get("data-sub") == "1",
                    has_dub=anchor.get("data-dub") == "1",
                )
            )
        return list(reversed(episodes))

    async def get_servers(self, episode_id: str) -> list[Server]:
        """Get available video servers."""
        if "&epurl=" not in episode_id:
            return []
        ids, epurl = episode_id.split("&epurl=", 1)
        epurl = epurl.split("&", 1)[0]
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{epurl}",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = await self._get_json(
            f"{self.base_url}/ajax/server/list?servers={ids}", headers=headers
        )
        if not isinstance(data, dict) or not (html_result := data.get("result", "")):
            return []
        servers: list[Server] = []
        for type_div in BeautifulSoup(html_result, "html.parser").select(
            "div.servers div.type[data-type]"
        ):
            video_type = self._resolve_video_type(type_div.get("data-type", "").lower())
            for item in type_div.select("li"):
                if (server_id := item.get("data-link-id", "")) and (
                    raw_name := item.get_text(strip=True)
                ):
                    servers.append(
                        Server(
                            id=server_id,
                            name=self._normalize_server_name(raw_name),
                            type=video_type,
                        )
                    )
        return servers

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Resolve the provider-specific extractor dynamically and extract streams."""
        embed_url = await self._get_embed_url(server_id, episode_id)
        if not embed_url:
            return []
        try:
            extractor = self.context.runtime.resolve_extractor(embed_url)
        except ExtractorError:
            log.warning("AniWaves has no registered extractor for the selected server")
            return []
        kwargs: dict[str, Any] = {"label_prefix": ""}
        if extractor.name == "Doodstream":
            kwargs["quality_prefix"] = kwargs.pop("label_prefix")
        elif extractor.name == "Byse":
            epurl = next(
                (
                    part.split("=", 1)[1]
                    for part in episode_id.split("&")
                    if part.startswith("epurl=")
                ),
                "",
            )
            kwargs.update(embed_parent=f"{self.base_url}{epurl}", embed_origin=self.base_url)
        try:
            return await extractor.extract(embed_url, **kwargs)
        except Exception as error:
            log.warning("AniWaves stream extraction failed with %s", type(error).__name__)
            return []

    async def _get_embed_url(self, server_id: str, episode_id: str) -> str | None:
        """Get an embed URL from an AniWaves server identifier."""
        if not server_id:
            return None
        epurl = next(
            (part.split("=", 1)[1] for part in episode_id.split("&") if part.startswith("epurl=")),
            "",
        )
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{self.base_url}{epurl}",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = await self._get_json(
            f"{self.base_url}/ajax/sources",
            headers=headers,
            params={"id": server_id, "asi": "0", "autoPlay": "0"},
        )
        result = data.get("result", {}) if isinstance(data, dict) else {}
        url = result.get("url") if isinstance(result, dict) else None
        return url if isinstance(url, str) and url.startswith(("http://", "https://")) else None

    @staticmethod
    def _resolve_video_type(label: str) -> str:
        """Resolve video type from source label."""
        if label == "dub":
            return "dub"
        if label in ("ssub", "soft sub"):
            return "soft-sub"
        return "sub"

    def _normalize_server_name(self, raw_name: str) -> str:
        """Normalize a source server name."""
        return self.HOSTER_LABELS.get(raw_name.lower(), raw_name.capitalize())
