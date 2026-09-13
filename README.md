# Anime Extensions (Python)

A modern asynchronous Python SDK and production FastAPI service for anime catalogs, episode indexes, server resolution, and video extraction.

[![CI](https://github.com/shariiq/anisource-api/actions/workflows/ci.yml/badge.svg)](https://github.com/shariiq/anisource-api/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## Features

- **Layered SDK architecture**: Framework contracts and infrastructure live in `anime_extensions.core`; source and extractor plugins build on those contracts without depending on the API.
- **Centralized asynchronous HTTP**: `HttpClient` owns connection pooling, timeouts, proxy configuration, secure TLS defaults, and translation of upstream failures into typed exceptions.
- **Explicit runtime lifecycle**: `ExtensionRuntime` is the composition root for the HTTP client and extension registries. It supports `async with` for deterministic startup and shutdown.
- **Dependency injection**: Every source and extractor receives an `ExtensionContext` (aliased as `SourceContext` for backward compatibility) rather than creating sessions or reaching into global application state.
- **Catalogue-driven discovery**: `BUILTIN_SOURCES` and `BUILTIN_EXTRACTORS` register plugins without global state or module-level side-effects.
- **Typed domain models**: Sources return consistent anime, episode, server, stream, and subtitle models.
- **Production API behavior**: FastAPI dependencies are resolved from application state, SDK errors map to appropriate HTTP status codes, and response contracts remain stable.
- **Stampede-resistant caching**: `AsyncTTLCache.get_or_set` coalesces concurrent cache misses for the same key into one upstream request.
- **Active sources**: AniWaves and Anikoto.
- **Built-in extractors**: Byse, DoodStream, EchoVideo, GogoStream, MegaPlay, Moon/Filemoon, Mp4Upload, Okru, StreamWish, Streamlare, VidMoly, Vtube, and WolfStream.

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

Built-in sources and extractors are discovered when the runtime is constructed from the explicit `BUILTIN_SOURCES` and `BUILTIN_EXTRACTORS` catalogues. A source receives the runtime-managed `HttpClient` and extractor registry through its `ExtensionContext` (`SourceContext` remains a compatibility alias). Use `ExtensionRuntime(disabled_sources={...})` to exclude enabled built-in sources for a specific runtime; catalogue entries may also be disabled with `BuiltinSource(..., enabled=False)`.

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

## Performance & Future Optimizations

The SDK is designed for high-concurrency production deployments. Key optimizations include:

- **uvloop compatibility**: `uvloop` is a Linux-only dependency, and the Render `Procfile`, `render.yaml`, and Docker entry point explicitly select it for Uvicorn. Local Windows development continues to use the standard `asyncio` loop.
- **Native C acceleration**: CPU-bound operations, such as the Byse stream Proof-of-Work solver, use a thread-safe, stack-allocated native C implementation (`_byse_pow_dll.c`) compiled in the container (`gcc -O3 -march=native -funroll-loops`) so the event loop remains responsive.

### Keep in Mind for Future Work

- **Prioritize Fast Path Extractors**: The stream pipeline resolves server extraction concurrently. Future optimizations should look into yielding fast-path extractors (like EchoVideo) before CPU-bound or captcha-heavy extractors (like Byse) finish, reducing response latency.
- **Reduced API Fetches**: Maximize the usage of composite opaque IDs (e.g., `&epurl=`) in sources like `Anikoto` and `AniWaves` to prevent redundant `get_details()` fallback fetches during `get_episodes()` calls.
- **Diagnostics Integrity**: True latency bottlenecks should be fixed in the source pipeline. Diagnostic scripts (e.g., `test_deployed.py`) must never be modified simply to hide overhead or artificially improve benchmark metrics.

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
5. Append the class to `BUILTIN_SOURCES` in `anime_extensions/sources/__init__.py`.
6. Add unit tests and `tests/live/test_live_<source>.py` coverage.

### Extractor

1. Inherit from `Extractor` in `anime_extensions/core/extractor.py`.
2. Use `self.context.http` for network access.
3. Define the host URL pattern and priority in the `BUILTIN_EXTRACTORS` entry.
4. Append the `(ExtractorClass, pattern, priority)` entry to `BUILTIN_EXTRACTORS` in `anime_extensions/extractors/__init__.py`.
5. Add deterministic unit tests for parsing and URL resolution.

See [the scraper maintenance guide](docs/MAINTENANCE.md) for porting and repair guidance.

## Contributing

- [Writing Extractors Guide](docs/WRITING_EXTRACTORS.md) — detailed guidance for implementing video extractors
- [Scraper Maintenance Guide](docs/MAINTENANCE.md) — evidence-driven protocol for porting and repairing scrapers

## Verification

Git hooks automatically handle validation:
- `.githooks/pre-commit` runs Ruff linting and formatting checks.
- `.githooks/pre-push` runs Ruff linting, formatting, bytecode compilation, and the complete unit-test suite.

Run only targeted tests or lints relevant to the changed area during active debugging:

```bash
uv run pytest tests/sources/test_<source>.py::<test_name>
uv run ruff check path/to/changed_file.py
```

Targeted live tests may be run explicitly with `--run-live` (or via `test_deployed.py --local-only`); they make real requests to third-party services and can fail when an upstream site is unavailable. GitHub Actions is authoritative for the full test and live-test matrix. Unit tests remain network-isolated.

## License

MIT
