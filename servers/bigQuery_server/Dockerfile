FROM python:3.12-slim

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy the monorepo configuration
COPY pyproject.toml uv.lock ./

# Copy packages
COPY registry registry
COPY servers servers

# Sync workspace dependencies
RUN uv sync --frozen --no-cache

# Run the BigQuery server by default on port 8080 using SSE transport
EXPOSE 8080
CMD ["uv", "run", "--package", "bigQuery-server", "bigQuery-server", "--transport", "sse", "--port", "8080", "--host", "0.0.0.0"]
