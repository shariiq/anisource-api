# Anime Extensions (Python)

A high-performance, asynchronous Python library and production-grade REST API for anime scrapers, episode indexers, server resolvers, and video extractors (ported from Tachiyomi / Aniyomi Kotlin extensions).

[![CI](https://github.com/YOUR_GITHUB_USERNAME/anime-extensions-py/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_GITHUB_USERNAME/anime-extensions-py/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

---

## ⚡ Features

- **Async & Non-Blocking**: Built from the ground up on `aiohttp` and `asyncio` for high concurrency.
- **Complete Extractor Parity**:
  - **DoodStream**: Direct MD5 pass and playback token generation.
  - **Byse / Filemoon**: ECDSA P-256 keypair attestation, ChaCha-based Proof-of-Work (PoW) solver, and AES-GCM decryption.
  - **EchoVideo (Vidplay / MyCloud / DatSaV)**: Quality-mapped streams (1080p/720p/480p/360p), subtitle tracks, and HLS playlist absolutizing.
- **REST API (`anime_extensions_api`)**:
  - Built with **FastAPI** & **Pydantic v2** for type safety and auto-generated OpenAPI documentation.
  - **Connection Pooling & Lifecycle**: Persistent connection reuse across scrapers.
  - **In-Memory TTL Caching**: Low-latency caching for popular listings, search results, anime metadata, and episode catalogs.
  - **Unified Error Handling**: Clear structured JSON error responses with proper HTTP status codes.
  - **Health & Telemetry**: `/health` endpoint tracking uptime, memory usage, cache hit rate, and active scrapers.

---

## 🚀 Getting Started

### 1. Installation

This project targets Python 3.12+ and uses [uv](https://docs.astral.sh/uv/) for fast, reproducible environments:

```bash
# Clone the repository and enter the project
 git clone https://github.com/YOUR_GITHUB_USERNAME/anime-extensions-py.git
 cd anime-extensions-py

# Install uv (if it is not already installed), then install the project
uv sync --extra dev
```

`pip install -e ".[dev]"` remains supported for standard Python environments.

### 2. Running the REST API

You can start the API server via the CLI script:

```bash
anime-api --host 0.0.0.0 --port 8000 --reload
```

Or directly using `uvicorn`:

```bash
uvicorn anime_extensions_api.app:app --host 0.0.0.0 --port 8000 --reload
```

Once running, explore the interactive documentation:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📡 API Endpoints

### 🩺 Health & System
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application status, uptime, memory, and cache telemetry. |
| `GET` | `/api/v1/health` | Versioned alias for system health check. |

### 🔍 Sources
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/sources` | List all registered scrapers (e.g. `aniwaves`, `anikoto`). |
| `GET` | `/api/v1/sources/{source_id}` | Get metadata for a specific source. |

### 📺 Anime Catalog & Discovery
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/{source_id}/popular?page=1` | Fetch trending/popular anime listing. |
| `GET` | `/api/v1/{source_id}/latest?page=1` | Fetch latest updated anime listing. |
| `GET` | `/api/v1/{source_id}/search?q={query}&page=1` | Keyword search for anime titles. |
| `GET` | `/api/v1/{source_id}/anime/{anime_id}` | Comprehensive details, score, genres, and synopsis. |
| `GET` | `/api/v1/{source_id}/episodes/{anime_id}` | Full episode list with sub/dub availability. |

### 🎬 Streams & Servers
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/{source_id}/servers/{episode_id}` | Available video hosters (Vidplay, DoodStream, etc). |
| `GET` | `/api/v1/{source_id}/streams/{episode_id}?server_id={server_id}` | Direct stream URLs (HLS/MP4), headers, and subtitle tracks. |

---

## 🔧 Maintenance

The Python source layout intentionally mirrors the Kotlin extension methods and selectors. When an upstream extension changes, use the [scraper maintenance guide](docs/MAINTENANCE.md) to locate and port selector, endpoint, VRF, or extractor updates while preserving parity.

## 🧪 Testing

Run the full automated test suite:

```bash
pytest
```

Run specific test files:

```bash
# Test API endpoints, schemas, caching, and error handling
pytest tests/test_api.py -v

# Run live scraper tests
pytest test_aniwaves.py -v
pytest test_e2e.py -v
```

---

## 🛠️ Configuration

Configuration is managed via environment variables (prefix `ANIME_API_`):

| Variable | Default | Description |
|---|---|---|
| `ANIME_API_HOST` | `0.0.0.0` | API bind host. |
| `ANIME_API_PORT` | `8000` | API bind port. |
| `ANIME_API_DEBUG` | `false` | Enable debug logs & reload. |
| `ANIME_API_CACHE_ENABLED` | `true` | Toggle in-memory caching. |
| `ANIME_API_CACHE_POPULAR_TTL` | `1800` | Popular listing TTL (seconds). |
| `ANIME_API_CACHE_DETAILS_TTL` | `3600` | Anime details TTL (seconds). |
| `ANIME_API_CACHE_STREAMS_TTL` | `300` | Stream URLs TTL (seconds). |
