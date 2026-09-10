"""Doodstream video extractor."""

from __future__ import annotations

import logging
import re
import secrets
import string
import time
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..base import BaseExtractor
from ..models import Stream, Subtitle

log = logging.getLogger(__name__)


class DoodExtractor(BaseExtractor):
    """Extractor for Doodstream and its mirrors (e.g. myvidplay, dood.to, etc.)."""

    async def extract(
        self,
        url: str,
        *,
        quality_prefix: str = "",
        external_subs: list[Subtitle] | None = None,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract video streams from Doodstream URL."""
        session = await self._ensure_session()
        subs = external_subs or []

        try:
            # 1. Fetch embed page
            async with session.get(url, headers={"User-Agent": "Aniyomi"}) as resp:
                new_url = str(resp.url)
                text = await resp.text(errors="replace")

            if "'/pass_md5/" not in text and '"/pass_md5/' not in text:
                return []

            parsed = urlparse(new_url)
            dood_host = f"{parsed.scheme}://{parsed.netloc}"

            # 2. Extract quality from page title
            soup = BeautifulSoup(text, "html.parser")
            title_text = soup.title.get_text() if soup.title else ""
            quality_match = re.search(r"(\d{3,4}p)", title_text)
            extracted_quality = quality_match.group(1) if quality_match else "1080p"

            label = (
                f"{quality_prefix} - Doodstream {extracted_quality}"
                if quality_prefix
                else f"Doodstream {extracted_quality}"
            )

            # 3. Get MD5 pass path
            md5_match = re.search(r"/pass_md5/[^'\"&?]+", text)
            if not md5_match:
                return []

            md5_url = f"{dood_host}{md5_match.group(0)}"
            token = md5_url.rsplit("/", 1)[-1]

            # 4. Fetch the video url prefix
            pass_headers = {
                "User-Agent": "Aniyomi",
                "Referer": new_url,
            }
            async with session.get(md5_url, headers=pass_headers) as pass_resp:
                video_url_start = await pass_resp.text()

            video_url_start = video_url_start.strip()
            if not video_url_start or not video_url_start.startswith("http"):
                return []

            # 5. Build final video URL
            random_str = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(10)
            )
            expiry = int(time.time() * 1000)
            final_url = f"{video_url_start}{random_str}?token={token}&expiry={expiry}"

            video_headers = {
                "User-Agent": "Aniyomi",
                "Referer": f"{dood_host}/",
            }

            return [
                Stream(
                    url=final_url,
                    quality=label,
                    headers=video_headers,
                    subtitles=subs,
                    is_hls=False,
                )
            ]
        except Exception as e:
            log.warning("Dood extraction failed for %s: %s", url, e)
            return []
