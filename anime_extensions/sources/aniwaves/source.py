"""AniWaves source implementation."""

from __future__ import annotations

import contextlib
import logging
import re
from typing import TYPE_CHECKING, Any

from selectolax.parser import HTMLParser

from ...core.metadata import SourceCapability, SourceMetadata
from ...core.source import Source
from ...models import Anime, Episode, Page, Server, Stream
from ...utils.crypto import vrf_encrypt

if TYPE_CHECKING:
    from ...core.runtime import ExtensionContext

log = logging.getLogger(__name__)
_EPISODE_SUFFIX_RE = re.compile(r"/(?:ep-\d+|episode/\d+)$")


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

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        """Fetch popular/trending anime."""
        items, has_next = self._parse_listing(
            await self._request(f"{self.base_url}/trending/page/{page}")
        )
        return Page(items=items, page=page, has_next=has_next)

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        """Fetch latest updated anime."""
        items, has_next = self._parse_listing(
            await self._request(
                f"{self.base_url}/filter", params={"sort_by": "last_updated", "page": page}
            )
        )
        return Page(items=items, page=page, has_next=has_next)

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        """Search anime by query."""
        if query.startswith("#"):
            slug = re.sub(r"[^a-z0-9-]", "", query[1:].strip().lower().replace(" ", "-"))
            suffix = "" if page == 1 else f"/page/{page}"
            items, has_next = self._parse_listing(
                await self._request(f"{self.base_url}/tags/{slug}{suffix}")
            )
            return Page(items=items, page=page, has_next=has_next)
        items, has_next = self._parse_listing(
            await self._request(f"{self.base_url}/filter", params={"keyword": query, "page": page})
        )
        return Page(items=items, page=page, has_next=has_next)

    def _parse_listing(self, html: str) -> tuple[list[Anime], bool]:
        """Parse an anime listing page."""
        tree = HTMLParser(html)
        animes: list[Anime] = []
        for item in tree.css("div.ani.items > div.item"):
            name_a = item.css_first("a.name, a.d-title")
            if not name_a:
                continue
            url_path = _EPISODE_SUFFIX_RE.sub("", name_a.attributes.get("href", "").split("?")[0])
            img = item.css_first("div.poster img, img")
            animes.append(
                Anime(
                    id=url_path.split("/watch/")[-1] if "/watch/" in url_path else url_path,
                    title=name_a.attributes.get("data-jp", "").strip() or name_a.text(strip=True),
                    url=f"{self.base_url}{url_path}",
                    thumbnail=(
                        (img.attributes.get("data-src") or img.attributes.get("src", ""))
                        if img
                        else ""
                    ),
                )
            )
        return animes, bool(tree.css("nav > ul.pagination > li.active ~ li"))

    async def get_details(self, anime_id: str) -> Anime:
        """Get full anime details."""
        clean_id = anime_id.split("#")[0].strip("/")
        anime_path = f"/watch/{clean_id}" if not clean_id.startswith("watch/") else f"/{clean_id}"
        tree = HTMLParser(await self._request(f"{self.base_url}{anime_path}"))
        title_elem = tree.css_first("h1.title, h2.title")
        title = (
            title_elem.attributes.get("data-jp", "").strip() or title_elem.text(strip=True)
            if title_elem
            else ""
        )
        watch_main = tree.css_first("#watch-main[data-id]")
        internal_id = watch_main.attributes.get("data-id", "") if watch_main else ""
        img = tree.css_first("#w-info div.poster img")
        thumbnail = (img.attributes.get("data-src") or img.attributes.get("src", "")) if img else ""
        genres: list[str] = []
        studios: list[str] = []
        status_text = ""
        score: float | None = None
        for div in tree.css("div.bmeta div.meta > div"):
            text = div.text()
            if "Genres" in text:
                genres = [a.text(strip=True) for a in div.css("span a")]
            elif "Studios" in text:
                studios = [a.text(strip=True) for a in div.css("span a")]
            elif "Status" in text and (span := div.css_first("span")):
                status_text = span.text(strip=True).lower()
            elif ("Scores" in text or "MAL" in text) and (span := div.css_first("span")):
                with contextlib.suppress(ValueError):
                    score = float(span.text(strip=True).split()[0])
        status = (
            "ongoing"
            if any(x in status_text for x in ("ongoing", "currently", "airing"))
            else "completed"
            if any(x in status_text for x in ("finished", "completed"))
            else "unknown"
        )
        synopsis = tree.css_first("div.shorting.film-description div.content")
        alt_titles = (
            [title_elem.attributes.get("data-jp", "").strip()]
            if title_elem and title_elem.attributes.get("data-jp")
            else []
        )
        if alt_container := tree.css_first("div.names.font-italic"):
            for name in alt_container.text(strip=True).split(","):
                if (clean := name.strip()) and clean not in alt_titles:
                    alt_titles.append(clean)
        return Anime(
            id=internal_id or anime_path,
            title=title,
            url=f"{anime_path}#{internal_id}" if internal_id else anime_path,
            thumbnail=thumbnail,
            description=synopsis.text(strip=True) if synopsis else "",
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
        path = _EPISODE_SUFFIX_RE.sub("", anime_path)
        for anchor in HTMLParser(html_result).css("div.episodes ul li a"):
            ep_num = anchor.attributes.get("data-num", "")
            ep_ids = anchor.attributes.get("data-ids", "")
            if not ep_num and not ep_ids:
                continue
            parent = anchor.parent
            title_span = parent.css_first("span.d-title") if parent else None
            title = title_span.text(strip=True) if title_span else ""
            if not title and parent and parent.attributes.get("title"):
                title = (
                    parent.attributes.get("title", "")
                    .split("Release:")[0]
                    .split("Softsub")[0]
                    .strip()
                )
            try:
                ep_number = float(ep_num)
            except ValueError:
                ep_number = 0.0
            episodes.append(
                Episode(
                    id=f"{ep_ids}&epurl={path}/episode/{ep_num}",
                    number=ep_number,
                    title=title or f"Episode {ep_num}",
                    has_sub=anchor.attributes.get("data-sub") == "1",
                    has_dub=anchor.attributes.get("data-dub") == "1",
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
        for type_div in HTMLParser(html_result).css("div.servers div.type[data-type]"):
            video_type = self._resolve_video_type(type_div.attributes.get("data-type", "").lower())
            for item in type_div.css("li"):
                if (server_id := item.attributes.get("data-link-id", "")) and (
                    raw_name := item.text(strip=True)
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
        epurl = self._episode_url_from_id(episode_id)
        embed_url = await self._get_embed_url(server_id, epurl)
        if not embed_url:
            return []

        extractor_cls = self.context.extractors.resolve(embed_url)
        extractor = extractor_cls(self.context)
        kwargs: dict[str, Any] = {"label_prefix": ""}
        if extractor.name == "Doodstream":
            kwargs["quality_prefix"] = kwargs.pop("label_prefix")
        elif extractor.name == "Byse":
            kwargs.update(embed_parent=f"{self.base_url}{epurl}", embed_origin=self.base_url)

        return await extractor.extract(embed_url, **kwargs)

    async def _get_embed_url(self, server_id: str, epurl: str) -> str | None:
        """Get an embed URL from an AniWaves server identifier."""
        if not server_id:
            return None
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
    def _episode_url_from_id(episode_id: str) -> str:
        """Extract the source-relative episode URL encoded in an episode ID."""
        marker = "&epurl="
        if marker not in episode_id:
            return ""
        return episode_id.split(marker, 1)[1].split("&", 1)[0]

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
