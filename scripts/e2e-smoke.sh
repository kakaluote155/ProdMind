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

echo "[1/6] Starting ProdMind demo stack..."
docker compose up -d --build

wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90

trace_id=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
parent_span_id=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
traceparent="00-${trace_id}-${parent_span_id}-01"

echo "[2/6] Triggering the duplicate-user incident with browser-owned trace context..."
create_response=$(curl -sS -X POST "http://localhost:8090/api/users" \
  -H "Content-Type: application/json" \
  -H "traceparent: ${traceparent}" \
  -d '{"name":"CI Duplicate","phone":"13800000000"}')

if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres' <<< "$create_response"; then
  echo "Customer error response leaked diagnostic details: $create_response" >&2
  exit 1
fi

echo "[3/6] Customer received only the generic application error."

echo "[4/6] Polling the customer-safe ProdMind endpoint..."
for attempt in {1..30}; do
  support_response=$(curl -sS -X POST "http://localhost:8088/api/v1/support/trace" \
    -H "Content-Type: application/json" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}" || true)

  category=$(python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("category", ""))
except Exception:
    print("")' <<< "$support_response")

  if [[ "$category" == "duplicate_data" ]]; then
    break
  fi
  sleep 2
done

if [[ "${category:-}" != "duplicate_data" ]]; then
  echo "Customer support endpoint did not diagnose the incident in time." >&2
  echo "$support_response" >&2
  exit 1
fi

if grep -qiE 'uk_user_phone|duplicatekey|postgres|jdbc|trace[_-]?id|evidence|engineer_answer' <<< "$support_response"; then
  echo "Customer-safe investigation leaked technical evidence: $support_response" >&2
  exit 1
fi

echo "[5/6] Customer-safe diagnosis succeeded without technical leakage."

engineer_response=$(curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
  -H "Content-Type: application/json" \
  -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}")

engineer_category=$(python3 -c 'import json,sys
try:
    root=(json.load(sys.stdin).get("root_cause") or {})
    print(root.get("category", ""))
except Exception:
    print("")' <<< "$engineer_response")

if [[ "$engineer_category" != "database_unique_violation" ]]; then
  echo "Engineer investigation did not retain the technical root cause." >&2
  echo "$engineer_response" >&2
  exit 1
fi

echo "[6/6] End-to-end customer + engineer policy split succeeded."
python3 -m json.tool <<< "$support_response"
