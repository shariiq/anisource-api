"""Module registration system for sources and extractors.

Extensions declare themselves using the decorators here. This explicit
registration gives deterministic startup over fragile dynamic imports.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from .errors import ExtractorError

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
            log.warning("Overwriting registered source %r with %r", id_, cls)

        self._sources[id_] = cls
        log.debug("Registered source %r", id_)

    def get(self, id_: str) -> type[Source] | None:
        return self._sources.get(id_)

    def list_all(self) -> list[type[Source]]:
        return list(self._sources.values())


# Global singleton purely for decorator-based registration
_SOURCE_REGISTRY = SourceRegistry()


def register_source[S: Source](cls: S) -> S:
    """Class decorator to register a concrete Source."""
    _SOURCE_REGISTRY.register(cls)
    return cls


# ----------------------------------------------------------------------
# Extractors
# ----------------------------------------------------------------------

E = TypeVar("E", bound=type["Extractor"])


class ExtractorRegistration:
    def __init__(self, cls: type[Extractor], pattern: re.Pattern[str]) -> None:
        self.cls = cls
        self.pattern = pattern


class ExtractorRegistry:
    """A registry of available video embed extractors."""

    def __init__(self) -> None:
        self._extractors: list[ExtractorRegistration] = []

    def register(self, cls: type[Extractor], pattern: str | re.Pattern[str]) -> None:
        """Register an extractor class to handle URLs matching *pattern*."""
        compiled = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
        self._extractors.append(ExtractorRegistration(cls, compiled))
        log.debug("Registered extractor %r for pattern %r", cls.__name__, compiled.pattern)

    def resolve(self, url: str) -> type[Extractor]:
        """Find the exact Extractor class that handles *url*.

        Raises:
            ExtractorError if no extractor matches, or multiple match.
        """
        matches = [reg.cls for reg in self._extractors if reg.pattern.search(url)]
        if not matches:
            raise ExtractorError(f"No extractor found for URL: {url}")

        # We allow exactly one match or pick the first if deliberately chained.
        # For our architecture, picking the first registered match is correct.
        return matches[0]


_EXTRACTOR_REGISTRY = ExtractorRegistry()


def register_extractor(pattern: str) -> Callable[[E], E]:
    """Class decorator to register a concrete Extractor by regex pattern."""

    def decorator(cls: E) -> E:
        _EXTRACTOR_REGISTRY.register(cls, pattern)
        return cls

    return decorator
