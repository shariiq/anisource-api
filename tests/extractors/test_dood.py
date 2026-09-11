"""Unit tests for Doodstream extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.dood import DoodExtractor
from anime_extensions.models import Stream, Subtitle


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
async def test_dood_extractor_success(mock_context):
    """Test standard extraction workflow with mocked network responses."""
    extractor = DoodExtractor(context=mock_context)

    # Mock embed page HTML
    embed_html = """
    <html>
        <head><title>Watch Anime 720p - DoodStream</title></head>
        <body>
            <script>
                var a = '/pass_md5/my_secret_token_123';
            </script>
        </body>
    </html>
    """

    mock_embed_resp = MagicMock()
    mock_embed_resp.url = "https://dood.to/e/abcdef12345"
    mock_embed_resp.text = AsyncMock(return_value=embed_html)

    # Mock pass_md5 endpoint response
    mock_pass_resp = MagicMock()
    mock_pass_resp.text = AsyncMock(return_value="https://video-cdn.dood.to/stream/")

    # Setup session.get to return context managers
    mock_context.http.session.get.side_effect = [
        _async_ctx(mock_embed_resp),
        _async_ctx(mock_pass_resp),
    ]

    subs = [Subtitle(url="https://example.com/sub.vtt", label="English", language="en")]
    streams = await extractor.extract(
        "https://dood.to/e/abcdef12345",
        quality_prefix="Mirror 1",
        external_subs=subs,
    )

    assert len(streams) == 1
    stream = streams[0]
    assert isinstance(stream, Stream)
    assert "Mirror 1 - Doodstream 720p" in stream.quality
    assert stream.url.startswith("https://video-cdn.dood.to/stream/")
    assert "token=my_secret_token_123" in stream.url
    assert "expiry=" in stream.url
    assert stream.subtitles == subs
    assert stream.is_hls is False


@pytest.mark.asyncio
async def test_dood_extractor_no_pass_md5(mock_context):
    """Test extractor returning empty list when pass_md5 is not present."""
    extractor = DoodExtractor(context=mock_context)

    embed_html = "<html><body>Protected / No token available</body></html>"
    mock_embed_resp = MagicMock()
    mock_embed_resp.url = "https://dood.to/e/abcdef12345"
    mock_embed_resp.text = AsyncMock(return_value=embed_html)

    mock_context.http.session.get.return_value = _async_ctx(mock_embed_resp)

    streams = await extractor.extract("https://dood.to/e/abcdef12345")
    assert streams == []
