# 1. Build Stage: Resolve dependencies using uv in python-slim (glibc)
FROM python:3.12-slim AS builder

# Install uv inside the builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1

# Copy root lockfile and workspace configurations
COPY pyproject.toml uv.lock ./
COPY servers/rag_server ./servers/rag_server

# Install only the rag-server package statically in the virtualenv
RUN uv sync --frozen --no-dev --package rag-server --no-editable

# 2. Production Stage: Create a clean runner image using the exact same base
FROM python:3.12-slim

WORKDIR /app

# Copy the built virtual environment (which contains the installed code!)
COPY --from=builder /app/.venv /app/.venv

# Set path to use the virtual environment binaries directly
ENV PATH="/app/.venv/bin:$PATH"

# Default container port
EXPOSE 8080

# Execute server using the dynamic PORT env var (required by Cloud Run)
CMD ["sh", "-c", "rag-server --transport sse --port ${PORT:-8080}"]
