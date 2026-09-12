"""Execution runtime connecting the core components together.

``ExtensionRuntime`` is the composition root. It owns the ``HttpClient``
and the registries, and provides the dependency-injection mechanism
(``SourceContext``) for instantiation of sources and extractors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .http import HttpClient
from .registry import ExtractorRegistry, SourceRegistry

if TYPE_CHECKING:
    from .extractor import Extractor
    from .source import Source

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SourceContext:
    """The dependency container injected into concrete sources and extractors."""

    http: HttpClient
    extractors: ExtractorRegistry


class ExtensionRuntime:
    """The root runtime environment for anime extensions."""

    def __init__(
        self,
        *,
        http_client: HttpClient | None = None,
        source_registry: SourceRegistry | None = None,
        extractor_registry: ExtractorRegistry | None = None,
        load_builtins: bool = True,
    ) -> None:
        """Initialize the runtime.

        If registries are not provided, new empty registries are created.
        If load_builtins is True, built-in sources and extractors are registered.
        """
        self.http = http_client or HttpClient()
        self.sources = source_registry or SourceRegistry()
        self.extractors = extractor_registry or ExtractorRegistry()

        if load_builtins:
            self._register_builtins()

    def _register_builtins(self) -> None:
        """Explicitly register built-in sources and extractors from catalogues."""
        # Import catalogues (not at module level to avoid circular imports)
        from anime_extensions.extractors import BUILTIN_EXTRACTORS
        from anime_extensions.sources import BUILTIN_SOURCES

        # Register sources
        for source_cls in BUILTIN_SOURCES:
            self.sources.register(source_cls)

        # Register extractors with their patterns and priorities
        for extractor_cls, pattern, priority in BUILTIN_EXTRACTORS:
            self.extractors.register(extractor_cls, pattern, priority)

        log.info(
            "Registered %d sources and %d extractors",
            len(self.sources),
            len(self.extractors),
        )

    async def start(self) -> None:
        """Start the runtime (connects HTTP)."""
        await self.http.start()

    async def close(self) -> None:
        """Tear down the runtime (closes HTTP)."""
        await self.http.close()

    # Context manager support
    async def __aenter__(self) -> ExtensionRuntime:
        await self.start()
        return self

    async def __aexit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        await self.close()

    @property
    def context(self) -> SourceContext:
        """Build the injection context for sources/extractors."""
        return SourceContext(
            http=self.http,
            extractors=self.extractors,
        )

    def get_source(self, id_: str) -> Source | None:
        """Instantiate a source by ID with its context bound."""
        cls = self.sources.get(id_)
        if not cls:
            return None
        return cls(context=self.context)

    def resolve_extractor(self, url: str) -> Extractor:
        """Resolve a URL to a concrete extractor and instantiate it."""
        cls = self.extractors.resolve(url)
        return cls(context=self.context)
