"""Unit tests for Doodstream extractor."""

from unittest.mock import AsyncMock, patch

import pytest

from anime_extensions.extractors.dood import DoodExtractor
from anime_extensions.models import Stream, Subtitle


@pytest.mark.asyncio
async def test_dood_extractor_success():
    """Test standard extraction workflow with mocked network responses."""
    extractor = DoodExtractor()

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

    mock_embed_resp = AsyncMock()
    mock_embed_resp.url = "https://dood.to/e/abcdef12345"
    mock_embed_resp.text = AsyncMock(return_value=embed_html)

    # Mock pass_md5 endpoint response
    mock_pass_resp = AsyncMock()
    mock_pass_resp.text = AsyncMock(return_value="https://video-cdn.dood.to/stream/")

    # Setup session.get context manager mocks
    mock_session = AsyncMock()
    mock_session.get.side_effect = [
        AsyncMock(__aenter__=AsyncMock(return_value=mock_embed_resp)),
        AsyncMock(__aenter__=AsyncMock(return_value=mock_pass_resp)),
    ]

    with patch.object(extractor, "_ensure_session", return_value=mock_session):
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
async def test_dood_extractor_no_pass_md5():
    """Test extractor returning empty list when pass_md5 is not present."""
    extractor = DoodExtractor()

    embed_html = "<html><body>Protected / No token available</body></html>"
    mock_embed_resp = AsyncMock()
    mock_embed_resp.url = "https://dood.to/e/abcdef12345"
    mock_embed_resp.text = AsyncMock(return_value=embed_html)

    mock_session = AsyncMock()
    mock_session.get.return_value = AsyncMock(__aenter__=AsyncMock(return_value=mock_embed_resp))

    with patch.object(extractor, "_ensure_session", return_value=mock_session):
        streams = await extractor.extract("https://dood.to/e/abcdef12345")
        assert streams == []
