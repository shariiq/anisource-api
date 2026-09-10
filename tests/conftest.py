"""Global Pytest configurations, fixtures, and markers."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options to pytest."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live tests that make actual network requests to external sources.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live: mark test as a live network test that requires --run-live to execute."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests if --run-live is not provided."""
    if config.getoption("--run-live"):
        # --run-live given in CLI: do not skip live tests
        return

    skip_live = pytest.mark.skip(reason="need --run-live option to run this test")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
