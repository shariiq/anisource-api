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
