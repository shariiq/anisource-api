"""Live end-to-end pipeline checks for every maintained anime source.

Each test deliberately exercises search, details, episodes, servers, and streams.  The
bounded fallback makes the checks resilient to an individual title or hoster rotating,
without hiding a source-wide extraction failure.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import pytest

from anime_extensions.models import Anime, Episode, Server, Stream
from anime_extensions.sources import Anikoto, AnimeNoSub, AniWaves

log = logging.getLogger(__name__)

SOURCES = (Anikoto, AnimeNoSub, AniWaves)
TEST_QUERIES = ("Death Note", "Dandadan", "Cowboy Bebop")
_MAX_ANIME_CANDIDATES = 3
_MAX_EPISODE_CANDIDATES = 3
_MAX_SERVER_CANDIDATES = 4


def _bounded(items: Iterable[Any], maximum: int) -> list[Any]:
    return list(items)[:maximum]


@pytest.mark.asyncio
@pytest.mark.live
@pytest.mark.parametrize("source_class", SOURCES, ids=lambda source: source.metadata.id)
async def test_source_full_pipeline(source_class: type[Any]) -> None:
    """Return at least one usable HTTP(S) stream from every source pipeline."""
    from anime_extensions.core import ExtensionRuntime

    runtime = ExtensionRuntime()
    await runtime.start()
    # Sources are already registered via _register_builtins() during start()
    source = runtime.get_source(source_class.metadata.id)
    diagnostics: list[str] = []
    try:
        candidates = await _search_candidates(source, diagnostics)
        assert candidates, f"{source.metadata.name}: no search results; {' | '.join(diagnostics)}"

        for candidate in candidates:
            try:
                details = await source.get_details(candidate.id)
                assert details.id and details.title
            except AssertionError as error:
                diagnostics.append(f"details({candidate.id}): {error}")
                continue
            except Exception as error:
                diagnostics.append(f"details({candidate.id}): {error}")
                continue

            try:
                episodes = await source.get_episodes(candidate.id)
            except Exception as error:
                diagnostics.append(f"episodes({candidate.id}): {error}")
                continue
            if not episodes:
                diagnostics.append(f"episodes({candidate.id}): empty")
                continue

            streams = await _streams_from_candidate(source, episodes, diagnostics)
            if streams:
                _assert_playable_streams(source.metadata.name, streams)
                log.info("%s pipeline passed with %d stream(s)", source.metadata.name, len(streams))
                return

        pytest.fail(f"{source.metadata.name}: no playable streams; {' | '.join(diagnostics)}")
    finally:
        await runtime.close()


async def _search_candidates(source: Any, diagnostics: list[str]) -> list[Anime]:
    candidates: list[Anime] = []
    for query in TEST_QUERIES:
        try:
            page_data = await source.search(query)
            results = page_data.items
        except Exception as error:
            diagnostics.append(f"search({query!r}): {error}")
            continue
        if results:
            candidates.extend(_bounded(results, _MAX_ANIME_CANDIDATES))
        if len(candidates) >= _MAX_ANIME_CANDIDATES:
            break
    return candidates[:_MAX_ANIME_CANDIDATES]


async def _streams_from_candidate(
    source: Any, episodes: list[Episode], diagnostics: list[str]
) -> list[Stream]:
    for episode in _bounded(episodes, _MAX_EPISODE_CANDIDATES):
        try:
            servers = await source.get_servers(episode.id)
        except Exception as error:
            diagnostics.append(f"servers({episode.id!r}): {error}")
            continue
        if not servers:
            diagnostics.append(f"servers({episode.id!r}): empty")
            continue
        streams = await _streams_from_servers(source, episode, servers, diagnostics)
        if streams:
            return streams
    return []


async def _streams_from_servers(
    source: Any, episode: Episode, servers: list[Server], diagnostics: list[str]
) -> list[Stream]:
    for server in _bounded(servers, _MAX_SERVER_CANDIDATES):
        try:
            streams = await source.get_streams(episode.id, server.id)
        except Exception as error:
            diagnostics.append(f"streams({episode.number}, {server.name!r}): {error}")
            continue
        if streams:
            return streams
        diagnostics.append(f"streams({episode.number}, {server.name!r}): empty")
    return []


def _assert_playable_streams(source_name: str, streams: list[Stream]) -> None:
    assert streams, f"{source_name}: stream extraction returned no streams"
    invalid_urls = [
        stream.url for stream in streams if not stream.url.startswith(("http://", "https://"))
    ]
    assert not invalid_urls, f"{source_name}: invalid stream URLs: {invalid_urls!r}"
