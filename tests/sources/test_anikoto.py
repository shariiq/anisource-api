"""Deterministic tests for Anikoto HTML and VRF parsing."""

from unittest.mock import AsyncMock

import pytest

from anime_extensions.models import Anime, Server
from anime_extensions.sources.anikoto import Anikoto, vrf_encrypt

LISTING_HTML = """
<div class="ani items">
  <div class="item">
    <a class="name" href="/watch/frieren-1/ep-5" data-jp="葬送のフリーレン">Frieren</a>
    <div class="poster"><img data-src="https://img.example/frieren.jpg"></div>
  </div>
</div>
<ul class="pagination"><li class="active">1</li><li><a>2</a></li></ul>
"""

DETAILS_HTML = """
<h2 class="title" data-jp="葬送のフリーレン">Frieren</h2>
<div id="watch-main" data-id="internal-999"></div>
<img class="thumbnail" src="https://img.example/frieren.jpg">
<div class="bmeta">
  <div class="meta">
    <div>Genres: <span><a>Fantasy</a><a>Drama</a></span></div>
    <div>Studios: <span><a>Madhouse</a></span></div>
    <div>Status: <span>Finished Airing</span></div>
    <div>MAL: <span>9.3</span></div>
  </div>
</div>
<div class="synopsis"><div class="content">An elf mage reflects on her journey.</div></div>
<div class="names font-italic">Sousou no Frieren; Beyond Journey's End</div>
"""

EPISODES_HTML = """
<div class="episodes"><ul>
  <li title="The Beginning Release: 1725840000"><a data-num="1" data-ids="ep-id-1" data-sub="1"><span class="d-title">The Journey</span></a></li>
  <li class="filler"><a data-num="2" data-ids="ep-id-2" data-dub="1" data-timestamp="1725926400"></a></li>
</ul></div>
"""

SERVERS_HTML = """
<div class="servers">
  <div class="type"><label>Sub</label><ul><li data-link-id="srv-1">Server 1</li></ul></div>
  <div class="type"><label>H-Sub</label><ul><li data-link-id="srv-2">Server 2</li></ul></div>
  <div class="type"><label>Dub</label><ul><li data-link-id="srv-3">Server 3</li></ul></div>
</div>
"""


@pytest.fixture
def source() -> Anikoto:
    return Anikoto(domain="anikoto.example")


def test_vrf_encrypt_deterministic():
    """Test VRF cipher produces consistent output for AniKoto VRF param."""
    result = vrf_encrypt("test-query")
    assert isinstance(result, str)
    assert len(result) > 0
    assert vrf_encrypt("test-query") == result


def test_parse_listing_prefers_japanese_title(source: Anikoto):
    """Test JP title preference, thumbnail extraction, and pagination."""
    animes, has_next = source._parse_listing(LISTING_HTML)

    assert has_next is True
    assert len(animes) == 1
    assert isinstance(animes[0], Anime)
    assert animes[0].id == "frieren-1"
    assert animes[0].title == "葬送のフリーレン"
    assert animes[0].url == "/watch/frieren-1"
    assert animes[0].thumbnail == "https://img.example/frieren.jpg"


@pytest.mark.asyncio
async def test_get_details_extracts_internal_id_and_metadata(source: Anikoto):
    """Test details page metadata extraction and composite IDs."""
    source._request = AsyncMock(return_value=(200, DETAILS_HTML))

    anime = await source.get_details("frieren-1")

    assert isinstance(anime, Anime)
    assert anime.id == "internal-999"
    assert anime.title == "葬送のフリーレン"
    assert anime.url == "/watch/frieren-1#internal-999"
    assert anime.genres == ["Fantasy", "Drama"]
    assert anime.studios == ["Madhouse"]
    assert anime.status == "completed"
    assert anime.score == 9.3
    assert anime.description == "An elf mage reflects on her journey."
    assert "Beyond Journey's End" in anime.alternative_titles


@pytest.mark.asyncio
async def test_get_episodes_reverse_and_parse_timestamps(source: Anikoto):
    """Test episodes reversed, flags parsed, and IDs built."""
    source._get_json = AsyncMock(return_value=(200, {"result": EPISODES_HTML}))

    episodes = await source.get_episodes("/watch/frieren-1#internal-999")

    assert [ep.number for ep in episodes] == [2.0, 1.0]
    assert episodes[0].is_filler is True
    assert episodes[0].has_dub is True
    assert episodes[0].title == "Episode 2"
    assert "ep-id-2" in episodes[0].id
    assert episodes[1].has_sub is True
    assert episodes[1].title == "The Journey"
    assert episodes[1].released_at is not None


@pytest.mark.asyncio
async def test_get_servers_filters_downloads_and_resolves_types(source: Anikoto):
    """Test server parsing with type resolution: sub, dub, h-sub."""
    source._get_json = AsyncMock(return_value=(200, {"result": SERVERS_HTML}))

    servers = await source.get_servers("ep-id-1&epurl=/watch/frieren-1/ep-1")

    assert len(servers) == 3
    assert isinstance(servers[0], Server)
    assert servers[0].id == "srv-1"
    assert servers[0].type == "sub"
    assert servers[1].type == "h-sub"
    assert servers[2].type == "dub"


def test_resolve_video_type(source: Anikoto):
    """Test label-to-type mapping: dub, h-sub, and sub fallback."""
    assert source._resolve_video_type("dub") == "dub"
    assert source._resolve_video_type("h-sub") == "h-sub"
    assert source._resolve_video_type("hsub") == "h-sub"
    assert source._resolve_video_type("sub") == "sub"
    assert source._resolve_video_type("unknown") == "sub"
