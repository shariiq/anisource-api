"""High-performance asynchronous TTL cache for API endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

# Type variables for decorating functions
F = TypeVar("F", bound=Callable[..., Any])

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

    Operations on the underlying dict are thread-safe in CPython due to the GIL,
    meaning we don't strictly need locks for get/set, but we'll use an asyncio lock
    when performing bulk evictions.
    """

    def __init__(self, max_items: int = 5000) -> None:
        self._cache: dict[str, CacheEntry] = {}
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
        }


# Global cache instance for the API
api_cache = AsyncTTLCache(max_items=5000)
