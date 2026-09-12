"""Live network end-to-end tests for the AniWaves source."""

import pytest

from anime_extensions.models import Anime, Stream
from anime_extensions.sources.aniwaves import AniWaves


@pytest.fixture
async def aniwaves_source():
    """Provide an initialized AniWaves source for tests."""
    from anime_extensions.core import ExtensionRuntime

    async with ExtensionRuntime() as runtime:
        # Sources are already registered via _register_builtins() during start()
        yield runtime.get_source("aniwaves")


@pytest.mark.live
@pytest.mark.asyncio
async def test_get_popular(aniwaves_source: AniWaves) -> None:
    """Test fetching popular anime from AniWaves."""
    page_data = await aniwaves_source.get_popular(page=1)
    animes = page_data.items
    has_next = page_data.has_next

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
    page_data = await aniwaves_source.search("Naruto", page=1)
    results = page_data.items

    assert len(results) > 0, "Expected search results for 'Naruto'"
    assert "naruto" in results[0].title.lower(), "Search result should contain query"


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_extraction_flow(aniwaves_source: AniWaves) -> None:
    """End-to-end test verifying details, episodes, servers, and streams."""
    # 1. Search for a stable anime
    page_data = await aniwaves_source.search("Naruto", page=1)
    results = page_data.items
    assert results, "Search failed, aborting flow"
    anime = results[0]

    # 2. Get details, episodes, servers, and streams (try bounded fallback across candidates)
    streams: list[Stream] = []

    for anime in results[:3]:
        details = await aniwaves_source.get_details(anime.id)
        assert details.title == anime.title
        assert details.description, "Expected a valid description"

        episodes = await aniwaves_source.get_episodes(anime.id)
        if not episodes:
            continue

        for ep in episodes[:3]:
            try:
                servers = await aniwaves_source.get_servers(ep.id)
            except Exception:
                continue

            for srv in servers[:3]:
                try:
                    streams = await aniwaves_source.get_streams(ep.id, srv.id)
                    if streams:
                        break
                except Exception:
                    continue
            if streams:
                break
        if streams:
            break

    assert len(streams) > 0, "Expected at least one playable stream across all available servers"
    assert isinstance(streams[0], Stream)
    assert streams[0].url.startswith("http"), "Stream URL must be an absolute HTTP(S) URL"
