"""Tests for the HLS proxy router and registry service."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from anime_extensions.core import ExtensionRuntime
from anime_extensions_api.app import create_app
from anime_extensions_api.config import APISettings, CacheSettings


@pytest.fixture
async def app_with_runtime():
    """Create an application initialized for proxy testing."""
    settings = APISettings(
        cache=CacheSettings(enabled=True),
    )
    app = create_app(settings)
    runtime = ExtensionRuntime()
    await runtime.start()
    app.state.runtime = runtime
    try:
        yield app
    finally:
        await runtime.close()
        app.state.hls_proxy_registry.clear()


@pytest.mark.asyncio
async def test_hls_proxy_registry_lifecycle(app_with_runtime):
    registry = app_with_runtime.state.hls_proxy_registry
    token = registry.register(
        "https://upstream.example.com/stream.m3u8", {"Referer": "https://embed.com"}
    )

    target = registry.resolve(token)
    assert target is not None
    assert target.url == "https://upstream.example.com/stream.m3u8"
    assert target.headers == {"Referer": "https://embed.com"}

    # Resolving nonexistent token
    assert registry.resolve("invalid") is None


@pytest.mark.asyncio
async def test_proxy_hls_not_found(app_with_runtime):
    transport = ASGITransport(app=app_with_runtime)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/proxy/hls/invalidtoken123")
        assert res.status_code == 404
        assert res.json()["error"]["message"] == "Expired or invalid proxy target."


@pytest.mark.asyncio
async def test_proxy_hls_rewrites_protected_playlist_resources(app_with_runtime):
    """Proxy every external child resource with the embed-bound request headers."""
    runtime = app_with_runtime.state.runtime
    runtime.http.get_bytes = AsyncMock(
        return_value=b"""#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1280000
variants/1080.m3u8
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"audio\",URI=\"audio/eng.m3u8\"
#EXT-X-I-FRAME-STREAM-INF:BANDWIDTH=86000,URI=\"iframes.m3u8\"
#EXT-X-SESSION-KEY:METHOD=AES-128,URI=\"keys/session.key\"
#EXT-X-SESSION-DATA:DATA-ID=\"com.example.meta\",URI=\"meta.json\"
#EXT-X-KEY:METHOD=AES-128,URI=\"keys/segment.key\"
#EXT-X-MAP:URI=\"init.mp4\"
#EXT-X-PART:DURATION=0.333,URI=\"parts/0.m4s\"
#EXT-X-PRELOAD-HINT:TYPE=PART,URI=\"parts/1.m4s\"
#EXT-X-RENDITION-REPORT:URI=\"audio/eng.m3u8\",LAST-MSN=123,LAST-PART=2
#EXTINF:4.0,
segments/0.ts
"""
    )
    upstream_url = "https://cdn.example.com/live/master.m3u8"
    upstream_headers = {
        "Origin": "https://megaplay.buzz",
        "Referer": "https://megaplay.buzz/stream/episode",
        "User-Agent": "Mozilla/5.0 Test",
    }
    token = app_with_runtime.state.hls_proxy_registry.register(upstream_url, upstream_headers)

    transport = ASGITransport(app=app_with_runtime)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/proxy/hls/{token}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["cache-control"] == "no-store"
    runtime.http.get_bytes.assert_awaited_once_with(upstream_url, headers=upstream_headers)

    references = re.findall(r"http://test/api/v1/proxy/hls/([^\s\",]+)", response.text)
    assert len(references) == 11
    targets = [app_with_runtime.state.hls_proxy_registry.resolve(token) for token in references]
    assert all(target is not None for target in targets)
    assert {target.url for target in targets if target is not None} == {
        "https://cdn.example.com/live/variants/1080.m3u8",
        "https://cdn.example.com/live/audio/eng.m3u8",
        "https://cdn.example.com/live/iframes.m3u8",
        "https://cdn.example.com/live/keys/session.key",
        "https://cdn.example.com/live/meta.json",
        "https://cdn.example.com/live/keys/segment.key",
        "https://cdn.example.com/live/init.mp4",
        "https://cdn.example.com/live/parts/0.m4s",
        "https://cdn.example.com/live/parts/1.m4s",
        "https://cdn.example.com/live/segments/0.ts",
    }
    assert all(target.headers == upstream_headers for target in targets if target is not None)


@pytest.mark.asyncio
async def test_proxy_hls_recursively_proxies_child_playlists_and_segments(app_with_runtime):
    """A rewritten child playlist remains able to fetch protected segments."""
    runtime = app_with_runtime.state.runtime
    master_url = "https://cdn.example.com/live/master.m3u8"
    child_url = "https://cdn.example.com/live/720/playlist.m3u8"
    segment_url = "https://cdn.example.com/live/720/segment-1.ts"
    upstream_headers = {"Referer": "https://megaplay.buzz/embed"}
    runtime.http.get_bytes = AsyncMock(
        side_effect=[
            b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\n720/playlist.m3u8\n",
            b"#EXTM3U\n#EXTINF:4.0,\nsegment-1.ts\n",
            b"transport-stream-bytes",
        ]
    )
    token = app_with_runtime.state.hls_proxy_registry.register(master_url, upstream_headers)

    transport = ASGITransport(app=app_with_runtime)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        master_response = await client.get(f"/api/v1/proxy/hls/{token}")
        child_token = re.search(r"/proxy/hls/([^\s\",]+)", master_response.text)
        assert child_token is not None
        child_response = await client.get(f"/api/v1/proxy/hls/{child_token.group(1)}")
        segment_token = re.search(r"/proxy/hls/([^\s\",]+)", child_response.text)
        assert segment_token is not None
        segment_response = await client.get(f"/api/v1/proxy/hls/{segment_token.group(1)}")

    assert segment_response.status_code == 200
    assert segment_response.content == b"transport-stream-bytes"
    assert segment_response.headers["content-type"].startswith("video/mp2t")
    assert runtime.http.get_bytes.await_args_list[0].args == (master_url,)
    assert runtime.http.get_bytes.await_args_list[1].args == (child_url,)
    assert runtime.http.get_bytes.await_args_list[2].args == (segment_url,)
    assert all(
        call.kwargs == {"headers": upstream_headers}
        for call in runtime.http.get_bytes.await_args_list
    )
