"""Unit tests for the Byse challenge and playback extractor."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from anime_extensions.exceptions import ExtractorError
from anime_extensions.extractors.byse import ByseExtractor
from anime_extensions.models import Stream


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
    responses = [
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

    mock_session = AsyncMock()
    mock_session.post.side_effect = [
        AsyncMock(
            __aenter__=AsyncMock(
                return_value=type(
                    "Response", (), {"status": 200, "json": AsyncMock(return_value=data)}
                )()
            )
        )
        for data in responses
    ]

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
    response = type("Response", (), {"status": 403})()
    mock_session = AsyncMock()
    mock_session.post.return_value = AsyncMock(__aenter__=AsyncMock(return_value=response))

    with (
        patch.object(extractor, "_ensure_session", return_value=mock_session),
        pytest.raises(ExtractorError, match="challenge failed with status 403"),
    ):
        await extractor.extract("https://byse.example/embed/media-123")


@pytest.mark.asyncio
async def test_byse_extractor_requires_media_id():
    """Test malformed embed paths fail before making any network request."""
    extractor = ByseExtractor()
    mock_session = AsyncMock()

    with (
        patch.object(extractor, "_ensure_session", return_value=mock_session),
        pytest.raises(ExtractorError, match="could not read media id"),
    ):
        await extractor.extract("https://byse.example/embed")
    mock_session.post.assert_not_called()
