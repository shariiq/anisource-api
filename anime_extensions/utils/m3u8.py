"""M3U8 parsing and playlist processing utilities using the m3u8 library."""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urljoin

import m3u8

from ..models import Stream, Subtitle


def decode_numeric_hls(text: str) -> str:
    """Decode numeric-encoded HLS playlist (where text is decimal bytes).

    Parity with Kotlin AniWaves.decodeNumericHls.
    """
    trimmed = text.strip()
    if not trimmed or not trimmed[0].isdigit():
        return text

    try:
        bytes_list: list[int] = []
        for token in text.replace("\r", "\n").split("\n"):
            t = token.strip()
            if not t:
                continue
            val = int(t)
            if not (0 <= val <= 255):
                return text
            bytes_list.append(val)

        if bytes_list:
            return bytes(bytes_list).decode("utf-8")
    except ValueError, UnicodeDecodeError:
        pass

    return text


def absolutize_m3u8_urls(text: str, base_url: str) -> str:
    """Resolve all relative URLs (playlists, segments, keys, maps) to absolute URLs."""
    uri_attr_regex = re.compile(r'URI="([^"]+)"')
    lines = []

    for line in text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("#EXT-X-KEY") or trimmed.startswith("#EXT-X-MAP"):

            def replace_uri(m: re.Match[str]) -> str:
                return f'URI="{urljoin(base_url, m.group(1))}"'

            lines.append(uri_attr_regex.sub(replace_uri, line))
        elif trimmed and not trimmed.startswith("#"):
            lines.append(urljoin(base_url, trimmed))
        else:
            lines.append(line)

    return "\n".join(lines)


def parse_m3u8_streams(
    playlist_text: str,
    master_url: str,
    *,
    referer: str | None = None,
    subtitles: list[Subtitle] | None = None,
    default_headers: Mapping[str, str] | None = None,
    label_prefix: str = "",
) -> list[Stream]:
    """Parse an M3U8 master or media playlist text using the m3u8 library.

    Returns a list of Stream objects with quality and absolute URLs.
    """
    decoded_text = decode_numeric_hls(playlist_text)
    sub_list = subtitles or []
    headers = dict(default_headers or {})
    if referer and "Referer" not in headers:
        headers["Referer"] = referer

    try:
        parsed = m3u8.loads(decoded_text, uri=master_url)
    except Exception:
        # Fallback to single stream if parsing fails
        label = f"{label_prefix} - auto" if label_prefix else "auto"
        return [
            Stream(
                url=master_url,
                quality=label,
                headers=headers,
                subtitles=sub_list,
                is_hls=True,
            )
        ]

    streams: list[Stream] = []

    if parsed.is_variant and parsed.playlists:
        for p in parsed.playlists:
            quality = "auto"
            if p.stream_info:
                if p.stream_info.resolution:
                    _, h = p.stream_info.resolution
                    quality = f"{h}p"
                elif p.stream_info.bandwidth:
                    quality = f"{p.stream_info.bandwidth // 1000}kbps"

            full_quality = f"{label_prefix} - {quality}" if label_prefix else quality
            stream_url = p.absolute_uri if p.absolute_uri else urljoin(master_url, p.uri)

            streams.append(
                Stream(
                    url=stream_url,
                    quality=full_quality,
                    headers=headers,
                    subtitles=sub_list,
                    is_hls=True,
                )
            )

    if not streams:
        label = f"{label_prefix} - auto" if label_prefix else "auto"
        streams.append(
            Stream(
                url=master_url,
                quality=label,
                headers=headers,
                subtitles=sub_list,
                is_hls=True,
            )
        )

    return streams
