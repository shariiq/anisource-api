"""Live network end-to-end tests for the AniWaves source."""

import pytest

from anime_extensions.models import Anime, Episode, Server, Stream
from anime_extensions.sources.aniwaves import AniWaves


@pytest.fixture
async def aniwaves_source():
    """Provide an initialized AniWaves source for tests."""
    async with AniWaves() as source:
        yield source


@pytest.mark.live
@pytest.mark.asyncio
async def test_get_popular(aniwaves_source: AniWaves) -> None:
    """Test fetching popular anime from AniWaves."""
    animes, has_next = await aniwaves_source.get_popular(page=1)

    assert isinstance(has_next, bool)
    assert len(animes) > 0, "Expected at least one popular anime"

    first = animes[0]
    assert isinstance(first, Anime)
    assert first.title, "Anime title should not be empty"
    assert first.id, "Anime ID should not be empty"
    assert first.url.startswith("http"), "Anime URL should be absolute"


@pytest.mark.live
@pytest.mark.asyncio
async def test_search(aniwaves_source: AniWaves) -> None:
    """Test searching for anime on AniWaves."""
    results, _ = await aniwaves_source.search("Naruto", page=1)

    assert len(results) > 0, "Expected search results for 'Naruto'"
    assert "naruto" in results[0].title.lower(), "Search result should contain query"


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_extraction_flow(aniwaves_source: AniWaves) -> None:
    """End-to-end test verifying details, episodes, servers, and streams."""
    # 1. Search for a stable anime
    results, _ = await aniwaves_source.search("Naruto", page=1)
    assert results, "Search failed, aborting flow"
    anime = results[0]

    # 2. Get details
    details = await aniwaves_source.get_details(anime.id)
    assert details.title == anime.title
    assert details.description, "Expected a valid description"
    assert len(details.genres) > 0, "Expected genres to be parsed"
    assert details.status in ("completed", "ongoing", "upcoming", "unknown")

    # 3. Get episodes
    episodes = await aniwaves_source.get_episodes(anime.id)
    assert len(episodes) > 0, "Expected episodes for Naruto"

    ep = episodes[0]  # First episode
    assert isinstance(ep, Episode)
    assert ep.title, "Episode title is missing"
    assert ep.id, "Episode ID is missing"

    # 4. Get servers
    servers = await aniwaves_source.get_servers(ep.id)
    assert len(servers) > 0, "Expected servers for the episode"
    srv = servers[0]
    assert isinstance(srv, Server)
    assert srv.name, "Server name should be populated"

    # 5. Get streams (if possible, may fail due to captchas/WAF intermittently)
    try:
        streams = await aniwaves_source.get_streams(ep.id, srv.id)
        if streams:
            assert isinstance(streams[0], Stream)
            assert streams[0].url.startswith("http")
    except Exception as e:
        pytest.fail(f"Stream extraction failed: {e}")
