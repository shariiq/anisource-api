"""Abstract source contract.

Every anime source implements ``Source``.  The core module declares the
interface; concrete sources live under ``anime_extensions.sources.*`` and
never leak back into this layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .errors import UnsupportedCapabilityError
from .metadata import SourceCapability, SourceMetadata
from .models import Anime, Episode, Page, Server, Stream

if TYPE_CHECKING:
    from .runtime import SourceContext


class Source(ABC):
    """Contract that every anime source must fulfil.

    Concrete sources declare a class-level ``metadata`` describing their
    identity and capabilities.  The runtime reads this to build the
    public source registry without constructing an instance.

    All methods receive their ``SourceContext`` (and through it the
    ``HttpClient`` / ``ExtractorRegistry``) at ``__init__`` time, never
    as per-call arguments.
    """

    metadata: SourceMetadata

    def __init__(self, context: SourceContext) -> None:
        """Initialize the source with its execution context."""
        self.context = context

    def supports(self, capability: SourceCapability) -> bool:
        """Check if the source supports a specific operation."""
        return capability in self.metadata.capabilities

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        """Return a Page of anime for popular/trending.

        Raises UnsupportedCapabilityError if the source does not declare POPULAR.
        """
        raise UnsupportedCapabilityError(self.metadata.id, "POPULAR")

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        """Return a Page of anime for latest updates.

        Raises UnsupportedCapabilityError if the source does not declare LATEST.
        """
        raise UnsupportedCapabilityError(self.metadata.id, "LATEST")

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        """Search by *query*, returning a Page of anime."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Details & episodes
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_details(self, anime_id: str) -> Anime:
        """Full metadata for a single anime."""
        raise NotImplementedError

    @abstractmethod
    async def get_episodes(self, anime_id: str) -> list[Episode]:
        """Episode list for *anime_id*."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Servers & streams
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_servers(self, episode_id: str) -> list[Server]:
        """Streaming servers available for *episode_id*."""
        raise NotImplementedError

    @abstractmethod
    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        """Playable streams for the given server."""
        raise NotImplementedError
