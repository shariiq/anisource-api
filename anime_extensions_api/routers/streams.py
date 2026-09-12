"""Router for episode streaming servers and video extraction."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from anime_extensions.core.errors import UnsupportedCapabilityError
from anime_extensions.core.metadata import SourceCapability
from anime_extensions.core.models import Server, Stream

from ..config import get_settings
from ..dependencies import CacheDep, ManagerDep
from ..schemas import ServerSchema, StreamSchema
from ._cache import fetch_cached

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
    if not source.supports(SourceCapability.SERVERS):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.SERVERS)

    settings = get_settings()

    async def _fetch() -> list[Server]:
        return await source.get_servers(episode_id=episode_id)

    cache_key = f"{source.metadata.id}:servers:{episode_id}"
    servers: list[Server] = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.servers_ttl_seconds,
    )

    return [ServerSchema.model_validate(srv) for srv in servers]


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
    if not source.supports(SourceCapability.STREAMS):
        raise UnsupportedCapabilityError(source.metadata.id, SourceCapability.STREAMS)

    settings = get_settings()

    async def _fetch() -> list[Stream]:
        return await source.get_streams(episode_id=episode_id, server_id=server_id)

    cache_key = f"{source.metadata.id}:streams:{episode_id}:{server_id}"
    streams: list[Stream] = await fetch_cached(
        cache,
        cache_key,
        _fetch,
        enabled=settings.cache.enabled,
        ttl_seconds=settings.cache.streams_ttl_seconds,
    )

    return [StreamSchema.model_validate(stream) for stream in streams]
