# ==============================================================================
# Modern 2026 High-Performance Multi-Stage Dockerfile (uv-powered)
# ==============================================================================
FROM ghcr.io/astral-sh/uv:0.6-python3.13-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy dependency specifications first for layer caching
COPY pyproject.toml README.md ./

# Install dependencies into virtual environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --no-cache -r pyproject.toml

# Copy source code and install project
COPY anime_extensions/ anime_extensions/
COPY anime_extensions_api/ anime_extensions_api/
COPY docs/ docs/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache -e .

# ==============================================================================
# Production Runtime Stage
# ==============================================================================
FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

# Security: Create non-privileged user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Runtime environment settings
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANIME_API_HOST=0.0.0.0 \
    ANIME_API_PORT=8000

# Copy application and virtualenv from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Production server execution with uvicorn
CMD ["uvicorn", "anime_extensions_api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
