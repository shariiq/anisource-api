"""High-performance asynchronous TTL cache for API endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar, cast

# Type variables for decorating functions
F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

log = logging.getLogger(__name__)


class CacheEntry:
    """Wrapper holding a cached value and its expiration time."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at

    def is_expired(self, now: float) -> bool:
        return now > self.expires_at


class AsyncTTLCache:
    """In-memory cache with Time-To-Live (TTL) and LRU-like capacity bounding.

    Includes single-flight request coalescing to prevent cache stampedes.
    """

    def __init__(self, max_items: int = 5000) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        self.max_items = max_items
        self._lock = asyncio.Lock()

        # Metrics
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> Any | None:
        """Retrieve a value by key. Returns None if missing or expired."""
        entry = self._cache.get(key)
        if entry is None:
            self.misses += 1
            return None

        if entry.is_expired(time.time()):
            # Expired: lazy removal
            del self._cache[key]
            self.misses += 1
            return None

        self.hits += 1
        return entry.value

    async def get_or_set(self, key: str, coro: Callable[[], Awaitable[T]], ttl_seconds: int) -> T:
        """Get a value or atomically set it via single-flight execution to prevent stampedes."""
        # Fast path check
        val = await self.get(key)
        if val is not None:
            return val

        async with self._lock:
            # Double checked locking
            entry = self._cache.get(key)
            if entry is not None and not entry.is_expired(time.time()):
                self.misses -= 1
                self.hits += 1
                return entry.value

            # If request is already inflight, wait for it
            if key in self._inflight:
                task = self._inflight[key]
            else:
                # Need to fetch it ourselves
                task = asyncio.create_task(self._fetch_and_cache(key, coro, ttl_seconds))
                self._inflight[key] = task

        # Wait outside the lock so we don't block other keys
        try:
            return await task
        except Exception:
            # If the task fails, whoever successfully fetches it later should not hit cache
            if key in self._cache:
                del self._cache[key]
            raise

    async def _fetch_and_cache(
        self, key: str, coro: Callable[[], Awaitable[T]], ttl_seconds: int
    ) -> T:
        """Wrapper to fetch data and write to cache, then cleanup inflight."""
        try:
            val = await coro()
            await self.set(key, val, ttl_seconds)
            return val
        finally:
            async with self._lock:
                self._inflight.pop(key, None)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store a value with a given TTL in seconds."""
        if len(self._cache) >= self.max_items:
            await self._evict_expired()
            # If still full, drop a random item (simplified LRU approach)
            if len(self._cache) >= self.max_items:
                try:
                    # Next iter removes the "oldest" inserted due to dict ordering
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                except StopIteration:
                    pass

        expires_at = time.time() + ttl_seconds
        self._cache[key] = CacheEntry(value, expires_at)

    async def _evict_expired(self) -> None:
        """Scan and remove all expired items. Runs under lock."""
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, v in self._cache.items() if v.is_expired(now)]
            for k in expired_keys:
                del self._cache[k]

    def clear(self) -> None:
        """Clear the entire cache synchronously."""
        self._cache.clear()
        self.hits = 0
        self.misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Return cache health telemetry."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0

        return {
            "item_count": len(self._cache),
            "max_items": self.max_items,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "inflight_requests": len(self._inflight),
        }


def cached(key_builder: Callable[..., str], ttl_seconds: int = 1800) -> Callable[[F], F]:
    """Decorator to cache an endpoint handler."""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # find cache dependency
            cache = None
            if len(args) > 0 and isinstance(args[0], AsyncTTLCache):
                cache = args[0]
            else:
                for arg in args:
                    if isinstance(arg, AsyncTTLCache):
                        cache = arg
                        break
                if not cache:
                    for arg in kwargs.values():
                        if isinstance(arg, AsyncTTLCache):
                            cache = arg
                            break

            key = key_builder(*args, **kwargs)
            if not cache:
                log.warning(
                    f"No AsyncTTLCache found in arguments for {func.__name__} - skipping cache"
                )
                return await func(*args, **kwargs)

            async def coro() -> Any:
                return await func(*args, **kwargs)

            return await cache.get_or_set(key, coro, ttl_seconds)

        return cast(F, wrapper)

    return decorator
