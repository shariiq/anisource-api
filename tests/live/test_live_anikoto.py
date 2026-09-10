"""Live network end-to-end tests for the Anikoto source."""

import pytest

from anime_extensions.models import Anime, Episode, Server, Stream
from anime_extensions.sources.anikoto import Anikoto


@pytest.fixture
async def anikoto_source():
    """Provide an initialized Anikoto source for tests."""
    async with Anikoto() as source:
        yield source


@pytest.mark.live
@pytest.mark.asyncio
async def test_get_popular(anikoto_source: Anikoto) -> None:
    """Test fetching popular anime from Anikoto."""
    animes, has_next = await anikoto_source.get_popular(page=1)

    assert isinstance(has_next, bool)
    assert len(animes) > 0, "Expected at least one popular anime"
    assert isinstance(animes[0], Anime)
    assert animes[0].title, "Anime title should not be empty"


@pytest.mark.live
@pytest.mark.asyncio
async def test_search(anikoto_source: Anikoto) -> None:
    """Test searching for anime on Anikoto."""
    results, has_next = await anikoto_source.search("Naruto", page=1)

    assert len(results) > 0, "Expected search results for 'Naruto'"
    found = any("naruto" in a.title.lower() for a in results)
    assert found, "Search results should contain query term"


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_extraction_flow(anikoto_source: Anikoto) -> None:
    """End-to-end test verifying details, episodes, servers, and streams."""
    # 1. Search
    results, _ = await anikoto_source.search("Naruto", page=1)
    assert results, "Search failed, aborting flow"
    anime = results[0]

    # 2. Get details
    details = await anikoto_source.get_details(anime.id)
    assert details.id == anime.id
    assert details.description, "Expected a synopsis"

    # 3. Get episodes
    episodes = await anikoto_source.get_episodes(anime.id)
    assert len(episodes) > 0, "Expected episodes"
    ep = episodes[0]
    assert isinstance(ep, Episode)

    # 4. Get servers
    servers = await anikoto_source.get_servers(ep.id)
    assert len(servers) > 0, "Expected servers"
    srv = servers[0]
    assert isinstance(srv, Server)

    # 5. Get streams
    try:
        streams = await anikoto_source.get_streams(ep.id, srv.id)
        if streams:
            stream = streams[0]
            assert isinstance(stream, Stream)
            assert stream.url.startswith("http")
    except Exception as e:
        pytest.fail(f"Stream extraction failed: {e}")
