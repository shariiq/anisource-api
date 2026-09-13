"""Tests for server-level diagnostics in the deployment verification script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from anime_extensions import Stream, UpstreamUnreachable


@pytest.fixture(scope="module")
def deployed_module():
    """Load the standalone diagnostic script as a module."""
    script_path = Path(__file__).parents[1] / "test_deployed.py"
    spec = importlib.util.spec_from_file_location("deployment_diagnostics", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_resolve_servers_skips_unreachable_upstream_and_continues(deployed_module):
    """Verify an unreachable host does not conceal other server outcomes."""

    async def resolve(server_id: str) -> list[Stream]:
        if server_id == "unreachable":
            raise UpstreamUnreachable("cannot connect to host")
        if server_id == "broken":
            raise RuntimeError("extractor parsing failed")
        return [
            Stream(
                url="https://stream.example.test/master.m3u8",
                quality="720p",
                is_hls=True,
                headers={"Referer": "https://embed.example.test/", "User-Agent": "test"},
            )
        ]

    results = await deployed_module.resolve_servers(
        [("working", "Working"), ("unreachable", "Offline"), ("broken", "Broken")], resolve
    )

    assert results[0].stream_count == 1
    assert results[0].error is None
    assert results[1].skip_reason == "cannot connect to host"
    assert results[1].error is None
    assert results[2].error == "RuntimeError: extractor parsing failed"

    report = deployed_module.PipelineReport("local", "mock")
    report.start()
    deployed_module.record_stream_results(report, results)
    report.finish()

    assert report.status is deployed_module.Status.PASS
    assert report.servers_tested == 3
    assert report.servers_resolved == 1
    assert report.streams_resolved == 1
    assert report.errors == ["server 'Broken': RuntimeError: extractor parsing failed"]
