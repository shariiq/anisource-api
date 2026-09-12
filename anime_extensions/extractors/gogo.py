"""GogoStream / Vidstreaming video extractor."""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..core.errors import ExtractorError
from ..core.extractor import Extractor
from ..core.models import Stream
from ..utils.m3u8 import parse_m3u8_streams

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class GogoStreamExtractor(Extractor):
    """Extractor for GogoStream / Vidstreaming video hosting."""

    name = "GogoStream"

    @staticmethod
    def _crypto_handler(
        data: str,
        iv: bytes,
        key: bytes,
        *,
        encrypt: bool = True,
    ) -> str:
        """AES-CBC encrypt or decrypt with PKCS7 padding."""
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        if not encrypt:
            decryptor = cipher.decryptor()
            raw_data = base64.b64decode(data)
            padded_data = decryptor.update(raw_data) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            unpadded = unpadder.update(padded_data) + unpadder.finalize()
            return unpadded.decode("utf-8")
        else:
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(data.encode("utf-8")) + padder.finalize()
            encryptor = cipher.encryptor()
            encrypted = encryptor.update(padded_data) + encryptor.finalize()
            return base64.b64encode(encrypted).decode("utf-8")

    @staticmethod
    def _get_bytes_after(element_classes: list[str] | str, prefix: str) -> bytes:
        class_str = (
            " ".join(element_classes) if isinstance(element_classes, list) else element_classes
        )
        after = class_str.split(prefix, 1)[-1] if prefix in class_str else ""
        digits = "".join(c for c in after if c.isdigit())
        return digits.encode("utf-8")

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract streams from GogoStream/Vidstreaming embed URL."""
        label_prefix = kwargs.get("label_prefix", "")

        session = self.context.http.session
        if not session:
            raise ExtractorError("GogoStream: runtime HTTP client is not started")

        if url.startswith("//"):
            url = f"https:{url}"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise ExtractorError(f"GogoStream: failed to fetch page, status {resp.status}")
                text = await resp.text(errors="replace")

            soup = BeautifulSoup(text, "lxml")

            wrapper = soup.find("div", class_=lambda c: c and "container-" in c) or soup.find(
                "div", class_="wrapper"
            )
            body = soup.find("body", class_=lambda c: c and "container-" in c) or soup.find("body")
            videocontent = soup.find(
                "div", class_=lambda c: c and "videocontent-" in c
            ) or soup.find("div", class_="videocontent")
            script_data = soup.find("script", {"data-value": True})

            if not wrapper or not body or not videocontent or not script_data:
                log.warning("GogoStream: required crypto elements not found in %s", url)
                return []

            iv = self._get_bytes_after(wrapper.get("class", []), "container-")
            secret_key = self._get_bytes_after(body.get("class", []), "container-")
            decryption_key = self._get_bytes_after(videocontent.get("class", []), "videocontent-")
            encrypted_data = script_data.get("data-value", "")

            if not isinstance(encrypted_data, str) or not encrypted_data:
                return []

            decrypted_ajax = self._crypto_handler(encrypted_data, iv, secret_key, encrypt=False)
            if "&" in decrypted_ajax:
                decrypted_ajax = decrypted_ajax.split("&", 1)[-1]

            parsed = urlparse(url)
            host = f"{parsed.scheme}://{parsed.netloc}"
            qs = parse_qs(parsed.query)
            video_id = qs.get("id", [""])[0]
            if not video_id:
                return []

            encrypted_id = self._crypto_handler(video_id, iv, secret_key, encrypt=True)
            token = qs.get("token", [None])[0]
            quality_prefix = (
                f"{label_prefix or 'GogoStream'} - "
                if token
                else f"{label_prefix or 'Vidstreaming'} - "
            )

            ajax_url = (
                f"{host}/encrypt-ajax.php?id={encrypted_id}&{decrypted_ajax}&alias={video_id}"
            )
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": url,
            }

            async with session.get(ajax_url, headers=headers) as ajax_resp:
                if ajax_resp.status != 200:
                    return []
                ajax_json = await ajax_resp.json()

            encrypted_response = ajax_json.get("data", "")
            if not encrypted_response:
                return []

            decrypted_response = self._crypto_handler(
                encrypted_response, iv, decryption_key, encrypt=False
            )
            response_data = json.loads(decrypted_response)
            source_list = response_data.get("source", [])
            if not isinstance(source_list, list):
                return []

            if len(source_list) == 1 and source_list[0].get("type") == "hls":
                playlist_url = source_list[0].get("file", "")
                if playlist_url:
                    async with session.get(playlist_url, headers={"Referer": url}) as hls_resp:
                        if hls_resp.status == 200:
                            hls_text = await hls_resp.text(errors="replace")
                            return parse_m3u8_streams(
                                hls_text,
                                playlist_url,
                                referer=url,
                                label_prefix=quality_prefix.rstrip(" -"),
                            )

            streams: list[Stream] = []
            for video in source_list:
                file_url = video.get("file")
                if not file_url:
                    continue
                label = video.get("label", "auto")
                streams.append(
                    Stream(
                        url=file_url,
                        quality=f"{quality_prefix}{label}",
                        headers={"Referer": url},
                        is_hls=".m3u8" in file_url,
                    )
                )

            return streams

        except Exception as e:
            log.warning("GogoStream extraction failed for %s: %s", url, e)
            return []
