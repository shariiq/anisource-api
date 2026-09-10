"""CLI entrypoint for running the Anime Extensions API server."""

import argparse
import sys

import uvicorn

from .config import get_settings


def cli() -> None:
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Run the Anime Extensions REST API server.",
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Bind socket to this host (overrides ANIME_API_HOST env var).",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Bind socket to this port (overrides ANIME_API_PORT env var).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="Number of worker processes.",
    )

    args = parser.parse_args()
    settings = get_settings()

    host = args.host or settings.host
    port = args.port or settings.port
    reload = args.reload or settings.debug
    workers = args.workers or settings.workers

    print(
        f"Starting Anime Extensions API server on {host}:{port} "
        f"(workers: {workers}, reload: {reload})..."
    )

    uvicorn.run(
        "anime_extensions_api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


if __name__ == "__main__":
    cli()
    sys.exit(0)
