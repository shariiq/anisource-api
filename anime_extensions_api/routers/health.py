"""Health check router for monitoring service status."""

from __future__ import annotations

import time

from fastapi import APIRouter

from ..config import get_settings
from ..dependencies import CacheDep, ManagerDep
from ..schemas import HealthCheckResponse

router = APIRouter(tags=["Health"])

# Record server boot time
_START_TIME = time.time()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check & System Observability",
    description="Returns the status of the service, uptime, active scrapers, and cache statistics.",
)
async def health_check(
    *,
    source_manager: ManagerDep,
    cache: CacheDep,
) -> HealthCheckResponse:
    """Check health, cache stats, and memory telemetry."""
    settings = get_settings()

    # Optional: Get process memory info via standard library if available
    memory_mb = 0.0
    try:
        import sys

        if sys.platform != "win32":
            import resource  # Available on Unix/POSIX

            memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # type: ignore[attr-defined]
    except ImportError:
        # Fallback on Windows/other platforms
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                memory_mb = pmc.WorkingSetSize / (1024 * 1024)
        except Exception:
            memory_mb = 0.0

    return HealthCheckResponse(
        status="ok",
        version=settings.version,
        uptime_seconds=round(time.time() - _START_TIME, 2),
        memory_usage_mb=round(memory_mb, 2),
        active_sources=len(source_manager.list_sources()),
        cache_stats=cache.get_stats(),
    )
