"""AnimeNoSub source implementation."""

from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser, Node

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
        tree = HTMLParser(html)
        items: list[Anime] = []
        for anchor in tree.css("div.listupd article a.tip"):
            href = anchor.attributes.get("href", "")
            title_element = anchor.css_first("div.tt, div.ttl")
            title = title_element.text(separator=" ", strip=True) if title_element else ""
            image = anchor.css_first("img")
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
        has_next = bool(tree.css_first("div.pagination a.next, div.hpage > a.r"))
        return items, has_next

    async def get_details(self, anime_id: str) -> Anime:
        path = self._anime_path(anime_id)
        url = urljoin(self.base_url, path)
        tree = HTMLParser(await self.context.http.get(url))
        title_el = tree.css_first("h1.entry-title")
        info = tree.css_first("div.info-content, div.right ul.data")
        if title_el is None or info is None:
            raise ParsingError(f"AnimeNoSub returned unusable details content for {anime_id}")
        image = tree.css_first("div.thumb > img, div.limage > img")
        alt = tree.css_first(".alter")
        description_nodes = tree.css(".entry-content[itemprop=description], .desc")

        info_dict = self._parse_info(info)
        status_text = info_dict.get("status", "")
        status = "unknown"
        if status_text.lower() == "completed":
            status = "completed"
        elif status_text.lower() == "ongoing":
            status = "ongoing"
        genres = [item.text(separator=" ", strip=True) for item in info.css("div.genxed > a")]
        if not genres:
            for item in info.css("li"):
                if "genre" in item.text(separator=" ", strip=True).lower():
                    genres = [anchor.text(separator=" ", strip=True) for anchor in item.css("a")]
                    break

        return Anime(
            id=self._id_from_url(url),
            title=title_el.text(separator=" ", strip=True),
            url=url,
            thumbnail=self._image_url(image),
            description=description_nodes[-1].text(separator=" ", strip=True)
            if description_nodes
            else "",
            genres=genres,
            studios=[info_dict["studio"]] if "studio" in info_dict else [],
            producers=[info_dict["fansub"]] if "fansub" in info_dict else [],
            alternative_titles=[alt.text(separator=" ", strip=True)] if alt else [],
            status=status,
        )

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        path = self._anime_path(anime_id)
        tree = HTMLParser(await self.context.http.get(urljoin(self.base_url, path)))
        episodes: list[Episode] = []
        for anchor in tree.css("div.eplister > ul > li > a"):
            number_el = anchor.css_first(".epl-num")
            href = anchor.attributes.get("href", "")
            if not number_el or not href:
                continue
            number_text = number_el.text(separator=" ", strip=True)
            match = re.search(r"\d+(?:\.\d+)?", number_text)
            number = float(match.group()) if match else 0.0
            title_el = anchor.css_first("div.epl-title")
            title = title_el.text(separator=" ", strip=True) if title_el else ""
            default = f"Ep. {number_text}"
            if title and f"Episode {number_text}".lower() not in title.lower():
                default = f"{default} {title}"
            scanlator_el = anchor.css_first(".epl-sub")
            date_el = anchor.css_first(".epl-date")
            released_at = (
                self._parse_date(date_el.text(separator=" ", strip=True)) if date_el else None
            )
            episodes.append(
                Episode(
                    id=urljoin(self.base_url, href),
                    number=number,
                    title=default,
                    scanlator=scanlator_el.text(separator=" ", strip=True) if scanlator_el else "",
                    has_sub=True,
                    released_at=released_at,
                )
            )
        return episodes

    async def get_servers(self, episode_id: str) -> list[Server]:
        tree = HTMLParser(await self.context.http.get(episode_id))
        servers: list[Server] = []
        for index, element in enumerate(
            tree.css("select.mirror > option[data-index], ul.mirror a[data-em]")
        ):
            encoded = (
                element.attributes.get("value")
                if element.tag == "option"
                else element.attributes.get("data-em")
            )
            if not encoded:
                continue
            name = element.text(separator=" ", strip=True) or f"Server {index + 1}"
            servers.append(Server(id=encoded, name=name, type="sub"))
        return servers

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        embed_url = await self._resolve_embed_url(server_id)
        extractor_cls = self.context.extractors.resolve(embed_url)
        extractor = extractor_cls(self.context)
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
        tree = HTMLParser(html)
        frame = tree.css_first("iframe[src]")
        if frame and frame.attributes.get("src"):
            return urljoin(self.base_url, frame.attributes.get("src", ""))
        meta = tree.css_first("meta[itemprop=embedUrl][content]")
        if meta and meta.attributes.get("content"):
            return urljoin(self.base_url, meta.attributes.get("content", ""))
        if encoded.startswith(("http://", "https://")):
            parsed = urlparse(encoded)
            if parsed.scheme and parsed.netloc:
                return encoded
        raise ParsingError("AnimeNoSub server did not contain an embed URL")

    @staticmethod
    def _parse_info(container: Node) -> dict[str, str]:
        info: dict[str, str] = {}
        for item in container.css("div.spe > span, li"):
            if item.tag == "li" and not item.css_first("b"):
                continue
            b_tag = item.css_first("b")
            anchor = item.css_first("a")
            if b_tag:
                b_text = b_tag.text(strip=True)
                key = b_text.rstrip(":").strip().lower()
                if anchor:
                    val = anchor.text(separator=" ", strip=True)
                else:
                    full_text = item.text(separator=" ", strip=True)
                    val = re.sub(
                        rf"^{re.escape(b_text)}\s*:?\s*",
                        "",
                        full_text,
                        flags=re.IGNORECASE,
                    )
                info[key] = val
            else:
                full_text = item.text(separator=" ", strip=True)
                if ":" in full_text:
                    label, rest = full_text.split(":", 1)
                    key = label.strip().lower()
                    val = anchor.text(separator=" ", strip=True) if anchor else rest.strip()
                    info[key] = val
        return info

    def _image_url(self, image: Node | None) -> str:
        """Extract image URL, resolving relative paths against base_url."""
        if image is None:
            return ""
        raw = (
            image.attributes.get("data-src")
            or image.attributes.get("data-lazy-src")
            or image.attributes.get("srcset", "").split(" ")[0]
            or image.attributes.get("src", "")
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
