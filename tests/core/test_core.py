"""Unit tests for core framework components."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from anime_extensions.core import (
    ExtensionRuntime,
    Extractor,
    ExtractorRegistry,
    HttpClient,
    Source,
    SourceCapability,
    SourceMetadata,
    SourceRegistry,
    UpstreamNotFound,
    UpstreamUnavailable,
)
from anime_extensions.models import Anime, Page

# --- Mock Extensions ---


class MockSource(Source):
    metadata = SourceMetadata(
        id="mock-source",
        name="Mock Source",
        base_url="https://mock.source",
        capabilities={SourceCapability.SEARCH, SourceCapability.DETAILS},
    )

    async def get_popular(self, page: int = 1) -> Page[Anime]:
        return Page(items=[], page=page, has_next=False)

    async def get_latest(self, page: int = 1) -> Page[Anime]:
        return Page(items=[], page=page, has_next=False)

    async def search(self, query: str, page: int = 1) -> Page[Anime]:
        return Page(items=[], page=page, has_next=False)

    async def get_details(self, anime_id: str):
        return f"details for {anime_id}"

    async def get_episodes(self, anime_id: str):
        return []

    async def get_servers(self, episode_id: str):
        return []

    async def get_streams(self, episode_id: str, server_id: str):
        return []


class MockExtractor(Extractor):
    name = "Mock Extractor"

    async def extract(self, url: str, **kwargs):
        return [{"url": "http://stream.com", "quality": "1080p"}]


# --- Tests ---


@pytest.mark.asyncio
async def test_http_client_lifecycle():
    """Verify HttpClient starts and closes the aiohttp session."""
    client = HttpClient()
    await client.start()
    assert client.session is not None
    assert not client.session.closed
    await client.close()
    assert client.session is None


@pytest.mark.asyncio
async def test_runtime_composition():
    """Verify ExtensionRuntime correctly orchestrates registries and HTTP."""
    async with ExtensionRuntime() as runtime:
        # Test default registries
        assert isinstance(runtime.sources, SourceRegistry)
        assert isinstance(runtime.extractors, ExtractorRegistry)

        # Register a source
        runtime.sources.register(MockSource)
        source = runtime.get_source("mock-source")
        assert source is not None
        assert isinstance(source, MockSource)
        assert source.context.http == runtime.http


@pytest.mark.asyncio
async def test_extractor_resolution():
    """Verify extractor resolution by regex pattern."""
    runtime = ExtensionRuntime()
    # Register extractor for a specific pattern
    runtime.extractors.register(MockExtractor, r"mock-host\.com")

    extractor_cls = runtime.extractors.resolve("https://mock-host.com/embed/123")
    assert extractor_cls == MockExtractor

    from anime_extensions.core.errors import ExtractorError

    with pytest.raises(ExtractorError):
        runtime.extractors.resolve("https://unknown.com/123")


@pytest.mark.asyncio
async def test_source_context_injection():
    """Verify that instantiated sources receive the correct context."""
    async with ExtensionRuntime() as runtime:
        runtime.sources.register(MockSource)
        source = runtime.get_source("mock-source")

        assert source.context.http == runtime.http
        assert source.context.extractors == runtime.extractors


@pytest.mark.asyncio
async def test_http_error_translation():
    """Verify that 404s are translated to UpstreamNotFound."""
    client = HttpClient()
    await client.start()

    # We mock the internal aiohttp response
    mock_resp = AsyncMock()
    mock_resp.status = 404
    mock_resp.__aenter__.return_value = mock_resp

    # Patch session.get to return our mock
    client.session.get = MagicMock(return_value=mock_resp)

    with pytest.raises(UpstreamNotFound):
        await client.get("https://mock.source/404")

    await client.close()


def test_source_registry_is_generic():
    """Verify source registration does not apply source-specific policies."""
    registry = SourceRegistry()
    registry.register(MockSource)

    assert registry.get("mock-source") is MockSource
    assert MockSource in registry.list_all()


def test_builtin_source_catalogue_marks_mkissa_disabled():
    """Verify built-in source availability policy belongs to the catalogue."""
    from anime_extensions.sources import BUILTIN_SOURCES

    builtins = {item.cls.metadata.id: item for item in BUILTIN_SOURCES}

    assert builtins["mkissa"].enabled is False
    assert all(item.enabled for id_, item in builtins.items() if id_ != "mkissa")


def test_runtime_skips_disabled_builtin_sources():
    """Verify disabled source catalogue entries are not registered."""
    runtime = ExtensionRuntime()

    assert runtime.sources.get("mkissa") is None
    assert {source.metadata.id for source in runtime.sources.list_all()} == {
        "aniwaves",
        "anikoto",
        "animenosub",
    }
    assert len(runtime.extractors) == 12


def test_runtime_accepts_runtime_source_exclusions():
    """Verify callers can exclude enabled built-ins at runtime."""
    runtime = ExtensionRuntime(disabled_sources={"aniwaves", "anikoto"})

    assert runtime.sources.get("aniwaves") is None
    assert runtime.sources.get("anikoto") is None
    assert runtime.sources.get("animenosub") is not None


@pytest.mark.asyncio
async def test_http_error_translation_for_upstream_unavailability():
    """Verify gateway status codes translate to UpstreamUnavailable."""
    client = HttpClient()
    await client.start()
    mock_resp = AsyncMock()
    mock_resp.status = 503
    mock_resp.__aenter__.return_value = mock_resp
    client.session.get = MagicMock(return_value=mock_resp)

    with pytest.raises(UpstreamUnavailable) as exc_info:
        await client.get("https://mock.source/unavailable")

    assert exc_info.value.status_code == 503
    await client.close()
