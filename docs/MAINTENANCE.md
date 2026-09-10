# Scraper Maintenance Guide

This guide explains how to update the Python anime scrapers whenever their upstream Kotlin counterparts are modified, ensuring the Python library stays in sync with bug fixes and selector changes.

## Architecture Alignment

The Python REST API heavily mirrors the `Tachiyomi / Aniyomi` extension design pattern. Understanding the 1:1 correspondence will make syncing updates straightforward.

| Kotlin (Tachiyomi/Aniyomi) | Python (Anime Extensions API) | Purpose |
|----------------------------|-------------------------------|---------|
| `popularAnimeParse(response)` | `get_popular(page)` | Parses trending anime listings |
| `latestUpdatesParse(response)`| `get_latest(page)` | Parses recently updated listings |
| `searchAnimeParse(response)` | `search(query, page)` | Parses keyword search results |
| `animeDetailsParse(response)` | `get_details(anime_id)` | Parses exact genres, synopsis, score |
| `episodeListParse(response)` | `get_episodes(anime_id)` | Parses episode URLs and sub/dub flags |
| `videoListParse(response)` | `get_servers(episode_id)` <br>& `get_streams(ep_id, srv_id)` | Fetches hosts and decrypts HLS streams |

### Where to Look for Upstream Changes

The Kotlin extractors for these sources live in:
- `anime-extensions/src/en/aniwaves/src/eu/kanade/tachiyomi/animeextension/en/aniwaves/*.kt`
- `anime-extensions/lib-multisrc/anikototheme/src/eu/kanade/tachiyomi/multisrc/anikototheme/*.kt`

The Python implementations live in:
- `anime-extensions-py/anime_extensions/sources/aniwaves.py`
- `anime-extensions-py/anime_extensions/sources/anikoto.py`
- `anime-extensions-py/anime_extensions/extractors/*.py` 

---

## 🛠 Action Checklist for Updates

When a website updates (e.g. DOM changes, API route changes, crypto obfuscation updates), follow these steps to port the fix:

### 1. Identify CSS Selector Changes
If empty listings or missing metadata occur:
1. Check the Kotlin `popularAnimeSelector()`, `animeDetailsParse()`, and `episodeListParse()` methods.
2. Note any updated `document.select(...)` queries in Kotlin.
3. Apply the exact same `.select(...)` updates to `BeautifulSoup` calls in the Python `get_popular()`, `get_details()`, or `get_episodes()` methods.
    - Example: `document.selectFirst("h1.title")` ➔ `soup.select_one("h1.title")`

### 2. Verify Crypto / VRF Cipher Updates
Sources like Anikoto and AniWaves often change their "VRF" encryption payloads which secure their JSON endpoints:
1. Locate the `vrfEncrypt` or `vrf_encrypt` logic in Kotlin.
2. Inspect if `_EXCHANGE_KEY_1`, `_EXCHANGE_KEY_2`, `_KEY_1`, or `_KEY_2` have changed. 
3. If new keys or passphrases appear in upstream Kotlin, overwrite them identically in the Python source (`anime_extensions/sources/aniwaves.py` and `anikoto.py`).

### 3. Synchronize Video Extractor Logic
If streams are failing to resolve:
1. Upstream extractors are stored in generic libraries. Check:
    - *EchoVideo (Vidplay, MyCloud)*
    - *Byse (Filemoon)*
    - *DoodStream*
2. If keys or decryptor logic changes in Kotlin, update the matching Python extractor inside `anime-extensions-py/anime_extensions/extractors/`.
3. Pay close attention to regex updates in stream JS decryption logic (e.g. finding the hidden ChaCha/AES passphrase).

---

## Example: Porting a Change

**Upstream Kotlin Change (AnikotoTheme.kt)**:
```kotlin
// Before
open fun popularAnimeSelector(): String = "div.ani.items > div.item"
// After (Website changed DOM)
open fun popularAnimeSelector(): String = "div.anime-grid > div.anime-card"
```

**Corresponding Python Update (anikoto.py)**:
```python
# Before
for item in soup.select("div.ani.items > div.item"):
    # ...
    
# After 
for item in soup.select("div.anime-grid > div.anime-card"):
    # ...
```

---

## Testing Verification

After applying updates:

```bash
# 1. Run unit test suite
pytest tests/test_api.py -v

# 2. Run E2E integrations bridging source extractors and extractors
pytest test_e2e.py -v
```

If tests gracefully pass without `SourceNotFoundError` or `AnimeExtensionError`, the Python parser is successfully synced and production-ready.
