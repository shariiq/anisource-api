"""Byse (BYFMS/Filemoon/Gn1r5n) video extractor."""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any
from urllib.parse import urlparse

from ..core.errors import ExtractorError, ParsingError
from ..core.extractor import Extractor
from ..core.registry import register_extractor
from ..models import Stream, Subtitle
from ..utils.crypto import (
    b64url_encode,
    decrypt_byse_playback,
    generate_byse_keypair_and_attestation,
    solve_byse_pow,
)
from ..utils.m3u8 import parse_m3u8_streams

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)

# Maximum time to spend solving the Proof-of-Work challenge.
# High difficulties (d16+) can take minutes, so we cap it to avoid
# blocking the event loop indefinitely.
POW_TIMEOUT_SECONDS = 60


@register_extractor(r"byse|byfms|filemoon|gn1r5n")
class ByseExtractor(Extractor):
    """Extractor for Byse/BYFMS video provider.

    Handles multi-stage challenge/attestation/PoW/playback flow.
    The Proof-of-Work solver is CPU-intensive and runs in a thread pool
    with an explicit timeout to avoid blocking the event loop.
    """

    name = "Byse"

    def _build_fingerprint(self) -> dict[str, Any]:
        """Construct the client fingerprint payload matching Kotlin ByseExtractor."""

        def random_hash() -> str:
            return b64url_encode(secrets.token_bytes(32))

        return {
            "user_agent": USER_AGENT,
            "pixel_ratio": 1,
            "screen_width": 1920,
            "screen_height": 1080,
            "color_depth": 24,
            "languages": ["en-US", "en"],
            "timezone": "America/New_York",
            "hardware_concurrency": 8,
            "touch_points": 0,
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5)",
            "canvas_hash": random_hash(),
            "audio_hash": random_hash(),
            "webgl_params_hash": random_hash(),
            "fonts_hash": random_hash(),
            "codecs_hash": random_hash(),
            "media_devices": "ai0ao0vi0",
            "pointer_type": "fine,hover",
            "extra": {"vendor": "", "appVersion": "5.0 (X11)"},
        }

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from Byse embed URL."""
        embed_url = url
        embed_parent = kwargs.get("embed_parent", "")
        embed_origin = kwargs.get("embed_origin", "")
        label_prefix = kwargs.get("label_prefix", "")

        parsed_url = urlparse(embed_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

        path_segments = [s for s in parsed_url.path.split("/") if s]
        if len(path_segments) < 2:
            raise ParsingError(f"Byse: could not read media id from {embed_url}")

        media_id = path_segments[1]

        base_headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": USER_AGENT,
        }

        # 1. Challenge
        challenge_url = f"{origin}/api/videos/access/challenge"
        challenge = await self.context.http.post_json(
            challenge_url, headers=base_headers, json_data={}
        )

        nonce = challenge["nonce"]
        challenge_id = challenge["challenge_id"]

        # 2. Keypair & Attestation
        jwk, signature = generate_byse_keypair_and_attestation(nonce)
        fingerprint_client = self._build_fingerprint()

        attest_payload = {
            "viewer_id": "",
            "device_id": "",
            "challenge_id": challenge_id,
            "nonce": nonce,
            "signature": signature,
            "public_key": jwk,
            "client": fingerprint_client,
            "storage": {},
            "attributes": {"entropy": "low"},
        }

        attest_url = f"{origin}/api/videos/access/attest"
        attest = await self.context.http.post_json(
            attest_url, headers=base_headers, json_data=attest_payload
        )

        fingerprint = {
            "token": attest["token"],
            "viewer_id": attest["viewer_id"],
            "device_id": attest["device_id"],
            "confidence": attest.get("confidence", 1.0),
        }

        gate_origin_host = urlparse(embed_origin).netloc if embed_origin else parsed_url.netloc
        gate_headers = dict(base_headers)
        gate_headers.update(
            {
                "Cookie": f"byse_viewer_id={attest['viewer_id']}; byse_device_id={attest['device_id']}",
                "X-Embed-Origin": gate_origin_host,
                "X-Embed-Referer": embed_parent or embed_url,
                "X-Embed-Parent": embed_parent or embed_url,
            }
        )

        # 3. Captcha challenge
        captcha_url = f"{origin}/api/videos/{media_id}/embed/captcha"
        captcha = await self.context.http.post_json(
            captcha_url,
            headers=gate_headers,
            json_data={"fingerprint": fingerprint},
        )

        # 4. Solve PoW & Verify
        # The PoW solver is CPU-intensive and can take minutes for high difficulties.
        # Run it in a thread pool with an explicit timeout to avoid blocking the event loop.
        try:
            async with asyncio.timeout(POW_TIMEOUT_SECONDS):
                solution = await asyncio.to_thread(
                    solve_byse_pow, captcha["pow_nonce"], captcha["pow_difficulty"]
                )
        except TimeoutError as exc:
            raise ExtractorError(
                f"Byse: Proof-of-Work solver timed out after {POW_TIMEOUT_SECONDS}s"
            ) from exc

        verify_payload = {
            "pow_token": captcha["pow_token"],
            "solution": solution,
            "fingerprint": fingerprint,
        }

        verify_url = f"{origin}/api/videos/{media_id}/embed/captcha/verify"
        verify = await self.context.http.post_json(
            verify_url, headers=gate_headers, json_data=verify_payload
        )

        if verify.get("status") != "ok":
            raise ExtractorError(f"Byse: PoW verification failed ({verify.get('status')})")

        captcha_token = verify.get("token")
        if not captcha_token:
            raise ParsingError("Byse: missing captcha token in verification response")

        # 5. Playback
        playback_headers = dict(gate_headers)
        playback_headers["X-Captcha-Token"] = captcha_token

        playback_url = f"{origin}/api/videos/{media_id}/embed/playback"
        playback_data = await self.context.http.post_json(
            playback_url,
            headers=playback_headers,
            json_data={"fingerprint": fingerprint},
        )

        encrypted_playback = playback_data.get("playback")
        if not encrypted_playback:
            raise ParsingError("Byse: no encrypted playback payload received")

        # 6. Decrypt Playback
        decrypted_json_str = decrypt_byse_playback(encrypted_playback)
        decrypted = json.loads(decrypted_json_str)

        # Parse Subtitles
        subtitles: list[Subtitle] = []
        for track in decrypted.get("tracks") or []:
            track_url = track.get("file") or track.get("url")
            if track_url and track_url.startswith("http"):
                label = track.get("label") or track.get("language") or "Subtitle"
                subtitles.append(Subtitle(url=track_url, label=label))

        # Parse Sources
        streams: list[Stream] = []
        video_referer = f"{origin}/"
        for src in decrypted.get("sources") or []:
            src_url = src.get("url") or src.get("file")
            if not src_url or not src_url.startswith("http"):
                continue

            src_label = src.get("label")
            prefix = (
                f"{label_prefix} - {src_label}"
                if label_prefix and src_label
                else (label_prefix or src_label or "")
            )

            # If it's an m3u8 playlist, parse it
            if ".m3u8" in src_url:
                hls_text = await self.context.http.get(
                    src_url, headers={"Referer": video_referer, "User-Agent": USER_AGENT}
                )
                parsed_streams = parse_m3u8_streams(
                    hls_text,
                    src_url,
                    referer=video_referer,
                    subtitles=subtitles,
                    default_headers={
                        "User-Agent": USER_AGENT,
                        "Referer": video_referer,
                    },
                    label_prefix=prefix,
                )
                streams.extend(parsed_streams)
                continue

            # Fallback direct video stream
            streams.append(
                Stream(
                    url=src_url,
                    quality=prefix or "auto",
                    headers={"Referer": video_referer, "User-Agent": USER_AGENT},
                    subtitles=subtitles,
                    is_hls=".m3u8" in src_url,
                )
            )

        if not streams:
            raise ParsingError("Byse: playback metadata did not contain usable streams")

        return streams
