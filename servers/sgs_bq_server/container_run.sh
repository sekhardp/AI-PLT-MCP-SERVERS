#!/usr/bin/env bash
#
# Build and run the MCP Server in Docker.
# The script ensures the shared Docker network exists and attaches the


set -euo pipefail

readonly DEFAULT_IMAGE="suntory-gcp-productivity-bqclient-mcp"
readonly DEFAULT_PORT="4208"
readonly DEFAULT_HOST="0.0.0.0"
readonly DEFAULT_NETWORK="MCP-Shared-Network"
readonly DEFAULT_CONTAINER="suntory-gcp-productivity-bqclient-mcp"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-${DEFAULT_IMAGE}}"
PORT="${PORT:-${DEFAULT_PORT}}"
HOST="${HOST:-${DEFAULT_HOST}}"
NETWORK_NAME="${NETWORK_NAME:-${DEFAULT_NETWORK}}"
CONTAINER_NAME="${CONTAINER_NAME:-${DEFAULT_CONTAINER}}"

ensure_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: Required command '${command_name}' was not found in PATH." >&2
    exit 1
  fi
}

ensure_network() {
  if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    echo "Creating Docker network ${NETWORK_NAME}..."
    docker network create "${NETWORK_NAME}" >/dev/null
  fi
}


main() {
  ensure_command docker
  ensure_network

  echo "Building Docker image ${IMAGE_NAME}..."
  docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping existing container ${CONTAINER_NAME}..."
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi

  echo "Starting MCP Server BigQuery container on http://${HOST}:${PORT}..."
  echo "Success! MCP HTTP server is running."
  echo "Endpoint URLs:"
  echo "  - Health: http://localhost:$PORT/health"
  echo "  - MCP Endpoint: http://localhost:$PORT/mcp"
  docker run --rm -it \
    --name "${CONTAINER_NAME}" \
    --network "${NETWORK_NAME}" \
    -p "${PORT}:${PORT}" \
    -e "MCP_HOST=${HOST}" \
    -e "MCP_PORT=${PORT}" \
    -e "MCP_TRANSPORT=streamable-http" \
    -e "SERVICE_ACCOUNT_FILE=/app/credentials.json" \
    -e "GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json" \
    -e "BIGQUERY_PROJECT_ID=${BIGQUERY_PROJECT_ID:-bsi-sftphub-dev}" \
    "${IMAGE_NAME}"
}

main "$@"