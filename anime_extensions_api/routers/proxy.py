"""Proxy protected HLS playlists and playback resources."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import m3u8
from fastapi import APIRouter, HTTPException, Request, Response

from ..dependencies import RuntimeDep
from ..services.hls_proxy import HlsProxyRegistry, HlsProxyTarget

if TYPE_CHECKING:
    from anime_extensions.core import ExtensionRuntime

log = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy", tags=["Proxy"])

_PLAYLIST_CONTENT_TYPE = "application/vnd.apple.mpegurl"


def _proxy_url(request: Request, token: str) -> str:
    """Build an absolute proxy URL that the player can request."""
    return str(request.url_for("proxy_hls", token=token))


def register_hls_proxy_target(
    request: Request,
    url: str,
    headers: dict[str, str],
) -> str:
    """Register an upstream target and return its opaque proxy URL."""
    registry: HlsProxyRegistry = request.app.state.hls_proxy_registry
    token = registry.register(url, headers)
    return _proxy_url(request, token)


def _is_playlist(url: str, content: bytes) -> bool:
    """Recognize HLS by URL extension or definitive playlist content."""
    suffix = urlparse(url).path.lower()
    return suffix.endswith((".m3u8", ".m3u")) or content.lstrip().startswith(b"#EXTM3U")


def _rewrite_playlist(
    content: str,
    base_url: str,
    request: Request,
    registry: HlsProxyRegistry,
    headers: dict[str, str],
) -> str:
    """Rewrite every HLS URI reference to an opaque proxy target."""
    playlist = m3u8.loads(content)

    def proxy_uri(uri: str | None) -> str | None:
        if not uri or uri.startswith("data:"):
            return uri
        target_url = urljoin(base_url, uri)
        token = registry.register(target_url, headers)
        return _proxy_url(request, token)

    for variant in playlist.playlists:
        variant.uri = proxy_uri(variant.uri)
    for media in playlist.media:
        media.uri = proxy_uri(media.uri)
    for iframe in playlist.iframe_playlists:
        iframe.uri = proxy_uri(iframe.uri)

    for key in playlist.keys:
        if key is not None:
            key.uri = proxy_uri(key.uri)
    for session_key in playlist.session_keys:
        session_key.uri = proxy_uri(session_key.uri)
    for session_data in playlist.session_data:
        session_data.uri = proxy_uri(session_data.uri)

    for segment in playlist.segments:
        segment.uri = proxy_uri(segment.uri)
        if segment.init_section is not None:
            segment.init_section.uri = proxy_uri(segment.init_section.uri)
        for part in segment.parts:
            part.uri = proxy_uri(part.uri)

    if playlist.preload_hint is not None:
        playlist.preload_hint.uri = proxy_uri(playlist.preload_hint.uri)
    for rendition_report in playlist.rendition_reports:
        rendition_report.uri = proxy_uri(rendition_report.uri)

    return playlist.dumps()


def _media_type(url: str) -> str:
    """Choose a safe media type for a proxied HLS resource."""
    suffix = urlparse(url).path.lower().rsplit(".", maxsplit=1)[-1]
    media_types = {
        "aac": "audio/aac",
        "m4s": "video/iso.segment",
        "mp4": "video/mp4",
        "m4v": "video/mp4",
        "ts": "video/mp2t",
        "vtt": "text/vtt",
    }
    return media_types.get(suffix, "application/octet-stream")


async def _fetch(runtime: ExtensionRuntime, target: HlsProxyTarget) -> bytes:
    """Fetch a protected resource through the runtime-owned HTTP client."""
    return await runtime.http.get_bytes(target.url, headers=target.headers)


@router.get("/hls/{token}", name="proxy_hls")
async def proxy_hls(token: str, request: Request, runtime: RuntimeDep) -> Response:
    """Serve a protected HLS resource with its embed-bound upstream headers."""
    registry: HlsProxyRegistry = request.app.state.hls_proxy_registry
    target = registry.resolve(token)
    if target is None:
        raise HTTPException(status_code=404, detail="Expired or invalid proxy target.")

    content = await _fetch(runtime, target)
    headers = {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"}

    if not _is_playlist(target.url, content):
        return Response(content=content, media_type=_media_type(target.url), headers=headers)

    try:
        playlist = content.decode("utf-8")
        rewritten = _rewrite_playlist(playlist, target.url, request, registry, target.headers)
    except (UnicodeDecodeError, ValueError) as exc:
        log.warning("Invalid HLS playlist from %s: %s", target.url, exc)
        raise HTTPException(
            status_code=502, detail="Upstream returned an invalid HLS playlist."
        ) from exc

    return Response(content=rewritten, media_type=_PLAYLIST_CONTENT_TYPE, headers=headers)
