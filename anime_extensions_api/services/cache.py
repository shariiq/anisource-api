"""High-performance asynchronous TTL cache for API endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

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
    """In-memory cache with Time-To-Live (TTL) and FIFO capacity bounding.

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

        # Wait outside the lock so we don't block other keys.
        # Shield against caller cancellation so disconnected clients do not
        # abort the shared background fetch for other or subsequent callers.
        try:
            return await asyncio.shield(task)
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
        """Store a value with a given TTL in seconds.

        When capacity is exceeded, expired items are evicted first. If capacity
        remains exceeded, items are evicted in FIFO order based on insertion order.
        """
        if len(self._cache) >= self.max_items:
            await self._evict_expired()
            # If still full, drop oldest inserted item (FIFO eviction via dict insertion order)
            if len(self._cache) >= self.max_items:
                try:
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
