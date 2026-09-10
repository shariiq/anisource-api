"""Router for listing and inspecting available anime scraper sources."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import SourceInfoResponse, SourceListResponse
from ..services.source_manager import source_manager

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get(
    "",
    response_model=SourceListResponse,
    summary="List all available anime sources",
    description="Returns metadata for all scraper extensions currently registered in the API.",
)
async def list_sources() -> SourceListResponse:
    sources = [
        SourceInfoResponse(
            id=src.id,
            name=src.name,
            base_url=src.base_url,
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
async def get_source(source_id: str) -> SourceInfoResponse:
    src = source_manager.get_source(source_id)
    return SourceInfoResponse(
        id=src.id,
        name=src.name,
        base_url=src.base_url,
    )
