"""Unit tests for Mp4Upload extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.mp4upload import Mp4UploadExtractor


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
async def test_mp4upload_extractor_success(mock_context):
    extractor = Mp4UploadExtractor(context=mock_context)

    html_content = """
    <html>
        <body>
            <script>
                player.src({src: "https://www123.mp4upload.com:282/d/abc/video.mp4"});
                var HEIGHT=1080;
            </script>
        </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value=html_content)

    mock_context.http.session.get.return_value = _async_ctx(mock_resp)

    streams = await extractor.extract("https://www.mp4upload.com/embed-abc12345.html")
    assert len(streams) == 1
    assert streams[0].url == "https://www123.mp4upload.com:282/d/abc/video.mp4"
    assert "1080p" in streams[0].quality
