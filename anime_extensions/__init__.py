"""
Anime Extensions - Minimal Python library for anime sources.
Designed as the data-layer for anime streaming apps.
"""

from .base import BaseExtractor, BaseSource
from .models import Anime, Episode, Server, Stream, Subtitle
from .sources import Anikoto, AniWaves, MKissa

__all__ = [
    "BaseExtractor",
    "BaseSource",
    "Anime",
    "Episode",
    "Server",
    "Stream",
    "Subtitle",
    "Anikoto",
    "AniWaves",
    "MKissa",
]

__version__ = "0.3.0"
