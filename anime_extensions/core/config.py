"""Centralized configuration for sources and extractors.

This module provides a typed configuration system for runtime parameters
like timeouts, retry policies, and extractor-specific constants, avoiding
magic numbers scattered across implementation files.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HttpConfig:
    """HTTP client configuration."""

    default_timeout: float = 30.0
    max_redirects: int = 10
    retry_attempts: int = 0
    retry_backoff: float = 1.0


@dataclass(frozen=True)
class ExtractorConfig:
    """Base configuration for video extractors."""

    timeout: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )


@dataclass(frozen=True)
class ByseConfig(ExtractorConfig):
    """Configuration for Byse/BYFMS/Filemoon extractor."""

    pow_timeout: float = 180.0  # Proof-of-Work solver timeout
    challenge_timeout: float = 10.0
    playback_timeout: float = 15.0


@dataclass(frozen=True)
class DoodConfig(ExtractorConfig):
    """Configuration for DoodStream extractor."""

    default_quality: str = "1080p"
    token_length: int = 10


@dataclass(frozen=True)
class EchoVideoConfig(ExtractorConfig):
    """Configuration for EchoVideo/Vidplay/MyCloud/DatSaV extractor."""

    quality_labels: dict[str, str] = field(
        default_factory=lambda: {
            "FHD": "1080p",
            "HD": "720p",
            "HQ": "480p",
            "SD": "360p",
        }
    )
    fallback_endpoints: list[str] = field(default_factory=lambda: ["getSources", "getSourcesNew"])


@dataclass(frozen=True)
class SourceConfig:
    """Base configuration for anime sources."""

    search_page_size: int = 24
    episodes_per_page: int = 100
    request_timeout: float = 30.0


# Global default configurations
DEFAULT_HTTP_CONFIG = HttpConfig()
DEFAULT_EXTRACTOR_CONFIG = ExtractorConfig()
DEFAULT_BYSE_CONFIG = ByseConfig()
DEFAULT_DOOD_CONFIG = DoodConfig()
DEFAULT_ECHOVIDEO_CONFIG = EchoVideoConfig()
DEFAULT_SOURCE_CONFIG = SourceConfig()
