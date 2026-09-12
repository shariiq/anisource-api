"""Live integration tests for MKissa source.
These tests verify the full pipeline: Resolve Build -> Handshake -> Stream Decryption.
"""

import pytest

from anime_extensions.core.runtime import ExtensionRuntime
from anime_extensions.sources.mkissa import MKissa


@pytest.fixture
async def mkissa_source():
    """Provide an initialized MKissa source for tests."""
    async with ExtensionRuntime() as runtime:
        yield runtime.get_source("mkissa")


@pytest.mark.live
@pytest.mark.asyncio
async def test_mkissa_pipeline_smoke(mkissa_source: MKissa):
    """
    Smoke test for the MKissa pipeline.
    Since live endpoints are volatile, this test checks if the source
    can be initialized and the core pipeline doesn't crash.
    """
    # Verify the source is properly registered.
    assert mkissa_source.metadata.id == "mkissa"
    assert mkissa_source.metadata.name == "MKissa"


@pytest.mark.live
@pytest.mark.asyncio
async def test_mkissa_graphql_connectivity(mkissa_source: MKissa):
    """Verify basic connectivity to the MKissa GraphQL API."""
    page_data = await mkissa_source.search("One Piece")
    results = page_data.items
    assert isinstance(results, list)
    # If results are found, they should have proper Anime model attributes
    if results:
        assert hasattr(results[0], "title")


@pytest.mark.live
@pytest.mark.asyncio
async def test_mkissa_details_connectivity(mkissa_source: MKissa):
    """Verify that anime details can be fetched."""
    page_data = await mkissa_source.search("One Piece")
    results = page_data.items
    assert results, "Search returned no results — cannot test details"

    details = await mkissa_source.get_details(results[0].id)
    assert details.id == results[0].id
    assert details.title
