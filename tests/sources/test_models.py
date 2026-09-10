"""Unit tests for the core domain models and serialization contracts."""

from datetime import datetime

from anime_extensions.models import Anime, Episode, Stream, Subtitle


def test_anime_model_to_dict():
    """Verify Anime dataclass serializes cleanly to a dictionary."""
    anime = Anime(
        id="frieren-1",
        title="Sousou no Frieren",
        url="https://example.com/watch/frieren-1",
        thumbnail="https://example.com/cover.jpg",
        description="Elven mage journey",
        genres=["Fantasy", "Drama"],
        status="completed",
        score=9.35,
    )
    d = anime.to_dict()
    assert d["id"] == "frieren-1"
    assert d["title"] == "Sousou no Frieren"
    assert d["score"] == 9.35
    assert "Fantasy" in d["genres"]


def test_episode_model_with_datetime():
    """Verify Episode serializes ISO-8601 timestamps properly."""
    now = datetime(2026, 9, 10, 12, 0, 0)
    episode = Episode(
        id="ep-1",
        number=1.0,
        title="The Journey's Beginning",
        is_filler=False,
        has_sub=True,
        released_at=now,
    )
    d = episode.to_dict()
    assert d["number"] == 1.0
    assert d["released_at"] == "2026-09-10T12:00:00"


def test_stream_model_with_subtitles():
    """Verify Stream nested Subtitle serialization."""
    stream = Stream(
        url="https://cdn.example.com/stream.m3u8",
        quality="1080p",
        is_hls=True,
        subtitles=[Subtitle(url="https://cdn.example.com/en.vtt", label="English", language="en")],
    )
    d = stream.to_dict()
    assert d["is_hls"] is True
    assert len(d["subtitles"]) == 1
    assert d["subtitles"][0]["label"] == "English"
