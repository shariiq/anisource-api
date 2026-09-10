"""Lifecycle manager for anime scraping sources."""

from __future__ import annotations

import logging

import aiohttp

from anime_extensions import Anikoto, AniWaves
from anime_extensions.base import BaseSource
from anime_extensions.exceptions import AnimeExtensionError

log = logging.getLogger(__name__)


class SourceNotFoundError(AnimeExtensionError):
    """Exception raised when an invalid source ID is requested."""

    def __init__(self, source_id: str) -> None:
        super().__init__(f"Source '{source_id}' not found or unsupported.")


class SourceManager:
    """Centralized registry and session manager for anime sources.

    Maintains a core aiohttp ClientSession and ensures all sources
    route requests through it to pool connections and avoid exhaustion.
    """

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._registry: dict[str, BaseSource] = {}

    async def initialize(self) -> None:
        """Initialize the shared aiohttp session and instantiate all sources."""
        log.info("Initializing SourceManager and connection pools...")
        if self._session is None or self._session.closed:
            # Custom TCPConnector for performance and disabling SSL verify broadly (like the base classes)
            connector = aiohttp.TCPConnector(ssl=False, limit=100)
            timeout = aiohttp.ClientTimeout(total=45)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )

        # Register known sources
        aniwaves = AniWaves(session=self._session)
        anikoto = Anikoto(session=self._session)

        # Initialize internal state if needed
        await aniwaves._ensure_session()
        await anikoto._ensure_session()

        self._registry[aniwaves.id] = aniwaves
        self._registry[anikoto.id] = anikoto

        log.info(f"Successfully registered sources: {list(self._registry.keys())}")

    async def close(self) -> None:
        """Gracefully close the shared session."""
        log.info("Shutting down SourceManager...")
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._registry.clear()
        log.info("SourceManager shutdown complete.")

    def get_source(self, source_id: str) -> BaseSource:
        """Retrieve a source instance by its ID.

        Raises:
            SourceNotFoundError if the source is not registered.
        """
        source = self._registry.get(source_id.lower())
        if not source:
            raise SourceNotFoundError(source_id)
        return source

    def list_sources(self) -> list[BaseSource]:
        """Return all registered source instances."""
        return list(self._registry.values())


# Global singleton manager for the FastAPI app
source_manager = SourceManager()
