#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run the ProdMind demo." >&2
  exit 1
fi
docker compose version >/dev/null

build_args=(--build)
if [[ "${1:-}" == "--no-build" ]]; then build_args=(); fi

echo "Starting the ProdMind demo stack..."
docker compose up -d "${build_args[@]}"

wait_http() {
  local name="$1" url="$2" attempts="${3:-90}"
  for ((attempt=1; attempt<=attempts; attempt++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "Ready: $name"
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for $name at $url" >&2
  docker compose ps >&2
  docker compose logs --tail=80 prodmind-server demo-user-service >&2 || true
  return 1
}

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required for demo health checks." >&2
  exit 1
fi

api_port="${PRODMIND_API_PORT:-8088}"
wait_http "ProdMind API" "http://localhost:${api_port}/health"
wait_http "customer demo" "http://localhost:8090/actuator/health"
wait_http "Prometheus" "http://localhost:9090/-/ready"

cat <<EOF

ProdMind is ready.

Customer demo:   http://localhost:8090
Multi-service:   http://localhost:8090/multiservice.html
Engineer viewer: http://localhost:${api_port}/engineer
API docs:        http://localhost:${api_port}/docs

Local project: demo
Engineer key:  demo-engineer-key

Stop without deleting data: bash scripts/demo-down.sh
Stop and reset demo data:   bash scripts/demo-down.sh --volumes
EOF
