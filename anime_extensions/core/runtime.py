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
from .registry import _EXTRACTOR_REGISTRY, _SOURCE_REGISTRY, ExtractorRegistry, SourceRegistry

if TYPE_CHECKING:
    from .extractor import Extractor
    from .source import Source

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SourceContext:
    """The dependency container injected into concrete sources and extractors."""

    http: HttpClient
    extractors: ExtractorRegistry
    # We pass the runtime itself in case sources need to instantiate other components
    runtime: ExtensionRuntime


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

        If components are not provided, it registers the global defaults.
        """
        if load_builtins:
            self._load_builtins()

        self.http = http_client or HttpClient()
        self.sources = source_registry or _SOURCE_REGISTRY
        self.extractors = extractor_registry or _EXTRACTOR_REGISTRY

    @staticmethod
    def _load_builtins() -> None:
        """Import built-in sources and extractors to ensure decorator registration."""
        import anime_extensions.extractors  # noqa: F401
        import anime_extensions.sources  # noqa: F401

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
            runtime=self,
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
