"""Deterministic stream-resolution tests for MKissa."""

import json
from unittest.mock import MagicMock

import pytest

from anime_extensions.sources.mkissa import MKissa
from anime_extensions.sources.mkissa.source import STREAM_HASH, STREAM_QUERY
from anime_extensions.utils.mkissa_crypto import MKissaCrypto


def test_stream_query_hash_is_stable() -> None:
    """Keep APQ query text and its derived SHA-256 hash in lockstep."""
    assert STREAM_QUERY == (
        "query(\n"
        "    $showId: String!\n"
        "    $translationType: VaildTranslationTypeEnumType!\n"
        "    $episodeString: String!\n"
        ") {\n"
        "    episode(\n"
        "        showId: $showId\n"
        "        translationType: $translationType\n"
        "        episodeString: $episodeString\n"
        "    ) {\n"
        "        sourceUrls\n"
        "        show {\n"
        "            _id\n"
        "        }\n"
        "    }\n"
        "}"
    )
    assert MKissaCrypto.sha256_hex(STREAM_QUERY) == STREAM_HASH


def test_source_urls_supports_decrypted_top_level_episode() -> None:
    """Accept MKissa's encrypted payload shape after AES-GCM decryption."""
    key = b"k" * 32
    payload = json.dumps(
        {
            "episode": {
                "sourceUrls": [
                    {"sourceUrl": "https://cdn.example/video.m3u8", "sourceName": "Default"}
                ]
            }
        },
        separators=(",", ":"),
    )
    encrypted = _encrypt(payload, key)
    response = json.dumps({"data": {"tobeparsed": encrypted}})

    source_urls = MKissa._source_urls_from_response(response, key)

    assert source_urls == [{"sourceUrl": "https://cdn.example/video.m3u8", "sourceName": "Default"}]


@pytest.mark.asyncio
async def test_stream_resolution_preserves_direct_url_and_priority() -> None:
    """Direct HTTP sources remain usable without an unnecessary extractor round trip."""
    context = MagicMock()
    source = MKissa(context=context)

    streams = await source._streams_from_sources(
        [
            {"sourceUrl": "https://cdn.example/low.m3u8", "sourceName": "Low", "priority": 1},
            {"sourceUrl": "//cdn.example/high.m3u8", "sourceName": "High", "priority": 10},
        ]
    )

    assert [stream.url for stream in streams] == [
        "https://cdn.example/high.m3u8",
        "https://cdn.example/low.m3u8",
    ]
    assert all(stream.is_hls for stream in streams)


@pytest.mark.asyncio
async def test_internal_source_resolves_hls_subtitles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve MKissa's internal player JSON endpoint into a playable HLS stream."""
    context = MagicMock()
    source = MKissa(context=context)

    async def get_json(url: str, **_: object) -> object:
        assert url == "https://allanime.day/apivtwo/clock.json?id=42"
        return {
            "links": [
                {
                    "link": "https://cdn.example/master.m3u8",
                    "hls": True,
                    "resolutionStr": "1080p",
                    "subtitles": [{"src": "https://cdn.example/en.vtt", "lang": "en"}],
                }
            ]
        }

    monkeypatch.setattr(source, "_get_json", get_json)
    streams = await source._streams_from_sources(
        [{"sourceUrl": "/apivtwo/clock?id=42", "sourceName": "Ac-Hls", "priority": 5}]
    )

    assert len(streams) == 1
    assert streams[0].url == "https://cdn.example/master.m3u8"
    assert streams[0].is_hls
    assert streams[0].subtitles[0].language == "en"


def _encrypt(payload: str, key: bytes) -> str:
    """Build a wire-compatible AES-GCM response for parser coverage."""
    from base64 import b64encode

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iv = b"i" * 12
    return b64encode(b"\x01" + iv + AESGCM(key).encrypt(iv, payload.encode(), None)).decode()
