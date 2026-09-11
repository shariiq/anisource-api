# Architecture Improvements Roadmap

This document tracks the surgical architectural enhancements for the `anime-extensions-py` SDK, progressing the codebase towards library-grade design (~9.5+/10).

## Implementation Status

- **Status**: In Progress
- **Last Updated**: 2026-09-12

---

## Roadmap Checklist

- [x] **Documentation**: Extractor Contributor Guide (`docs/WRITING_EXTRACTORS.md`)
- [x] **Config System Foundation**: Typed configuration dataclasses (`anime_extensions/core/config.py`)
- [ ] **1. Explicit Plugin Catalogue & Runtime-Owned Registries**: Remove global decorator mutation side-effects on module import; runtime directly registers explicit `BUILTIN_SOURCES` and `BUILTIN_EXTRACTORS`.
- [ ] **2. Capability & Source Contract Reconciliation**: Add `supports(capability)` on `Source`; raise typed `UnsupportedCapabilityError` and enforce in FastAPI handlers (HTTP 501/400).
- [ ] **3. Decouple Context from Runtime**: Remove `SourceContext.runtime` to prevent composition-root leakage and service locator anti-patterns; restrict context strictly to `http` and `extractors`.
- [ ] **4. Single Composition Root (Remove Redundant `SourceManager`)**: Bind `ExtensionRuntime` directly into `app.state` and provide clean FastAPI dependencies (`RuntimeDep`, `SourceDep`).
- [ ] **5. Cache Hardening (Cancellation Shielding & FIFO Eviction)**: Wrap shared single-flight task awaiters in `asyncio.shield()`, formally document FIFO bounded eviction, and delete unused `@cached` decorator.
- [ ] **6. Router Boilerplate Consolidation**: Extract recurring fetch/cache flow into a clean `cached_call(cache, key, ttl, factory)` helper across anime endpoints.
- [ ] **7. `Page[T]` Domain Model & Direct Cache Serialization**: Replace raw `tuple[list[Anime], bool]` return types with a typed `Page[T]` dataclass; cache domain instances directly.
- [ ] **8. Complete HTTP Transport Error Mapping**: Map all `aiohttp` transport exceptions (`ClientConnectorError`, `ClientSSLError`, DNS resolution failures) to typed SDK exceptions.
- [ ] **9. Deterministic Extractor Resolution & Conflict Semantics**: Introduce explicit registration priority on extractors and raise `DuplicateSourceError` on collisions.
- [ ] **10. Clean Public Root Package Namespace**: Export only SDK framework abstractions and contracts from `anime_extensions/__init__.py`, removing concrete plugin imports.
- [ ] **11. Python Compatibility Target**: Reconcile `requires-python = ">=3.12"` in `pyproject.toml` with PyPI classifiers.

---

## Architectural Improvement Cards

### 1. Explicit Plugin Catalogue (High Priority)
Replace global module-import side-effects with explicit `BUILTIN_SOURCES` / `BUILTIN_EXTRACTORS` tuples. Runtime owns its own registries without mutating globals.
- **Target Files**: `anime_extensions/core/registry.py`, `anime_extensions/core/runtime.py`

### 2. Capability Enforcement (High Priority)
Reconcile abstract methods vs capability flags. Add `supports(capability)` on `Source`, raise typed `UnsupportedCapabilityError`, and return 501/400 at HTTP boundary.
- **Target Files**: `anime_extensions/core/models.py`, `anime_extensions/core/source.py`, `anime_extensions_api/routers/`

### 3. Decouple Context from Runtime (High Priority)
Remove `SourceContext.runtime` to prevent composition root leaks and service-locator anti-patterns. Narrow context strictly to `http` and `extractors`.
- **Target Files**: `anime_extensions/core/runtime.py`, `anime_extensions/core/source.py`

### 4. Single Composition Root (High Priority)
Eliminate redundant `SourceManager` wrapper. Bind `ExtensionRuntime` directly to `app.state` and provide clean FastAPI dependency injection (`SourceDep`, `RuntimeDep`).
- **Target Files**: `anime_extensions_api/services/`, `anime_extensions_api/app.py`, `anime_extensions_api/routers/`

### 5. Single-Flight Shielding & FIFO Eviction (Medium Priority)
Wrap shared single-flight task awaiters in `asyncio.shield()` so client disconnects do not cancel background fetches. Formally label FIFO eviction and delete unused `@cached` magic.
- **Target Files**: `anime_extensions_api/services/cache.py`, `tests/`

### 6. Router Boilerplate Consolidation (Medium Priority)
Extract recurring fetch/cache flow into a clean `cached_call(cache, key, ttl, factory)` helper, cutting repeated conditional boilerplate across endpoints.
- **Target Files**: `anime_extensions_api/routers/anime.py`

### 7. `Page[T]` Domain Model (Medium Priority)
Replace raw `tuple[list[Anime], bool]` return signatures with a typed `Page[T]` dataclass. Cache domain instances directly instead of premature dict conversions.
- **Target Files**: `anime_extensions/core/models.py`, `anime_extensions/sources/`, `anime_extensions_api/`

### 8. Complete HTTP Error Translation (Medium Priority)
Map all aiohttp transport exceptions (`ClientConnectorError`, `ClientSSLError`, DNS failures) to typed SDK exceptions so `aiohttp` never leaks to callers.
- **Target Files**: `anime_extensions/core/http.py`, `anime_extensions/core/exceptions.py`

### 9. Deterministic Extractor Resolution (Low Priority)
Introduce explicit priorities on extractor registrations to resolve overlapping patterns deterministically. Raise `DuplicateSourceError` on conflicting registrations.
- **Target Files**: `anime_extensions/core/registry.py`

### 10. Clean Root Namespace Export (Low Priority)
Remove concrete plugin imports (e.g. `AniWaves`, `ByseExtractor`) from `anime_extensions/__init__.py` to keep the root framework namespace clean and decoupled.
- **Target Files**: `anime_extensions/__init__.py`

### 11. Python Compatibility Target (Low Priority)
Lower `requires-python = ">=3.12"` in `pyproject.toml` to match declared PyPI classifiers and widen library adoption while preserving modern typing.
- **Target Files**: `pyproject.toml`
