"""FastAPI dependencies for clean dependency injection."""

from typing import Annotated

from fastapi import Depends, Request

from .services.cache import AsyncTTLCache
from .services.source_manager import SourceManager


def get_source_manager(request: Request) -> SourceManager:
    """Dependency to retrieve the configured SourceManager from application state."""
    return request.app.state.source_manager


def get_cache(request: Request) -> AsyncTTLCache:
    """Dependency to retrieve the TTL cache from application state."""
    return request.app.state.cache


ManagerDep = Annotated[SourceManager, Depends(get_source_manager)]
CacheDep = Annotated[AsyncTTLCache, Depends(get_cache)]
