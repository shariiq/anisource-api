"""Shared router helpers for cached source operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..services.cache import AsyncTTLCache


async def fetch_cached[T](
    cache: AsyncTTLCache,
    key: str,
    factory: Callable[[], Awaitable[T]],
    *,
    enabled: bool,
    ttl_seconds: int,
) -> T:
    """Fetch a source result, using the cache when it is enabled."""
    if not enabled:
        return await factory()
    return await cache.get_or_set(key, factory, ttl_seconds=ttl_seconds)
