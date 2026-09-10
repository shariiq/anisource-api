"""Pydantic schemas for request validation and response serialization.

These schemas provide strict typing, automatic documentation generation (OpenAPI),
and output sanitization for the REST API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ==============================================================================
# Model Schemas (matching underlying domain models)
# ==============================================================================


class AnimeSchema(BaseModel):
    """Schema representing an anime's metadata and details."""

    id: str = Field(..., description="Source-specific unique identifier for the anime.")
    title: str = Field(..., description="Display title of the anime.")
    url: str = Field(..., description="Direct URL to the anime page on the source website.")
    thumbnail: str = Field("", description="URL to the anime poster or thumbnail image.")
    description: str = Field("", description="Synopsis or detailed description of the anime.")
    genres: list[str] = Field(
        default_factory=list, description="List of genres associated with the anime."
    )
    studios: list[str] = Field(default_factory=list, description="Studios that produced the anime.")
    producers: list[str] = Field(default_factory=list, description="Producers of the anime.")
    alternative_titles: list[str] = Field(
        default_factory=list, description="Known alternative or localized titles."
    )
    status: str = Field("unknown", description="Release status (ongoing, completed, unknown).")
    score: float | None = Field(None, description="Average viewer score or rating if available.")
    tags: list[str] = Field(default_factory=list, description="General tags or classifiers.")


class EpisodeSchema(BaseModel):
    """Schema representing a single playable episode."""

    id: str = Field(..., description="Source-specific unique identifier for the episode.")
    number: float = Field(..., description="Numeric sequencing of the episode.")
    title: str = Field(..., description="Display title of the episode.")
    is_filler: bool = Field(False, description="Whether this episode is considered filler.")
    has_sub: bool = Field(False, description="Whether subtitles are guaranteed to be available.")
    has_dub: bool = Field(False, description="Whether audio dubbing is guaranteed to be available.")
    scanlator: str = Field("", description="Release group or organization behind the translation.")
    released_at: datetime | None = Field(None, description="Official release timestamp.")


class ServerSchema(BaseModel):
    """Schema representing an available video streaming server for an episode."""

    id: str = Field(..., description="Source-specific unique identifier for the server.")
    name: str = Field(
        ..., description="Display name of the video hoster (e.g. DoodStream, Vidplay)."
    )
    type: str = Field(..., description="Type of video track provided (e.g. Sub, Dub, Soft Sub).")


class SubtitleSchema(BaseModel):
    """Schema representing a subtitle track for a video stream."""

    url: str = Field(..., description="Direct URL to the subtitle file (VTT/SRT/ASS).")
    label: str = Field("", description="Display label for the subtitle (e.g. English, Spanish).")
    language: str = Field("", description="ISO 639-1 language code if available.")


class StreamSchema(BaseModel):
    """Schema representing a playable video stream and its configurations."""

    url: str = Field(..., description="Direct playback URL (MP4, M3U8, etc).")
    quality: str = Field(..., description="Video resolution or quality label (e.g. 1080p, Auto).")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Required HTTP headers for playback (e.g. Referer, User-Agent).",
    )
    subtitles: list[SubtitleSchema] = Field(
        default_factory=list, description="Available subtitle tracks for this stream."
    )
    is_hls: bool = Field(False, description="Whether the stream is an HLS playlist (.m3u8).")


# ==============================================================================
# API Response Wrappers
# ==============================================================================


class PaginatedResponse[T](BaseModel):
    """Standardized response format for paginated listings."""

    items: list[T] = Field(description="List of returned items.")
    page: int = Field(description="Current page number.")
    has_next: bool = Field(description="Indicates if there is a subsequent page available.")
    total_returned: int = Field(description="Number of items returned in this response.")


class SourceInfoResponse(BaseModel):
    """Schema describing an active scraper source."""

    id: str = Field(
        ..., description="Unique technical identifier for the source (e.g. 'aniwaves')."
    )
    name: str = Field(..., description="Display name of the source (e.g. 'AniWaves').")
    base_url: str = Field(..., description="Base domain URI targeted by this source.")


class SourceListResponse(BaseModel):
    """List of available scraper sources."""

    sources: list[SourceInfoResponse] = Field(description="List of active sources.")
    count: int = Field(description="Total number of registered sources.")


class ErrorDetail(BaseModel):
    """Schema for structured error details."""

    code: str = Field(..., description="Application-specific error code.")
    message: str = Field(..., description="Human-readable error description.")
    path: str = Field(..., description="Path where the error occurred.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Time of occurrence.",
    )


class ErrorResponse(BaseModel):
    """Standardized error response payload."""

    error: ErrorDetail


class HealthCheckResponse(BaseModel):
    """Schema for system health observability."""

    status: str = Field("ok", description="Overall system health status.")
    version: str = Field(..., description="API semantic version.")
    uptime_seconds: float = Field(..., description="Application uptime in seconds.")
    memory_usage_mb: float = Field(..., description="Current RSS memory usage in megabytes.")
    active_sources: int = Field(..., description="Number of registered scraping sources.")
    cache_stats: dict[str, Any] = Field(..., description="Current state of the memory cache.")
