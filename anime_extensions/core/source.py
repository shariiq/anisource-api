"""Abstract source contract.

Every anime source implements ``Source``.  The core module declares the
interface; concrete sources live under ``anime_extensions.sources.*`` and
never leak back into this layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .metadata import SourceMetadata
from .models import Anime, Episode, Server, Stream

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

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def get_popular(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Return (anime list, has_next_page) for popular/trending."""
        raise NotImplementedError

    async def get_latest(self, page: int = 1) -> tuple[list[Anime], bool]:
        """Return (anime list, has_next_page) for latest updates."""
        raise NotImplementedError

    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        """Search by *query*, returning (anime list, has_next_page)."""
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
