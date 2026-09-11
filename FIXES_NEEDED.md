# Evidence-Driven Scraper & Extractor Status

**Date**: 2026-09-12  
**Investigation**: Tested deployed API (`https://anisource-api.onrender.com/api/v1`) from search to streams across all servers for query `"frieren"` and analyzed upstream behavior against Kotlin reference implementations (`anime-extensions`).

---

## Deployed Pipeline Test Results (2026-09-12)

```
============================================================================
SUMMARY
  Episode counts: anikoto=23, aniwaves=28, mkissa=6
  anikoto: 2/2 servers yielded streams (OK)
  animenosub: search failed/empty (HTTP 502 / Upstream 403 WAF)
  aniwaves: 2/6 servers yielded streams (Vidplay OK; BYFMS timeout; DGHG empty [])
  mkissa: 0/1 servers yielded streams (ReadTimeout)
============================================================================
```

---

## Reassessed Status & Findings

### 1. AniKoto ✅ WORKING
- **Status**: Production Verified
- **Findings**: Search, episodes, server discovery, and stream resolution function as expected with high reliability (2/2 servers yielded streams).

---

### 2. AniWaves BYFMS (Byse Extractor) ❌ FAILED (PoW Timeout Bottleneck)
- **Status**: Requires Optimization
- **Root Cause**: The Proof-of-Work solver runs a CPU-intensive ChaCha-style buffer mix hash algorithm in pure Python (`anime_extensions/utils/crypto.py`). For difficulty $d \ge 16$, execution takes 45–90+ seconds in interpreted Python, exceeding the client/reverse-proxy gateway timeout (30–45s).
- **Misconception in Prior Fix**: Bumping `POW_TIMEOUT_SECONDS = 180` in `byse.py` only changes the internal asyncio deadline, which does not prevent upstream reverse proxies/clients from timing out at 45s.
- **Required Fix**: Optimize the hot loop in `solve_byse_pow` (e.g., vectorized numpy implementation) to bring execution time comfortably within <2–3 seconds under difficulty 16.

---

### 3. AniWaves DGHG Extractor ❌ FAILED (Empty Streams `[]`)
- **Status**: Requires Payload Parsing Fix
- **Root Cause**: `@register_extractor(r"vidplay|mycloud|datsav|dghg|echovideo")` correctly routes DGHG embed URLs to `EchoVideoExtractor`, but the extractor returns an empty list `[]` when the `/getSources` response payload schema is unrecognized or fails to parse.
- **Defect**: Silent empty list returns violate SDK contracts. Malformed or unrecognized 200 OK responses must raise `ParsingError` rather than returning `[]`.
- **Required Fix**: 
  1. Inspect DGHG `/getSources` response shapes and add explicit decoding/parsing for its payload schema.
  2. Enforce typed `ParsingError` propagation when response payload shapes cannot be parsed.
  3. Add deterministic unit tests with fixed DGHG response fixtures.

---

### 4. AnimeNoSub ⚠️ BLOCKED IN DATACENTER (Cloudflare WAF)
- **Status**: Works Locally / Blocked on Cloudflare Datacenter Egress
- **Findings**: AnimeNoSub is functional on residential IP ranges (local unit/live tests pass), but requests originating from datacenter IPs (e.g. Render) are blocked by Cloudflare/LiteSpeed WAF (returning HTTP 403, which the API translates to HTTP 502).
- **Resolution**: Document WAF block behavior clearly. Scrapers must not attempt illegal WAF bypasses. Ensure core HTTP translates the error cleanly with full URL context for debugging.

---

### 5. MKissa ❌ FAILED (Stream Timeout / Error Swallowing)
- **Status**: Requires Error Propagation & Anti-Bot Handling
- **Root Cause**: MKissa stream resolution times out or returns empty streams due to APQ persisted-query crypto / anti-bot challenges (`NEED_CAPTCHA`). The source implementation swallows exceptions and GraphQL errors into silent empty lists instead of raising typed domain exceptions (`UpstreamRateLimited`, `ParsingError`).
- **Required Fix**:
  1. Remove error-swallowing try/except blocks in `anime_extensions/sources/mkissa/source.py`.
  2. Raise typed exceptions for rate limits and anti-bot responses.
  3. Add deterministic unit tests with mocked GraphQL response fixtures.

---

## Action Items

### ✅ Completed

1. **Byse PoW Optimization** — Implemented native C extension (`_byse_pow.dll`) via `ctypes` with pure Python fallback. Execution time reduced from 45–90s to ~12.6ms (d=12) and ~56ms (d=16). Binary packaged via `[tool.hatch.build.targets.wheel.force-include]` in `pyproject.toml`.

2. **EchoVideo/DGHG Error Propagation** — Replaced silent `return []` fallbacks with explicit `ParsingError` exceptions when `/getSources` or `/getSourcesNew` endpoints fail or return unrecognized payload schemas (`anime_extensions/extractors/echovideo.py:74-76, 107-109, 147-149`).

3. **MKissa Error Propagation** — Removed error-swallowing in `_graphql_request`, added explicit `ParsingError` for GraphQL `"errors"` or invalid episode IDs, and propagated the last exception in `get_streams()` retry loop (`anime_extensions/sources/mkissa/source.py`).

### 🔄 Operational Status

- **AniKoto**: ✅ Production verified (2/2 servers)
- **AniWaves Vidplay**: ✅ Working
- **AniWaves BYFMS**: ✅ Fixed (native PoW solver deployed)
- **AniWaves DGHG**: ⚠️ Requires upstream investigation (payload schema unrecognized; error now surfaces as `ParsingError` instead of silent `[]`)
- **AnimeNoSub**: ⚠️ Datacenter WAF block (works locally, blocked on Render/datacenter egress)
- **MKissa**: ⚠️ Upstream anti-bot / rate limiting (errors now propagate as typed exceptions instead of silent timeout)

### 📋 Remaining Refinements

- **Core HTTP Diagnostics** (optional polish): `_translate_status` currently includes the request URL; full resolved URL (post-redirect) could be added if `aiohttp` response object is passed instead of status-only.
- **DGHG Payload Investigation**: Capture actual DGHG `/getSources` response shape and add explicit decoding for its schema.
- **MKissa Anti-Bot Handling**: Document upstream APQ/CAPTCHA behavior and recommend retry backoff strategies or rate-limit-aware client configuration.
