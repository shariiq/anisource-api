"""Router for anime discovery, search, metadata, and episode catalog."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from anime_extensions.core.errors import SourceNotFoundError, UnsupportedCapabilityError
from anime_extensions.core.metadata import SourceCapability
from anime_extensions.core.models import Anime, Episode, Page

from ..config import get_settings
from ..dependencies import CacheDep, RuntimeDep
from ..schemas import (
    AnimeSchema,
    EpisodeSchema,
    PaginatedResponse,
)
from ._cache import fetch_cached

log = logging.getLogger(__name__)

router = APIRouter(tags=["Anime"])


@router.get(
    "/{source_id}/popular",
    response_model=PaginatedResponse[AnimeSchema],
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Get popular anime listing",
    description="Fetch a paginated list of trending/popular anime from the specified source.",
)
async def get_popular(
    source_id: str,
    page: int = Query(1, ge=1, description="Page number to fetch."),
    *,
    runtime: RuntimeDep,
    cache: CacheDep,
) -> PaginatedResponse[AnimeSchema]:
    source = runtime.get_source(source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    if not source.supports(SourceCapability.POPULAR):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.POPULAR)

    settings = get_settings()

    async def _fetch() -> Page[Anime]:
        return await source.get_popular(page=page)

    cache_key = f"{source.metadata.id}:popular:{page}"
    page_data: Page[Anime] = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.popular_ttl_seconds,
    )

    return PaginatedResponse[AnimeSchema](
        items=[AnimeSchema.model_validate(item) for item in page_data.items],
        page=page_data.page,
        has_next=page_data.has_next,
        total_returned=page_data.total_returned or len(page_data.items),
    )


@router.get(
    "/{source_id}/latest",
    response_model=PaginatedResponse[AnimeSchema],
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Get latest updated anime",
    description="Fetch a paginated list of recently updated anime from the specified source.",
)
async def get_latest(
    source_id: str,
    page: int = Query(1, ge=1, description="Page number to fetch."),
    *,
    runtime: RuntimeDep,
    cache: CacheDep,
) -> PaginatedResponse[AnimeSchema]:
    source = runtime.get_source(source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    if not source.supports(SourceCapability.LATEST):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.LATEST)

    settings = get_settings()

    async def _fetch() -> Page[Anime]:
        return await source.get_latest(page=page)

    cache_key = f"{source.metadata.id}:latest:{page}"
    page_data: Page[Anime] = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.latest_ttl_seconds,
    )

    return PaginatedResponse[AnimeSchema](
        items=[AnimeSchema.model_validate(item) for item in page_data.items],
        page=page_data.page,
        has_next=page_data.has_next,
        total_returned=page_data.total_returned or len(page_data.items),
    )


@router.get(
    "/{source_id}/search",
    response_model=PaginatedResponse[AnimeSchema],
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Search anime by title",
    description="Perform a keyword search for anime titles on the specified source.",
)
async def search_anime(
    source_id: str,
    q: str = Query(..., min_length=1, description="Search query string."),
    page: int = Query(1, ge=1, description="Page number to fetch."),
    *,
    runtime: RuntimeDep,
    cache: CacheDep,
) -> PaginatedResponse[AnimeSchema]:
    source = runtime.get_source(source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    if not source.supports(SourceCapability.SEARCH):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.SEARCH)

    settings = get_settings()

    async def _fetch() -> Page[Anime]:
        return await source.search(query=q, page=page)

    cache_key = f"{source.metadata.id}:search:{q}:{page}"
    page_data: Page[Anime] = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.search_ttl_seconds,
    )

    return PaginatedResponse[AnimeSchema](
        items=[AnimeSchema.model_validate(item) for item in page_data.items],
        page=page_data.page,
        has_next=page_data.has_next,
        total_returned=page_data.total_returned or len(page_data.items),
    )


@router.get(
    "/{source_id}/anime/{anime_id:path}",
    response_model=AnimeSchema,
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Get anime details and metadata",
    description="Retrieve comprehensive details, synopsis, genres, and release status for an anime.",
)
async def get_anime_details(
    source_id: str,
    anime_id: str,
    *,
    runtime: RuntimeDep,
    cache: CacheDep,
) -> AnimeSchema:
    source = runtime.get_source(source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    if not source.supports(SourceCapability.DETAILS):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.DETAILS)

    settings = get_settings()

    async def _fetch() -> Anime:
        return await source.get_details(anime_id=anime_id)

    cache_key = f"{source.metadata.id}:details:{anime_id}"
    anime: Anime = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.details_ttl_seconds,
    )

    return AnimeSchema.model_validate(anime)


@router.get(
    "/{source_id}/episodes/{anime_id:path}",
    response_model=list[EpisodeSchema],
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Get full episode list for an anime",
    description="Retrieve all indexed episodes, sub/dub flags, and titles for an anime.",
)
async def get_episodes(
    source_id: str,
    anime_id: str,
    *,
    runtime: RuntimeDep,
    cache: CacheDep,
) -> list[EpisodeSchema]:
    source = runtime.get_source(source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    if not source.supports(SourceCapability.EPISODES):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.EPISODES)

    settings = get_settings()

    async def _fetch() -> list[Episode]:
        return await source.get_episodes(anime_id=anime_id)

    cache_key = f"{source.metadata.id}:episodes:{anime_id}"
    episodes: list[Episode] = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.episodes_ttl_seconds,
    )

    return [EpisodeSchema.model_validate(ep) for ep in episodes]
