"""Unit tests for EchoVideo extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.echovideo import EchoVideoExtractor
from anime_extensions.models import Stream


def _async_ctx(resp):
    """Helper to create async context manager from mock response."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.http = MagicMock()
    ctx.http.session = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_echovideo_extractor_m3u8(mock_context):
    """Test extraction of HLS stream from EchoVideo."""
    extractor = EchoVideoExtractor(context=mock_context)

    sources_json = {
        "sources": "https://cdn.echovideo.ru/playlist.m3u8",
        "tracks": [
            {"file": "https://subs.example.com/en.vtt", "label": "English", "kind": "subtitles"}
        ],
    }

    mock_sources_resp = MagicMock()
    mock_sources_resp.status = 200
    mock_sources_resp.json = AsyncMock(return_value=sources_json)

    mock_hls_resp = MagicMock()
    mock_hls_resp.status = 200
    mock_hls_resp.text = AsyncMock(
        return_value="""#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
1080p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
720p.m3u8
"""
    )

    mock_context.http.session.get.side_effect = [
        _async_ctx(mock_sources_resp),
        _async_ctx(mock_hls_resp),
    ]

    streams = await extractor.extract("https://play.echovideo.ru/embed/abc123")

    assert len(streams) > 0
    assert all(isinstance(s, Stream) for s in streams)
    assert any("1080p" in s.quality for s in streams)
    assert streams[0].subtitles[0].url == "https://subs.example.com/en.vtt"


@pytest.mark.asyncio
async def test_echovideo_extractor_quality_files(mock_context):
    """Test extraction of DatSaV quality-keyed files."""
    extractor = EchoVideoExtractor(context=mock_context)

    sources_json = {
        "sources": {
            "qualityFiles": {
                "FHD": ["https://cdn.datsav.com/video_1080p.mp4"],
                "HD": ["https://cdn.datsav.com/video_720p.mp4"],
            }
        },
        "subtitles": [],
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=sources_json)

    mock_context.http.session.get.return_value = _async_ctx(mock_resp)

    streams = await extractor.extract("https://datsav.com/embed/xyz789", label_prefix="Server 2")

    assert len(streams) == 2
    assert any("Server 2 - 1080p" in s.quality for s in streams)
    assert any("Server 2 - 720p" in s.quality for s in streams)
    assert all(s.url.endswith(".mp4") for s in streams)
