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
)
from .exceptions import (
    AnimeExtensionError,
    HttpError,
    ParsingError,
    TimeoutError,
    UpstreamNotFound,
    UpstreamRateLimited,
)
from .extractors import (
    ByseExtractor,
    DoodExtractor,
    EchoVideoExtractor,
    MoonExtractor,
    StreamWishExtractor,
    VidMolyExtractor,
    VtubeExtractor,
    WolfStreamExtractor,
)
from .sources import Anikoto, AnimeNoSub, AniWaves, MKissa

__all__ = [
    "Anime",
    "AnimeExtensionError",
    "AnimeNoSub",
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
    "MoonExtractor",
    "ParsingError",
    "Server",
    "Source",
    "SourceCapability",
    "SourceContext",
    "SourceMetadata",
    "SourceRegistry",
    "Stream",
    "StreamWishExtractor",
    "Subtitle",
    "TimeoutError",
    "UpstreamNotFound",
    "UpstreamRateLimited",
    "VidMolyExtractor",
    "VtubeExtractor",
    "WolfStreamExtractor",
]

__version__ = "0.3.0"
