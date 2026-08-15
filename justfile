# List all available recipes
default:
    @just --list

# Sync all workspace packages and dependencies
sync:
    uv sync

# Run the Weather Server locally using stdio transport
run-weather-stdio:
    uv run --package weather-server weather-server --transport stdio

# Run the Weather Server locally using SSE transport on a specific port
run-weather-sse port="8020":
    uv run --package weather-server weather-server --transport sse --port {{port}}

# Run the Registry Gateway locally using stdio transport
run-gateway-stdio:
    uv run --package registry-gateway registry-gateway --transport stdio

# Run the Registry Gateway locally using SSE transport on a specific port
run-gateway-sse port="8081":
    uv run --package registry-gateway registry-gateway --transport sse --port {{port}}

# Run the verification test client script
test-client:
    uv run python .gemini/antigravity-ide/brain/650ceb51-5366-449b-9025-24ac39fc132d/scratch/test_client.py

# Build and start the services locally via Docker Compose
docker-up:
    docker-compose up --build

# Stop and clean up Docker Compose containers and networks
docker-down:
    docker-compose down

# Launch the official visual MCP Inspector for the Weather Server
inspect:
    uv run --package weather-server fastmcp dev inspector servers/weather_server/src/weather_server/main.py
