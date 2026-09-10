"""Deterministic tests for AniWaves HTML and server parsing."""

from unittest.mock import AsyncMock

import pytest

from anime_extensions.models import Anime, Server
from anime_extensions.sources.aniwaves import AniWaves

LISTING_HTML = """
<div class="ani items">
  <div class="item">
    <a class="name" href="/watch/one-piece/ep-3" data-jp="One Piece JP">One Piece</a>
    <div class="poster"><img data-src="https://img.example/one-piece.jpg"></div>
  </div>
  <div class="item"><span>Malformed item</span></div>
</div>
<nav><ul class="pagination"><li class="active">1</li><li><a>2</a></li></ul></nav>
"""

DETAILS_HTML = """
<h1 class="title" data-jp="Naruto JP">Naruto</h1>
<div id="watch-main" data-id="internal-42"></div>
<div id="w-info"><div class="poster"><img src="https://img.example/naruto.jpg"></div></div>
<div class="bmeta">
  <div class="meta">
    <div>Genres: <span><a>Action</a><a>Shonen</a></span></div>
    <div>Studios: <span><a>Studio Pierrot</a></span></div>
    <div>Status: <span>Currently Airing</span></div>
    <div>MAL: <span>8.7</span></div>
  </div>
</div>
<div class="shorting film-description"><div class="content">A ninja story.</div></div>
<div class="names font-italic">NARUTO; Naruto Uzumaki</div>
"""

EPISODES_HTML = """
<div class="episodes"><ul>
  <li title="Episode one Release: 2024"><a data-num="1" data-ids="id-one" data-sub="1"><span class="d-title">Enter</span></a></li>
  <li><a class="filler" data-num="2.5" data-ids="id-two" data-dub="1" data-timestamp="1725840000"></a></li>
</ul></div>
"""

SERVERS_HTML = """
<div class="servers">
  <div class="type"><label>Sub</label><ul><li data-link-id="s1">Vidplay</li><li class="download-icon">Download</li></ul></div>
  <div class="type"><label>Dub</label><ul><li data-link-id="s2">Dood</li></ul></div>
</div>
"""


@pytest.fixture
def source() -> AniWaves:
    return AniWaves(domain="aniwaves.example")


def test_parse_listing_prefers_japanese_title_and_detects_pagination(source: AniWaves):
    """Test listing normalization, thumbnail extraction, and pagination."""
    animes, has_next = source._parse_listing(LISTING_HTML)

    assert has_next is True
    assert len(animes) == 1
    assert isinstance(animes[0], Anime)
    assert animes[0].id == "one-piece"
    assert animes[0].title == "One Piece JP"
    assert animes[0].url == "/watch/one-piece"
    assert animes[0].thumbnail == "https://img.example/one-piece.jpg"


@pytest.mark.asyncio
async def test_get_details_parses_metadata(source: AniWaves):
    """Test detail page metadata and canonical source identifier."""
    source._request = AsyncMock(return_value=(200, DETAILS_HTML))

    anime = await source.get_details("naruto")

    assert isinstance(anime, Anime)
    assert anime.id == "internal-42"
    assert anime.title == "Naruto JP"
    assert anime.url == "/watch/naruto#internal-42"
    assert anime.genres == ["Action", "Shonen"]
    assert anime.studios == ["Studio Pierrot"]
    assert anime.status == "ongoing"
    assert anime.score == 8.7
    assert anime.description == "A ninja story."
    assert "Naruto JP" in anime.alternative_titles


@pytest.mark.asyncio
async def test_get_episodes_reverses_site_order_and_builds_ids(source: AniWaves):
    """Test episode flags, fallback title, release timestamp, and IDs."""
    source._get_json = AsyncMock(return_value=(200, {"result": EPISODES_HTML}))

    episodes = await source.get_episodes("/watch/naruto#internal-42")

    assert [episode.number for episode in episodes] == [2.5, 1.0]
    assert episodes[0].is_filler is True
    assert episodes[0].has_dub is True
    assert episodes[0].title == "Episode 2.5"
    assert episodes[0].id == "id-two&epurl=/watch/naruto/ep-2.5"
    assert episodes[1].has_sub is True
    assert episodes[1].title == "Enter"


@pytest.mark.asyncio
async def test_get_servers_normalizes_names_and_types(source: AniWaves):
    """Test server filtering and Sub/Dub type normalization."""
    source._get_json = AsyncMock(return_value=(200, {"result": SERVERS_HTML}))

    servers = await source.get_servers("id-one&epurl=/watch/naruto/ep-1")

    assert [server.id for server in servers] == ["s1", "s2"]
    assert isinstance(servers[0], Server)
    assert servers[0].name == "Vidplay"
    assert servers[0].type == "sub"
    assert servers[1].name == "Doodstream"
    assert servers[1].type == "dub"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("embed_url", "method"),
    [
        ("https://dood.to/e/abc", "_extract_from_dood"),
        ("https://filemoon.sx/e/abc", "_extract_from_byse"),
        ("https://vidplay.example/e/abc", "_extract_from_echovideo"),
    ],
)
async def test_get_streams_routes_by_host(source: AniWaves, embed_url: str, method: str):
    """Test host-based routing keeps source orchestration separate from extraction."""
    source._get_embed_url = AsyncMock(return_value=embed_url)
    routed = AsyncMock(return_value=[])
    setattr(source, method, routed)

    await source.get_streams("id-one&epurl=/watch/naruto/ep-1", "server-1")

    routed.assert_awaited_once()
