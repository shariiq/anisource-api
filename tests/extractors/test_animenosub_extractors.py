"""Tests for AnimeNoSub extractors."""

import base64
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from anime_extensions.extractors.moon import MoonExtractor
from anime_extensions.extractors.streamwish import StreamWishExtractor
from anime_extensions.extractors.vidmoly import VidMolyExtractor
from anime_extensions.extractors.vtube import VtubeExtractor
from anime_extensions.extractors.wolfstream import WolfStreamExtractor


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.http = MagicMock()
    ctx.http.get = AsyncMock()
    ctx.http.get_json = AsyncMock()
    ctx.http.post_json = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_moon_extractor(mock_context):
    extractor = MoonExtractor(context=mock_context)

    mock_context.http.get_json.return_value = {"embed_frame_url": "https://embed.moon/embed/123"}
    mock_context.http.post_json.return_value = {"sources": [{"url": "https://moon/video.m3u8"}]}

    with patch("anime_extensions.extractors.moon.parse_m3u8_streams") as mock_parse:
        mock_parse.return_value = [MagicMock()]
        streams = await extractor.extract(
            "https://moon/video/123", site_url="https://animenosub.to"
        )

        assert streams
        mock_context.http.get_json.assert_called_once()
        mock_context.http.post_json.assert_called_once()
        args, kwargs = mock_context.http.get.call_args
        assert args[0] == "https://moon/video.m3u8"
        assert isinstance(kwargs.get("headers"), dict)


@pytest.mark.asyncio
async def test_moon_extractor_encrypted_payload(mock_context):
    extractor = MoonExtractor(context=mock_context)

    key = AESGCM.generate_key(bit_length=256)
    part1 = base64.urlsafe_b64encode(key[:16]).decode().rstrip("=")
    part2 = base64.urlsafe_b64encode(key[16:]).decode().rstrip("=")

    iv = os.urandom(12)
    iv_b64 = base64.urlsafe_b64encode(iv).decode().rstrip("=")

    inner_json = json.dumps({"sources": [{"url": "https://moon/encrypted_video.m3u8"}]}).encode()
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, inner_json, None)
    payload_b64 = base64.urlsafe_b64encode(ciphertext).decode().rstrip("=")

    mock_context.http.get_json.return_value = {"embed_frame_url": "https://embed.moon/embed/123"}
    mock_context.http.post_json.return_value = {
        "playback": {
            "key_parts": [part1, part2],
            "iv": iv_b64,
            "payload": payload_b64,
        }
    }

    with patch("anime_extensions.extractors.moon.parse_m3u8_streams") as mock_parse:
        mock_parse.return_value = [MagicMock()]
        streams = await extractor.extract(
            "https://moon/video/123", site_url="https://animenosub.to"
        )

        assert streams
        args, kwargs = mock_context.http.get.call_args
        assert args[0] == "https://moon/encrypted_video.m3u8"


@pytest.mark.asyncio
async def test_vidmoly_extractor(mock_context):
    extractor = VidMolyExtractor(context=mock_context)
    html = """
    <script>
    sources: [{file: "https://vidmoly.biz/video.m3u8"}],
    </script>
    """
    mock_context.http.get.return_value = html

    with patch("anime_extensions.extractors.vidmoly.parse_m3u8_streams") as mock_parse:
        mock_parse.return_value = [MagicMock()]
        streams = await extractor.extract("https://vidmoly.biz/embed-123")

        assert streams
        assert mock_context.http.get.call_count == 2  # Once for HTML, once for M3U8


@pytest.mark.asyncio
async def test_streamwish_extractor(mock_context):
    extractor = StreamWishExtractor(context=mock_context)
    html = """
    <script>
    var m3u8 = "https://streamwish.com/master.m3u8";
    </script>
    """
    playlist = "#EXTM3U"

    mock_context.http.get.side_effect = [html, playlist]

    with patch("anime_extensions.extractors.streamwish.parse_m3u8_streams") as mock_parse:
        mock_parse.return_value = [MagicMock()]
        streams = await extractor.extract("https://streamwish.com/e/123")

        assert streams
        assert mock_context.http.get.call_count == 2


@pytest.mark.asyncio
async def test_vtube_extractor(mock_context):
    extractor = VtubeExtractor(context=mock_context)
    html = """
    <script>
    sources: [{file: "https://vtbe.to/video.m3u8"}],
    </script>
    """
    mock_context.http.get.return_value = html

    with patch("anime_extensions.extractors.vtube.parse_m3u8_streams") as mock_parse:
        mock_parse.return_value = [MagicMock()]
        streams = await extractor.extract("https://vtbe.to/embed-123")

        assert streams
        assert mock_context.http.get.call_count == 2


@pytest.mark.asyncio
async def test_wolfstream_extractor(mock_context):
    extractor = WolfStreamExtractor(context=mock_context)
    html = """
    <script>
    sources: [{file: "https://wolfstream.tv/video.mp4"}],
    </script>
    """
    mock_context.http.get.return_value = html

    streams = await extractor.extract("https://wolfstream.tv/embed-123")

    assert streams
    assert streams[0].url == "https://wolfstream.tv/video.mp4"
    assert streams[0].headers["Referer"] == "https://wolfstream.tv/embed-123"
