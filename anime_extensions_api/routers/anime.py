"""Router for anime discovery, search, metadata, and episode catalog."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from ..config import get_settings
from ..dependencies import CacheDep, ManagerDep
from ..schemas import (
    AnimeSchema,
    EpisodeSchema,
    PaginatedResponse,
)

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
    source_manager: ManagerDep,
    cache: CacheDep,
) -> PaginatedResponse[AnimeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> dict[str, Any]:
        animes, has_next = await source.get_popular(page=page)
        items = [AnimeSchema.model_validate(anime) for anime in animes]
        return {
            "items": [item.model_dump() for item in items],
            "page": page,
            "has_next": has_next,
            "total_returned": len(items),
        }

    cache_key = f"{source.metadata.id}:popular:{page}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.popular_ttl_seconds
        )
        return PaginatedResponse[AnimeSchema](**data)

    data = await fetch()
    return PaginatedResponse[AnimeSchema](**data)


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
    source_manager: ManagerDep,
    cache: CacheDep,
) -> PaginatedResponse[AnimeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> dict[str, Any]:
        animes, has_next = await source.get_latest(page=page)
        items = [AnimeSchema.model_validate(anime) for anime in animes]
        return {
            "items": [item.model_dump() for item in items],
            "page": page,
            "has_next": has_next,
            "total_returned": len(items),
        }

    cache_key = f"{source.metadata.id}:latest:{page}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.latest_ttl_seconds
        )
        return PaginatedResponse[AnimeSchema](**data)

    data = await fetch()
    return PaginatedResponse[AnimeSchema](**data)


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
    source_manager: ManagerDep,
    cache: CacheDep,
) -> PaginatedResponse[AnimeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> dict[str, Any]:
        animes, has_next = await source.search(query=q, page=page)
        items = [AnimeSchema.model_validate(anime) for anime in animes]
        return {
            "items": [item.model_dump() for item in items],
            "page": page,
            "has_next": has_next,
            "total_returned": len(items),
        }

    cache_key = f"{source.metadata.id}:search:{q}:{page}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.search_ttl_seconds
        )
        return PaginatedResponse[AnimeSchema](**data)

    data = await fetch()
    return PaginatedResponse[AnimeSchema](**data)


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
    source_manager: ManagerDep,
    cache: CacheDep,
) -> AnimeSchema:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> dict[str, Any]:
        anime = await source.get_details(anime_id=anime_id)
        item = AnimeSchema.model_validate(anime)
        return item.model_dump()

    cache_key = f"{source.metadata.id}:details:{anime_id}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.details_ttl_seconds
        )
        return AnimeSchema.model_validate(data)

    data = await fetch()
    return AnimeSchema.model_validate(data)


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
    source_manager: ManagerDep,
    cache: CacheDep,
) -> list[EpisodeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> list[dict[str, Any]]:
        episodes = await source.get_episodes(anime_id=anime_id)
        items = [EpisodeSchema.model_validate(ep) for ep in episodes]
        return [item.model_dump() for item in items]

    cache_key = f"{source.metadata.id}:episodes:{anime_id}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.episodes_ttl_seconds
        )
        return [EpisodeSchema.model_validate(ep) for ep in data]

    data = await fetch()
    return [EpisodeSchema.model_validate(ep) for ep in data]
