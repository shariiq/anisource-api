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
    CryptoError,
    ExtractorError,
    HttpError,
    ParsingError,
    SourceError,
    SourceNotFoundError,
    TimeoutError,
    UnsupportedCapabilityError,
    UpstreamNotFound,
    UpstreamRateLimited,
    UpstreamUnavailable,
)

__all__ = [
    # Core models
    "Anime",
    "Episode",
    "Server",
    "Stream",
    "Subtitle",
    # Runtime
    "ExtensionRuntime",
    "SourceContext",
    # Registry
    "ExtractorRegistry",
    "SourceRegistry",
    # HTTP
    "HttpClient",
    # Extractor
    "Extractor",
    # Source
    "Source",
    # Metadata
    "SourceMetadata",
    "SourceCapability",
    # Exceptions
    "AnimeExtensionError",
    "SourceError",
    "SourceNotFoundError",
    "HttpError",
    "TimeoutError",
    "ParsingError",
    "UpstreamNotFound",
    "UpstreamRateLimited",
    "UpstreamUnavailable",
    "UnsupportedCapabilityError",
    "CryptoError",
    "ExtractorError",
]

__version__ = "0.3.0"
