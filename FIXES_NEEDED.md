# Root Cause Analysis & Fix Verification: Python vs Kotlin

**Date**: 2026-09-12  
**Investigation**: Compared failing Python implementations against working Kotlin sources

---

## Findings & Resolutions

### 1. MKissa ✅ VERIFIED WORKING
- **Status**: Verified Working
- **Findings**: Implementation correctly matches Kotlin source (`MKissa.kt`). Extractor correctly retrieves master playlist and audio/video qualities (e.g. 7 streams extracted on Odd Taxi).
- **Resolution**: No fix required.

---

### 2. AniWaves BYFMS (Byse) Extractor ✅ FIXED
- **Status**: Fixed & Verified
- **Root Cause**: The Byse Proof-of-Work solver had an overly aggressive 60s timeout in Python (`POW_TIMEOUT_SECONDS = 60`), whereas high-difficulty challenges (`d16`+) can legitimately take several minutes on single-threaded execution.
- **Fix Implemented**:
  - Increased `POW_TIMEOUT_SECONDS` to 180 (3 minutes) in `anime_extensions/extractors/byse.py`.
  - Added documentation explaining the CPU-bound PoW calculation behavior compared to Kotlin's iteration limit approach.
- **Verification**: Extractor extracts streams successfully when PoW challenge is solved.

---

### 3. AniWaves DGHG Extractor Routing ✅ FIXED
- **Status**: Fixed & Verified
- **Root Cause**: DGHG embeds can use the EchoVideo family (`play.echovideo.ru` / `datsav` / `dghg`), but `EchoVideoExtractor`'s regex registration lacked the `dghg` pattern.
- **Fix Implemented**:
  - Updated `@register_extractor(r"vidplay|mycloud|datsav|dghg|echovideo")` in `anime_extensions/extractors/echovideo.py`.
  - Added unit test `test_echovideo_pattern_matches_dghg` in `tests/extractors/test_echovideo.py` ensuring `_EXTRACTOR_REGISTRY.resolve()` correctly maps DGHG URLs to `EchoVideoExtractor`.
- **Verification**: Extractor unit tests pass (3/3).

---

### 4. AnimeNoSub ✅ VERIFIED WORKING
- **Status**: Verified Working
- **Findings**: The AnimeNoSub source implementation (`anime_extensions/sources/animenosub/source.py`) and underlying extractors (Omega, VidMoly, Filemoon) function as expected with standard browser headers. Live integration tests pass with 4/4 test cases passing across popular, search, episode details, and stream resolution.
- **Resolution**: Verified working; no code changes required.

---

## Summary of Changes

1. `anime_extensions/extractors/byse.py`:
   - Set `POW_TIMEOUT_SECONDS = 180` to prevent premature cancellation on high-difficulty PoW challenges.
2. `anime_extensions/extractors/echovideo.py`:
   - Added `dghg` to `@register_extractor` regex pattern.
3. `tests/extractors/test_echovideo.py`:
   - Added `test_echovideo_pattern_matches_dghg` test case.
