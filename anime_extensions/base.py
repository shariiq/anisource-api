"""Base abstractions for anime sources and video extractors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

import aiohttp

from .models import Anime, Episode, Server, Stream
from .exceptions import HttpError, ParsingError

log = logging.getLogger(__name__)


class BaseSource(ABC):
    """Abstract base class for anime sources.

    All sources must inherit from this and implement the abstract methods.
    """

    name: str
    id: str
    base_url: str

    def __init__(self, *, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._own_session = session is None
        self._headers: dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        self._extractors: dict[type[BaseExtractor], BaseExtractor] = {}

    async def _get_extractor(self, extractor_cls: type[BaseExtractor]) -> BaseExtractor:
        """Return a cached extractor instance or create a new one."""
        if extractor_cls not in self._extractors:
            session = await self._ensure_session()
            self._extractors[extractor_cls] = extractor_cls(session=session)
        return self._extractors[extractor_cls]

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure an active aiohttp session exists."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=self._headers,
            )
        return self._session

    async def __aenter__(self) -> BaseSource:
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> str:
        """Make a GET request and return the body. Raises HttpError on failure."""
        session = await self._ensure_session()
        final_headers = dict(self._headers)
        if headers:
            final_headers.update(headers)

        async with session.get(url, headers=final_headers, params=params) as response:
            if response.status < 200 or response.status >= 300:
                raise HttpError(f"GET {url} failed with status {response.status}", status_code=response.status)

            body = await response.text(errors="replace")
            return body

    async def _get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Make a GET request expecting a JSON response. Raises HttpError on failure."""
        session = await self._ensure_session()
        final_headers = dict(self._headers)
        if headers:
            final_headers.update(headers)

        async with session.get(url, headers=final_headers, params=params) as response:
            if response.status < 200 or response.status >= 300:
                raise HttpError(f"GET JSON {url} failed with status {response.status}", status_code=response.status)
            try:
                data = await response.json(content_type=None)
            except Exception:
                raise ParsingError(f"Failed to decode JSON response from {url}")
            return data

    async def _post_json(
        self,
        url: str,
        *,
        json_data: Any = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Make a POST request with JSON payload expecting a JSON response. Raises HttpError on failure."""
        session = await self._ensure_session()
        final_headers = dict(self._headers)
        if headers:
            final_headers.update(headers)

        async with session.post(
            url,
            json=json_data,
            headers=final_headers,
            params=params,
        ) as response:
            if response.status < 200 or response.status >= 300:
                raise HttpError(f"POST JSON {url} failed with status {response.status}", status_code=response.status)
            try:
                data = await response.json(content_type=None)
            except Exception:
                raise ParsingError(f"Failed to decode JSON response from {url}")
            return data

    # === Abstract Methods ===

    @abstractmethod
    async def get_popular(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch popular anime listing.

        Returns:
            Tuple of (anime list, has_next_page)
        """
        raise NotImplementedError

    @abstractmethod
    async def get_latest(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Fetch latest updated anime listing.

        Returns:
            Tuple of (anime list, has_next_page)
        """
        raise NotImplementedError

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        """Search anime by query.

        Returns:
            Tuple of (anime list, has_next_page)
        """
        raise NotImplementedError

    @abstractmethod
    async def get_details(self, anime_id: str) -> Anime:
        """Get full details for an anime."""
        raise NotImplementedError

    @abstractmethod
    async def get_episodes(self, anime_id: str) -> list[Episode]:
        """Get episode list for an anime."""
        raise NotImplementedError

    @abstractmethod
    async def get_servers(self, episode_id: str) -> list[Server]:
        """Get available streaming servers for an episode."""
        raise NotImplementedError

    @abstractmethod
    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Extract playable streams from a server.

        Args:
            episode_id: The episode identifier (needed for referer)
            server_id: The server identifier to extract streams from
        """
        raise NotImplementedError


class BaseExtractor(ABC):
    """Abstract base class for video hoster extractors (e.g. Dood, Byse, EchoVideo)."""

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._own_session = session is None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure an active aiohttp session exists."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def __aenter__(self) -> BaseExtractor:
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @abstractmethod
    async def extract(self, url: str, **kwargs: Any) -> list[Stream]:
        """Extract video streams from the given embed URL."""
        raise NotImplementedError
