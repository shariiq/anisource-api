"""Unit tests for the Byse challenge and playback extractor."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anime_extensions.core.errors import HttpError, ParsingError
from anime_extensions.extractors.byse import ByseExtractor
from anime_extensions.models import Stream


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.http = MagicMock()
    ctx.http.post_json = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_byse_extractor_challenge_and_playback_flow(mock_context):
    """Test challenge, attestation, PoW verification, and playback parsing."""
    extractor = ByseExtractor(context=mock_context)

    decrypted_playback = json.dumps(
        {
            "sources": [{"url": "https://cdn.byse.example/video.mp4", "label": "1080p"}],
            "tracks": [
                {
                    "file": "https://cdn.byse.example/en.vtt",
                    "label": "English",
                }
            ],
        }
    )

    # Mock post_json responses in order
    response_data = [
        {"nonce": "nonce-1", "challenge_id": "challenge-1"},
        {
            "token": "fingerprint-token",
            "viewer_id": "viewer-1",
            "device_id": "device-1",
            "confidence": 0.98,
        },
        {"pow_nonce": "pow-1", "pow_difficulty": 1, "pow_token": "pow-token"},
        {"status": "ok", "token": "captcha-token"},
        {"playback": "encrypted-payload"},
    ]

    mock_context.http.post_json.side_effect = response_data

    with (
        patch(
            "anime_extensions.extractors.byse.generate_byse_keypair_and_attestation",
            return_value=({"kty": "EC"}, "signature"),
        ),
        patch("anime_extensions.extractors.byse.solve_byse_pow", return_value="42") as solve_pow,
        patch(
            "anime_extensions.extractors.byse.decrypt_byse_playback",
            return_value=decrypted_playback,
        ),
    ):
        streams = await extractor.extract(
            "https://byse.example/embed/media-123",
            embed_parent="https://ani.example/watch/episode-1",
            label_prefix="BYFMS",
        )

    assert solve_pow.call_args.args == ("pow-1", 1)
    assert len(streams) == 1
    assert isinstance(streams[0], Stream)
    assert streams[0].url == "https://cdn.byse.example/video.mp4"
    assert streams[0].quality == "BYFMS - 1080p"
    assert streams[0].subtitles[0].label == "English"
    assert streams[0].headers["Referer"] == "https://byse.example/"


@pytest.mark.asyncio
async def test_byse_extractor_rejects_failed_challenge(mock_context):
    """Test a non-success challenge response raises a useful extractor error."""
    extractor = ByseExtractor(context=mock_context)
    mock_context.http.post_json.side_effect = HttpError("challenge failed with status 403")

    with pytest.raises(HttpError, match="challenge failed with status 403"):
        await extractor.extract("https://byse.example/embed/media-123")


@pytest.mark.asyncio
async def test_byse_extractor_requires_media_id(mock_context):
    """Test malformed embed paths fail before making any network request."""
    extractor = ByseExtractor(context=mock_context)

    with pytest.raises(ParsingError, match="could not read media id"):
        await extractor.extract("https://byse.example/embed")
    mock_context.http.post_json.assert_not_called()
