# Scraper Maintenance Guide

This guide covers source and extractor repairs in the current `anime-extensions-py` architecture. The parent Kotlin extension repository is read-only reference material; all Python changes, tests, and commits belong in this repository.

## Architecture Map

| Layer | Location | Responsibility |
|---|---|---|
| Core contracts | `anime_extensions/core/source.py`, `extractor.py` | Source and extractor interfaces |
| Domain models | `anime_extensions/core/models.py`, `metadata.py` | Anime, episode, server, stream, subtitle, and source metadata types |
| Networking | `anime_extensions/core/http.py` | Shared session lifecycle, pooling, timeouts, TLS, and HTTP error translation |
| Registration | `anime_extensions/core/registry.py` | Source and URL-pattern extractor registries |
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

---

## Evidence-Driven Repair Protocol

### Principle: Verification Must Prove Production Behavior, Not Test-Environment Success

A source or extractor is "verified working" only when:

1. **End-to-end production evidence**: The deployed API successfully returns streams from real episode/server pairs under representative query loads, observed through the live deployed endpoint or equivalent production request path.
2. **Performance constraints met**: Every cryptographic, CPU-bound, or network operation completes within the deployed API/proxy/client timeout budget (typically 30-45 seconds).
3. **Failure modes are typed and explicit**: Upstream blocks, rate limits, captchas, and malformed responses raise or return typed SDK exceptions rather than being silently absorbed into empty results.
4. **Deterministic test coverage**: Fixed HTML/JSON/playlist fixtures prove selector correctness, request construction, crypto transforms, and error translation without depending on upstream availability.

**A passing local live test, CI green check, or synthetic fixture test alone does not establish production readiness.** Each proves only that the implementation can work under the test environment's network, timeout, and upstream-availability conditions.

---

## Repair and Porting Protocol

### 1. Reproduce the failure in the smallest boundary that isolates the defect

Start with the exact production failure or the narrowest affected test. Identify the first failed pipeline stage:

- catalog discovery (search/popular/latest parsing);
- details metadata;
- episode list parsing;
- server discovery or embed value encoding;
- embed URL normalization and extractor selection;
- hoster token/key derivation, decryption, or playlist resolution; or
- stream URL validation, headers, subtitles, or HLS/DASH parsing.

**Do not change a source to compensate for an extractor defect, or an extractor to compensate for source embed-normalization behavior.**

**Record the complete failure telemetry before changing code:**

- exact request URL (including query parameters as resolved by the HTTP client);
- request method, headers, cookies, referer/origin;
- response HTTP status, content-type, and body shape (HTML structure, JSON keys, encrypted vs. clear, error payload);
- whether the response was valid but empty, malformed, or a typed upstream error (403/429/502/504/captcha/rate-limit);
- SDK exception type raised, if any;
- performance: whether the operation timed out, and the elapsed time before timeout or completion.

An HTTP 403, 5xx, timeout, or empty response is an **observation**, not proof the Python implementation is defective. Possible causes include:

- upstream WAF/CDN blocking datacenter egress IPs (Cloudflare, LiteSpeed, bot detection);
- upstream service degradation, rate limits, or captcha challenges;
- missing or incorrect request headers, cookies, or referer/origin;
- CPU-bound operation (proof-of-work, decryption) exceeding client/gateway timeout;
- malformed or unexpected upstream response shape requiring updated parsing logic.

**Reproduce the boundary narrowly:**

For a search/catalog failure, invoke the source's `search()` method directly with `HttpClient` and `ExtensionRuntime` in a minimal script; compare the request and response against an equivalent direct `httpx` or `curl` call from the same network.

For a stream extraction failure, capture the embed URL, upstream hoster response, and intermediate decryption/token/playlist steps; compare against the Kotlin extractor's request sequence.

**When a narrow live test is necessary**, run only the relevant test and record whether it reproduces the production failure:

```bash
uv run pytest tests/live/test_live_<source>.py::<test_name> --run-live -v
```

### 2. Trace the complete Kotlin implementation graph before writing Python code

Read the corresponding Kotlin source class and every dependency that contributes to the affected behavior:

- source/provider base class, domain, and base URL;
- catalog, details, episodes, servers, and stream method implementations;
- associated hoster extractors, host domain aliases, and embed URL provider variants;
- request utilities and helpers: URL builders, encoding/normalization, request sequencing, AJAX markers, custom headers, cookies, referer/origin policies;
- VRF, crypto, signatures, proof-of-work, token derivation, decryption, and shared cryptographic utilities;
- Kotlin unit tests or fixtures that establish expected behavior, especially for crypto, URL normalization, and response shapes.

**Create a behavior matrix before implementing:**

For each changed or newly ported pipeline boundary, document the evidence comparing Kotlin and Python:

| Concern | Record |
|---|---|
| **Request** | Full URL (path + query params in order), HTTP method, request body encoding (form/JSON/plaintext), and request order when multiple requests are required |
| **Request context** | All headers (User-Agent, Accept, Content-Type, Origin, Referer, custom headers), cookies (name/value/path), AJAX markers (`X-Requested-With`), and whether headers/cookies/referer are required or optional |
| **Response** | HTTP status, Content-Type, HTML structure (parent/child selectors, class/id/attribute patterns), JSON schema (required keys, nested structure, encrypted vs. clear payloads), error response shape (status + body for 403/429/5xx) |
| **Source parsing** | Selectors (exact CSS/XPath expressions), opaque ID extraction (from href, data attributes, JSON fields), pagination detection (selector + logic for `has_next`), model field mappings (title, thumbnail, status, genres, etc.) |
| **Server/embed handoff** | Server label/name, raw embed value (base64, URL, JSON), normalized embed URL (protocol, domain, path, query params), extractor host aliases |
| **Extractor** | Runtime-selected extractor class, token/key derivation sequence, proof-of-work challenge (nonce/difficulty/timeout), decryption algorithm and parameters, playlist URL resolution (m3u8/mpd/direct), required stream headers (Referer/Origin), subtitles (format/language/URL), expected stream URL validation (HTTP(S), relative-to-absolute normalization) |
| **Performance** | Measured elapsed time for CPU-bound operations (crypto, proof-of-work) and network requests; compare against deployed timeout budget (default 30s HTTP, 45s gateway/proxy) |

This matrix is the authoritative definition of "correct behavior." It prevents changes based on:

- source or hoster name/label alone;
- single transient upstream response;
- raw regex pattern inspection without runtime resolution evidence;
- unfounded assumptions about expected request headers, crypto parameters, or response schemas.

### 3. Implement the minimal, evidence-backed change

**For empty listings, missing metadata, or incorrect parsing:**

1. Compare Kotlin selectors, response field extraction, and transformations with the Python source under `anime_extensions/sources/<source>/source.py`.
2. Preserve opaque IDs exactly as returned by upstream; do not rewrite or normalize IDs unless Kotlin does so for a documented reason.
3. Return core domain models (`Anime`, `Episode`, `Server`, `Stream`, `Subtitle`), never API schemas or raw dictionaries.
4. Keep pagination detection explicit: compute `has_next` from a next-page link, a page-count field, or item-count logic matching Kotlin's implementation.
5. When an upstream response is HTTP 200 but contains no usable content (empty search results when you expect listings, missing stream sources when servers exist), determine whether:
   - this is a valid terminal state (no results for this query; no streams available for this server), in which case return an empty list;
   - the response shape has changed or is unrecognized, in which case raise `ParsingError` with a specific message naming the missing field/selector.

**For protected JSON, encrypted endpoints, or crypto operations:**

1. Compare keys, cipher modes, IV/nonce generation, parameter encoding order, transformation sequence, request method, Content-Type, and required request context (headers/cookies/referer) with Kotlin.
2. Route all HTTP requests through `self.context.http`, never construct a direct `aiohttp.ClientSession`.
3. Let core HTTP exceptions (`HttpError`, `UpstreamNotFound`, `UpstreamRateLimited`, `TimeoutError`) propagate unless the source adds meaningful domain-specific context.
4. **Translate malformed successful responses into `ParsingError`**: when upstream returns HTTP 200 with a response that cannot be parsed (missing required JSON key, invalid encrypted payload, HTML when JSON was expected), raise `ParsingError("Source returned invalid <response type>: <specific missing field or shape>")` instead of disguising the failure as a network error or silently returning empty results.
5. **Profile CPU-bound operations** (proof-of-work, complex decryption, large-buffer mixing):
   - measure elapsed time with `time.perf_counter()` for representative production challenge difficulties;
   - establish a hard acceptance criterion: the slowest supported operation must complete comfortably within the deployed timeout budget, ideally **under 2-3 seconds** to leave margin for network latency and API processing;
   - if the measured time exceeds the acceptance criterion, optimize the hot loop (use integer buffers, bitwise operations, precomputed tables) or implement an evidenced alternative approach compatible with the deployment environment;
   - **do not increase internal timeout constants** (`POW_TIMEOUT_SECONDS`, `asyncio.wait_for` deadline) as a substitute for meeting the performance criterion—an internal timeout that exceeds the gateway/client timeout wastes server CPU after the caller has disconnected.

**For extractor registration, routing, and stream extraction:**

1. **Prove extractor selection** through `ExtensionRuntime.resolve_extractor(url)` or direct registry resolution API with a representative normalized embed URL. A server label or raw regex pattern match alone is not sufficient proof—verify that the runtime registry resolves the exact normalized embed URL to the expected extractor class.
2. Inspect the matching Kotlin extractor implementation and relevant host domain aliases before changing `BUILTIN_EXTRACTORS` patterns or hoster extraction logic.
3. Keep registration patterns narrowly evidenced: add a host alias only when Kotlin includes it or live production evidence shows that host serves the same payload format; broad patterns (`.*video.*`, `\w+play`) silently route incompatible hosters to the wrong extractor.
4. Preserve required stream headers (`Referer`, `Origin`, custom auth tokens) exactly as Kotlin specifies.
5. Normalize relative HLS playlist URLs to absolute URLs where required by the player; validate that every returned stream URL begins with `http://` or `https://`.
6. **When an extractor returns empty streams from a successful HTTP response**:
   - capture the full upstream hoster response (request URL + headers, response status/content-type/body);
   - compare the response schema (JSON keys, playlist format, encrypted payload structure) against Kotlin's expected shape;
   - determine whether:
     - the hoster genuinely returned no streams (valid terminal state) → return `[]`;
     - the response has a recognized schema but empty `sources`/`qualityFiles` array (valid terminal state) → return `[]`;
     - the response schema is unrecognized, missing expected keys, or encrypted in an unexpected way → raise `ParsingError("Hoster returned unrecognized response shape: <specific detail>")`;
   - implement only the response variant evidenced by the captured payload comparison, never add speculative fallback parsing for schemas you have not observed.

**Do not:**

- add speculative request headers (User-Agent variants, Accept-Language, custom headers) without Kotlin or comparative upstream-request evidence;
- add retry loops, exponential backoff, or broad exception handling (`except Exception: return []`) to mask transient or undiagnosed failures;
- register extractor patterns based on server label text, visual similarity of embed URLs, or single-attempt resolution without comparing Kotlin hoster aliases;
- introduce catch-all fallbacks that silently return empty results when the actual failure mode is an upstream block, malformed response, or crypto/parsing defect or anything else;
- change timeout constants, add `asyncio.wait_for` extensions, or increase proof-of-work deadlines without profiling actual operation duration against production timeout budgets.

Each behavior change must cite Kotlin implementation evidence, comparative upstream request/response capture, or measured performance data.

### 4. Preserve API contracts

Public API response shapes are deployment contracts. Do not change them while repairing a scraper:

- `GET /api/v1/sources` returns `{"sources": [...], "count": N}`.
- Search, popular, and latest return `{"items": [...], "page": N, "has_next": bool, "total_returned": N}`.
- Episodes, servers, and streams return plain JSON arrays `[...]`.

SDK exceptions are mapped centrally in `anime_extensions_api/app.py` exception handlers. Add or adjust exception-to-HTTP-status mappings only when introducing a genuinely new SDK exception type with a distinct operational meaning (e.g., a new `UpstreamCaptchaRequired` exception distinct from `UpstreamRateLimited`).

### 5. Add deterministic tests that prove the implementation without depending on upstream availability

**Required test coverage for every source/extractor change:**

1. **Selector parsing tests** with fixed HTML fixtures:
   - save a representative upstream HTML response (search results, anime details page, episode list) as a fixture file under `tests/fixtures/<source>/`;
   - write a unit test that parses the fixture and asserts extracted titles, IDs, thumbnail URLs, pagination state;
   - use `unittest.mock.AsyncMock` or `pytest-mock` to mock `self.context.http.get` returning the fixture HTML string.

2. **Request construction tests**:
   - mock `self.context.http.get` and `self.context.http.post_json`;
   - invoke the source method (e.g., `source.search("query", page=2)`);
   - assert the mock was called with the expected URL, params/JSON body, and headers (when headers are non-default).

3. **Crypto and transformation tests** with known test vectors:
   - for proof-of-work, VRF, decryption, token derivation: define fixed input (key/nonce/challenge) and expected output pairs;
   - assert the utility function produces the expected output;
   - add a performance assertion: `assert elapsed < 3.0` (or appropriate threshold) after measuring `time.perf_counter()` delta.

4. **Extractor registry resolution tests**:
   - construct `ExtensionRuntime` with `load_builtins=True` (or manually register extractors for isolated tests);
   - assert `runtime.resolve_extractor("https://normalized.embed.url/path")` returns the expected extractor class;
   - do **not** test only the raw regex pattern or catalogue entry—runtime resolution is the contract.

5. **Extractor parsing tests** with fixed playlist/JSON fixtures:
   - save a representative hoster response (m3u8 playlist, JSON sources payload, encrypted blob) as a fixture;
   - mock HTTP responses and assert the extractor's `extract()` method returns typed `Stream` domain models with valid URLs, headers, subtitles, and `is_hls` flags.

6. **Error translation tests**:
   - mock `self.context.http` raising `HttpError("...", status_code=403)`;
   - assert the source method propagates the exception or wraps it with added domain context;
   - ensure `ParsingError` is raised for malformed successful responses, not for network errors.

**Add or update narrow live tests only when they provide integration coverage beyond deterministic tests:**

Live tests validate that:

- the current upstream HTML/JSON structure still matches the selectors and schemas in fixtures;
- upstream crypto keys, build IDs, or challenge parameters have not rotated;
- the deployed API can reach the upstream without being blocked.

**Live test design principles:**

- run only one targeted test at a time: `uv run pytest tests/live/test_live_<source>.py::<test_name> --run-live -v`;
- do **not** run the full local live suite before committing;
- when a live test fails, record the failing boundary, request, response status/body, and compare against Kotlin before deciding whether code is needed;
- **never weaken assertions or add broad exception handling merely to make a transient upstream failure pass**—record the terminal state as an expected transient condition if that is the evidenced diagnosis, or fix the implementation defect if request/response comparison reveals one.

### 6. Attribute upstream blocks and transient failures correctly

**When an upstream request returns HTTP 403, 429, 502, 503, 504, timeout, or a captcha/rate-limit error:**

1. **Reproduce the failure from multiple networks**: test from the local development environment, GitHub Actions CI runner, and the deployed API environment (Render, or equivalent).
2. **Compare request construction against Kotlin**: ensure all required headers, cookies, referer/origin, and request sequencing match.
3. **Capture response details**: HTTP status, response body, `X-` headers indicating WAF/CDN behavior (e.g., `cf-ray`, `x-cache`).
4. **Diagnose the cause**:
   - **Upstream WAF/CDN blocking datacenter IPs**: if the local environment succeeds but deployed API fails with 403, and direct browser access works, the upstream is likely blocking datacenter egress IPs (Cloudflare WAF, LiteSpeed bot detection). This is an **operational deployment constraint**, not a code defect. Document it as such; do not add retries, header spoofing, or proxy rotation to the source implementation without explicit deployment infrastructure to support it.
   - **Rate limiting**: HTTP 429 or captcha challenges after repeated requests indicate upstream rate limits. Document the limit; implement respectful backoff if the source's contract permits retries; otherwise, propagate `UpstreamRateLimited` or a typed rate-limit error.
   - **Malformed request**: if request construction differs from Kotlin (missing header, incorrect parameter encoding, wrong request order), fix the source implementation.
   - **Transient upstream degradation**: if both local and deployed environments fail with 5xx or timeout, and the upstream is a third-party service, this may be transient. Record the observation, allow the live test to reflect the transient state, and re-test after upstream recovery.

**Do not:**

- change source selectors, add headers, or alter request construction based solely on a single transient 403/5xx response;
- disable SSL verification, add proxy rotation, or implement request spoofing to bypass upstream blocks without deployment infrastructure approval;
- attribute every 403 to "upstream blocking the source"—compare Kotlin's request construction first.

---

## Registering Built-ins

Add a source class to `BUILTIN_SOURCES` in `anime_extensions/sources/__init__.py`. Add an extractor entry `(ExtractorClass, pattern, priority)` to `BUILTIN_EXTRACTORS` in `anime_extensions/extractors/__init__.py`, using a narrowly scoped URL pattern and an explicit priority.

`ExtensionRuntime._register_builtins()` imports these catalogues and registers their entries into its runtime-scoped registries. Do not manually register sources in `SourceManager` or add concrete imports outside the corresponding catalogue module.

For isolated registry tests, construct `ExtensionRuntime` with custom registries and `load_builtins=False`.

---

## Local Checks and PR Validation

Before committing, run the repository-wide lint and formatting checks and any changed deterministic test cases:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/<area>/test_<module>.py::<test_name> -v
```

The third command is an example of a narrow local test, not a requirement to run the entire test suite. **Do not run the full local pytest suite or the full live-test suite locally.** Do not alter pre-commit or pre-push hooks to add or remove pytest execution.

Open a pull request after targeted local verification. **GitHub Actions is authoritative** for the complete lint, format, unit-test, live-test, build, and quality matrix.

**When CI fails:**

1. Read the failure log and identify the exact failing test, lint error, or build step.
2. Reproduce the failure locally if possible (for unit tests and lint); for live-test failures, compare the CI response telemetry against the behavior matrix.
3. Investigate the root cause: is this a code defect, a transient upstream condition, an incorrect test assertion, or a genuine regression?
4. Push an evidence-backed correction: fix the defect, update the test to reflect corrected expected behavior, or document the transient condition.
5. **Do not:**
   - change code or tests merely to make a transient failure disappear without diagnosing the root cause;
   - merge a PR with failing tests unless the failure is a known transient upstream condition documented in the test or PR description;
   - weaken test assertions to accommodate incomplete implementations.

---

## Common Failure Signals and Diagnostic Starting Points

| Symptom | First place to inspect | Diagnostic approach |
|---|---|---|
| All requests to one source time out | `anime_extensions/core/http.py` default timeout, upstream service availability, network egress path | Reproduce with `curl`/`httpx` from same network; compare deployed vs. local environment; check upstream status page |
| Source returns no catalog entries | Source selectors, endpoint URL construction, request parameters | Compare Kotlin selectors and request shape; capture upstream HTML/JSON response; verify fixture HTML structure matches live response |
| Details method works but episodes are empty | Episode endpoint, AJAX headers, episode list selectors, pagination | Compare Kotlin episode request (method, headers, cookies, params); capture response and check for auth/session requirements |
| Servers are present but no extractor resolves | Extractor registration pattern, normalized embed URL, runtime registry resolution | Print normalized embed URL; call `runtime.resolve_extractor(url)` and assert it returns expected class; compare Kotlin hoster aliases |
| Extractor resolves but streams are empty | Hoster token/key derivation, playlist parsing, response schema | Capture hoster response (status, content-type, body); compare JSON keys/playlist format against Kotlin extractor; check for encrypted payload or numeric HLS encoding |
| Extractor times out | Proof-of-work or decryption performance, network latency, hoster response time | Profile hot loop with `time.perf_counter()`; compare measured time against 2-3s acceptance criterion; optimize or implement alternative |
| API returns unexpected HTTP status | SDK exception type raised, `anime_extensions_api/app.py` exception handlers | Trace exception from source → SDK exception type → FastAPI exception handler; verify handler maps to correct HTTP status |
| Repeated concurrent upstream calls for same query | Cache key construction, `AsyncTTLCache.get_or_set` usage, single-flight coalescing | Check cache key includes all relevant parameters (source_id, query, page); verify `get_or_set` factory is async and does not bypass cache |

Keep repairs small, source-specific, and covered by deterministic tests wherever possible. Attribute failures to their actual boundary—source parsing, extractor resolution, hoster extraction, crypto performance, or upstream service behavior—and document the evidence that led to the diagnosis.

---

## Definition: "Verified Working" Status

A source or extractor may be marked "verified working" in documentation or commit messages only when all of the following criteria are met:

1. **Deterministic unit tests pass** for selector parsing, request construction, crypto operations, and extractor resolution.
2. **Narrow live tests pass** for at least one representative query, anime, episode, and server/stream combination.
3. **Deployed API successfully returns streams** from the source under normal query load, verified through manual smoke test or deployed endpoint request logs showing successful stream extraction.
4. **Performance constraints are met**: every CPU-bound operation (crypto, proof-of-work) completes within the deployed timeout budget (typically < 3s per operation).
5. **Failure modes are explicitly typed**: upstream blocks, rate limits, malformed responses, and empty valid states are distinguishable in logs and error responses.

**A passing local live test alone is not sufficient for "verified working" status.** Local test success proves only that the source can work from the test runner's network and under its timeout/upstream-availability conditions.

**When claiming a repair is verified:**

- cite the test that proves selector correctness;
- cite the performance measurement that proves timeout compliance;
- cite the deployed endpoint request or smoke-test result that proves production stream availability;
- record any known constraints (e.g., "works from non-datacenter IPs; deployed API blocked by upstream WAF").
