"""FastAPI application factory and middleware configuration."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from anime_extensions.exceptions import AnimeExtensionError

from .config import APISettings, get_settings
from .routers import anime, health, sources, streams
from .schemas import ErrorDetail, ErrorResponse
from .services.cache import api_cache
from .services.source_manager import SourceNotFoundError, source_manager

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("anime_extensions_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup and shutdown event handling."""
    log.info("Starting up Anime Extensions API...")
    await source_manager.initialize()
    yield
    log.info("Shutting down Anime Extensions API...")
    await source_manager.close()
    api_cache.clear()


def create_app(settings: APISettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.title,
        description=settings.description,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ==========================================================================
    # Middleware
    # ==========================================================================

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Request timing & telemetry
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):  # type: ignore[no-untyped-def]
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log.exception(f"Unhandled exception during request processing: {exc}")
            raise exc
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time * 1000:.2f}ms"
        return response

    # ==========================================================================
    # Exception Handlers
    # ==========================================================================

    @app.exception_handler(SourceNotFoundError)
    async def source_not_found_handler(request: Request, exc: SourceNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="SOURCE_NOT_FOUND",
                    message=str(exc),
                    path=request.url.path,
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(AnimeExtensionError)
    async def anime_extension_error_handler(
        request: Request, exc: AnimeExtensionError
    ) -> JSONResponse:
        log.error(f"AnimeExtensionError on {request.url.path}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="UPSTREAM_SOURCE_ERROR",
                    message=f"Scraper/upstream error: {exc}",
                    path=request.url.path,
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=f"HTTP_{exc.status_code}",
                    message=str(exc.detail),
                    path=request.url.path,
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        message = errors[0]["msg"] if errors else "Invalid request parameters."
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message=f"Validation failed: {message}",
                    path=request.url.path,
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception(f"Internal server error processing {request.url.path}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_SERVER_ERROR",
                    message="An unexpected internal server error occurred.",
                    path=request.url.path,
                )
            ).model_dump(mode="json"),
        )

    # ==========================================================================
    # Routers
    # ==========================================================================

    # Root health endpoint
    app.include_router(health.router)

    # API v1 prefix
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(health.router)
    api_v1.include_router(sources.router)
    api_v1.include_router(anime.router)
    api_v1.include_router(streams.router)

    app.include_router(api_v1)

    return app


# Default ASGI application instance for uvicorn
app = create_app()
