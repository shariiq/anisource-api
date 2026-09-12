from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.extractors.echovideo import EchoVideoExtractor


class MockHttp:
    pass


class MockContext:
    def __init__(self):
        self.http = MockHttp()


@pytest.fixture
def extractor():
    ctx = MockContext()
    ctx.http.session = MagicMock()
    return EchoVideoExtractor(ctx)


@pytest.mark.asyncio
async def test_echovideo_dghg_quality_map(extractor):
    """Test DGHG-style quality-keyed sources map."""
    embed_url = "https://play.echovideo.ru/embed/dghg-test-id"

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "sources": {
            "FHD": "https://example.com/fhd.m3u8",
            "HD": ["https://example.com/hd.m3u8"],
        },
        "tracks": [],
    }
    mock_resp.__aenter__.return_value = mock_resp
    mock_resp.__aexit__.return_value = None

    extractor.context.http.session.get.return_value = mock_resp

    streams = await extractor.extract(embed_url, label_prefix="DGHG")

    assert len(streams) == 2

    # Check FHD stream
    fhd = next(s for s in streams if "1080p" in s.quality)
    assert fhd.url == "https://example.com/fhd.m3u8"
    assert fhd.quality == "DGHG - 1080p"
    assert fhd.is_hls is True

    # Check HD stream
    hd = next(s for s in streams if "720p" in s.quality)
    assert hd.url == "https://example.com/hd.m3u8"
    assert hd.quality == "DGHG - 720p"
    assert hd.is_hls is True


@pytest.mark.asyncio
async def test_echovideo_fallback_get_sources_new(extractor):
    """Test fallback to getSourcesNew when getSources returns non-200 or invalid data."""
    embed_url = "https://play.echovideo.ru/embed/fallback-test-id"

    # First call to getSources returns 404
    mock_resp_fail = AsyncMock()
    mock_resp_fail.status = 404
    mock_resp_fail.__aenter__.return_value = mock_resp_fail
    mock_resp_fail.__aexit__.return_value = None

    # Second call to getSourcesNew returns 200 with sources
    mock_resp_success = AsyncMock()
    mock_resp_success.status = 200
    mock_resp_success.json.return_value = {
        "sources": {
            "FHD": "https://example.com/fallback-fhd.m3u8",
        },
        "tracks": [],
    }
    mock_resp_success.__aenter__.return_value = mock_resp_success
    mock_resp_success.__aexit__.return_value = None

    extractor.context.http.session.get.side_effect = [mock_resp_fail, mock_resp_success]

    streams = await extractor.extract(embed_url, label_prefix="FallbackTest")

    assert len(streams) == 1
    assert streams[0].url == "https://example.com/fallback-fhd.m3u8"
    assert streams[0].quality == "FallbackTest - 1080p"


@pytest.mark.asyncio
async def test_echovideo_both_endpoints_fail_raises_parsing_error(extractor):
    """Test ParsingError raised when both getSources and getSourcesNew fail."""
    from anime_extensions.core.errors import ParsingError

    embed_url = "https://play.echovideo.ru/embed/fail-test-id"

    mock_resp_fail = AsyncMock()
    mock_resp_fail.status = 500
    mock_resp_fail.__aenter__.return_value = mock_resp_fail
    mock_resp_fail.__aexit__.return_value = None

    extractor.context.http.session.get.return_value = mock_resp_fail

    with pytest.raises(ParsingError, match="both getSources and getSourcesNew"):
        await extractor.extract(embed_url)
