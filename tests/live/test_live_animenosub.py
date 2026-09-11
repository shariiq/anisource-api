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
    """Test end-to-end extraction, finding any working server."""
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

    # Try each server until one produces streams
    streams: list[Stream] = []
    for server in servers:
        try:
            streams = await animenosub_source.get_streams(episode.id, server.id)
            if streams:
                break
        except Exception:
            continue

    assert streams, "Expected at least one playable stream from any server"
    assert streams[0].url.startswith("http")


@pytest.mark.live
@pytest.mark.asyncio
async def test_all_server_extraction(animenosub_source: AnimeNoSub) -> None:
    """Test stream extraction across all discovered AnimeNoSub servers."""
    results, _ = await animenosub_source.search("Attack on Titan", page=1)
    assert results, "Search failed"
    anime = results[0]

    episodes = await animenosub_source.get_episodes(anime.id)
    assert episodes, "No episodes found"

    episode = episodes[0]
    servers = await animenosub_source.get_servers(episode.id)
    assert servers, "No servers found"

    outcomes = []
    for server in servers:
        try:
            streams = await animenosub_source.get_streams(episode.id, server.id)
            if streams:
                outcomes.append(f"✓ {server.name}: {len(streams)} streams")
            else:
                outcomes.append(f"✗ {server.name}: no streams returned")
        except Exception as exc:
            outcomes.append(f"✗ {server.name}: {type(exc).__name__}: {exc}")

    print("\nAnimeNoSub Server Coverage:")
    for outcome in outcomes:
        print(f"  {outcome}")

    working = [o for o in outcomes if o.startswith("✓")]
    assert working, "No working servers found. Outcomes:\n" + "\n".join(outcomes)
