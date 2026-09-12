"""Router for listing and inspecting available anime scraper sources."""

from __future__ import annotations

from fastapi import APIRouter

from anime_extensions.core.errors import SourceNotFoundError

from ..dependencies import RuntimeDep
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
    runtime: RuntimeDep,
) -> SourceListResponse:
    sources = [
        SourceInfoResponse(
            id=source_cls.metadata.id,
            name=source_cls.metadata.name,
            base_url=source_cls.metadata.base_url,
        )
        for source_cls in runtime.sources.list_all()
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
    runtime: RuntimeDep,
) -> SourceInfoResponse:
    source_cls = runtime.sources.get(source_id)
    if source_cls is None:
        raise SourceNotFoundError(source_id)

    # Instantiate source to access metadata
    source = source_cls(context=runtime.context)
    return SourceInfoResponse(
        id=source.metadata.id,
        name=source.metadata.name,
        base_url=source.metadata.base_url,
    )
