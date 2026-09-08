# List all available recipes
default:
    @just --list

# Sync all workspace packages and dependencies
sync:
    uv sync

# Run the RAG Server locally using stdio transport
run-rag-stdio:
    uv run --package rag-server rag-server --transport stdio

# Run the RAG Server locally using SSE transport on a specific port
run-rag-sse port="8020":
    uv run --package rag-server rag-server --transport sse --port {{port}}

# Run the BigQuery Server locally using stdio transport
run-bigquery-stdio:
    uv run --package bigQuery-server bigQuery-server --transport stdio

# Run the BigQuery Server locally using SSE transport on a specific port
run-bigquery-sse port="8030":
    uv run --package bigQuery-server bigQuery-server --transport sse --port {{port}}

# Run the SGS BigQuery Server productivity locally using stdio transport
run-bigquery-sgs-stdio:
    uv run --package sgs-bq-server sgs-bq-server --transport stdio

# Run the SGS BigQuery Server for productivity locally using SSE transport on a specific port
run-bigquery-sgs-sse port="8040":
    uv run --package sgs-bq-server sgs-bq-server --transport sse --port {{port}}

# Run the Registry Gateway locally using stdio transport
run-gateway-stdio:
    uv run --package registry-gateway registry-gateway --transport stdio

# Run the Registry Gateway locally using SSE transport on a specific port
run-gateway-sse port="8081":
    uv run --package registry-gateway registry-gateway --transport sse --port {{port}}

# Build and start the services locally via Docker Compose
docker-up:
    docker-compose up --build

# Stop and clean up Docker Compose containers and networks
docker-down:
    docker-compose down

# Launch the official visual MCP Inspector for the RAG Server
inspect-rag:
    uv run --package rag-server fastmcp dev inspector servers/rag_server/src/rag_server/main.py

# Launch the official visual MCP Inspector for the BigQuery Server
inspect-bigquery:
    uv run --package bigQuery-server fastmcp dev inspector servers/bigQuery_server/src/bigQuery_server/main.py

# Launch the official visual MCP Inspector for the BigQuery Server
inspect-bigquery-sgs:
    uv run --package sgs-bq-server fastmcp dev inspector servers/sgs_bq_server/src/sgs_bq_server/main.py
