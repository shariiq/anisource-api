"""Unit tests for StreamWish extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.streamwish import StreamWishExtractor


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
async def test_streamwish_extractor_success(mock_context):
    extractor = StreamWishExtractor(context=mock_context)

    html_content = """
    <html>
        <body>
            <script>
                var player = jwplayer("vplayer");
                player.setup({
                    file: "https://wish.cdn.com/hls/stream.m3u8",
                });
            </script>
        </body>
    </html>
    """

    hls_m3u8 = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720
https://wish.cdn.com/hls/720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080
https://wish.cdn.com/hls/1080p.m3u8
"""

    mock_html_resp = MagicMock()
    mock_html_resp.status = 200
    mock_html_resp.text = AsyncMock(return_value=html_content)

    mock_hls_resp = MagicMock()
    mock_hls_resp.status = 200
    mock_hls_resp.text = AsyncMock(return_value=hls_m3u8)

    mock_context.http.session.get.side_effect = [
        _async_ctx(mock_html_resp),
        _async_ctx(mock_hls_resp),
    ]

    streams = await extractor.extract("https://streamwish.com/e/abc12345")
    assert len(streams) == 2
    assert streams[0].url == "https://wish.cdn.com/hls/720p.m3u8"
    assert "720p" in streams[0].quality
    assert streams[1].url == "https://wish.cdn.com/hls/1080p.m3u8"
    assert "1080p" in streams[1].quality
