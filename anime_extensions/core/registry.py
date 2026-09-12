"""Registry system for sources and extractors.

The runtime owns `SourceRegistry` and `ExtractorRegistry` instances. Sources and
extractors are registered explicitly via catalogue-driven discovery in
`ExtensionRuntime._register_builtins()`, giving deterministic startup without global state.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from .errors import DuplicateSourceError, ExtractorError

if TYPE_CHECKING:
    from .extractor import Extractor
    from .source import Source

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------


class SourceRegistry:
    """A registry of available anime source plugins."""

    def __init__(self) -> None:
        self._sources: dict[str, type[Source]] = {}

    def register(self, cls: type[Source]) -> None:
        """Register a source class. The ID is taken from its metadata."""
        if not hasattr(cls, "metadata"):
            raise ValueError(f"Source {cls.__name__} missing 'metadata'")

        id_ = cls.metadata.id
        if id_ in self._sources:
            raise DuplicateSourceError(id_)

        self._sources[id_] = cls
        log.debug("Registered source %r", id_)

    def get(self, id_: str) -> type[Source] | None:
        return self._sources.get(id_)

    def list_all(self) -> list[type[Source]]:
        return list(self._sources.values())

    def __len__(self) -> int:
        return len(self._sources)


# ----------------------------------------------------------------------
# Extractors
# ----------------------------------------------------------------------

E = TypeVar("E", bound=type["Extractor"])


@dataclass(frozen=True, slots=True)
class ExtractorRegistration:
    cls: type[Extractor]
    pattern: re.Pattern[str]
    priority: int = 0


class ExtractorRegistry:
    """A registry of available video embed extractors."""

    def __init__(self) -> None:
        self._extractors: list[ExtractorRegistration] = []

    def register(
        self, cls: type[Extractor], pattern: str | re.Pattern[str], priority: int = 0
    ) -> None:
        """Register an extractor class to handle URLs matching *pattern*."""
        compiled = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
        self._extractors.append(ExtractorRegistration(cls, compiled, priority))
        # Keep the list sorted by priority (descending) so that resolve() can be linear.
        # The sort is stable, so equal-priority items retain registration order.
        self._extractors.sort(key=lambda r: r.priority, reverse=True)
        log.debug(
            "Registered extractor %r for pattern %r (priority %d)",
            cls.__name__,
            compiled.pattern,
            priority,
        )

    def resolve(self, url: str) -> type[Extractor]:
        """Find the Extractor class that handles *url*.

        Extractors are evaluated in descending priority order. Equal-priority
        matches retain registration (catalogue) order, so the first registered
        matching extractor is selected deterministically.

        Returns the highest-priority matching extractor. If multiple extractors
        share the highest priority, returns the first match by catalogue order.

        Raises:
            ExtractorError if no extractor matches *url*.
        """
        for reg in self._extractors:
            if reg.pattern.search(url):
                return reg.cls
        raise ExtractorError(f"No extractor found for URL: {url}")

    def __len__(self) -> int:
        return len(self._extractors)
