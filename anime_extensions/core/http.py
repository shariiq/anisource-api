"""Centralized async HTTP client wrapping ``aiohttp``.

Design goals:

* **Secure by default** — TLS verification is on unless the caller explicitly
  opts out per-request.  The old global ``ssl=False`` is gone.
* **Single lifecycle** — one ``HttpClient`` per runtime; sources and
  extractors receive it through ``ExtensionContext``, never build their own.
* **Error translation** — networking / HTTP failures are mapped to the
  core error taxonomy so callers never import ``aiohttp`` for control flow.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import aiohttp

from .errors import (
    HttpError,
    ParsingError,
    TimeoutError,
    UpstreamNotFound,
    UpstreamRateLimited,
    UpstreamUnavailable,
)

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
    if status in {502, 503, 504}:
        return UpstreamUnavailable(base, status_code=status)
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

    @asynccontextmanager
    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        """Issue a request with shared headers and SDK error translation."""
        session = self._require_session()
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)

        request = session.get if method == "GET" else session.post
        try:
            async with request(url, headers=merged, **kwargs) as response:
                if response.status < 200 or response.status >= 300:
                    raise _translate_status(response.status, url, method)
                yield response
        except aiohttp.ServerTimeoutError as exc:
            raise TimeoutError(f"{method} {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpError(f"{method} {url} failed: {exc}") from exc

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
        async with self._request("GET", url, headers=headers, params=params, ssl=ssl) as response:
            return await response.text(errors="replace")

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        ssl: bool | Any = None,
    ) -> Any:
        """GET *url* and decode the JSON body."""
        async with self._request("GET", url, headers=headers, params=params, ssl=ssl) as response:
            try:
                return await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError) as exc:
                raise ParsingError(f"Failed to decode JSON from {url}") from exc

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
        async with self._request(
            "POST",
            url,
            headers=headers,
            params=params,
            json=json_data,
            ssl=ssl,
        ) as response:
            try:
                return await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError) as exc:
                raise ParsingError(f"Failed to decode JSON from {url}") from exc

    async def get_bytes(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        ssl: bool | Any = None,
    ) -> bytes:
        """GET *url* and return the raw bytes."""
        async with self._request("GET", url, headers=headers, params=params, ssl=ssl) as response:
            return await response.read()

    # Context manager support
    async def __aenter__(self) -> HttpClient:
        await self.start()
        return self

    async def __aexit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        await self.close()
