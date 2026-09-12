# Anime Extensions (Python)

A modern asynchronous Python SDK and production FastAPI service for anime catalogs, episode indexes, server resolution, and video extraction.

[![CI](https://github.com/shariiq/anisource-api/actions/workflows/ci.yml/badge.svg)](https://github.com/shariiq/anisource-api/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## Features

- **Layered SDK architecture**: Framework contracts and infrastructure live in `anime_extensions.core`; source and extractor plugins build on those contracts without depending on the API.
- **Centralized asynchronous HTTP**: `HttpClient` owns connection pooling, timeouts, proxy configuration, secure TLS defaults, and translation of upstream failures into typed exceptions.
- **Explicit runtime lifecycle**: `ExtensionRuntime` is the composition root for the HTTP client and extension registries. It supports `async with` for deterministic startup and shutdown.
- **Dependency injection**: Every source and extractor receives a `SourceContext` rather than creating sessions or reaching into global application state.
- **Catalogue-driven discovery**: Built-in sources and extractors are explicitly registered from catalogues (`BUILTIN_SOURCES`, `BUILTIN_EXTRACTORS`) during runtime initialization.
- **Typed domain models**: Sources return consistent anime, episode, server, stream, and subtitle models.
- **Production API behavior**: FastAPI dependencies are resolved from application state, SDK errors map to appropriate HTTP status codes, and response contracts remain stable.
- **Stampede-resistant caching**: `AsyncTTLCache.get_or_set` coalesces concurrent cache misses for the same key into one upstream request.
- **Active sources**: AniWaves, Anikoto, and AnimeNoSub (MKissa quarantined due to upstream anti-bot/CAPTCHA).
- **Built-in extractors**: Byse/Filemoon, DoodStream, and EchoVideo-compatible hosts.

## Architecture

```text
anime_extensions/
├── core/                  # Contracts, models, HTTP, registries, runtime
├── sources/               # Source plugins (built-in catalogue)
└── extractors/            # Video extractor plugins (built-in catalogue)

anime_extensions_api/
├── routers/               # HTTP route definitions
├── services/              # Cache service
├── dependencies.py        # FastAPI dependency aliases
├── schemas.py             # Public response schemas
└── app.py                 # Application factory and lifecycle
```

Dependencies flow inward:

```text
core ← sources/extractors ← runtime ← API
```

The SDK does not depend on FastAPI. `ExtensionRuntime` can be used independently by applications, scripts, tests, and alternative frontends.

## Requirements

- Python 3.14+
- [`uv`](https://docs.astral.sh/uv/)

## Installation

```bash
git clone https://github.com/shariiq/anisource-api.git
cd anisource-api
uv sync --extra dev
```

A standard editable installation is also supported:

```bash
pip install -e ".[dev]"
```

## Using the SDK

```python
import asyncio

from anime_extensions import ExtensionRuntime


async def main() -> None:
    async with ExtensionRuntime() as runtime:
        source = runtime.get_source("aniwaves")
        if source is None:
            raise RuntimeError("Source is not registered")

        page = await source.search(query="One Piece", page=1)
        print(page.items, page.has_next)


asyncio.run(main())
```

Built-in sources and extractors are discovered when the runtime starts. A source receives the runtime-managed `HttpClient` and extractor registry through its `SourceContext`.

## Running the API

Use the installed CLI:

```bash
uv run anime-api --host 0.0.0.0 --port 8000 --reload
```

Or launch Uvicorn directly:

```bash
uv run uvicorn anime_extensions_api.app:app --host 0.0.0.0 --port 8000 --reload
```

Interactive documentation is available at:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

## API Contracts

### Health

| Method | Endpoint | Response |
|---|---|---|
| `GET` | `/health` | Service health and runtime telemetry |
| `GET` | `/api/v1/health` | Versioned health alias |

### Sources

| Method | Endpoint | Response |
|---|---|---|
| `GET` | `/api/v1/sources` | `{"sources": [...], "count": N}` |
| `GET` | `/api/v1/sources/{source_id}` | Source metadata |

### Anime catalog

| Method | Endpoint | Response |
|---|---|---|
| `GET` | `/api/v1/{source_id}/popular?page=1` | Paginated anime object |
| `GET` | `/api/v1/{source_id}/latest?page=1` | Paginated anime object |
| `GET` | `/api/v1/{source_id}/search?q={query}&page=1` | Paginated anime object |
| `GET` | `/api/v1/{source_id}/anime/{anime_id}` | Anime details object |
| `GET` | `/api/v1/{source_id}/episodes/{anime_id}` | Plain episode array |

Paginated endpoints return:

```json
{
  "items": [],
  "page": 1,
  "has_next": false,
  "total_returned": 0
}
```

### Servers and streams

| Method | Endpoint | Response |
|---|---|---|
| `GET` | `/api/v1/{source_id}/servers/{episode_id}` | Plain server array |
| `GET` | `/api/v1/{source_id}/streams/{episode_id}?server_id={server_id}` | Plain stream array |

IDs are opaque source-owned values and may contain path separators. Clients should URL-encode IDs when constructing requests.

## Adding an Extension

### Source

1. Inherit from `Source` in `anime_extensions/core/source.py`.
2. Define source metadata (declaring its capabilities like `SourceCapability.SEARCH`) and implement the supported asynchronous methods:
   - `get_popular(page)`
   - `get_latest(page)`
   - `search(query, page)`
   - `get_details(anime_id)`
   - `get_episodes(anime_id)`
   - `get_servers(episode_id)`
   - `get_streams(episode_id, server_id)`
3. Unimplemented capabilities will automatically raise `UnsupportedCapabilityError`.
4. Use `self.context.http` for all network access.
5. Add the class to `BUILTIN_SOURCES` in `anime_extensions/sources/__init__.py`.
6. Add unit tests and `tests/live/test_live_<source>.py` coverage.

### Extractor

1. Inherit from `Extractor` in `anime_extensions/core/extractor.py`.
2. Use `self.context.http` for network access.
3. Add the extractor, its regex pattern, and priority to `BUILTIN_EXTRACTORS` in `anime_extensions/extractors/__init__.py`.
4. Add deterministic unit tests for parsing and URL resolution.

See [the scraper maintenance guide](docs/MAINTENANCE.md) for porting and repair guidance.

## Architecture Roadmap

The project tracks planned architectural improvements in [docs/ROADMAP.md](docs/ROADMAP.md). This includes SDK enhancements, API optimizations, and library-grade refactorings planned for incremental implementation.

## Contributing

- [Writing Extractors Guide](docs/WRITING_EXTRACTORS.md) — detailed guidance for implementing video extractors
- [Scraper Maintenance Guide](docs/MAINTENANCE.md) — evidence-driven protocol for porting and repairing scrapers

## Verification

Run all four checks before committing:

```bash
uv run ruff check anime_extensions anime_extensions_api tests
uv run ruff format --check anime_extensions anime_extensions_api tests
uv run pytest
uv run pytest tests/live/ --run-live
```

Live tests make real requests to third-party services and can fail when an upstream site is unavailable or changes behavior. Unit tests remain network-isolated.

## License

MIT
