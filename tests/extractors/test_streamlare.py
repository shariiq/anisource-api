"""Unit tests for Streamlare extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.streamlare import StreamlareExtractor


def _async_ctx(resp):
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
async def test_streamlare_extractor_direct(mock_context):
    extractor = StreamlareExtractor(context=mock_context)

    mock_api_resp = MagicMock()
    mock_api_resp.status = 200
    mock_api_resp.json = AsyncMock(
        return_value={
            "status": "success",
            "result": {
                "1080p": {"file": "https://streamlare.com/download/1080p"},
                "720p": {"file": "https://streamlare.com/download/720p"},
            },
        }
    )

    mock_file_resp_1 = MagicMock()
    mock_file_resp_1.status = 200
    mock_file_resp_1.url = "https://cdn.streamlare.com/video_1080p.mp4"

    mock_file_resp_2 = MagicMock()
    mock_file_resp_2.status = 200
    mock_file_resp_2.url = "https://cdn.streamlare.com/video_720p.mp4"

    mock_context.http.session.post.side_effect = [
        _async_ctx(mock_api_resp),
        _async_ctx(mock_file_resp_1),
        _async_ctx(mock_file_resp_2),
    ]

    streams = await extractor.extract("https://streamlare.com/e/abc12345")
    assert len(streams) == 2
    assert streams[0].url == "https://cdn.streamlare.com/video_1080p.mp4"
    assert "1080p" in streams[0].quality
    assert streams[1].url == "https://cdn.streamlare.com/video_720p.mp4"
    assert "720p" in streams[1].quality
