# Scraper Maintenance Guide

This guide covers source and extractor repairs in the current `anime-extensions-py` architecture. The parent Kotlin extension repository is read-only reference material; all Python changes, tests, and commits belong in this repository.

## Architecture Map

| Layer | Location | Responsibility |
|---|---|---|
| Core contracts | `anime_extensions/core/source.py`, `extractor.py` | Source and extractor interfaces |
| Domain models | `anime_extensions/core/models.py`, `metadata.py` | Anime, episode, server, stream, subtitle, and source metadata types |
| Networking | `anime_extensions/core/http.py` | Shared session lifecycle, pooling, timeouts, TLS, and HTTP error translation |
| Registration | `anime_extensions/core/registry.py` | Source and URL-pattern extractor registries and decorators |
| Composition | `anime_extensions/core/runtime.py` | `ExtensionRuntime` and `SourceContext` dependency injection |
| Sources | `anime_extensions/sources/` | Site-specific catalog and server implementations |
| Extractors | `anime_extensions/extractors/` | Hoster-specific stream extraction |
| API | `anime_extensions_api/` | FastAPI routing, schemas, caching, lifecycle, and error responses |

A scraper must not create or close its own `aiohttp.ClientSession`. Use `self.context.http` so requests share the runtime-managed connection pool and consistent timeout, TLS, proxy, and exception behavior.

TLS certificate verification is enabled by default. Do not disable it globally to work around one upstream. If an integration has a legitimate compatibility requirement, isolate and document that exception as narrowly as possible.

## Source Pipeline

Every source implements the same asynchronous pipeline:

1. `search(query, page)` returns `(list[Anime], has_next)`.
2. `get_details(anime_id)` returns `Anime` metadata.
3. `get_episodes(anime_id)` returns `list[Episode]`.
4. `get_servers(episode_id)` returns `list[Server]`.
5. `get_streams(episode_id, server_id)` returns `list[Stream]` with valid `http://` or `https://` URLs.

Popular and latest listings follow the same paginated tuple convention as search.

## Kotlin-to-Python Mapping

| Kotlin extension concept | Python SDK method |
|---|---|
| `popularAnimeParse(response)` | `get_popular(page)` |
| `latestUpdatesParse(response)` | `get_latest(page)` |
| `searchAnimeParse(response)` | `search(query, page)` |
| `animeDetailsParse(response)` | `get_details(anime_id)` |
| `episodeListParse(response)` | `get_episodes(anime_id)` |
| server/embed discovery | `get_servers(episode_id)` |
| `videoListParse(response)` / extractor calls | `get_streams(episode_id, server_id)` and registered extractors |

When porting an upstream change, preserve the Python contracts rather than reproducing Kotlin framework plumbing. Port selectors, endpoints, request shapes, VRF logic, decryption behavior, and extractor routing.

## Repair Workflow

### 1. Reproduce the failure narrowly

Run the affected live test first:

```bash
uv run pytest tests/live/test_live_<source>.py --run-live -v
```

Determine which pipeline boundary fails: discovery, details, episodes, servers, or streams. Avoid changing extractor code for a catalog parsing failure, or source parsing for a hoster failure.

### 2. Compare upstream behavior

Inspect the corresponding Kotlin implementation for:

- base URL and endpoint changes;
- CSS selectors and HTML structure;
- query and form parameters;
- headers, referers, cookies, and AJAX markers;
- pagination indicators;
- VRF keys, transformations, or encrypted payload shapes;
- server labels and embed URL normalization;
- extractor routing or supported hostnames.

Apply only the behavior needed by the Python source or extractor.

### 3. Update source parsing

For empty listings or missing metadata:

1. Compare the Kotlin selectors with the source implementation under `anime_extensions/sources/<source>/`.
2. Update the corresponding `BeautifulSoup` selector.
3. Preserve opaque source IDs exactly; API path routes are designed to carry nested IDs.
4. Return core domain models, not API schemas or dictionaries.
5. Keep pagination detection explicit and return an accurate `has_next` value.

Example selector translation:

```kotlin
document.selectFirst("h1.title")
```

```python
soup.select_one("h1.title")
```

### 4. Update VRF or API request logic

For a protected JSON endpoint:

1. Compare exchange keys, cipher parameters, URL encoding order, and transformation order with Kotlin.
2. Verify whether the site changed request method, content type, or required headers.
3. Route requests through `self.context.http`.
4. Let core HTTP exceptions propagate unless the source can add meaningful domain context.
5. Translate malformed successful responses into `ParsingError`; do not disguise them as network errors.

### 5. Update extractor behavior

If server discovery succeeds but streams do not resolve:

1. Confirm the embed URL matches a registered extractor pattern.
2. Check `anime_extensions/extractors/` for host-specific token, signature, key, or playlist changes.
3. Keep extractor URL patterns narrowly scoped to avoid resolving unrelated hosts.
4. Preserve required request headers on returned streams.
5. Normalize relative HLS URLs against the playlist URL when required.
6. Validate that every returned stream URL uses HTTP(S).

`ExtensionRuntime.resolve_extractor(url)` performs pattern resolution and injects the same `SourceContext` used by the source.

### 6. Preserve API contracts

Do not change public response shapes while repairing a scraper:

- `/api/v1/sources` returns `{"sources": [...], "count": N}`.
- Search, popular, and latest return `{"items": [...], "page": N, "has_next": bool, "total_returned": N}`.
- Episodes, servers, and streams return plain JSON arrays.

SDK exceptions are mapped centrally by the API application. Add or adjust mappings in `anime_extensions_api/app.py` only when introducing a genuinely new failure category.

## Registering Built-ins

Decorate a source with `@register_source` and an extractor with `@register_extractor(pattern)`. Then export its module from the corresponding package `__init__.py`.

`ExtensionRuntime` imports `anime_extensions.sources` and `anime_extensions.extractors` during built-in discovery, which triggers decorator registration. Do not add concrete source imports to `SourceManager`.

For isolated registry tests, construct `ExtensionRuntime` with custom registries and `load_builtins=False`.

## Testing Strategy

### Deterministic tests

Add or update unit tests for:

- selector parsing using fixed HTML fixtures;
- request URL, payload, and header construction;
- crypto and VRF transformations with fixed inputs;
- extractor parsing and URL normalization;
- registry resolution;
- error translation;
- response schema and route contract behavior.

Unit tests must not depend on live upstream services.

### Live tests

Live tests validate that the current upstream still supports the complete source pipeline. They require `--run-live`:

```bash
uv run pytest tests/live/test_live_<source>.py --run-live -v
```

When a source or extractor affects multiple integrations, run the full live suite:

```bash
uv run pytest tests/live/ --run-live
```

A live failure can be transient. Record the failing stage and response behavior before deciding that a code change is necessary; do not weaken assertions merely to accommodate an upstream outage.

## Required Pre-Commit Checks

Run all four commands and fix failures before committing:

```bash
uv run ruff check anime_extensions anime_extensions_api tests
uv run ruff format --check anime_extensions anime_extensions_api tests
uv run pytest
uv run pytest tests/live/ --run-live
```

The GitHub Actions workflow should remain aligned with these checks.

## Common Failure Signals

| Symptom | First place to inspect |
|---|---|
| All requests time out | `core/http.py`, upstream availability, proxy configuration |
| One source returns no catalog entries | Source selectors and endpoint parameters |
| Details work but episodes are empty | Episode endpoint, AJAX headers, or episode selectors |
| Servers are present but no extractor resolves | Extractor registration pattern and normalized embed URL |
| Extractor resolves but streams are empty | Hoster token/key logic and playlist parsing |
| API returns an unexpected status | Exception type raised by SDK and handlers in `api/app.py` |
| Repeated concurrent upstream calls | Cache key construction and `AsyncTTLCache.get_or_set` usage |

Keep repairs small, source-specific, and covered by deterministic tests wherever possible.
