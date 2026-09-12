"""Unit tests for the core domain models and serialization contracts."""

from datetime import datetime

from anime_extensions.models import Anime, Episode, Stream, Subtitle


def test_anime_model_creation():
    """Verify Anime dataclass is properly constructed."""
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
    assert anime.id == "frieren-1"
    assert anime.title == "Sousou no Frieren"
    assert anime.score == 9.35
    assert "Fantasy" in anime.genres


def test_episode_model_with_datetime():
    """Verify Episode accepts datetime properly."""
    now = datetime(2026, 9, 10, 12, 0, 0)
    episode = Episode(
        id="ep-1",
        number=1.0,
        title="The Journey's Beginning",
        is_filler=False,
        has_sub=True,
        released_at=now,
    )
    assert episode.number == 1.0
    assert episode.released_at == now


def test_stream_model_with_subtitles():
    """Verify Stream accepts Subtitle objects."""
    stream = Stream(
        url="https://cdn.example.com/stream.m3u8",
        quality="1080p",
        is_hls=True,
        subtitles=[Subtitle(url="https://cdn.example.com/en.vtt", label="English", language="en")],
    )
    assert stream.is_hls is True
    assert len(stream.subtitles) == 1
    assert stream.subtitles[0].label == "English"
