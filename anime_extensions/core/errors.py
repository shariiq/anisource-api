"""Custom exception hierarchy for anime extensions."""

from __future__ import annotations


class AnimeExtensionError(Exception):
    """Base exception for all anime extension errors."""


class SourceError(AnimeExtensionError):
    """Raised when an error occurs during anime source operations."""


class DuplicateSourceError(SourceError):
    """Raised when a source is registered with an ID that already exists."""

    def __init__(self, source_id: str) -> None:
        super().__init__(f"Source with ID {source_id!r} is already registered.")


class CryptoError(SourceError):
    """Raised when a cryptographic operation fails."""


class HttpError(SourceError):
    """Raised when an HTTP request fails or returns an unexpected status code."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpstreamNotFound(HttpError):
    """Raised when an upstream source returns 404."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class UpstreamRateLimited(HttpError):
    """Raised when an upstream source returns 429."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=429)


class UpstreamUnavailable(HttpError):
    """Raised when an upstream source is unavailable (502, 503, 504)."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message, status_code=status_code)


class TimeoutError(HttpError):
    """Raised when a request times out."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=504)


class ParsingError(SourceError):
    """Raised when parsing HTML, JSON, or media manifests fails."""


class ExtractorError(AnimeExtensionError):
    """Raised when video stream extraction fails."""


class UnsupportedCapabilityError(SourceError):
    """Raised when a source does not support a requested capability."""

    def __init__(self, source_id: str, capability: str) -> None:
        super().__init__(f"Source {source_id!r} does not support capability {capability!r}")
        self.source_id = source_id
        self.capability = capability
