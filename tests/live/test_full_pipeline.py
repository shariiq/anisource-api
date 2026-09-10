"""Full pipeline integration tests for all anime sources.
Verifies: Search -> Details -> Episodes -> Servers -> Streams.
"""

import logging

import pytest

from anime_extensions.sources import Anikoto, AniWaves, MKissa

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

SOURCES = [Anikoto, AniWaves, MKissa]
TEST_QUERIES = ["One Piece", "Naruto", "Bleach", "Attack on Titan"]

@pytest.mark.asyncio
@pytest.mark.parametrize("SourceClass", SOURCES)
async def test_source_full_pipeline(SourceClass):
    """Verify the full data pipeline for a source."""
    source = SourceClass()
    try:
        log.info(f"Testing full pipeline for {source.name}")

        # 1. Search
        selected_anime = None
        for query in TEST_QUERIES:
            log.info(f"[{source.name}] Searching for '{query}'...")
            res, _ = await source.search(query)
            if res:
                selected_anime = res[0]
                log.info(f"[{source.name}] Found results for '{query}'")
                break

        if not selected_anime:
            pytest.skip(f"No results found for any test queries on {source.name}")
            return

        anime = selected_anime
        log.info(f"[{source.name}] Selected anime: {anime.title} (ID: {anime.id})")

        # 2. Details
        log.info(f"[{source.name}] Fetching details...")
        details = await source.get_details(anime.id)
        assert details.id
        assert details.title
        log.info(f"[{source.name}] Details fetched: {details.title}")

        # 3. Episodes
        log.info(f"[{source.name}] Fetching episodes...")
        episodes = await source.get_episodes(anime.id)
        if not episodes:
            pytest.skip(f"No episodes found for {anime.title} on {source.name}")
            return

        episode = episodes[0]
        log.info(f"[{source.name}] Found episode: {episode.title} (ID: {episode.id})")

        # 4. Servers
        log.info(f"[{source.name}] Fetching servers...")
        servers = await source.get_servers(episode.id)
        if not servers:
            pytest.skip(f"No servers found for episode {episode.number} on {source.name}")
            return

        server = servers[0]
        log.info(f"[{source.name}] Found server: {server.name}")

        # 5. Streams
        log.info(f"[{source.name}] Extracting streams...")
        streams = await source.get_streams(episode.id, server.id)
        log.info(f"[{source.name}] Found {len(streams)} streams")

        # streams are critical.
        assert len(streams) > 0, "Streams should be available for a valid episode"
        log.info(f"[{source.name}] Found streams: {[stream.url for stream in streams]}")

        log.info(f"[{source.name}] Full pipeline test passed for {anime.title}")

    except Exception as e:
        log.exception(f"Pipeline failed for {source.name}")
        pytest.fail(f"Full pipeline failed for {source.name}: {e}")
    finally:
        if hasattr(source, "close"):
            await source.close()
