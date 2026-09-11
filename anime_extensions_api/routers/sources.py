"""Router for listing and inspecting available anime scraper sources."""

from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import ManagerDep
from ..schemas import SourceInfoResponse, SourceListResponse

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get(
    "",
    response_model=SourceListResponse,
    summary="List all available anime sources",
    description="Returns metadata for all scraper extensions currently registered in the API.",
)
async def list_sources(
    *,
    source_manager: ManagerDep,
) -> SourceListResponse:
    sources = [
        SourceInfoResponse(
            id=src.metadata.id,
            name=src.metadata.name,
            base_url=src.metadata.base_url,
        )
        for src in source_manager.list_sources()
    ]
    return SourceListResponse(sources=sources, count=len(sources))


@router.get(
    "/{source_id}",
    response_model=SourceInfoResponse,
    summary="Get source details",
    description="Returns metadata for a specific scraper extension by ID.",
)
async def get_source(
    source_id: str,
    *,
    source_manager: ManagerDep,
) -> SourceInfoResponse:
    src = source_manager.get_source(source_id)
    return SourceInfoResponse(
        id=src.metadata.id,
        name=src.metadata.name,
        base_url=src.metadata.base_url,
    )
