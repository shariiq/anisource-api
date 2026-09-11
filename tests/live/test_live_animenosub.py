import pytest

from anime_extensions.core.runtime import ExtensionRuntime
from anime_extensions.models import Anime, Stream
from anime_extensions.sources.animenosub import AnimeNoSub


@pytest.fixture
async def animenosub_source():
    """Provide an initialized AnimeNoSub source for tests."""
    async with ExtensionRuntime() as runtime:
        yield runtime.get_source("animenosub")


@pytest.mark.live
@pytest.mark.asyncio
async def test_get_popular(animenosub_source: AnimeNoSub) -> None:
    animes, has_next = await animenosub_source.get_popular(page=1)
    assert isinstance(has_next, bool)
    assert len(animes) > 0, "Expected at least one popular anime"
    assert isinstance(animes[0], Anime)
    assert animes[0].title


@pytest.mark.live
@pytest.mark.asyncio
async def test_search(animenosub_source: AnimeNoSub) -> None:
    results, has_next = await animenosub_source.search("One Piece", page=1)
    assert len(results) > 0
    found = any("one piece" in a.title.lower() for a in results)
    assert found


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_extraction_flow(animenosub_source: AnimeNoSub) -> None:
    results, _ = await animenosub_source.search("Attack on Titan", page=1)
    assert results, "Search failed"
    anime = results[0]

    details = await animenosub_source.get_details(anime.id)
    assert details.id
    assert details.title

    episodes = await animenosub_source.get_episodes(anime.id)
    assert len(episodes) > 0

    episode = episodes[0]
    servers = await animenosub_source.get_servers(episode.id)
    assert servers, "Expected at least one server"

    streams: list[Stream] = await animenosub_source.get_streams(episode.id, servers[0].id)
    assert streams, "Expected at least one playable stream"
    assert streams[0].url.startswith("http")
