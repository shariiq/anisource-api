"""MegaPlay and its clones (e.g. nexabloom.top, megaplay.buzz) video extractor."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..core.extractor import Extractor
from ..models import Stream, Subtitle

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class MegaPlayExtractor(Extractor):
    """Extractor for MegaPlay / nexabloom HLS streams.

    Expects an embed URL like `https://nexabloom.top/stream/s-sub/...`
    """

    name = "MegaPlay"

    async def extract(
        self,
        url: str,
        *,
        quality_prefix: str = "",
        external_subs: list[Subtitle] | None = None,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract video streams from MegaPlay embed URL."""
        return await self._extract_from_player(url, quality_prefix, external_subs)

    async def _extract_from_player(
        self,
        embed_url: str,
        quality_prefix: str,
        external_subs: list[Subtitle] | None,
        page_referer: str | None = None,
    ) -> list[Stream]:
        from urllib.parse import urljoin, urlparse

        try:
            parsed = urlparse(embed_url)
            host = parsed.netloc
        except Exception:
            return []

        # We fall back to a reasonable base_url like https://anikototv.to/ if referer not set
        # But for generic extractor use, we can use the embed_url itself as fallback
        page_referer = page_referer or embed_url
        headers = {"Referer": page_referer}

        try:
            body = await self.context.http.get(embed_url, headers=headers)
        except Exception:
            return []

        if not body:
            return []

        # Try to find data-id for API extraction
        data_id_match = re.search(r'data-id="([^"]+)"', body)
        if data_id_match:
            data_id = data_id_match.group(1)
            return await self._fetch_sources_from_api(
                data_id, host, embed_url, quality_prefix, external_subs
            )

        # Try to find iframe src
        iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', body)
        if iframe_match:
            iframe_src = urljoin(embed_url, iframe_match.group(1))
            return await self._extract_from_player(
                iframe_src, quality_prefix, external_subs, embed_url
            )

        # Try to find direct m3u8.
        m3u8_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', body)
        if m3u8_match:
            return self._return_master_stream(
                m3u8_match.group(0),
                f"https://{host}",
                embed_url,
                quality_prefix,
                external_subs,
            )

        # Try JS variable patterns
        js_m3u8_match = re.search(
            r"""(?:var|let|const)\s+\w+\s*=\s*["']([^"']*(?:\.m3u8|/stream/)[^"']*)["']"""
            r"""|(?:file|source|url|src)\s*[:=]\s*["']([^"']*(?:\.m3u8|/stream/)[^"']*)["']""",
            body,
        )
        if js_m3u8_match:
            js_url = js_m3u8_match.group(1) or js_m3u8_match.group(2)
            if js_url:
                resolved_url = urljoin(embed_url, js_url)
                if ".m3u8" in resolved_url or "/stream/" in resolved_url:
                    try:
                        return await self._fetch_sources_from_page(
                            resolved_url, embed_url, quality_prefix, external_subs
                        )
                    except Exception:
                        return self._return_master_stream(
                            resolved_url,
                            f"https://{host}",
                            embed_url,
                            quality_prefix,
                            external_subs,
                        )

        return []

    async def _fetch_sources_from_api(
        self,
        data_id: str,
        host: str,
        embed_url: str,
        quality_prefix: str,
        external_subs: list[Subtitle] | None = None,
    ) -> list[Stream]:
        path_segments = embed_url.rstrip("/").split("/")
        stream_type = path_segments[-1] if path_segments[-1] in ("sub", "dub", "hsub") else ""

        api_headers = {
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": embed_url,
            "Origin": f"https://{host}",
        }

        data = None
        fallback_data = None
        for endpoint in ("getSources", "getSourcesNew"):
            for s_val in ("bcdn", "tcdn", None):
                query = f"?id={data_id}&id={data_id}&type={stream_type}&type={stream_type}"
                if s_val:
                    query += f"&s={s_val}"
                else:
                    query += "&bypass=yes"

                api_url = f"https://{host}/stream/{endpoint}{query}"
                try:
                    resp_data = await self.context.http.get_json(api_url, headers=api_headers)
                except Exception:
                    continue
                if not isinstance(resp_data, dict):
                    continue
                if resp_data.get("enc"):
                    decrypted = self._decrypt_megaplay_sources(resp_data["enc"])
                    if decrypted:
                        resp_data = {**resp_data, **decrypted}
                source_value = resp_data.get("sources", resp_data.get("file"))
                if self._has_source_url(source_value):
                    url_candidate = self._extract_first_url(source_value)
                    if "fetch.nexabloom.top" not in url_candidate:
                        data = resp_data
                        break
                    if fallback_data is None:
                        fallback_data = resp_data
            if data:
                break

        data = data or fallback_data
        if not data:
            return []

        source_value = data.get("sources", data.get("file"))
        if isinstance(source_value, dict):
            m3u8_url = source_value.get("file", "")
        elif isinstance(source_value, str):
            m3u8_url = source_value
        elif isinstance(source_value, list):
            m3u8_url = source_value[0] if source_value else ""
        else:
            m3u8_url = ""

        if not isinstance(m3u8_url, str) or not m3u8_url.startswith("http"):
            return []

        subs = external_subs or []
        for track in data.get("tracks", []) or []:
            if isinstance(track, dict) and track.get("kind") == "captions":
                track_url = track.get("file", "")
                if isinstance(track_url, str) and track_url.startswith("http"):
                    subs.append(
                        Subtitle(
                            url=track_url,
                            label=track.get("label", ""),
                            language=track.get("label", ""),
                        )
                    )

        # Return the raw master playlist URL with the embed-bound upstream headers.
        # The FastAPI layer wraps it in a proxy for playback.
        return self._return_master_stream(
            m3u8_url, f"https://{host}", f"https://{host}/", quality_prefix, subs
        )

    async def _fetch_sources_from_page(
        self,
        url: str,
        referer: str,
        quality_prefix: str,
        subs: list[Subtitle] | None,
    ) -> list[Stream]:
        headers = {"Referer": referer}
        body = await self.context.http.get(url, headers=headers)

        if not body:
            raise Exception("Page fetch failed")

        from urllib.parse import urlparse

        host = urlparse(url).netloc

        if body.lstrip().startswith("#EXTM3U"):
            return self._return_master_stream(url, f"https://{host}", referer, quality_prefix, subs)

        m3u8_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', body)
        if m3u8_match:
            return self._return_master_stream(
                m3u8_match.group(0), f"https://{host}", referer, quality_prefix, subs
            )

        raise Exception("No m3u8 found in page")

    def _return_master_stream(
        self,
        m3u8_url: str,
        origin: str,
        referer: str,
        quality_prefix: str,
        subs: list[Subtitle] | None,
    ) -> list[Stream]:
        headers = {
            "Referer": referer,
            "Origin": origin,
        }
        label = f"{quality_prefix} - Auto" if quality_prefix else "Auto"
        return [
            Stream(
                url=m3u8_url,
                quality=label,
                headers=headers,
                subtitles=subs or [],
                is_hls=True,
            )
        ]

    @staticmethod
    def _has_source_url(sources: Any) -> bool:
        """Return whether an API source value contains a usable URL."""
        if isinstance(sources, dict):
            return isinstance(sources.get("file"), str) and sources["file"].startswith("http")
        if isinstance(sources, str):
            return sources.startswith("http")
        if isinstance(sources, list):
            return bool(sources) and isinstance(sources[0], str) and sources[0].startswith("http")
        return False

    @staticmethod
    def _extract_first_url(sources: Any) -> str:
        """Extract the first URL from an API source value."""
        if isinstance(sources, dict):
            return sources.get("file", "")
        if isinstance(sources, str):
            return sources
        if isinstance(sources, list) and sources:
            return sources[0]
        return ""

    @staticmethod
    def _decrypt_megaplay_sources(encoded: Any) -> dict[str, Any] | None:
        """Decrypt MegaPlay's URL-safe Base64 AES-CBC response payload."""
        if not isinstance(encoded, str) or not encoded:
            return None
        try:
            encoded = encoded.replace("-", "+").replace("_", "/")
            ciphertext = base64.b64decode(encoded + "=" * (-len(encoded) % 4))
            key = b"i?LMTAx0Q6,:}50U".ljust(32, b"\0")[:32]
            iv = b"W0;27ToaUpl_P%'c"
            decryptor = Cipher(
                algorithms.AES(key), modes.CBC(iv), backend=default_backend()
            ).decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            padding = plaintext[-1]
            if 1 <= padding <= 16 and plaintext.endswith(bytes([padding]) * padding):
                plaintext = plaintext[:-padding]
            payload = json.loads(plaintext.decode("utf-8"))
        except ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else {"sources": payload}
