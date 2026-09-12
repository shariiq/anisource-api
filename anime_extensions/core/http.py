"""Centralized async HTTP client wrapping ``aiohttp``.

Design goals:

* **Secure by default** — TLS verification is on unless the caller explicitly
  opts out per-request.  The old global ``ssl=False`` is gone.
* **Single lifecycle** — one ``HttpClient`` per runtime; sources and
  extractors receive it through ``SourceContext``, never build their own.
* **Error translation** — networking / HTTP failures are mapped to the
  core error taxonomy so callers never import ``aiohttp`` for control flow.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp

from .errors import HttpError, ParsingError, TimeoutError, UpstreamNotFound, UpstreamRateLimited

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _translate_status(status: int, url: str, method: str) -> HttpError:
    """Map an HTTP status code to the appropriate error subclass."""
    base = f"{method} {url} returned {status}"
    if status == 404:
        return UpstreamNotFound(base)
    if status == 429:
        return UpstreamRateLimited(base)
    return HttpError(base, status_code=status)


class HttpClient:
    """Thin ``aiohttp`` wrapper with secure defaults and error translation.

    Parameters
    ----------
    timeout:
        Request timeout configuration.  Falls back to 30 s total.
    ssl:
        TLS context or ``True`` (system default) / ``False`` (disable
        verification).  The default — ``True`` — enforces certificate
        validation.  Per-request ``ssl`` kwargs in individual calls can
        still override for hosts that genuinely need it.
    """

    def __init__(
        self,
        *,
        timeout: aiohttp.ClientTimeout | None = None,
        ssl: bool | Any = True,
    ) -> None:
        self._timeout = timeout or _DEFAULT_TIMEOUT
        self._ssl = ssl
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Create the underlying ``aiohttp.ClientSession``."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=self._ssl)
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
                headers=_DEFAULT_HEADERS,
            )

    async def close(self) -> None:
        """Shut down the underlying session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession | None:
        """Raw session for extractors that need direct access.

        Returns ``None`` if the client has not been started or has been closed.
        """
        if self._session is None or self._session.closed:
            return None
        return self._session

    def _require_session(self) -> aiohttp.ClientSession:
        """Return the live session or fail with a lifecycle error."""
        session = self.session
        if session is None:
            raise RuntimeError("HttpClient has not been started — call start() first")
        return session

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        ssl: bool | Any = None,
    ) -> str:
        """GET *url* and return the body text.  Raises ``HttpError`` on failure."""
        session = self._require_session()
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)

        try:
            async with session.get(url, headers=merged, params=params, ssl=ssl) as resp:
                if resp.status < 200 or resp.status >= 300:
                    raise _translate_status(resp.status, url, "GET")
                return await resp.text(errors="replace")
        except aiohttp.ServerTimeoutError as exc:
            raise TimeoutError(f"GET {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpError(f"GET {url} failed: {exc}") from exc

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        ssl: bool | Any = None,
    ) -> Any:
        """GET *url* and decode the JSON body."""
        session = self._require_session()
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)

        try:
            async with session.get(url, headers=merged, params=params, ssl=ssl) as resp:
                if resp.status < 200 or resp.status >= 300:
                    raise _translate_status(resp.status, url, "GET")
                try:
                    return await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise ParsingError(f"Failed to decode JSON from {url}") from exc
        except aiohttp.ServerTimeoutError as exc:
            raise TimeoutError(f"GET {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpError(f"GET {url} failed: {exc}") from exc

    async def post_json(
        self,
        url: str,
        *,
        json_data: Any = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        ssl: bool | Any = None,
    ) -> Any:
        """POST JSON to *url* and decode the JSON response."""
        session = self._require_session()
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)

        try:
            async with session.post(
                url, json=json_data, headers=merged, params=params, ssl=ssl
            ) as resp:
                if resp.status < 200 or resp.status >= 300:
                    raise _translate_status(resp.status, url, "POST")
                try:
                    return await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise ParsingError(f"Failed to decode JSON from {url}") from exc
        except aiohttp.ServerTimeoutError as exc:
            raise TimeoutError(f"POST {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpError(f"POST {url} failed: {exc}") from exc

    async def get_bytes(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        ssl: bool | Any = None,
    ) -> bytes:
        """GET *url* and return the raw bytes."""
        session = self._require_session()
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)

        try:
            async with session.get(url, headers=merged, params=params, ssl=ssl) as resp:
                if resp.status < 200 or resp.status >= 300:
                    raise _translate_status(resp.status, url, "GET")
                return await resp.read()
        except aiohttp.ServerTimeoutError as exc:
            raise TimeoutError(f"GET {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpError(f"GET {url} failed: {exc}") from exc

    # Context manager support
    async def __aenter__(self) -> HttpClient:
        await self.start()
        return self

    async def __aexit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        await self.close()
