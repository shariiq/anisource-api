"""Lifecycle manager for anime scraping sources."""

from __future__ import annotations

import logging

from anime_extensions.core.runtime import ExtensionRuntime
from anime_extensions.core.source import Source
from anime_extensions.exceptions import AnimeExtensionError

log = logging.getLogger(__name__)


class SourceNotFoundError(AnimeExtensionError):
    """Exception raised when an invalid source ID is requested."""

    def __init__(self, source_id: str) -> None:
        super().__init__(f"Source '{source_id}' not found or unsupported.")


class SourceManager:
    """Centralized registry and lifecycle manager for anime sources.

    Wraps ExtensionRuntime to provide clean API-layer access to sources
    with proper HTTP client lifecycle management.
    """

    def __init__(self) -> None:
        self._runtime: ExtensionRuntime | None = None

    async def initialize(self) -> None:
        """Initialize the extension runtime and all registered sources."""
        log.info("Initializing SourceManager and ExtensionRuntime...")
        self._runtime = ExtensionRuntime()
        await self._runtime.start()
        log.info(
            "Successfully registered sources: %s",
            [source.metadata.id for source in self._runtime.sources.list_all()],
        )

    async def close(self) -> None:
        """Gracefully close the runtime and release resources."""
        log.info("Shutting down SourceManager...")
        if self._runtime:
            await self._runtime.close()
            self._runtime = None
        log.info("SourceManager shutdown complete.")

    def get_source(self, source_id: str) -> Source:
        """Retrieve a source instance by its ID.

        Raises:
            SourceNotFoundError if the source is not registered.
        """
        if not self._runtime:
            raise AnimeExtensionError("SourceManager not initialized")

        source = self._runtime.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source

    def list_sources(self) -> list[Source]:
        """Return all registered source instances."""
        if not self._runtime:
            raise AnimeExtensionError("SourceManager not initialized")
        return [
            source_cls(context=self._runtime.context)
            for source_cls in self._runtime.sources.list_all()
        ]
