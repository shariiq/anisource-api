"""Deterministic AnimeNoSub parsing tests."""

import base64
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.sources.animenosub import AnimeNoSub

LISTING_HTML = """
<div class="listupd"><article><a class="tip" href="/anime/show/"><div class="tt">Show</div>
<img data-src="/images/show.jpg?resize=100"></a></article></div>
<div class="pagination"><a class="next">Next</a></div>
"""
DETAILS_HTML = """
<h1 class="entry-title">Show</h1><div class="thumb"><img src="https://img/show.jpg"></div>
<div class="info-content"><div class="genxed"><a>Action</a></div><div class="spe">
<span>Status: Completed</span><span>Studio: <a>Studio A</a></span><span>Fansub: <a>Group</a></span>
</div></div><div class="entry-content" itemprop="description">Synopsis.</div><div class="alter">Alt Show</div>
"""
EPISODES_HTML = """
<div class="eplister"><ul><li><a href="/episode/show-1"><div class="epl-num">1</div>
<div class="epl-title">Pilot</div><div class="epl-sub">English Sub</div>
<div class="epl-date">Dec 25, 2024</div></a></li></ul></div>
"""


@pytest.fixture
def source() -> AnimeNoSub:
    context = MagicMock()
    context.http = MagicMock()
    context.extractors = MagicMock()
    return AnimeNoSub(context=context)


def test_parse_listing(source: AnimeNoSub):
    items, has_next = source._parse_listing(LISTING_HTML)
    assert has_next is True
    assert len(items) == 1
    assert items[0].id == "anime/show"
    assert items[0].thumbnail == "https://animenosub.to/images/show.jpg"


@pytest.mark.asyncio
async def test_details_and_episodes(source: AnimeNoSub):
    source.context.http.get = AsyncMock(side_effect=[DETAILS_HTML, EPISODES_HTML])
    anime = await source.get_details("anime/show")
    episodes = await source.get_episodes("anime/show")
    assert anime.title == "Show"
    assert anime.status == "completed"
    assert anime.genres == ["Action"]
    assert anime.studios == ["Studio A"]
    assert episodes[0].number == 1.0
    assert episodes[0].title == "Ep. 1 Pilot"
    assert episodes[0].released_at == datetime(2024, 12, 25)


@pytest.mark.asyncio
async def test_servers_and_stream_delegation(source: AnimeNoSub):
    encoded = base64.b64encode(b'<iframe src="https://vidmoly.biz/embed-a"></iframe>').decode()
    source.context.http.get = AsyncMock(
        return_value=f'<select class="mirror"><option data-index="1" value="{encoded}">VidMoly</option></select>'
    )
    servers = await source.get_servers("https://animenosub.to/episode/show-1")
    assert servers[0].name == "VidMoly"
    extractor = MagicMock(name="extractor")
    extractor.name = "VidMoly"
    extractor.extract = AsyncMock(return_value=[])
    source.context.extractors.resolve.return_value = extractor
    assert await source.get_streams("unused", servers[0].id) == []
    source.context.extractors.resolve.assert_called_once_with("https://vidmoly.biz/embed-a")
