# Architecture Improvements Roadmap

This document tracks the surgical architectural enhancements for the `anime-extensions-py` SDK, progressing the codebase towards library-grade design (~9.5+/10).

## Implementation Status

- **Status**: Phase 1 & 2 Complete — Phase 3 Next
- **Last Updated**: 2026-09-12

---

## Roadmap Checklist

- [x] **Config System Foundation**: Typed configuration dataclasses (`anime_extensions/core/config.py`)
- [x] **Documentation**: Extractor Contributor Guide (`docs/WRITING_EXTRACTORS.md`)
- [x] **1. Explicit Plugin Catalogue & Runtime-Owned Registries**: Remove global decorator mutation side-effects on module import; runtime directly registers explicit `BUILTIN_SOURCES` and `BUILTIN_EXTRACTORS`.
- [x] **2. Deterministic Extractor Resolution & Conflict Semantics**: Introduce explicit registration priority on extractors and raise `DuplicateSourceError` on collisions. In a plugin architecture, implicit resolution order is a correctness issue.
- [x] **3. Capability & Source Contract Reconciliation**: Add `supports(capability)` on `Source`; raise typed `UnsupportedCapabilityError` and enforce in FastAPI handlers (HTTP 501/400).
- [x] **4. Decouple Context from Runtime**: Remove `SourceContext.runtime` to prevent composition-root leakage and service locator anti-patterns; restrict context strictly to `http` and `extractors`.
- [x] **5. Single Composition Root (Remove Redundant `SourceManager`)**: Bind `ExtensionRuntime` directly into `app.state` and provide clean FastAPI dependencies (`RuntimeDep`, `SourceDep`).
- [ ] **6. Complete HTTP Transport Error Mapping**: Map all `aiohttp` transport exceptions (`ClientConnectorError`, `ClientSSLError`, DNS resolution failures) to typed SDK exceptions in `anime_extensions/core/errors.py`.
- [ ] **7. Cache Hardening (Cancellation Shielding & FIFO Eviction)**: Wrap shared single-flight task awaiters in `asyncio.shield()`, formally document FIFO bounded eviction, and delete unused `@cached` decorator.
- [x] **8. `Page[T]` Domain Model & Direct Cache Serialization**: Replace raw `tuple[list[Anime], bool]` return types with a typed `Page[T]` dataclass; cache domain instances directly.
- [x] **9. Router Boilerplate Consolidation**: Consolidated cache/fetch orchestration via explicit `fetch_cached` helper; handlers remain traceable.
- [ ] **10. Clean Public Root Package Namespace**: Export only SDK framework abstractions and contracts from `anime_extensions/__init__.py`, removing concrete plugin imports.
- [ ] **11. Python Compatibility Target**: Reconcile `requires-python = ">=3.12"` in `pyproject.toml` with PyPI classifiers.

---

## Architectural Improvement Cards

### Config System Foundation

**Why a centralized configuration system is necessary:**

1. **Eliminate magic numbers**: Extractor timeouts, retry policies, user-agent strings, and quality labels are currently scattered across implementation files. When a hoster changes its behavior (e.g., longer PoW solving time), developers must hunt through multiple files to update constants.

2. **Enable runtime tuning**: A typed configuration dataclass allows operators to override settings via environment variables or config files without code changes — critical for production deployments where different hosters require different timeouts.

3. **Type safety**: Using `dataclass(frozen=True)` provides immutable configuration with proper type hints, so linters and IDEs catch misconfiguration at development time rather than runtime.

4. **Consistency**: Configuration for related components (Byse, Dood, EchoVideo) inherits from a common `ExtractorConfig`, ensuring all extractors share the same timeout and user-agent defaults unless explicitly overridden.

---

### 1. Explicit Plugin Catalogue (High Priority)

Replace global module-import side-effects with explicit `BUILTIN_SOURCES` / `BUILTIN_EXTRACTORS` tuples. Runtime owns its own registries without mutating globals.

- **Target Files**: `anime_extensions/core/registry.py`, `anime_extensions/core/runtime.py`

### 2. Deterministic Extractor Resolution (High Priority)

Introduce explicit priorities on extractor registrations to resolve overlapping patterns deterministically. Raise `DuplicateSourceError` on conflicting registrations. In a plugin architecture, resolution order being implicit is a correctness issue, not just polish.

- **Target Files**: `anime_extensions/core/registry.py`

### 3. Capability Enforcement (High Priority)

Reconcile abstract methods vs capability flags. Add `supports(capability)` on `Source`, raise typed `UnsupportedCapabilityError`, and return 501/400 at HTTP boundary.

- **Target Files**: `anime_extensions/core/models.py`, `anime_extensions/core/source.py`, `anime_extensions_api/routers/`

### 4. Decouple Context from Runtime (High Priority)

Remove `SourceContext.runtime` to prevent composition root leaks and service-locator anti-patterns. Narrow context strictly to `http` and `extractors`.

- **Target Files**: `anime_extensions/core/runtime.py`, `anime_extensions/core/source.py`

### 5. Single Composition Root (High Priority)

Eliminate redundant `SourceManager` wrapper. Bind `ExtensionRuntime` directly to `app.state` and provide clean FastAPI dependency injection (`SourceDep`, `RuntimeDep`).

- **Target Files**: `anime_extensions_api/services/`, `anime_extensions_api/app.py`, `anime_extensions_api/routers/`

### 6. Complete HTTP Error Translation (Medium Priority)

Map all aiohttp transport exceptions (`ClientConnectorError`, `ClientSSLError`, DNS failures) to typed SDK exceptions in `anime_extensions/core/errors.py` so `aiohttp` never leaks to callers.

- **Target Files**: `anime_extensions/core/http.py`, `anime_extensions/core/errors.py`

### 7. Single-Flight Shielding & FIFO Eviction (Medium Priority)

Wrap shared single-flight task awaiters in `asyncio.shield()` so client disconnects do not cancel background fetches. Formally label FIFO eviction and delete unused `@cached` magic.

- **Target Files**: `anime_extensions_api/services/cache.py`, `tests/`

### 8. `Page[T]` Domain Model (Medium Priority)

Replace raw `tuple[list[Anime], bool]` return signatures with a typed `Page[T]` dataclass. Cache domain instances directly instead of premature dict conversions.

- **Target Files**: `anime_extensions/core/models.py`, `anime_extensions/sources/`, `anime_extensions_api/`

### 9. Router Boilerplate Consolidation (Medium Priority)

Consolidate repeated cache/fetch orchestration only where the abstraction stays explicit and type-safe. The goal is to remove repeated plumbing, not create an abstraction that makes handlers harder to trace. A generic `cached_call(cache, key, ttl, factory)` is fine, but don't force every endpoint through it if doing so hides endpoint semantics.

- **Target Files**: `anime_extensions_api/routers/anime.py`

### 10. Clean Root Namespace Export (Low Priority)

Remove concrete plugin imports (e.g. `AniWaves`, `ByseExtractor`) from `anime_extensions/__init__.py` to keep the root framework namespace clean and decoupled.

- **Target Files**: `anime_extensions/__init__.py`

### 11. Python Compatibility Target (Low Priority)

Lower `requires-python = ">=3.12"` in `pyproject.toml` to match declared PyPI classifiers and widen library adoption while preserving modern typing.

- **Target Files**: `pyproject.toml`