"""Unit tests for the Byse challenge and playback extractor."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anime_extensions.exceptions import ExtractorError
from anime_extensions.extractors.byse import ByseExtractor
from anime_extensions.models import Stream


def _async_ctx(resp):
    """Helper to create async context manager from mock response."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


@pytest.mark.asyncio
async def test_byse_extractor_challenge_and_playback_flow():
    """Test challenge, attestation, PoW verification, and playback parsing."""
    extractor = ByseExtractor()

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

    # Create mock responses with proper async context manager support
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

    mock_responses = []
    for data in response_data:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=data)
        mock_responses.append(_async_ctx(mock_resp))

    mock_session = MagicMock()
    mock_session.post.side_effect = mock_responses

    with (
        patch.object(extractor, "_ensure_session", return_value=mock_session),
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
async def test_byse_extractor_rejects_failed_challenge():
    """Test a non-success challenge response raises a useful extractor error."""
    extractor = ByseExtractor()
    mock_resp = MagicMock()
    mock_resp.status = 403
    mock_session = MagicMock()
    mock_session.post.return_value = _async_ctx(mock_resp)

    with (
        patch.object(extractor, "_ensure_session", return_value=mock_session),
        pytest.raises(ExtractorError, match="challenge failed with status 403"),
    ):
        await extractor.extract("https://byse.example/embed/media-123")


@pytest.mark.asyncio
async def test_byse_extractor_requires_media_id():
    """Test malformed embed paths fail before making any network request."""
    extractor = ByseExtractor()
    mock_session = MagicMock()

    with (
        patch.object(extractor, "_ensure_session", return_value=mock_session),
        pytest.raises(ExtractorError, match="could not read media id"),
    ):
        await extractor.extract("https://byse.example/embed")
    mock_session.post.assert_not_called()
