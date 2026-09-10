"""Application configuration settings for the Anime Extensions API service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class CacheSettings:
    """Cache duration settings in seconds for various endpoints."""

    enabled: bool = True
    popular_ttl_seconds: int = 1800  # 30 minutes
    latest_ttl_seconds: int = 600  # 10 minutes
    search_ttl_seconds: int = 1800  # 30 minutes
    details_ttl_seconds: int = 3600  # 1 hour
    episodes_ttl_seconds: int = 1800  # 30 minutes
    servers_ttl_seconds: int = 600  # 10 minutes
    streams_ttl_seconds: int = 300  # 5 minutes (streams/tokens expire quickly)
    max_items: int = 5000


@dataclass(frozen=True)
class APISettings:
    """Main API configuration settings."""

    # Server settings
    title: str = "Anime Extensions API"
    description: str = (
        "Production-grade async REST API for anime discovery, episode indexing, "
        "and video stream extraction."
    )
    version: str = "0.2.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    workers: int = 1

    # Security & CORS
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = field(default_factory=lambda: ["*"])

    # Network / Upstream
    request_timeout_seconds: float = 30.0
    proxy_url: str | None = None

    # Caching
    cache: CacheSettings = field(default_factory=CacheSettings)

    @classmethod
    def from_env(cls) -> APISettings:
        """Create settings instance populated from environment variables."""

        def get_bool(key: str, default: bool) -> bool:
            val = os.getenv(key)
            if val is None:
                return default
            return val.lower() in ("true", "1", "yes", "on")

        def get_int(key: str, default: int) -> int:
            val = os.getenv(key)
            if val is None:
                return default
            try:
                return int(val)
            except ValueError:
                return default

        def get_float(key: str, default: float) -> float:
            val = os.getenv(key)
            if val is None:
                return default
            try:
                return float(val)
            except ValueError:
                return default

        def get_list(key: str, default: list[str]) -> list[str]:
            val = os.getenv(key)
            if val is None:
                return default
            return [x.strip() for x in val.split(",") if x.strip()]

        cache_settings = CacheSettings(
            enabled=get_bool("ANIME_API_CACHE_ENABLED", True),
            popular_ttl_seconds=get_int("ANIME_API_CACHE_POPULAR_TTL", 1800),
            latest_ttl_seconds=get_int("ANIME_API_CACHE_LATEST_TTL", 600),
            search_ttl_seconds=get_int("ANIME_API_CACHE_SEARCH_TTL", 1800),
            details_ttl_seconds=get_int("ANIME_API_CACHE_DETAILS_TTL", 3600),
            episodes_ttl_seconds=get_int("ANIME_API_CACHE_EPISODES_TTL", 1800),
            servers_ttl_seconds=get_int("ANIME_API_CACHE_SERVERS_TTL", 600),
            streams_ttl_seconds=get_int("ANIME_API_CACHE_STREAMS_TTL", 300),
            max_items=get_int("ANIME_API_CACHE_MAX_ITEMS", 5000),
        )

        return cls(
            title=os.getenv("ANIME_API_TITLE", "Anime Extensions API"),
            host=os.getenv("ANIME_API_HOST", "0.0.0.0"),
            port=get_int("ANIME_API_PORT", 8000),
            debug=get_bool("ANIME_API_DEBUG", False),
            workers=get_int("ANIME_API_WORKERS", 1),
            cors_origins=get_list("ANIME_API_CORS_ORIGINS", ["*"]),
            request_timeout_seconds=get_float("ANIME_API_REQUEST_TIMEOUT", 30.0),
            proxy_url=os.getenv("ANIME_API_PROXY_URL"),
            cache=cache_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> APISettings:
    """Return cached application settings singleton."""
    return APISettings.from_env()
