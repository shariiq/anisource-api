"""Shared data models returned by anime sources and extractors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Anime:
    """An anime shown in a listing or on a details page."""

    id: str
    title: str
    url: str
    thumbnail: str = ""
    description: str = ""
    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    producers: list[str] = field(default_factory=list)
    alternative_titles: list[str] = field(default_factory=list)
    status: str = "unknown"  # "ongoing", "completed", "unknown"
    score: float | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Episode:
    """An episode and the source-specific identifier needed to load it."""

    id: str
    number: float
    title: str
    is_filler: bool = False
    has_sub: bool = False
    has_dub: bool = False
    scanlator: str = ""
    released_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["released_at"] = self.released_at.isoformat() if self.released_at else None
        return data


@dataclass(slots=True)
class Server:
    """A streaming server available for an episode."""

    id: str
    name: str
    type: str  # e.g., "Sub", "Dub", "Soft Sub"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Subtitle:
    """A subtitle track attached to a stream."""

    url: str
    label: str = ""
    language: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Stream:
    """A directly playable video stream."""

    url: str
    quality: str
    headers: dict[str, str] = field(default_factory=dict)
    subtitles: list[Subtitle] = field(default_factory=list)
    is_hls: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["subtitles"] = [subtitle.to_dict() for subtitle in self.subtitles]
        return data
