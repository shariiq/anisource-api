"""Abstract video extractor contract.

Extractors resolve a specific hoster's embed URL into playable video
streams. Rather than hardcoding if/elif chains in sources, extractors
register the domain patterns they handle, and the runtime matches
URLs to extractors dynamically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from .models import Stream

if TYPE_CHECKING:
    from .runtime import SourceContext


class Extractor(ABC):
    """Contract that every video extractor must fulfil."""

    name: str

    def __init__(self, context: SourceContext) -> None:
        """Initialize the extractor with its execution context."""
        self.context = context

    @abstractmethod
    async def extract(self, url: str, **kwargs: Any) -> list[Stream]:
        """Extract video streams from the given embed *url*.

        Args:
            url: Hoster embed URL (e.g. from a server payload).
            **kwargs: Extra parameters like ``label_prefix`` or referer
                      from the calling source.
        Returns:
            List of playable streams with headers needed to access them.
        """
        raise NotImplementedError
