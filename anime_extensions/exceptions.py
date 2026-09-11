"""Backward-compatible exports for the core exception hierarchy."""

from .core.errors import (
    AnimeExtensionError,
    CryptoError,
    ExtractorError,
    HttpError,
    ParsingError,
    SourceError,
    TimeoutError,
    UpstreamNotFound,
    UpstreamRateLimited,
    UpstreamUnavailable,
)

__all__ = [
    "AnimeExtensionError",
    "CryptoError",
    "ExtractorError",
    "HttpError",
    "ParsingError",
    "SourceError",
    "TimeoutError",
    "UpstreamNotFound",
    "UpstreamRateLimited",
    "UpstreamUnavailable",
]
