"""Core framework components for anime extensions.

This module provides the foundation for building anime source plugins:

* **Contracts**: ``Source`` and ``Extractor`` abstract base classes
* **Models**: ``Anime``, ``Episode``, ``Server``, ``Stream``, ``Subtitle``
* **Metadata**: ``SourceMetadata`` and ``SourceCapability``
* **HTTP**: ``HttpClient`` with secure defaults
* **Registry**: ``@register_source`` and ``@register_extractor`` decorators
* **Runtime**: ``ExtensionRuntime`` and ``SourceContext``
* **Errors**: Fine-grained exception hierarchy

Example:
    >>> from anime_extensions.core import ExtensionRuntime
    >>> async with ExtensionRuntime() as runtime:
    ...     source = runtime.get_source("aniwaves")
    ...     popular, has_next = await source.get_popular(page=1)
"""

from __future__ import annotations

from .errors import (
    AnimeExtensionError,
    CryptoError,
    ExtractorError,
    HttpError,
    ParsingError,
    SourceError,
    TimeoutError,
    UnsupportedCapabilityError,
    UpstreamNotFound,
    UpstreamRateLimited,
    UpstreamUnavailable,
)
from .extractor import Extractor
from .http import HttpClient
from .metadata import SourceCapability, SourceMetadata
from .models import Anime, AnimeStatus, Episode, Server, Stream, Subtitle
from .registry import ExtractorRegistry, SourceRegistry
from .runtime import ExtensionRuntime, SourceContext
from .source import Source

__all__ = [
    # Contracts
    "Source",
    "Extractor",
    # Models
    "Anime",
    "AnimeStatus",
    "Episode",
    "Server",
    "Stream",
    "Subtitle",
    # Metadata
    "SourceMetadata",
    "SourceCapability",
    # HTTP
    "HttpClient",
    # Registry
    "SourceRegistry",
    "ExtractorRegistry",
    # Runtime
    "ExtensionRuntime",
    "SourceContext",
    # Errors
    "AnimeExtensionError",
    "SourceError",
    "HttpError",
    "UpstreamNotFound",
    "UpstreamRateLimited",
    "UpstreamUnavailable",
    "TimeoutError",
    "ParsingError",
    "ExtractorError",
    "CryptoError",
    "UnsupportedCapabilityError",
]
