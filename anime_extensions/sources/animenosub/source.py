"""AnimeNoSub source implementation."""

from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from ...core.errors import ParsingError
from ...core.metadata import SourceCapability, SourceMetadata
from ...core.source import Source
from ...models import Anime, Episode, Page, Server, Stream


class AnimeNoSub(Source):
    """English AnimeNoSub source backed by the AnimeStream WordPress theme."""

    metadata = SourceMetadata(
        id="animenosub",
        name="AnimeNoSub",
        base_url="https://animenosub.to",
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
        domains=("animenosub.to",),
    )
    id = metadata.id
    base_url = metadata.base_url

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        html = await self.context.http.get(
            f"{self.base_url}/anime/", params={"page": page, "order": "popular"}
        )
        items, has_next = self._parse_listing(html)
        return Page(items=items, page=page, has_next=has_next)

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        html = await self.context.http.get(
            f"{self.base_url}/anime/", params={"page": page, "order": "update"}
        )
        items, has_next = self._parse_listing(html)
        return Page(items=items, page=page, has_next=has_next)

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        html = await self.context.http.get(f"{self.base_url}/page/{page}/", params={"s": query})
        items, has_next = self._parse_listing(html)
        return Page(items=items, page=page, has_next=has_next)

    def _parse_listing(self, html: str) -> tuple[list[Anime], bool]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[Anime] = []
        for anchor in soup.select("div.listupd article a.tip"):
            href = anchor.get("href", "")
            title_element = anchor.select_one("div.tt, div.ttl")
            title = title_element.get_text(" ", strip=True) if title_element else ""
            image = anchor.select_one("img")
            if not href or not title:
                continue
            items.append(
                Anime(
                    id=self._id_from_url(href),
                    title=title,
                    url=urljoin(self.base_url, href),
                    thumbnail=self._image_url(image),
                )
            )
        has_next = bool(soup.select_one("div.pagination a.next, div.hpage > a.r"))
        return items, has_next

    async def get_details(self, anime_id: str) -> Anime:
        path = self._anime_path(anime_id)
        url = urljoin(self.base_url, path)
        soup = BeautifulSoup(await self.context.http.get(url), "html.parser")
        title_el = soup.select_one("h1.entry-title")
        info = soup.select_one("div.info-content, div.right ul.data")
        if title_el is None or info is None:
            raise ParsingError(f"AnimeNoSub returned unusable details content for {anime_id}")
        image = soup.select_one("div.thumb > img, div.limage > img")
        alt = soup.select_one(".alter")
        description_nodes = soup.select(".entry-content[itemprop=description], .desc")
        status_text = self._info_value(info, "Status")
        status = "unknown"
        if status_text.lower() == "completed":
            status = "completed"
        elif status_text.lower() == "ongoing":
            status = "ongoing"
        genres = [item.get_text(" ", strip=True) for item in info.select("div.genxed > a")]
        if not genres:
            for item in info.select("li"):
                if "genre" in item.get_text(" ", strip=True).lower():
                    genres = [anchor.get_text(" ", strip=True) for anchor in item.select("a")]
                    break

        return Anime(
            id=self._id_from_url(url),
            title=title_el.get_text(" ", strip=True),
            url=url,
            thumbnail=self._image_url(image),
            description=description_nodes[-1].get_text(" ", strip=True)
            if description_nodes
            else "",
            genres=genres,
            studios=[value] if (value := self._info_value(info, "Studio")) else [],
            producers=[value] if (value := self._info_value(info, "Fansub")) else [],
            alternative_titles=[alt.get_text(" ", strip=True)] if alt else [],
            status=status,
        )

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        path = self._anime_path(anime_id)
        soup = BeautifulSoup(
            await self.context.http.get(urljoin(self.base_url, path)), "html.parser"
        )
        episodes: list[Episode] = []
        for anchor in soup.select("div.eplister > ul > li > a"):
            number_el = anchor.select_one(".epl-num")
            href = anchor.get("href", "")
            if not number_el or not href:
                continue
            number_text = number_el.get_text(" ", strip=True)
            match = re.search(r"\d+(?:\.\d+)?", number_text)
            number = float(match.group()) if match else 0.0
            title_el = anchor.select_one("div.epl-title")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            default = f"Ep. {number_text}"
            if title and f"Episode {number_text}".lower() not in title.lower():
                default = f"{default} {title}"
            scanlator_el = anchor.select_one(".epl-sub")
            date_el = anchor.select_one(".epl-date")
            released_at = self._parse_date(date_el.get_text(" ", strip=True)) if date_el else None
            episodes.append(
                Episode(
                    id=urljoin(self.base_url, href),
                    number=number,
                    title=default,
                    scanlator=scanlator_el.get_text(" ", strip=True) if scanlator_el else "",
                    has_sub=True,
                    released_at=released_at,
                )
            )
        return episodes

    async def get_servers(self, episode_id: str) -> list[Server]:
        soup = BeautifulSoup(await self.context.http.get(episode_id), "html.parser")
        servers: list[Server] = []
        for index, element in enumerate(
            soup.select("select.mirror > option[data-index], ul.mirror a[data-em]")
        ):
            encoded = element.get("value") if element.name == "option" else element.get("data-em")
            if not encoded:
                continue
            name = element.get_text(" ", strip=True) or f"Server {index + 1}"
            servers.append(Server(id=encoded, name=name, type="sub"))
        return servers

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        embed_url = await self._resolve_embed_url(server_id)
        extractor = self.context.extractors.resolve(embed_url)
        kwargs: dict[str, Any] = {"label_prefix": ""}
        if extractor.name == "Moon":
            kwargs["site_url"] = self.base_url
        elif extractor.name == "StreamWish":
            kwargs["headers"] = {"Referer": f"{self.base_url}/"}
        elif extractor.name == "Vtube":
            kwargs["base_url"] = self.base_url
        return await extractor.extract(embed_url, **kwargs)

    async def _resolve_embed_url(self, encoded: str) -> str:
        if encoded.startswith(("http://", "https://")):
            html = await self.context.http.get(encoded)
        else:
            try:
                html = base64.b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise ParsingError("AnimeNoSub returned an invalid encoded server") from exc
        soup = BeautifulSoup(html, "html.parser")
        frame = soup.select_one("iframe[src]")
        if frame and frame.get("src"):
            return urljoin(self.base_url, frame.get("src", ""))
        meta = soup.select_one("meta[itemprop=embedUrl][content]")
        if meta and meta.get("content"):
            return urljoin(self.base_url, meta.get("content", ""))
        if encoded.startswith(("http://", "https://")):
            parsed = urlparse(encoded)
            if parsed.scheme and parsed.netloc:
                return encoded
        raise ParsingError("AnimeNoSub server did not contain an embed URL")

    @staticmethod
    def _info_value(container: Tag, label: str) -> str:
        for item in container.select("div.spe > span, li:has(b)"):
            if label.lower() in item.get_text(" ", strip=True).lower():
                anchor = item.select_one("a")
                if anchor:
                    return anchor.get_text(" ", strip=True)
                text = item.get_text(" ", strip=True)
                return re.sub(rf"^{re.escape(label)}\s*:?\s*", "", text, flags=re.IGNORECASE)
        return ""

    def _image_url(self, image: Tag | None) -> str:
        """Extract image URL, resolving relative paths against base_url."""
        if image is None:
            return ""
        raw = (
            image.get("data-src")
            or image.get("data-lazy-src")
            or image.get("srcset", "").split(" ")[0]
            or image.get("src", "")
        ).split("?resize")[0]
        return urljoin(self.base_url, raw) if raw else ""

    @staticmethod
    def _id_from_url(url: str) -> str:
        return urlparse(url).path.strip("/")

    @staticmethod
    def _anime_path(anime_id: str) -> str:
        if anime_id.startswith(("http://", "https://")):
            return urlparse(anime_id).path
        return f"/{anime_id.strip('/')}"

    @staticmethod
    def _parse_date(text: str) -> datetime | None:
        """Parse episode date text like 'Dec 25, 2024' into datetime."""
        if not text:
            return None
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(text.strip(), fmt)
            except ValueError:
                continue
        return None
