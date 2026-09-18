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


# Run the PPT Server locally using stdio transport
run-ppt-stdio:
    uv run --package ppt-server ppt-server --transport stdio

# Run the PPT Server locally using SSE transport on a specific port
run-ppt-sse port="8050":
    uv run --package ppt-server ppt-server --transport sse --port {{port}}

# Launch the official visual MCP Inspector for the PPT Server
inspect-ppt:
    uv run --package ppt-server fastmcp dev inspector servers/ppt_server/src/ppt_server/main.py

# Run the Sales & Products BigQuery Server locally using stdio transport
run-sales-stdio:
    uv run --package sales-products-server sales-products-server --transport stdio

# Run the Sales & Products BigQuery Server locally using SSE transport on a specific port
run-sales-sse port="8060":
    uv run --package sales-products-server sales-products-server --transport sse --port {{port}}

# Launch the official visual MCP Inspector for the Sales & Products Server
inspect-sales:
    uv run --package sales-products-server fastmcp dev inspector servers/sales_products_server/src/sales_products_server/main.py

