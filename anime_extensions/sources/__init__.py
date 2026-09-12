"""Built-in anime source implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anime_extensions.core.source import Source

from .anikoto import Anikoto
from .animenosub import AnimeNoSub
from .aniwaves import AniWaves
from .mkissa import MKissa

# Explicit catalogue of built-in sources for runtime registration
BUILTIN_SOURCES: tuple[type[Source], ...] = (
    AniWaves,
    Anikoto,
    AnimeNoSub,
    MKissa,
)

__all__ = ["Anikoto", "AnimeNoSub", "AniWaves", "MKissa", "BUILTIN_SOURCES"]
