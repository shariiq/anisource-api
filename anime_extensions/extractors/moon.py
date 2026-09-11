"""Moon video extractor."""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..core.errors import HttpError, ParsingError
from ..core.extractor import Extractor
from ..core.registry import register_extractor
from ..models import Stream
from ..utils.crypto import b64url_decode
from ..utils.m3u8 import parse_m3u8_streams

log = logging.getLogger(__name__)


@register_extractor(r"bysesayeveum|fmoon|filemoon|moonembed")
class MoonExtractor(Extractor):
    """Extractor for Moon and variations like fmoon / filemoon / bysesayeveum."""

    name = "Moon"

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        session = self.context.http
        site_url = kwargs.get("site_url", "https://animenosub.to")
        prefix = kwargs.get("label_prefix", "")

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        segments = [s for s in parsed_url.path.split("/") if s]
        if not segments:
            raise ParsingError(f"Moon: invalid URL format {url}")
        video_id = segments[-1]

        details_headers = {
            "Referer": f"{site_url}/",
            "Origin": site_url,
            "User-Agent": user_agent,
        }

        try:
            details_url = f"https://{host}/api/videos/{video_id}/embed/details"
            details_json = await session.get_json(details_url, headers=details_headers)
        except HttpError as e:
            log.warning("Moon details request failed: %s", e)
            raise

        embed_url = details_json.get("embed_frame_url")
        if not embed_url:
            raise ParsingError("Moon: missing embed_frame_url in details response")

        embed_host = urlparse(embed_url).netloc
        viewer_id = uuid.uuid4().hex
        device_id = uuid.uuid4().hex
        now_sec = int(time.time())
        exp_sec = now_sec + 600

        fp_payload = json.dumps(
            {
                "viewer_id": viewer_id,
                "device_id": device_id,
                "confidence": 0.93,
                "iat": now_sec,
                "exp": exp_sec,
            },
            separators=(",", ":"),
        )

        payload_b64 = base64.urlsafe_b64encode(fp_payload.encode()).decode().rstrip("=")
        fp_token = f"{payload_b64}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

        fp_body = {
            "fingerprint": {
                "token": fp_token,
                "viewer_id": viewer_id,
                "device_id": device_id,
                "confidence": 0.93,
            }
        }

        playback_headers = {
            "Referer": embed_url,
            "Origin": f"https://{embed_host}",
            "User-Agent": user_agent,
            "X-Embed-Origin": site_url.removeprefix("https://").removeprefix("http://"),
            "X-Embed-Parent": f"https://{host}/e/{video_id}",
            "X-Embed-Referer": f"{site_url}/",
        }

        try:
            playback_url = f"https://{embed_host}/api/videos/{video_id}/embed/playback"
            resp = await session.post_json(
                playback_url, json_data=fp_body, headers=playback_headers
            )
        except HttpError as e:
            log.warning("Moon playback request failed: %s", e)
            raise

        master_url = ""
        sources = resp.get("sources")
        if sources:
            master_url = sources[0].get("url") or sources[0].get("file")
        elif "playback" in resp:
            pb = resp["playback"]
            try:
                decrypted = self._decrypt_payload(pb)
                inner_resp = json.loads(decrypted)
                inner_sources = inner_resp.get("sources")
                if inner_sources:
                    master_url = inner_sources[0].get("url") or inner_sources[0].get("file")
            except Exception as e:
                log.warning("Moon decryption failed: %s", e)
                raise ParsingError(f"Moon: decryption failed: {e}") from e

        if not master_url:
            raise ParsingError("Moon: no master URL found in playback response")

        video_headers = {
            "Referer": f"https://{embed_host}/",
            "Origin": f"https://{embed_host}",
            "User-Agent": user_agent,
        }

        try:
            playlist_text = await session.get(master_url, headers=video_headers)
            qual = prefix.strip()
            if not qual:
                qual = "Moon"
            elif "Moon" not in qual:
                qual = f"Moon - {qual}"

            return parse_m3u8_streams(
                playlist_text,
                master_url,
                referer=video_headers["Referer"],
                default_headers=video_headers,
                label_prefix=qual,
            )
        except HttpError:
            raise

    def _decrypt_payload(self, pb: dict[str, Any]) -> str:
        key_parts = pb.get("key_parts", [])
        if len(key_parts) < 2:
            raise ValueError("Invalid key_parts")

        key_bytes = b64url_decode(key_parts[0]) + b64url_decode(key_parts[1])
        iv_bytes = b64url_decode(pb["iv"])
        cipher_bytes = b64url_decode(pb["payload"])

        aesgcm = AESGCM(key_bytes)
        decrypted = aesgcm.decrypt(iv_bytes, cipher_bytes, None)
        return decrypted.decode("utf-8")
