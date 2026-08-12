#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose logs --no-color > /tmp/prodmind-compose.log 2>&1 || true
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_http() {
  local url="$1"
  local attempts="${2:-60}"
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

echo "[1/5] Starting ProdMind demo stack..."
docker compose up -d --build

wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90

echo "[2/5] Triggering the duplicate-user incident..."
create_response=$(curl -sS -X POST "http://localhost:8090/api/users" \
  -H "Content-Type: application/json" \
  -d '{"name":"CI Duplicate","phone":"13800000000"}')

trace_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("traceId", ""))' <<< "$create_response")
if [[ -z "$trace_id" || "$trace_id" == "unavailable" ]]; then
  echo "Demo failure did not return a usable trace ID: $create_response" >&2
  exit 1
fi

echo "[3/5] Trace captured: $trace_id"

echo "[4/5] Polling ProdMind until telemetry is available..."
for attempt in {1..30}; do
  investigation=$(curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
    -H "Content-Type: application/json" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}" || true)

  category=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    root=data.get("root_cause") or {}
    print(root.get("category", ""))
except Exception:
    print("")' <<< "$investigation")

  if [[ "$category" == "database_unique_violation" ]]; then
    echo "[5/5] End-to-end diagnosis succeeded."
    python3 -m json.tool <<< "$investigation"
    exit 0
  fi

  sleep 2
done

echo "ProdMind did not diagnose the duplicate-user incident in time." >&2
echo "Last investigation response:" >&2
echo "$investigation" >&2
cat /tmp/prodmind-compose.log >&2 2>/dev/null || true
exit 1
