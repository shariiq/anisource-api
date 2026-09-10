"""Byse (BYFMS/Filemoon/Gn1r5n) video extractor."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any
from urllib.parse import urlparse

from ..base import BaseExtractor
from ..exceptions import ExtractorError
from ..models import Stream, Subtitle
from ..utils.crypto import (
    b64url_encode,
    decrypt_byse_playback,
    generate_byse_keypair_and_attestation,
    solve_byse_pow,
)
from ..utils.m3u8 import parse_m3u8_streams

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)


class ByseExtractor(BaseExtractor):
    """Extractor for Byse/BYFMS video provider."""

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
        embed_url: str,
        *,
        embed_parent: str = "",
        embed_origin: str = "",
        label_prefix: str = "",
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from Byse embed URL."""
        session = await self._ensure_session()
        parsed_url = urlparse(embed_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

        path_segments = [s for s in parsed_url.path.split("/") if s]
        if len(path_segments) < 2:
            raise ExtractorError(f"Byse: could not read media id from {embed_url}")

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
        async with session.post(challenge_url, headers=base_headers, json={}) as resp:
            if resp.status != 200:
                raise ExtractorError(f"Byse: challenge failed with status {resp.status}")
            challenge = await resp.json()

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
        async with session.post(attest_url, headers=base_headers, json=attest_payload) as resp:
            if resp.status != 200:
                raise ExtractorError(f"Byse: attest failed with status {resp.status}")
            attest = await resp.json()

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
        async with session.post(
            captcha_url,
            headers=gate_headers,
            json={"fingerprint": fingerprint},
        ) as resp:
            if resp.status != 200:
                raise ExtractorError(f"Byse: captcha request failed with status {resp.status}")
            captcha = await resp.json()

        # 4. Solve PoW & Verify
        solution = solve_byse_pow(captcha["pow_nonce"], captcha["pow_difficulty"])
        verify_payload = {
            "pow_token": captcha["pow_token"],
            "solution": solution,
            "fingerprint": fingerprint,
        }

        verify_url = f"{origin}/api/videos/{media_id}/embed/captcha/verify"
        async with session.post(verify_url, headers=gate_headers, json=verify_payload) as resp:
            if resp.status != 200:
                raise ExtractorError(f"Byse: verify request failed with status {resp.status}")
            verify = await resp.json()

        if verify.get("status") != "ok":
            raise ExtractorError(f"Byse: PoW verification failed ({verify.get('status')})")

        captcha_token = verify.get("token")
        if not captcha_token:
            raise ExtractorError("Byse: missing captcha token in verification response")

        # 5. Playback
        playback_headers = dict(gate_headers)
        playback_headers["X-Captcha-Token"] = captcha_token

        playback_url = f"{origin}/api/videos/{media_id}/embed/playback"
        async with session.post(
            playback_url,
            headers=playback_headers,
            json={"fingerprint": fingerprint},
        ) as resp:
            if resp.status != 200:
                raise ExtractorError(f"Byse: playback request failed with status {resp.status}")
            playback_data = await resp.json()

        encrypted_playback = playback_data.get("playback")
        if not encrypted_playback:
            raise ExtractorError("Byse: no encrypted playback payload received")

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
                try:
                    async with session.get(
                        src_url, headers={"Referer": video_referer, "User-Agent": USER_AGENT}
                    ) as hls_resp:
                        if hls_resp.status == 200:
                            hls_text = await hls_resp.text(errors="replace")
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
                except Exception as e:
                    log.warning("Failed to parse Byse m3u8 playlist: %s", e)

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

        return streams
