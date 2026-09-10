"""Deterministic tests for Miruro pipe API parsing and stream extraction."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from anime_extensions.models import Anime, Server, Stream
from anime_extensions.sources.miruro import Miruro

# ── Fixture responses (pipe API JSON) ────────────────────────────────────────

POPULAR_DATA = {
    "media": [
        {
            "id": 154587,
            "title": {"userPreferred": "Frieren", "romaji": "Sousou no Frieren"},
            "coverImage": {"extraLarge": "https://img.example/frieren.jpg"},
            "status": "FINISHED",
        },
        {
            "id": 21,
            "title": {"userPreferred": "One Piece"},
            "coverImage": {"large": "https://img.example/one-piece.jpg"},
        },
    ],
    "pageInfo": {"hasNextPage": True},
}

DETAILS_DATA = {
    "media": {
        "id": 154587,
        "title": {"userPreferred": "Frieren", "romaji": "Sousou no Frieren"},
        "description": "An elf mage reflects on her journey.",
        "genres": ["Fantasy", "Adventure", "Drama"],
        "studios": {
            "edges": [
                {"isMain": True, "node": {"name": "Madhouse"}},
                {"isMain": False, "node": {"name": "Another Studio"}},
            ]
        },
        "status": "FINISHED",
        "averageScore": 91,
        "coverImage": {"extraLarge": "https://img.example/frieren.jpg"},
    }
}

EPISODES_DATA = {
    "providers": {
        "kiwi": {
            "episodes": {
                "sub": [
                    {"number": 1, "title": "The Journey Begins", "id": "kiwi-sub-ep1"},
                    {"number": 2, "title": "", "id": "kiwi-sub-ep2"},
                    {"number": 3, "title": "Rite of Passage", "id": "kiwi-sub-ep3"},
                ],
                "dub": [
                    {"number": 1, "title": "The Journey Begins", "id": "kiwi-dub-ep1"},
                    {"number": 2, "title": "", "id": "kiwi-dub-ep2"},
                ],
            }
        },
        "bee": {
            "episodes": {
                "sub": [
                    {"number": 1, "title": "", "id": "bee-sub-ep1"},
                ]
            }
        },
    }
}

STREAMS_DATA = {
    "streams": [
        {
            "url": "https://cdn.kwik.cx/video.m3u8",
            "quality": "1080",
            "type": "hls",
            "referer": "https://kwik.cx/",
            "codec": "h264",
            "audio": "aac",
            "resolution": {"width": 1920, "height": 1080},
        },
        {
            "url": "https://cdn.kwik.cx/video-720.m3u8",
            "quality": "720",
            "type": "hls",
            "referer": "https://kwik.cx/",
        },
        {
            # Embed streams should be skipped in the Python MVP
            "url": "https://megacloud.tv/embed/abc",
            "quality": "1080",
            "type": "embed",
            "referer": "",
        },
    ],
    "subtitles": [
        {"url": "https://cdn.example/en.vtt", "label": "English", "language": "en"},
        {"url": "https://cdn.example/es.vtt", "label": "Spanish", "language": "es"},
    ],
}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def source() -> Miruro:
    return Miruro(domain="miruro.tv")


# ── Listing Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_popular_parses_media_array(source: Miruro) -> None:
    """Test popular endpoint returns correct Anime objects and pagination signal."""
    source._pipe_get = AsyncMock(return_value=POPULAR_DATA)

    animes, has_next = await source.get_popular(page=1)

    assert has_next is True
    assert len(animes) == 2
    assert isinstance(animes[0], Anime)
    assert animes[0].id == "154587"
    assert animes[0].title == "Frieren"
    assert animes[0].thumbnail == "https://img.example/frieren.jpg"
    assert animes[0].url == "154587"  # Miruro uses AniList ID as URL


@pytest.mark.asyncio
async def test_get_latest_uses_updated_at_sort(source: Miruro) -> None:
    """Test that get_latest passes the correct sort parameter."""
    source._pipe_get = AsyncMock(return_value={"media": [], "pageInfo": {"hasNextPage": False}})

    await source.get_latest(page=2)

    source._pipe_get.assert_awaited_once()
    call_args = source._pipe_get.call_args
    assert call_args.args[0] == "search/browse"
    query = call_args.args[1]
    assert query["sort"] == "UPDATED_AT_DESC"
    assert query["page"] == 2


@pytest.mark.asyncio
async def test_search_text_query_uses_search_endpoint(source: Miruro) -> None:
    """Test text search calls the 'search' path with correct parameters."""
    source._pipe_get = AsyncMock(return_value={"media": []})

    await source.search("frieren", page=2)

    call_args = source._pipe_get.call_args
    assert call_args.args[0] == "search"
    query = call_args.args[1]
    assert query["q"] == "frieren"
    assert query["offset"] == 20  # (page=2 - 1) * 20


@pytest.mark.asyncio
async def test_search_prefix_routes_to_info_endpoint(source: Miruro) -> None:
    """Test miruro:<id> prefix search calls info/<id> directly."""
    source._pipe_get = AsyncMock(return_value=DETAILS_DATA)

    animes, has_next = await source.search("miruro:154587")

    assert has_next is False
    assert len(animes) == 1
    source._pipe_get.assert_awaited_once_with("info/154587")


# ── Details Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_details_extracts_full_metadata(source: Miruro) -> None:
    """Test details parsing with genres, studios, status, and score."""
    source._pipe_get = AsyncMock(return_value=DETAILS_DATA)

    anime = await source.get_details("154587")

    assert isinstance(anime, Anime)
    assert anime.id == "154587"
    assert anime.title == "Frieren"
    assert anime.description == "An elf mage reflects on her journey."
    assert anime.genres == ["Fantasy", "Adventure", "Drama"]
    assert anime.studios == ["Madhouse"]  # Only isMain=True studio
    assert anime.status == "completed"
    assert anime.score == pytest.approx(9.1, abs=0.01)  # 91 / 10


@pytest.mark.asyncio
async def test_get_details_handles_missing_fields(source: Miruro) -> None:
    """Test details parsing degrades gracefully when fields are absent."""
    source._pipe_get = AsyncMock(return_value={"media": {"id": 42, "title": {}}})

    anime = await source.get_details("42")

    assert anime.id == "42"
    assert anime.title == "Unknown"
    assert anime.genres == []
    assert anime.studios == []
    assert anime.status == "unknown"
    assert anime.score is None


# ── Episode Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_episodes_selects_preferred_provider(source: Miruro) -> None:
    """Test episode list uses preferred provider (kiwi) over alternatives."""
    source._pipe_get = AsyncMock(return_value=EPISODES_DATA)

    episodes = await source.get_episodes("154587")

    # kiwi has 3 episodes (sub has ep1,2,3 — dub has ep1,2; merged gives 3 unique)
    assert len(episodes) == 3
    # Sorted descending — highest episode first
    assert episodes[0].number == 3.0
    assert episodes[2].number == 1.0


@pytest.mark.asyncio
async def test_get_episodes_episode_ids_are_valid_json(source: Miruro) -> None:
    """Test that each episode ID is a parseable JSON envelope."""
    source._pipe_get = AsyncMock(return_value=EPISODES_DATA)

    episodes = await source.get_episodes("154587")

    for ep in episodes:
        ep_data = json.loads(ep.id)  # Must not raise
        assert "episodeId" in ep_data
        assert "provider" in ep_data
        assert "defaultSubType" in ep_data
        assert "subTypes" in ep_data
        assert ep_data["anilistId"] == "154587"
        assert ep_data["provider"] == "kiwi"


@pytest.mark.asyncio
async def test_get_episodes_has_sub_and_dub_flags(source: Miruro) -> None:
    """Test has_sub and has_dub flags are set correctly when both sub-types available."""
    source._pipe_get = AsyncMock(return_value=EPISODES_DATA)

    episodes = await source.get_episodes("154587")

    # Episodes 1 and 2 have both sub and dub from kiwi
    ep_by_num = {ep.number: ep for ep in episodes}
    assert ep_by_num[1.0].has_sub is True
    assert ep_by_num[1.0].has_dub is True
    assert ep_by_num[2.0].has_sub is True
    assert ep_by_num[2.0].has_dub is True
    # Episode 3 is sub-only
    assert ep_by_num[3.0].has_sub is True
    assert ep_by_num[3.0].has_dub is False


@pytest.mark.asyncio
async def test_get_episodes_fallback_provider_when_preferred_absent(source: Miruro) -> None:
    """Test fallback to another provider when preferred 'kiwi' has no episodes."""
    data = {
        "providers": {
            "bee": {"episodes": {"sub": [{"number": 1, "title": "Ep 1", "id": "bee-ep1"}]}}
        }
    }
    source._pipe_get = AsyncMock(return_value=data)

    episodes = await source.get_episodes("999")

    assert len(episodes) == 1
    ep_data = json.loads(episodes[0].id)
    assert ep_data["provider"] == "bee"


@pytest.mark.asyncio
async def test_get_episodes_returns_empty_when_no_providers(source: Miruro) -> None:
    """Test empty list returned when providers object is absent."""
    source._pipe_get = AsyncMock(return_value={})

    episodes = await source.get_episodes("999")

    assert episodes == []


# ── Server Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_servers_surfaces_one_server_per_sub_type(source: Miruro) -> None:
    """Test that each available sub-type becomes a discrete server entry."""
    episode_id = json.dumps(
        {
            "episodeId": "kiwi-sub-ep1",
            "provider": "kiwi",
            "defaultSubType": "sub",
            "subTypes": {"sub": "kiwi-sub-ep1", "dub": "kiwi-dub-ep1"},
            "anilistId": "154587",
        }
    )

    servers = await source.get_servers(episode_id)

    assert len(servers) == 2
    assert isinstance(servers[0], Server)
    server_types = {s.id for s in servers}
    assert "sub" in server_types
    assert "dub" in server_types
    assert all("AnimePahe" in s.name for s in servers)
    assert servers[0].type == "sub"
    assert servers[1].type == "dub"


@pytest.mark.asyncio
async def test_get_servers_returns_empty_on_invalid_json(source: Miruro) -> None:
    """Test graceful empty result for malformed episode ID."""
    servers = await source.get_servers("not-valid-json{{{")
    assert servers == []


# ── Stream Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_streams_proxies_hls_and_skips_embeds(source: Miruro) -> None:
    """Test that HLS streams are proxy-wrapped and embed streams are skipped."""
    source._pipe_get = AsyncMock(return_value=STREAMS_DATA)

    episode_id = json.dumps(
        {
            "episodeId": "kiwi-sub-ep1",
            "provider": "kiwi",
            "defaultSubType": "sub",
            "subTypes": {"sub": "kiwi-sub-ep1"},
            "anilistId": "154587",
        }
    )

    streams = await source.get_streams(episode_id, "sub")

    # 2 HLS streams; embed (megacloud) must be excluded
    assert len(streams) == 2
    assert all(isinstance(s, Stream) for s in streams)
    for s in streams:
        assert "vault" in s.url  # Proxied through vault01 or vault02
        assert s.is_hls is True
        assert ".m3u8" in s.url  # Vault URL ends with /pl.m3u8
        assert s.headers.get("Referer") == "https://miruro.tv/"


@pytest.mark.asyncio
async def test_get_streams_quality_labels_include_provider_and_sub_type(source: Miruro) -> None:
    """Test quality label contains provider name, quality, sub-type, and HLS tag."""
    source._pipe_get = AsyncMock(return_value=STREAMS_DATA)

    episode_id = json.dumps(
        {
            "episodeId": "kiwi-sub-ep1",
            "provider": "kiwi",
            "defaultSubType": "sub",
            "subTypes": {"sub": "kiwi-sub-ep1"},
            "anilistId": "154587",
        }
    )

    streams = await source.get_streams(episode_id, "sub")

    assert len(streams) >= 1
    # First stream has full metadata (codec, audio, resolution)
    first = streams[0]
    assert "AnimePahe" in first.quality
    assert "1080p" in first.quality
    assert "Sub" in first.quality
    assert "HLS" in first.quality
    assert "1920x1080" in first.quality


@pytest.mark.asyncio
async def test_get_streams_attaches_subtitles_to_all_streams(source: Miruro) -> None:
    """Test that subtitle tracks are attached to every returned stream."""
    source._pipe_get = AsyncMock(return_value=STREAMS_DATA)

    episode_id = json.dumps(
        {
            "episodeId": "kiwi-sub-ep1",
            "provider": "kiwi",
            "defaultSubType": "sub",
            "subTypes": {"sub": "kiwi-sub-ep1"},
            "anilistId": "154587",
        }
    )

    streams = await source.get_streams(episode_id, "sub")

    for stream in streams:
        assert len(stream.subtitles) == 2
        labels = {sub.label for sub in stream.subtitles}
        assert "English" in labels
        assert "Spanish" in labels


@pytest.mark.asyncio
async def test_get_streams_server_id_overrides_sub_type(source: Miruro) -> None:
    """Test that passing 'dub' as server_id fetches dub episode ID instead of sub."""
    captured_query: dict = {}

    async def fake_pipe_get(path: str, query: dict | None = None) -> dict:
        nonlocal captured_query
        if path == "sources":
            captured_query = query or {}
        return {"streams": [], "subtitles": []}

    source._pipe_get = fake_pipe_get

    episode_id = json.dumps(
        {
            "episodeId": "kiwi-sub-ep1",
            "provider": "kiwi",
            "defaultSubType": "sub",
            "subTypes": {"sub": "kiwi-sub-ep1", "dub": "kiwi-dub-ep1"},
            "anilistId": "154587",
        }
    )

    await source.get_streams(episode_id, "dub")

    assert captured_query.get("episodeId") == "kiwi-dub-ep1"
    assert captured_query.get("category") == "dub"


@pytest.mark.asyncio
async def test_get_streams_returns_empty_when_pipe_fails(source: Miruro) -> None:
    """Test graceful empty result when pipe API returns nothing."""
    source._pipe_get = AsyncMock(return_value={})

    episode_id = json.dumps(
        {
            "episodeId": "id",
            "provider": "kiwi",
            "defaultSubType": "sub",
            "subTypes": {"sub": "id"},
            "anilistId": "1",
        }
    )

    streams = await source.get_streams(episode_id, "sub")

    assert streams == []


# ── Crypto helper tests ────────────────────────────────────────────────────────


def test_miruro_proxy_url_contains_vault_domain(source: Miruro) -> None:
    """Test that proxy URL wrapping puts the stream behind vault01 or vault02."""
    from anime_extensions.utils.crypto import miruro_build_proxied_url

    proxied = miruro_build_proxied_url(
        stream_url="https://cdn.kwik.cx/video.m3u8",
        referer="https://kwik.cx/",
        proxy_seed="ep-id-123|154587",
    )

    assert "vault01.ultracloud.cc" in proxied or "vault02.ultracloud.cc" in proxied
    assert proxied.endswith("/pl.m3u8")
    # Proxy seed determinism: same seed always picks same vault
    proxied2 = miruro_build_proxied_url(
        stream_url="https://cdn.kwik.cx/video.m3u8",
        referer="https://kwik.cx/",
        proxy_seed="ep-id-123|154587",
    )
    assert proxied == proxied2


def test_miruro_pipe_url_is_base64url_encoded(source: Miruro) -> None:
    """Test that the pipe URL payload round-trips through base64url encoding."""
    import base64

    from anime_extensions.utils.crypto import miruro_build_pipe_url

    url = miruro_build_pipe_url(
        "https://www.miruro.tv",
        "search/browse",
        "GET",
        {"type": "ANIME", "page": 1},
    )

    assert "/api/secure/pipe?e=" in url

    # Extract and decode the payload
    encoded_payload = url.split("?e=", 1)[1]
    # Re-pad and decode
    padded = encoded_payload + "=" * ((4 - len(encoded_payload) % 4) % 4)
    payload_bytes = base64.urlsafe_b64decode(padded)
    payload = json.loads(payload_bytes.decode("utf-8"))

    assert payload["path"] == "search/browse"
    assert payload["method"] == "GET"
    assert payload["query"]["type"] == "ANIME"
    assert payload["version"] == "0.2.0"
