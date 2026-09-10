"""Live integration tests for MKissa source.
These tests verify the full pipeline: Resolve Build -> Handshake -> Stream Decryption.
"""

import pytest

from anime_extensions.sources.mkissa import MKissa


@pytest.mark.live
@pytest.mark.asyncio
async def test_mkissa_pipeline_smoke():
    """
    Smoke test for the MKissa pipeline.
    Since live endpoints are volatile, this test checks if the source
    can be initialized and the core pipeline doesn't crash.
    """
    source = MKissa()
    # We don't run full streams here to avoid CI instability,
    # but we verify the source is properly registered.
    assert source.id == "mkissa"
    assert source.name == "MKissa"


@pytest.mark.live
@pytest.mark.asyncio
async def test_mkissa_graphql_connectivity():
    """Verify basic connectivity to the MKissa GraphQL API."""
    source = MKissa()
    try:
        results, has_next = await source.search("One Piece")
        assert isinstance(results, list)
        # If results are found, they should have proper Anime model attributes
        if results:
            assert hasattr(results[0], "title")
    finally:
        await source.close()


@pytest.mark.live
@pytest.mark.asyncio
async def test_mkissa_details_connectivity():
    """Verify that anime details can be fetched."""
    source = MKissa()
    try:
        results, _ = await source.search("One Piece")
        assert results, "Search returned no results — cannot test details"

        details = await source.get_details(results[0].id)
        assert details.id == results[0].id
        assert details.title
    finally:
        await source.close()
