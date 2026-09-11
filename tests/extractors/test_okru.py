"""Unit tests for Okru extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.okru import OkruExtractor


def _async_ctx(resp):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.http = MagicMock()
    ctx.http.get = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_okru_extractor_direct_videos(mock_context):
    extractor = OkruExtractor(context=mock_context)

    html_content = """
    <html>
        <body>
            <div data-options="{&quot;flashvars&quot;:{&quot;metadata&quot;:&quot;{\\&quot;videos\\&quot;:[{\\&quot;name\\&quot;:\\&quot;hd\\&quot;,\\&quot;url\\&quot;:\\&quot;https://cdn.ok.ru/video_720.mp4\\&quot;},{\\&quot;name\\&quot;:\\&quot;sd\\&quot;,\\&quot;url\\&quot;:\\&quot;https://cdn.ok.ru/video_480.mp4\\&quot;}]}&quot;}}"></div>
        </body>
    </html>
    """

    mock_context.http.get.return_value = html_content

    streams = await extractor.extract("https://ok.ru/videoembed/123456", label_prefix="Okru")
    assert len(streams) == 2
    assert streams[0].url == "https://cdn.ok.ru/video_720.mp4"
    assert "720p" in streams[0].quality
    assert streams[1].url == "https://cdn.ok.ru/video_480.mp4"
    assert "480p" in streams[1].quality
