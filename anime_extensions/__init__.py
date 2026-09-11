"""Anime Extensions - Python SDK and framework for anime sources and extractors."""

from .core import (
    Anime,
    Episode,
    ExtensionRuntime,
    Extractor,
    ExtractorRegistry,
    HttpClient,
    Server,
    Source,
    SourceCapability,
    SourceContext,
    SourceMetadata,
    SourceRegistry,
    Stream,
    Subtitle,
    register_extractor,
    register_source,
)
from .exceptions import (
    AnimeExtensionError,
    HttpError,
    ParsingError,
    TimeoutError,
    UpstreamNotFound,
    UpstreamRateLimited,
)
from .extractors import ByseExtractor, DoodExtractor, EchoVideoExtractor
from .sources import Anikoto, AniWaves, MKissa

__all__ = [
    "Anime",
    "AnimeExtensionError",
    "Anikoto",
    "AniWaves",
    "ByseExtractor",
    "DoodExtractor",
    "EchoVideoExtractor",
    "Episode",
    "ExtensionRuntime",
    "Extractor",
    "ExtractorRegistry",
    "HttpClient",
    "HttpError",
    "MKissa",
    "ParsingError",
    "Server",
    "Source",
    "SourceCapability",
    "SourceContext",
    "SourceMetadata",
    "SourceRegistry",
    "Stream",
    "Subtitle",
    "TimeoutError",
    "UpstreamNotFound",
    "UpstreamRateLimited",
    "register_extractor",
    "register_source",
]

__version__ = "0.3.0"
