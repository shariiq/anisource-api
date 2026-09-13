"""Deterministic tests for MegaPlay extractor."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from anime_extensions.extractors.megaplay import MegaPlayExtractor
from anime_extensions.models import Stream


@pytest.fixture
def extractor() -> MegaPlayExtractor:
    context = MagicMock()
    context.http = MagicMock()
    return MegaPlayExtractor(context)


def _encrypt_megaplay_payload(payload: dict) -> str:
    """Helper to encrypt test payloads matching MegaPlay AES-CBC cipher."""
    plaintext = json.dumps(payload).encode("utf-8")
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len]) * pad_len
    key = b"i?LMTAx0Q6,:}50U".ljust(32, b"\0")[:32]
    iv = b"W0;27ToaUpl_P%'c"
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend()).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8").replace("+", "-").replace("/", "_")


def test_decrypt_megaplay_sources_success():
    """Test MegaPlay AES-CBC decryption with dual payload shapes."""
    # Test shape with "file"
    enc_file = _encrypt_megaplay_payload({"file": "https://server.test/master.m3u8"})
    decrypted_file = MegaPlayExtractor._decrypt_megaplay_sources(enc_file)
    assert decrypted_file == {"file": "https://server.test/master.m3u8"}

    # Test shape with "sources"
    enc_sources = _encrypt_megaplay_payload(
        {"sources": [{"file": "https://server.test/master.m3u8"}]}
    )
    decrypted_sources = MegaPlayExtractor._decrypt_megaplay_sources(enc_sources)
    assert decrypted_sources == {"sources": [{"file": "https://server.test/master.m3u8"}]}


def test_decrypt_megaplay_sources_invalid():
    """Test invalid payloads return None gracefully."""
    assert MegaPlayExtractor._decrypt_megaplay_sources("") is None
    assert MegaPlayExtractor._decrypt_megaplay_sources(None) is None
    assert MegaPlayExtractor._decrypt_megaplay_sources("invalid-base64-payload!!!") is None
    assert MegaPlayExtractor._decrypt_megaplay_sources(12345) is None


@pytest.mark.asyncio
async def test_fetch_sources_from_api_decryption_and_subtitles(extractor: MegaPlayExtractor):
    """Test _fetch_sources_from_api decrypts enc payload and extracts subtitles."""
    enc = _encrypt_megaplay_payload({"file": "https://stream.host/master.m3u8"})
    api_response = {
        "enc": enc,
        "tracks": [
            {"kind": "captions", "file": "https://sub.host/en.vtt", "label": "English"},
            {"kind": "thumbnails", "file": "https://sub.host/thumb.vtt"},
        ],
    }
    extractor.context.http.get_json = AsyncMock(return_value=api_response)

    streams = await extractor._fetch_sources_from_api(
        data_id="12345",
        host="megaplay.buzz",
        embed_url="https://megaplay.buzz/stream/s-1/12345/sub",
        quality_prefix="Test",
    )

    assert len(streams) == 1
    assert streams[0].url == "https://stream.host/master.m3u8"
    assert streams[0].quality == "Test - Auto"
    assert streams[0].is_hls is True
    assert streams[0].headers["Referer"] == "https://megaplay.buzz/stream/s-1/12345/sub"
    assert streams[0].headers["Origin"] == "https://megaplay.buzz"

    assert len(streams[0].subtitles) == 1
    assert streams[0].subtitles[0].url == "https://sub.host/en.vtt"
    assert streams[0].subtitles[0].label == "English"

    # Assert API call
    extractor.context.http.get_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_fallback_to_html_m3u8(extractor: MegaPlayExtractor):
    """Test fallback to regex parsing m3u8 in HTML."""
    html_content = """
    <html>
        <body>
            <script>
                var url = "https://stream.host/video.m3u8";
            </script>
        </body>
    </html>
    """
    extractor.context.http.get = AsyncMock(return_value=html_content)

    streams = await extractor.extract("https://nexabloom.top/stream/hash")

    assert len(streams) == 1
    assert streams[0].url == "https://stream.host/video.m3u8"
    assert streams[0].quality == "Auto"
    assert streams[0].is_hls is True
    assert streams[0].headers["Referer"] == "https://nexabloom.top/stream/hash"
    assert streams[0].headers["Origin"] == "https://nexabloom.top"


@pytest.mark.asyncio
async def test_extract_resolves_data_id(extractor: MegaPlayExtractor):
    """Test extracting data-id and cascading to API call."""
    html_content = """<div id="watch" data-id="123456"></div>"""
    extractor.context.http.get = AsyncMock(return_value=html_content)

    # Mock the API flow
    extractor._fetch_sources_from_api = AsyncMock(
        return_value=[
            Stream(url="https://api.host/api.m3u8", quality="Auto", is_hls=True, headers={})
        ]
    )

    streams = await extractor.extract("https://nexabloom.top/stream/hash")

    assert len(streams) == 1
    assert streams[0].url == "https://api.host/api.m3u8"
    extractor._fetch_sources_from_api.assert_awaited_once_with(
        "123456", "nexabloom.top", "https://nexabloom.top/stream/hash", "", None
    )
