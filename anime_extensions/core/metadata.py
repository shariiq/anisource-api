"""Source metadata and capability declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceCapability(StrEnum):
    """Operations a source can declare support for."""

    POPULAR = "popular"
    LATEST = "latest"
    SEARCH = "search"
    DETAILS = "details"
    EPISODES = "episodes"
    SERVERS = "servers"
    STREAMS = "streams"
    FILTERS = "filters"


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """Immutable identity and capability descriptor for a source.

    Each source declares exactly one ``SourceMetadata`` as a class-level
    constant. The runtime reads it to build the public registry and to
    validate capability queries without constructing an instance.
    """

    id: str
    name: str
    base_url: str
    language: str = "en"
    capabilities: frozenset[SourceCapability] = field(
        default_factory=lambda: frozenset(
            {
                SourceCapability.SEARCH,
                SourceCapability.DETAILS,
                SourceCapability.EPISODES,
                SourceCapability.SERVERS,
                SourceCapability.STREAMS,
            }
        )
    )
    domains: tuple[str, ...] = ()
