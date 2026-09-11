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

## Repair and Porting Protocol

### 1. Reproduce and classify the failure narrowly

Start with the smallest affected unit or live test. Identify the first failed boundary: catalog discovery, details, episodes, server discovery, embed normalization, extractor resolution, hoster extraction, or playlist parsing.

Do not change a downstream extractor for an upstream source-parsing failure, or source parsing for a hoster failure. An HTTP 403, 5xx, timeout, empty response, or malformed response is an observation—not evidence that the Python implementation is wrong. Record the stage, request, response status/content shape, and the exact result before changing behavior.

When a narrow live test is necessary, run only the relevant test:

```bash
uv run pytest tests/live/test_live_<source>.py::<test_name> --run-live -v
```

### 2. Trace the complete Kotlin implementation graph

Before coding, read the corresponding Kotlin source and every implementation that contributes to the affected behavior. This includes:

- source/provider classes, domain and base-URL mappings;
- catalog, details, episodes, servers, and stream methods;
- associated hoster extractors, host aliases, and embed provider variants;
- request utilities, request sequence, cookies, headers, AJAX markers, referer/origin behavior, and URL normalization;
- VRF, crypto, signatures, encoding, decryption, and other shared helpers; and
- Kotlin tests or fixtures that establish the expected result.

The Kotlin repository is reference material only. Port observable semantics into the Python architecture; do not copy framework plumbing line-by-line or replace exact behavior with a generic approximation.

### 3. Write a behavior matrix before implementation

For each changed pipeline boundary, document the evidence needed to compare Kotlin and Python:

| Concern | Record |
|---|---|
| Request | Endpoint, method, parameter/body encoding and request order |
| Request context | Headers, cookies, referer/origin, and AJAX markers |
| Response | Status, HTML/JSON/encrypted shape, required fields, and error shape |
| Source parsing | Selectors, opaque IDs, pagination condition, and model fields |
| Server handoff | Server label, raw embed value, normalized embed URL, and host alias |
| Extractor | Runtime-selected extractor, token/key/crypto sequence, playlist/direct-file parsing, headers, subtitles, and expected stream URLs |

This matrix prevents changes based on source names, server labels, raw regex inspection, or a single transient response. It also makes it possible to prove whether a defect belongs to the source, extractor, routing, or upstream service.

### 4. Make a minimal, evidence-backed implementation change

For empty listings or missing metadata:

1. Compare Kotlin selectors and response transformations with the Python source under `anime_extensions/sources/<source>/`.
2. Preserve opaque source IDs exactly; API path routes are designed to carry nested IDs.
3. Return core domain models, not API schemas or dictionaries.
4. Keep pagination detection explicit and return an accurate `has_next` value.

Example selector translation:

```kotlin
document.selectFirst("h1.title")
```

```python
soup.select_one("h1.title")
```

For protected JSON or encrypted endpoints:

1. Compare keys, cipher parameters, URL encoding order, transformation order, method, content type, and required request context with Kotlin.
2. Route requests through `self.context.http`.
3. Let core HTTP exceptions propagate unless the source adds meaningful domain context.
4. Translate malformed successful responses into `ParsingError`; do not disguise them as network errors.

For extractor behavior:

1. Verify the normalized embed URL through `ExtensionRuntime.resolve_extractor(url)` or the registry resolution API. A server label or raw regex match is not sufficient proof of routing.
2. Inspect the matching Kotlin extractor and relevant host aliases before changing registrations or hoster logic.
3. Keep patterns narrowly evidenced, preserve required returned-stream headers, normalize relative HLS URLs where required, and validate that every stream URL is HTTP(S).

Do not add speculative headers, retries, broad matching patterns, catch-all exception handling, or silent fallbacks. Each behavior change must have Kotlin or reproducible upstream evidence. Attribute a failure to a transient upstream condition only when request/response comparison supports that conclusion, and record that evidence rather than weakening tests.

### 5. Preserve API contracts

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

Live tests validate that the current upstream still supports the complete source pipeline. They require `--run-live` and are for narrow, targeted diagnosis only:

```bash
uv run pytest tests/live/test_live_<source>.py::<test_name> --run-live -v
```

Do not run the full local live suite. A live failure can be transient, but must be investigated through the behavior matrix and Kotlin comparison before deciding whether code is needed. Record the failing boundary and response behavior; do not weaken assertions merely to accommodate an upstream outage.

## Local Checks and PR Validation

Before committing, run the repository-wide lint and formatting checks and any changed deterministic test cases:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/<area>/test_<module>.py::<test_name>
```

The third command is an example of a narrow local test, not a requirement to run the entire test suite. Do not run full local pytest or the full live suite, and do not alter pre-commit or pre-push hooks to add or remove pytest behavior.

Open a pull request after targeted local verification. GitHub Actions is authoritative for the complete lint, format, unit-test, live-test, build, and quality matrix. Investigate CI failures at their actual pipeline boundary and push an evidence-backed correction; do not change code or tests merely to make a transient failure disappear.

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
