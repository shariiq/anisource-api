"""Unit tests for EchoVideo (Vidplay / MyCloud) video extractor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anime_extensions.extractors.echovideo import EchoVideoExtractor
from anime_extensions.models import Stream


def _async_ctx(resp):
    """Helper to create async context manager from mock response."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


@pytest.mark.asyncio
async def test_echovideo_extractor_m3u8_flow():
    """Test EchoVideo extractor parsing master m3u8 playlist."""
    extractor = EchoVideoExtractor()

    # JSON returned by getSources
    api_payload = {
        "sources": [{"file": "https://cdn.echovideo.ru/hls/master.m3u8"}],
        "tracks": [
            {
                "file": "https://cdn.echovideo.ru/subs/en.vtt",
                "label": "English",
                "kind": "captions",
            }
        ],
    }

    # HLS Master playlist text
    master_hls = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1920x1080\n1080p/index.m3u8\n"
    )

    mock_api_resp = MagicMock()
    mock_api_resp.status = 200
    mock_api_resp.json = AsyncMock(return_value=api_payload)

    mock_hls_resp = MagicMock()
    mock_hls_resp.status = 200
    mock_hls_resp.text = AsyncMock(return_value=master_hls)

    mock_session = MagicMock()
    mock_session.get.side_effect = [
        _async_ctx(mock_api_resp),
        _async_ctx(mock_hls_resp),
    ]

    with patch.object(extractor, "_ensure_session", return_value=mock_session):
        streams = await extractor.extract(
            "https://play.echovideo.ru/embed/video123",
            label_prefix="Vidplay",
        )

        assert len(streams) == 1
        stream = streams[0]
        assert isinstance(stream, Stream)
        assert stream.quality == "Vidplay - 1080p"
        assert stream.url == "https://cdn.echovideo.ru/hls/1080p/index.m3u8"
        assert len(stream.subtitles) == 1
        assert stream.subtitles[0].label == "English"
        assert stream.is_hls is True


@pytest.mark.asyncio
async def test_echovideo_extractor_datsav_quality_files():
    """Test DatSaV shape with qualityFiles map."""
    extractor = EchoVideoExtractor()

    api_payload = {
        "sources": {
            "qualityFiles": {
                "FHD": ["https://cdn.echovideo.ru/direct/1080p.mp4"],
                "HD": ["https://cdn.echovideo.ru/direct/720p.mp4"],
            }
        },
        "tracks": [],
    }

    mock_api_resp = MagicMock()
    mock_api_resp.status = 200
    mock_api_resp.json = AsyncMock(return_value=api_payload)

    mock_session = MagicMock()
    mock_session.get.return_value = _async_ctx(mock_api_resp)

    with patch.object(extractor, "_ensure_session", return_value=mock_session):
        streams = await extractor.extract(
            "https://play.echovideo.ru/embed/video456",
            label_prefix="MyCloud",
        )

        assert len(streams) == 2
        qualities = {s.quality for s in streams}
        assert "MyCloud - 1080p" in qualities
        assert "MyCloud - 720p" in qualities
        assert all(not s.is_hls for s in streams)
