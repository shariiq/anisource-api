"""Application-scoped state for protected HLS proxy resources."""

from __future__ import annotations

import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HlsProxyTarget:
    """A server-issued upstream request target for one protected HLS resource."""

    url: str
    headers: dict[str, str]
    expires_at: float


class HlsProxyRegistry:
    """Store short-lived, unguessable proxy targets in application state."""

    def __init__(self, *, ttl_seconds: int = 300) -> None:
        self._ttl_seconds = ttl_seconds
        self._targets: dict[str, HlsProxyTarget] = {}

    def register(self, url: str, headers: Mapping[str, str]) -> str:
        """Register an upstream resource and return its opaque public token."""
        self._purge_expired()
        token = secrets.token_urlsafe(32)
        self._targets[token] = HlsProxyTarget(
            url=url,
            headers=dict(headers),
            expires_at=time.monotonic() + self._ttl_seconds,
        )
        return token

    def resolve(self, token: str) -> HlsProxyTarget | None:
        """Return a valid target, removing it once its TTL has elapsed."""
        target = self._targets.get(token)
        if target is None:
            return None
        if target.expires_at <= time.monotonic():
            del self._targets[token]
            return None
        return target

    def clear(self) -> None:
        """Discard all proxy targets during application shutdown."""
        self._targets.clear()

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [token for token, target in self._targets.items() if target.expires_at <= now]
        for token in expired:
            del self._targets[token]
