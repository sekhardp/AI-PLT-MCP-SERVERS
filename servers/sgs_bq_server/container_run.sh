#!/usr/bin/env bash
#
# Build and run the SGS BigQuery MCP Server in Docker.
#

set -euo pipefail

readonly DEFAULT_IMAGE="sgs-bq-server"
readonly DEFAULT_PORT="8040"
readonly DEFAULT_HOST="0.0.0.0"
readonly DEFAULT_NETWORK="MCP-Shared-Network"
readonly DEFAULT_CONTAINER="sgs-bq-server"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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

  echo "Building Docker image ${IMAGE_NAME} from ${WORKSPACE_ROOT}..."
  docker build -f "${SCRIPT_DIR}/Dockerfile" -t "${IMAGE_NAME}" "${WORKSPACE_ROOT}"

  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping existing container ${CONTAINER_NAME}..."
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi

  echo "Starting SGS BigQuery MCP Server container on http://${HOST}:${PORT}..."
  echo "Endpoint URLs:"
  echo "  - Health: http://localhost:$PORT/health"
  echo "  - SSE Endpoint: http://localhost:$PORT/sse"
  docker run --rm -it \
    --name "${CONTAINER_NAME}" \
    --network "${NETWORK_NAME}" \
    -p "${PORT}:8080" \
    -e "PORT=8080" \
    -e "BIGQUERY_PROJECT_ID=${BIGQUERY_PROJECT_ID:-bsi-sftphub-dev}" \
    -v "${WORKSPACE_ROOT}/servers/sgs_bq_server/credentials.json:/app/servers/sgs_bq_server/credentials.json:ro" \
    "${IMAGE_NAME}"
}

main "$@"