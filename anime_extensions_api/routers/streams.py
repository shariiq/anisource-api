"""Router for episode streaming servers and video extraction."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from ..config import get_settings
from ..schemas import ServerSchema, StreamSchema
from ..services.cache import api_cache
from ..services.source_manager import source_manager

log = logging.getLogger(__name__)

router = APIRouter(tags=["Streams & Servers"])


@router.get(
    "/{source_id}/servers/{episode_id:path}",
    response_model=list[ServerSchema],
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Get streaming servers for an episode",
    description="List all available video hosting servers (e.g. Doodstream, Vidplay, Filemoon) for an episode.",
)
async def get_servers(
    source_id: str,
    episode_id: str,
) -> list[ServerSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:servers:{episode_id}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return [ServerSchema.model_validate(srv) for srv in cached_data]

    servers = await source.get_servers(episode_id=episode_id)
    items = [ServerSchema.model_validate(srv.to_dict()) for srv in servers]

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            [item.model_dump() for item in items],
            ttl_seconds=settings.cache.servers_ttl_seconds,
        )

    return items


@router.get(
    "/{source_id}/streams/{episode_id:path}",
    response_model=list[StreamSchema],
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    summary="Extract playable video streams",
    description="Resolve and extract direct video streams (HLS/MP4) and subtitle tracks from a chosen server.",
)
async def get_streams(
    source_id: str,
    episode_id: str,
    server_id: str = Query(..., description="Server identifier obtained from the /servers endpoint."),
) -> list[StreamSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    cache_key = f"{source.id}:streams:{episode_id}:{server_id}"
    if settings.cache.enabled:
        cached_data = await api_cache.get(cache_key)
        if cached_data is not None:
            return [StreamSchema.model_validate(stream) for stream in cached_data]

    streams = await source.get_streams(episode_id=episode_id, server_id=server_id)
    items = [StreamSchema.model_validate(stream.to_dict()) for stream in streams]

    if settings.cache.enabled:
        await api_cache.set(
            cache_key,
            [item.model_dump() for item in items],
            ttl_seconds=settings.cache.streams_ttl_seconds,
        )

    return items
