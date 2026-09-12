"""FastAPI dependencies for clean dependency injection."""

from typing import Annotated

from fastapi import Depends, Request

from anime_extensions.core import ExtensionRuntime

from .services.cache import AsyncTTLCache


def get_runtime(request: Request) -> ExtensionRuntime:
    """Dependency to retrieve the configured ExtensionRuntime from application state."""
    return request.app.state.runtime


def get_cache(request: Request) -> AsyncTTLCache:
    """Dependency to retrieve the TTL cache from application state."""
    return request.app.state.cache


RuntimeDep = Annotated[ExtensionRuntime, Depends(get_runtime)]
CacheDep = Annotated[AsyncTTLCache, Depends(get_cache)]
