"""Router for episode streaming servers and video extraction."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from ..config import get_settings
from ..dependencies import CacheDep, ManagerDep
from ..schemas import ServerSchema, StreamSchema

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
    *,
    source_manager: ManagerDep,
    cache: CacheDep,
) -> list[ServerSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> list[dict[str, Any]]:
        servers = await source.get_servers(episode_id=episode_id)
        items = [ServerSchema.model_validate(srv) for srv in servers]
        return [item.model_dump() for item in items]

    cache_key = f"{source.metadata.id}:servers:{episode_id}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.servers_ttl_seconds
        )
        return [ServerSchema.model_validate(srv) for srv in data]

    data = await fetch()
    return [ServerSchema.model_validate(srv) for srv in data]


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
    server_id: str = Query(
        ..., description="Server identifier obtained from the /servers endpoint."
    ),
    *,
    source_manager: ManagerDep,
    cache: CacheDep,
) -> list[StreamSchema]:
    source = source_manager.get_source(source_id)
    settings = get_settings()

    async def fetch() -> list[dict[str, Any]]:
        streams = await source.get_streams(episode_id=episode_id, server_id=server_id)
        items = [StreamSchema.model_validate(stream) for stream in streams]
        return [item.model_dump() for item in items]

    cache_key = f"{source.metadata.id}:streams:{episode_id}:{server_id}"
    if settings.cache.enabled:
        data = await cache.get_or_set(
            cache_key, fetch, ttl_seconds=settings.cache.streams_ttl_seconds
        )
        return [StreamSchema.model_validate(stream) for stream in data]

    data = await fetch()
    return [StreamSchema.model_validate(stream) for stream in data]
