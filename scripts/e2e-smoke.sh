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

new_trace_id() {
  python3 -c 'import secrets; print(secrets.token_hex(16))'
}

new_span_id() {
  python3 -c 'import secrets; print(secrets.token_hex(8))'
}

trigger_duplicate() {
  local trace_id="$1"
  local span_id="$2"
  curl -sS -X POST "http://localhost:8090/api/users" \
    -H "Content-Type: application/json" \
    -H "traceparent: 00-${trace_id}-${span_id}-01" \
    -d '{"name":"CI Duplicate","phone":"13800000000"}'
}

support_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/support/trace" \
    -H "Content-Type: application/json" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}"
}

engineer_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
    -H "Content-Type: application/json" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}"
}

echo "[1/8] Starting ProdMind demo stack..."
docker compose up -d --build

wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90

first_trace=$(new_trace_id)
first_span=$(new_span_id)

echo "[2/8] Triggering the first duplicate-user incident..."
first_create_response=$(trigger_duplicate "$first_trace" "$first_span")
if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres' <<< "$first_create_response"; then
  echo "Customer error response leaked diagnostic details: $first_create_response" >&2
  exit 1
fi

echo "[3/8] Diagnosing the first incident and seeding compact operational memory..."
first_category=""
for attempt in {1..30}; do
  first_support=$(support_for_trace "$first_trace" || true)
  first_category=$(python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("category", ""))
except Exception: print("")' <<< "$first_support")
  [[ "$first_category" == "duplicate_data" ]] && break
  sleep 2
done

if [[ "$first_category" != "duplicate_data" ]]; then
  echo "First incident was not diagnosed in time: $first_support" >&2
  exit 1
fi

if grep -qiE 'uk_user_phone|duplicatekey|postgres|jdbc|trace[_-]?id|evidence|engineer_answer|similar incident' <<< "$first_support"; then
  echo "Customer-safe first investigation leaked technical evidence: $first_support" >&2
  exit 1
fi

echo "[4/8] First incident diagnosed; triggering the same failure with a new trace..."
second_trace=$(new_trace_id)
second_span=$(new_span_id)
second_create_response=$(trigger_duplicate "$second_trace" "$second_span")
if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres' <<< "$second_create_response"; then
  echo "Second customer error leaked diagnostic details: $second_create_response" >&2
  exit 1
fi

echo "[5/8] Investigating the second incident and waiting for a history match..."
history_count=0
second_engineer=""
for attempt in {1..30}; do
  second_engineer=$(engineer_for_trace "$second_trace" || true)
  read -r engineer_category history_count <<< "$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    root=data.get("root_cause") or {}
    history=sum(1 for item in data.get("evidence", []) if item.get("type") == "history")
    print(root.get("category", ""), history)
except Exception:
    print("", 0)' <<< "$second_engineer")"
  if [[ "$engineer_category" == "database_unique_violation" && "$history_count" -ge 1 ]]; then
    break
  fi
  sleep 2
done

if [[ "${engineer_category:-}" != "database_unique_violation" || "$history_count" -lt 1 ]]; then
  echo "Second incident did not receive a historical match." >&2
  echo "$second_engineer" >&2
  exit 1
fi

echo "[6/8] Engineer investigation independently confirmed the failure and matched prior incident history."

second_support=$(support_for_trace "$second_trace")
if grep -qiE 'uk_user_phone|duplicatekey|postgres|jdbc|trace[_-]?id|evidence|engineer_answer|similar incident|incident-memory' <<< "$second_support"; then
  echo "Incident Memory leaked through the customer-safe response: $second_support" >&2
  exit 1
fi

echo "[7/8] Historical knowledge remains invisible across the customer boundary."

echo "[8/8] End-to-end Incident Memory test succeeded."
python3 -m json.tool <<< "$second_engineer"
