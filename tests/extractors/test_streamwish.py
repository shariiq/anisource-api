"""Unit tests for StreamWish extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.streamwish import StreamWishExtractor


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.http = MagicMock()
    # Explicitly mock get as an async function
    ctx.http.get = AsyncMock()
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

    mock_context.http.get.side_effect = [
        html_content,
        hls_m3u8,
    ]

    streams = await extractor.extract("https://streamwish.com/e/abc12345")
    assert len(streams) == 2
    assert streams[0].url == "https://wish.cdn.com/hls/720p.m3u8"
    assert "720p" in streams[0].quality
    assert streams[1].url == "https://wish.cdn.com/hls/1080p.m3u8"
    assert "1080p" in streams[1].quality
