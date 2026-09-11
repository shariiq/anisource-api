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
)

# --- Mock Extensions ---


class MockSource(Source):
    metadata = SourceMetadata(
        id="mock-source",
        name="Mock Source",
        base_url="https://mock.source",
        capabilities={SourceCapability.SEARCH, SourceCapability.DETAILS},
    )

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

        assert source.context.runtime == runtime
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


def test_source_registry_quarantine():
    from anime_extensions.core.registry import _QUARANTINED_SOURCES, SourceRegistry

    registry = SourceRegistry()
    registry.register(MockSource)

    assert registry.get("mock-source") is MockSource
    assert MockSource in registry.list_all()

    try:
        _QUARANTINED_SOURCES.add("mock-source")
        assert registry.get("mock-source") is None
        assert MockSource not in registry.list_all()
    finally:
        _QUARANTINED_SOURCES.remove("mock-source")
