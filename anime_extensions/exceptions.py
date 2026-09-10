"""Custom exception hierarchy for anime extensions."""

from __future__ import annotations


class AnimeExtensionError(Exception):
    """Base exception for all anime extension errors."""


class SourceError(AnimeExtensionError):
    """Raised when an error occurs during anime source operations."""


class HttpError(SourceError):
    """Raised when an HTTP request fails or returns an unexpected status code."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ParsingError(SourceError):
    """Raised when parsing HTML, JSON, or media manifests fails."""


class ExtractorError(AnimeExtensionError):
    """Raised when video stream extraction fails."""


class CryptoError(AnimeExtensionError):
    """Raised when cryptographic challenge solving or decryption fails."""
