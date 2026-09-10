"""Router for anime discovery, search, metadata, and episode catalog."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from ..config import get_settings
from ..schemas import (
    AnimeSchema,
    EpisodeSchema,
    PaginatedResponse,
)
from ..services.cache import api_cache
from ..services.source_manager import source_manager

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
) -> PaginatedResponse[AnimeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:popular:{page}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return PaginatedResponse[AnimeSchema](**cached_data)

    animes, has_next = await source.get_popular(page=page)

    items = [AnimeSchema.model_validate(anime.to_dict()) for anime in animes]
    response_data = {
        "items": items,
        "page": page,
        "has_next": has_next,
        "total_returned": len(items),
    }

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            {
                "items": [item.model_dump() for item in items],
                "page": page,
                "has_next": has_next,
                "total_returned": len(items),
            },
            ttl_seconds=settings.cache.popular_ttl_seconds,
        )

    return PaginatedResponse[AnimeSchema](**response_data)  # type: ignore[arg-type]


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
) -> PaginatedResponse[AnimeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:latest:{page}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return PaginatedResponse[AnimeSchema](**cached_data)

    animes, has_next = await source.get_latest(page=page)

    items = [AnimeSchema.model_validate(anime.to_dict()) for anime in animes]
    response_data = {
        "items": items,
        "page": page,
        "has_next": has_next,
        "total_returned": len(items),
    }

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            {
                "items": [item.model_dump() for item in items],
                "page": page,
                "has_next": has_next,
                "total_returned": len(items),
            },
            ttl_seconds=settings.cache.latest_ttl_seconds,
        )

    return PaginatedResponse[AnimeSchema](**response_data)  # type: ignore[arg-type]


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
) -> PaginatedResponse[AnimeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:search:{q}:{page}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return PaginatedResponse[AnimeSchema](**cached_data)

    animes, has_next = await source.search(query=q, page=page)

    items = [AnimeSchema.model_validate(anime.to_dict()) for anime in animes]
    response_data = {
        "items": items,
        "page": page,
        "has_next": has_next,
        "total_returned": len(items),
    }

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            {
                "items": [item.model_dump() for item in items],
                "page": page,
                "has_next": has_next,
                "total_returned": len(items),
            },
            ttl_seconds=settings.cache.search_ttl_seconds,
        )

    return PaginatedResponse[AnimeSchema](**response_data)  # type: ignore[arg-type]


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
) -> AnimeSchema:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:details:{anime_id}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return AnimeSchema.model_validate(cached_data)

    anime = await source.get_details(anime_id=anime_id)
    item = AnimeSchema.model_validate(anime.to_dict())

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            item.model_dump(),
            ttl_seconds=settings.cache.details_ttl_seconds,
        )

    return item


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
) -> list[EpisodeSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:episodes:{anime_id}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return [EpisodeSchema.model_validate(ep) for ep in cached_data]

    episodes = await source.get_episodes(anime_id=anime_id)
    items = [EpisodeSchema.model_validate(ep.to_dict()) for ep in episodes]

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            [item.model_dump() for item in items],
            ttl_seconds=settings.cache.episodes_ttl_seconds,
        )

    return items
