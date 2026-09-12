"""Comprehensive unit and integration test suite for Anime Extensions REST API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from anime_extensions.core import ExtensionRuntime, Source, SourceCapability, SourceMetadata
from anime_extensions.exceptions import AnimeExtensionError
from anime_extensions.models import Anime, Episode, Page, Server, Stream, Subtitle
from anime_extensions_api.app import create_app, lifespan
from anime_extensions_api.config import APISettings, CacheSettings
from anime_extensions_api.services.cache import AsyncTTLCache


class MockSource(Source):
    """Mock anime source for fast, deterministic unit testing."""

    metadata = SourceMetadata(
        id="mock",
        name="MockSource",
        base_url="https://mock.example.com",
        capabilities={
            SourceCapability.SEARCH,
            SourceCapability.DETAILS,
            SourceCapability.POPULAR,
            SourceCapability.LATEST,
            SourceCapability.EPISODES,
            SourceCapability.SERVERS,
            SourceCapability.STREAMS,
        },
    )

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        if page > 2:
            return Page(items=[], page=page, has_next=False)
        return Page(
            items=[
                Anime(
                    id="mock-1",
                    title="Mock Anime 1",
                    url="https://mock.example.com/watch/mock-1",
                    thumbnail="https://mock.example.com/thumb1.jpg",
                    genres=["Action", "Adventure"],
                    status="completed",
                    score=8.5,
                )
            ],
            page=page,
            has_next=True,
        )

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        return Page(
            items=[
                Anime(
                    id="mock-2",
                    title="Mock Anime 2",
                    url="https://mock.example.com/watch/mock-2",
                    status="ongoing",
                )
            ],
            page=page,
            has_next=False,
        )

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        if query == "notfound":
            return Page(items=[], page=page, has_next=False)
        return Page(
            items=[
                Anime(
                    id="mock-1",
                    title=f"Result for {query}",
                    url="https://mock.example.com/watch/mock-1",
                )
            ],
            page=page,
            has_next=False,
        )

    async def get_details(self, anime_id: str) -> Anime:
        if anime_id == "invalid":
            raise AnimeExtensionError("Anime not found on upstream")
        return Anime(
            id=anime_id,
            title="Detailed Mock Anime",
            url=f"https://mock.example.com/watch/{anime_id}",
            description="Full synopsis goes here.",
            genres=["Fantasy", "Sci-Fi"],
            status="ongoing",
            score=9.1,
        )

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        return [
            Episode(
                id=f"{anime_id}-ep-1",
                number=1.0,
                title="Episode 1: The Beginning",
                has_sub=True,
                has_dub=True,
            ),
            Episode(
                id=f"{anime_id}-ep-2",
                number=2.0,
                title="Episode 2: The Journey",
                has_sub=True,
            ),
        ]

    async def get_servers(self, episode_id: str) -> list[Server]:
        return [
            Server(id="srv-1", name="Vidplay", type="Sub"),
            Server(id="srv-2", name="DoodStream", type="Sub"),
        ]

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        if server_id == "broken":
            raise AnimeExtensionError("Extractor failed to parse media token")
        return [
            Stream(
                url="https://mock.example.com/stream.m3u8",
                quality="1080p",
                is_hls=True,
                headers={"Referer": "https://mock.example.com/"},
                subtitles=[
                    Subtitle(
                        url="https://mock.example.com/sub.vtt",
                        label="English",
                        language="en",
                    )
                ],
            )
        ]


class LimitedMockSource(Source):
    """Mock source with minimal capabilities for capability enforcement testing."""

    metadata = SourceMetadata(
        id="limited",
        name="LimitedMockSource",
        base_url="https://limited.example.com",
        capabilities={SourceCapability.SEARCH},
    )

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        return Page(items=[], page=page, has_next=False)

    async def get_details(self, anime_id: str) -> Anime:
        raise NotImplementedError

    async def get_episodes(self, anime_id: str) -> list[Episode]:
        raise NotImplementedError

    async def get_servers(self, episode_id: str) -> list[Server]:
        raise NotImplementedError

    async def get_streams(self, episode_id: str, server_id: str) -> list[Stream]:
        raise NotImplementedError


@pytest.fixture
async def app():
    """Create an initialized application with an injected mock source."""
    settings = APISettings(
        cache=CacheSettings(enabled=True, popular_ttl_seconds=60),
    )
    app = create_app(settings)
    runtime = ExtensionRuntime()
    await runtime.start()
    runtime.sources.register(MockSource)
    runtime.sources.register(LimitedMockSource)
    app.state.runtime = runtime
    app.state.cache = AsyncTTLCache(max_items=1000)
    try:
        yield app
    finally:
        await runtime.close()
        app.state.cache.clear()


@pytest.mark.asyncio
async def test_api_production_lifespan():
    """Verify the production lifespan owns runtime and cache lifecycles."""
    app = create_app()

    async with lifespan(app):
        runtime = app.state.runtime
        cache = app.state.cache

        assert runtime.http.session is not None
        assert not runtime.http.session.closed
        await cache.set("lifecycle", "value", ttl_seconds=60)
        assert await cache.get("lifecycle") == "value"

    assert runtime.http.session is None
    assert await cache.get("lifecycle") is None


@pytest.mark.asyncio
async def test_api_production_unmocked_e2e():
    """Verify production dependencies serve health and source catalog endpoints."""
    app = create_app()

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            sources = await client.get("/api/v1/sources")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert sources.status_code == 200
    assert sources.json()["count"] == 3


@pytest.mark.asyncio
async def test_health_check_endpoints(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Root /health
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["active_sources"] >= 1
        assert "uptime_seconds" in data
        assert "cache_stats" in data
        assert "X-Process-Time" in res.headers

        # /api/v1/health
        res_v1 = await client.get("/api/v1/health")
        assert res_v1.status_code == 200
        assert res_v1.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_sources_endpoints(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # List sources
        res = await client.get("/api/v1/sources")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1
        assert any(s["id"] == "mock" for s in data["sources"])

        # Get specific source
        res_mock = await client.get("/api/v1/sources/mock")
        assert res_mock.status_code == 200
        assert res_mock.json()["id"] == "mock"
        assert res_mock.json()["name"] == "MockSource"

        # Invalid source
        res_invalid = await client.get("/api/v1/sources/nonexistent_source")
        assert res_invalid.status_code == 404
        err = res_invalid.json()["error"]
        assert err["code"] == "SOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_anime_popular_and_cache(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First request (cache miss)
        res = await client.get("/api/v1/mock/popular?page=1")
        assert res.status_code == 200
        data = res.json()
        assert data["page"] == 1
        assert data["has_next"] is True
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "mock-1"

        # Second request (cache hit)
        res_cached = await client.get("/api/v1/mock/popular?page=1")
        assert res_cached.status_code == 200
        assert res_cached.json()["items"][0]["title"] == "Mock Anime 1"
        assert app.state.cache.hits >= 1


@pytest.mark.asyncio
async def test_anime_latest(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/mock/latest?page=1")
        assert res.status_code == 200
        data = res.json()
        assert data["page"] == 1
        assert data["items"][0]["title"] == "Mock Anime 2"


@pytest.mark.asyncio
async def test_anime_search(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Valid search
        res = await client.get("/api/v1/mock/search?q=Naruto&page=1")
        assert res.status_code == 200
        data = res.json()
        assert data["items"][0]["title"] == "Result for Naruto"

        # Missing query parameter
        res_missing = await client.get("/api/v1/mock/search")
        assert res_missing.status_code == 422

        # Invalid page
        res_bad_page = await client.get("/api/v1/mock/search?q=Naruto&page=0")
        assert res_bad_page.status_code == 422


@pytest.mark.asyncio
async def test_anime_details(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/mock/anime/mock-1")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "mock-1"
        assert data["title"] == "Detailed Mock Anime"
        assert data["score"] == 9.1
        assert "Fantasy" in data["genres"]


@pytest.mark.asyncio
async def test_anime_episodes(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/mock/episodes/mock-1")
        assert res.status_code == 200
        episodes = res.json()
        assert len(episodes) == 2
        assert episodes[0]["number"] == 1.0
        assert episodes[0]["has_sub"] is True
        assert episodes[1]["title"] == "Episode 2: The Journey"


@pytest.mark.asyncio
async def test_servers_and_streams(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get servers
        res_srv = await client.get("/api/v1/mock/servers/mock-1-ep-1")
        assert res_srv.status_code == 200
        servers = res_srv.json()
        assert len(servers) == 2
        assert servers[0]["name"] == "Vidplay"

        # Get streams for server
        res_stream = await client.get("/api/v1/mock/streams/mock-1-ep-1?server_id=srv-1")
        assert res_stream.status_code == 200
        streams = res_stream.json()
        assert len(streams) == 1
        assert streams[0]["quality"] == "1080p"
        assert streams[0]["is_hls"] is True
        assert len(streams[0]["subtitles"]) == 1
        assert streams[0]["subtitles"][0]["label"] == "English"


@pytest.mark.asyncio
async def test_upstream_error_handling(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Upstream failure on details
        res = await client.get("/api/v1/mock/anime/invalid")
        assert res.status_code == 502
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "UPSTREAM_SOURCE_ERROR"

        # Upstream failure on streams
        res_stream = await client.get("/api/v1/mock/streams/mock-1-ep-1?server_id=broken")
        assert res_stream.status_code == 502
        assert res_stream.json()["error"]["code"] == "UPSTREAM_SOURCE_ERROR"


@pytest.mark.asyncio
async def test_unsupported_capability(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # LimitedMockSource only has capability SEARCH
        res_popular = await client.get("/api/v1/limited/popular")
        assert res_popular.status_code == 501
        assert res_popular.json()["error"]["code"] == "UNSUPPORTED_CAPABILITY"

        res_details = await client.get("/api/v1/limited/anime/some-id")
        assert res_details.status_code == 501
        assert res_details.json()["error"]["code"] == "UNSUPPORTED_CAPABILITY"

        # Search should still work (will return empty page)
        res_search = await client.get("/api/v1/limited/search?q=test")
        assert res_search.status_code == 200
