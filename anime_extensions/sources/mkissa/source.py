"""MKissa anime source implementation."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ...core.errors import CryptoError, ExtractorError, HttpError, ParsingError
from ...core.metadata import SourceCapability, SourceMetadata
from ...core.source import Source
from ...models import Anime, Episode, Page, Server, Stream, Subtitle
from ...utils.mkissa_crypto import MKissaCrypto
from .key_manager import MKissaKeyManager

if TYPE_CHECKING:
    from ...core.runtime import ExtensionContext

log = logging.getLogger(__name__)

STREAM_QUERY = """query(
    $showId: String!
    $translationType: VaildTranslationTypeEnumType!
    $episodeString: String!
) {
    episode(
        showId: $showId
        translationType: $translationType
        episodeString: $episodeString
    ) {
        sourceUrls
        show {
            _id
        }
    }
}"""
STREAM_HASH = MKissaCrypto.sha256_hex(STREAM_QUERY)
ANIME_LANE = "k7"
_PLAYER_DOMAIN = "https://allanime.day"
_INTERNAL_HOSTER_NAMES = (
    "Default",
    "Ac",
    "Ak",
    "Kir",
    "Rab",
    "Luf-mp4",
    "Si-Hls",
    "S-mp4",
    "Ac-Hls",
    "Uv-mp4",
    "Pn-Hls",
)
_INTERNAL_HOSTER_PATTERNS = tuple(
    (name, re.compile(rf"\b{re.escape(name.lower())}\b")) for name in _INTERNAL_HOSTER_NAMES
)


class MKissa(Source):
    """MKissa anime source."""

    metadata = SourceMetadata(
        id="mkissa",
        name="MKissa",
        base_url="https://mkissa.to",
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
        domains=("mkissa.to", "mkissa.net", "api.mkissa.net"),
    )
    id = metadata.id
    base_url = metadata.base_url
    api_url = "https://api.mkissa.net"

    def __init__(self, context: ExtensionContext) -> None:
        super().__init__(context)
        self.key_manager = MKissaKeyManager(
            http_client=context.http,
            site_url=self.base_url,
            api_url=self.api_url,
        )

    async def _get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Fetch JSON through the runtime-owned HTTP client."""
        return await self.context.http.get_json(url, headers=headers, params=params)

    async def _graphql_request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Make a GraphQL POST request to the MKissa API."""
        payload = {
            "query": query,
            "variables": variables,
        }
        headers = {
            "Accept": "*/*",
            "Origin": "https://youtu-chan.com",
            "Referer": "https://youtu-chan.com/",
        }

        data = await self.context.http.post_json(
            f"{self.api_url}/api", json_data=payload, headers=headers
        )
        if not isinstance(data, dict):
            raise ParsingError(f"MKissa: Expected dict response, got {type(data)}")

        if "errors" in data:
            raise ParsingError(f"MKissa: GraphQL errors in response: {data['errors']}")

        return data

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        """Fetch popular anime."""
        query = """
        query($type: VaildPopularTypeEnumType!, $size: Int!, $page: Int, $dateRange: Int) {
            queryPopular(type: $type, size: $size, dateRange: $dateRange, page: $page) {
                total
                recommendations {
                    anyCard {
                        _id
                        name
                        thumbnail
                        englishName
                        nativeName
                        slugTime
                    }
                }
            }
        }
        """
        variables = {
            "type": "anime",
            "size": 26,
            "dateRange": 7,
            "page": page,
        }

        data = await self._graphql_request(query, variables)
        result = data.get("data", {}).get("queryPopular", {})
        recommendations = result.get("recommendations", [])

        animes = [
            self._parse_anime(rec.get("anyCard", {}))
            for rec in recommendations
            if rec.get("anyCard")
        ]

        has_next = len(animes) == 26
        return Page(items=animes, page=page, has_next=has_next)

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        """Fetch latest updates."""
        query = """
        query($search: SearchInput, $limit: Int, $page: Int, $translationType: VaildTranslationTypeEnumType, $countryOrigin: VaildCountryOriginEnumType) {
            shows(search: $search, limit: $limit, page: $page, translationType: $translationType, countryOrigin: $countryOrigin) {
                pageInfo {
                    total
                }
                edges {
                    _id
                    name
                    thumbnail
                    englishName
                    nativeName
                    slugTime
                }
            }
        }
        """
        variables = {
            "search": {
                "allowAdult": True,
                "allowUnknown": True,
            },
            "limit": 26,
            "page": page,
            "translationType": "sub",
            "countryOrigin": "ALL",
        }

        data = await self._graphql_request(query, variables)
        result = data.get("data", {}).get("shows", {})
        edges = result.get("edges", [])

        animes = [self._parse_anime(edge) for edge in edges]

        has_next = len(animes) == 26
        return Page(items=animes, page=page, has_next=has_next)

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        """Search anime."""
        gql_query = """
        query($search: SearchInput, $limit: Int, $page: Int, $translationType: VaildTranslationTypeEnumType, $countryOrigin: VaildCountryOriginEnumType) {
            shows(search: $search, limit: $limit, page: $page, translationType: $translationType, countryOrigin: $countryOrigin) {
                pageInfo {
                    total
                }
                edges {
                    _id
                    name
                    thumbnail
                    englishName
                    nativeName
                    slugTime
                }
            }
        }
        """
        variables = {
            "search": {
                "query": query,
                "allowAdult": True,
                "allowUnknown": True,
            },
            "limit": 26,
            "page": page,
            "translationType": "sub",
            "countryOrigin": "ALL",
        }

        data = await self._graphql_request(gql_query, variables)
        result = data.get("data", {}).get("shows", {})
        edges = result.get("edges", [])

        animes = [self._parse_anime(edge) for edge in edges]

        has_next = len(animes) == 26
        return Page(items=animes, page=page, has_next=has_next)

    async def get_details(self, anime_id: str) -> Anime:
        """Get anime details."""
        query = """
        query($_id: String!) {
            show(_id: $_id) {
                name
                thumbnail
                description
                type
                season
                score
                genres
                status
                studios
            }
        }
        """
        variables = {"_id": anime_id}

        data = await self._graphql_request(query, variables)
        show = data.get("data", {}).get("show", {})

        studios = self._parse_studios(show.get("studios"))
        status = {
            "Releasing": "ongoing",
            "Finished": "completed",
            "Not Yet Released": "ongoing",
        }.get(str(show.get("status", "")), "unknown")
        genres = show.get("genres", [])

        return Anime(
            id=anime_id,
            title=str(show.get("name") or "Unknown"),
            url=anime_id,
            thumbnail=str(show.get("thumbnail") or ""),
            description=self._build_description(show),
            genres=[str(genre) for genre in genres] if isinstance(genres, list) else [],
            studios=studios,
            status=status,
        )

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        """Get episode list."""
        query = """
        query($_id: String!) {
            show(_id: $_id) {
                _id
                availableEpisodesDetail
            }
        }
        """
        variables = {"_id": anime_id}

        data = await self._graphql_request(query, variables)
        show = data.get("data", {}).get("show", {})

        eps_detail = show.get("availableEpisodesDetail", {})
        if isinstance(eps_detail, str):
            try:
                eps_detail = json.loads(eps_detail)
            except json.JSONDecodeError:
                eps_detail = {}
        if not isinstance(eps_detail, dict):
            return []

        show_id = show.get("_id")
        if not isinstance(show_id, str) or not show_id:
            return []

        episodes: list[Episode] = []
        for translation_type in ("sub", "dub"):
            episode_strings = eps_detail.get(translation_type, [])
            if not isinstance(episode_strings, list):
                continue
            for episode_string in episode_strings:
                if not isinstance(episode_string, str) or not episode_string:
                    continue
                try:
                    number = float(episode_string)
                except ValueError:
                    number = 0.0
                episode_id = json.dumps(
                    {
                        "variables": {
                            "showId": show_id,
                            "translationType": translation_type,
                            "episodeString": episode_string,
                        }
                    },
                    separators=(",", ":"),
                )
                episodes.append(
                    Episode(
                        id=episode_id,
                        number=number,
                        title=f"Episode {episode_string} ({translation_type})",
                        has_sub=translation_type == "sub",
                        has_dub=translation_type == "dub",
                        scanlator="MKissa",
                    )
                )

        # Sort descending
        episodes.sort(key=lambda e: e.number, reverse=True)
        return episodes

    async def get_servers(self, episode_id: str) -> list[Server]:
        """Get available servers (MKissa usually provides a single internal source)."""
        return [Server(id="default", name="Default", type="sub")]

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Extract streams from MKissa's encrypted persisted-query endpoint."""
        del server_id  # MKissa has one logical server for each episode.
        try:
            ep_data = json.loads(episode_id)
            variables = ep_data["variables"]
            show_id = variables["showId"]
            translation_type = variables["translationType"]
            episode_string = variables["episodeString"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ParsingError(f"MKissa: invalid episode identifier: {e}") from e

        if not all(
            isinstance(value, str) and value
            for value in (show_id, translation_type, episode_string)
        ):
            raise ParsingError("MKissa: missing or empty required parameters in episode identifier")

        variables = {
            "showId": show_id,
            "translationType": translation_type,
            "episodeString": episode_string,
        }

        last_error = None
        for attempt in range(2):
            try:
                material = await self.key_manager.get_material(force_refresh=attempt > 0)
                body = await self._get_stream_response(material, variables)
                source_urls = self._source_urls_from_response(body, material.key)
                streams = await self._streams_from_sources(source_urls)
                if streams:
                    return streams
                message = self.key_manager.api_error_message(body)
                if message:
                    raise ParsingError(f"MKissa API blocked: {message}")
            except (
                CryptoError,
                HttpError,
                ParsingError,
                json.JSONDecodeError,
                ValueError,
            ) as error:
                last_error = error
                log.warning("MKissa stream attempt %s failed: %s", attempt + 1, error)

            self.key_manager.invalidate()
            if attempt == 0:
                self.key_manager.invalidate_build()

        if last_error is not None:
            raise last_error

        return []

    async def _get_stream_response(self, material: Any, variables: dict[str, str]) -> str:
        """Request MKissa's APQ stream endpoint with fresh crypto metadata."""
        aa_req = MKissaCrypto.build_aa_req(
            key=material.key,
            epoch=material.epoch,
            build_id=material.build_id,
            query_hash=STREAM_HASH,
            lane=ANIME_LANE,
        )
        params = {
            "query": STREAM_QUERY,
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(
                {
                    "persistedQuery": {"version": 1, "sha256Hash": STREAM_HASH},
                    "k": ANIME_LANE,
                    "aaReq": aa_req,
                },
                separators=(",", ":"),
            ),
        }
        headers = {
            "x-build-id": material.build_id,
            "Referer": f"{self.base_url}/",
        }
        try:
            return await self.context.http.get(
                f"{self.api_url}/api",
                params=params,
                headers=headers,
            )
        except TimeoutError as error:
            raise HttpError(
                "MKissa stream request timed out after 30s",
                status_code=504,
            ) from error

    @staticmethod
    def _source_urls_from_response(body: str, key: bytes) -> list[dict[str, Any]]:
        """Decode encrypted or direct stream data from a GraphQL response."""
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as error:
            decrypted = MKissaCrypto.decrypt(body, key)
            if decrypted is None:
                raise ParsingError("MKissa returned an invalid encrypted response") from error
            envelope = json.loads(decrypted)

        data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
        encrypted = data.get("tobeparsed") if isinstance(data, dict) else None
        if isinstance(encrypted, str):
            decrypted = MKissaCrypto.decrypt(encrypted, key)
            if decrypted is None:
                raise CryptoError("MKissa stream response could not be decrypted")
            try:
                envelope = json.loads(decrypted)
            except json.JSONDecodeError as error:
                raise ParsingError("MKissa decrypted stream response is invalid JSON") from error
            data = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope

        episode = data.get("episode", {}) if isinstance(data, dict) else {}
        source_urls = episode.get("sourceUrls", []) if isinstance(episode, dict) else []
        return source_urls if isinstance(source_urls, list) else []

    async def _streams_from_sources(self, source_urls: list[dict[str, Any]]) -> list[Stream]:
        """Resolve direct, internal-player, and supported external MKissa sources."""
        streams: list[tuple[float, Stream]] = []
        for source in source_urls:
            if not isinstance(source, dict):
                continue

            source_url = MKissaCrypto.decrypt_source_url(str(source.get("sourceUrl", "")))
            source_name = str(source.get("sourceName") or "Unknown")
            priority = self._source_priority(source.get("priority"))

            if source_url.startswith("//"):
                source_url = f"https:{source_url}"

            if source_url.startswith("/apivtwo/") and self._is_internal_hoster(source_name):
                streams.extend(
                    (priority, stream)
                    for stream in await self._extract_internal_source(source_url, source_name)
                )
                continue

            # Attempt to resolve using registered extractors
            try:
                extractor_cls = self.context.extractors.resolve(source_url)
                extractor = extractor_cls(self.context)
            except ExtractorError:
                extractor = None

            if extractor is not None:
                try:
                    extracted = await extractor.extract(
                        source_url,
                        label_prefix=source_name,
                        quality_prefix=source_name,
                        embed_parent=f"{self.base_url}/",
                        embed_origin=f"{self.base_url}/",
                    )
                    if extracted:
                        streams.extend((priority, stream) for stream in extracted)
                        continue
                except Exception as error:
                    log.warning(
                        "MKissa: failed to extract %s via %s: %s",
                        source_url,
                        extractor.name,
                        error,
                    )

            # Fallback to direct stream
            stream = self._direct_stream(source_url, source_name, priority)
            if stream is not None:
                streams.append((priority, stream))

        streams.sort(key=lambda item: item[0], reverse=True)
        return [stream for _, stream in streams]

    def _direct_stream(self, url: str, name: str, priority: float) -> Stream | None:
        if url.startswith("//"):
            url = f"https:{url}"
        if not url.startswith(("http://", "https://")):
            return None
        return Stream(
            url=url,
            quality=f"{name} - {priority:g}",
            headers={"Referer": f"{self.base_url}/"},
            is_hls=".m3u8" in url or "/clock" in url,
        )

    async def _extract_internal_source(self, path: str, name: str) -> list[Stream]:
        endpoint = f"{_PLAYER_DOMAIN}{path.replace('/clock?', '/clock.json?', 1)}"
        try:
            response = await self._get_json(endpoint, headers={"Referer": f"{_PLAYER_DOMAIN}/"})
        except (HttpError, ParsingError) as error:
            log.warning("MKissa internal source %s failed: %s", name, error)
            return []
        if not isinstance(response, Mapping):
            return []

        streams: list[Stream] = []
        links = response.get("links", [])
        if not isinstance(links, list):
            return streams
        for link in links:
            if not isinstance(link, Mapping):
                continue
            subtitles = self._parse_subtitles(link.get("subtitles"))
            resolution = str(link.get("resolutionStr") or "Unknown")
            url = link.get("link")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            if link.get("mp4") is True:
                streams.append(
                    Stream(
                        url=url, quality=f"Original ({name} - {resolution})", subtitles=subtitles
                    )
                )
            elif link.get("hls") is True:
                streams.append(
                    Stream(
                        url=url,
                        quality=f"HLS ({name} - {resolution})",
                        headers=self._player_headers(url),
                        subtitles=subtitles,
                        is_hls=True,
                    )
                )
            elif link.get("dash") is True:
                streams.extend(self._dash_streams(link, name, subtitles))
            elif link.get("crIframe") is True:
                streams.extend(self._cr_iframe_streams(link, subtitles))
        return streams

    @staticmethod
    def _source_priority(value: object) -> float:
        try:
            return float(value)
        except TypeError, ValueError:
            return 0.0

    @staticmethod
    def _is_internal_hoster(source_name: str) -> bool:
        normalized = source_name.lower()
        return any(pattern.search(normalized) for _, pattern in _INTERNAL_HOSTER_PATTERNS)

    @staticmethod
    def _parse_subtitles(value: object) -> list[Subtitle]:
        if not isinstance(value, list):
            return []
        subtitles: list[Subtitle] = []
        for subtitle in value:
            if not isinstance(subtitle, Mapping):
                continue
            url = subtitle.get("src")
            language = subtitle.get("lang")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                subtitles.append(
                    Subtitle(
                        url=url,
                        label=str(subtitle.get("label") or ""),
                        language=str(language or ""),
                    )
                )
        return subtitles

    @staticmethod
    def _player_headers(url: str) -> dict[str, str]:
        host = urlparse(url).netloc
        return {
            "Accept": "*/*",
            "Host": host,
            "Origin": _PLAYER_DOMAIN,
            "Referer": f"{_PLAYER_DOMAIN}/",
        }

    @staticmethod
    def _dash_streams(
        link: Mapping[str, object], name: str, subtitles: list[Subtitle]
    ) -> list[Stream]:
        raw_urls = link.get("rawUrls")
        if not isinstance(raw_urls, Mapping):
            return []
        streams: list[Stream] = []
        for video in raw_urls.get("vids", []):
            if not isinstance(video, Mapping):
                continue
            url = video.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            height = video.get("height")
            streams.append(
                Stream(
                    url=url,
                    quality=f"{name} - {height or 'DASH'}",
                    headers={"Accept": "*/*"},
                    subtitles=subtitles,
                )
            )
        return streams

    @staticmethod
    def _cr_iframe_streams(link: Mapping[str, object], subtitles: list[Subtitle]) -> list[Stream]:
        port_data = link.get("portData")
        streams_data = port_data.get("streams", []) if isinstance(port_data, Mapping) else []
        if not isinstance(streams_data, list):
            return []
        streams: list[Stream] = []
        for stream in streams_data:
            if not isinstance(stream, Mapping):
                continue
            url = stream.get("url")
            format_name = stream.get("format")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            if format_name == "adaptive_dash":
                streams.append(
                    Stream(
                        url=url,
                        quality="Original (AC - DASH)",
                        subtitles=subtitles,
                    )
                )
            elif format_name == "adaptive_hls":
                streams.append(
                    Stream(
                        url=url,
                        quality="Original (AC - HLS)",
                        headers={"Referer": f"{_PLAYER_DOMAIN}/"},
                        subtitles=subtitles,
                        is_hls=True,
                    )
                )
        return streams

    @staticmethod
    def _parse_studios(value: object) -> list[str]:
        if isinstance(value, list):
            return [studio for item in value if (studio := str(item))]
        if not isinstance(value, Mapping):
            return []
        edges = value.get("edges", [])
        if not isinstance(edges, list):
            return []
        studios: list[str] = []
        for edge in edges:
            if not isinstance(edge, Mapping) or not edge.get("isMain"):
                continue
            node = edge.get("node")
            if isinstance(node, Mapping) and isinstance(name := node.get("name"), str) and name:
                studios.append(name)
        return studios

    @staticmethod
    def _build_description(show: Mapping[str, object]) -> str:
        raw_description = show.get("description")
        description = ""
        if isinstance(raw_description, str):
            description = BeautifulSoup(raw_description.replace("<br>", "\n"), "lxml").get_text()
        season = show.get("season") or "-"
        if isinstance(season, Mapping):
            season = (
                " ".join(str(part) for part in (season.get("quarter"), season.get("year")) if part)
                or "-"
            )
        score = show.get("score") or "-"
        return f"{description}\n\nType: {show.get('type') or 'Unknown'}\nAired: {season}\nScore: {score}★"

    def _parse_anime(self, media: dict) -> Anime:
        """Parse media object into Anime model."""
        anime_id = media.get("_id", "")
        title_obj = media.get("name", "")
        if isinstance(title_obj, dict):
            title = (
                title_obj.get("userPreferred")
                or title_obj.get("romaji")
                or title_obj.get("english")
                or "Unknown"
            )
        else:
            title = title_obj

        thumbnail = media.get("thumbnail", "")

        return Anime(
            id=anime_id,
            title=title,
            url=anime_id,
            thumbnail=thumbnail,
        )
