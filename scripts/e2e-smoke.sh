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

new_trace_id() { python3 -c 'import secrets; print(secrets.token_hex(16))'; }
new_span_id() { python3 -c 'import secrets; print(secrets.token_hex(8))'; }

traceparent_for() {
  local trace_id="$1"
  printf '00-%s-%s-01' "$trace_id" "$(new_span_id)"
}

trigger_duplicate() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8090/api/users" \
    -H "Content-Type: application/json" \
    -H "traceparent: $(traceparent_for "$trace_id")" \
    -d '{"name":"CI Duplicate","phone":"13800000000"}'
}

trigger_downstream_outage() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8090/api/payments/charge" \
    -H "traceparent: $(traceparent_for "$trace_id")"
}

support_for_trace() {
  local trace_id="$1"
  local question="$2"
  local action="$3"
  curl -sS -X POST "http://localhost:8088/api/v1/support/trace" \
    -H "Content-Type: application/json" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"$question\",\"action\":\"$action\",\"page\":\"/\"}"
}

engineer_for_trace() {
  local trace_id="$1"
  local question="$2"
  local action="$3"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
    -H "Content-Type: application/json" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"$question\",\"action\":\"$action\",\"page\":\"/\"}"
}

poll_customer_category() {
  local trace_id="$1"
  local question="$2"
  local action="$3"
  local expected="$4"
  local response=""
  local category=""
  for attempt in {1..30}; do
    response=$(support_for_trace "$trace_id" "$question" "$action" || true)
    category=$(python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("category", ""))
except Exception: print("")' <<< "$response")
    if [[ "$category" == "$expected" ]]; then
      printf '%s' "$response"
      return 0
    fi
    sleep 2
  done
  echo "Expected customer category $expected but got: $response" >&2
  return 1
}

poll_engineer_category() {
  local trace_id="$1"
  local question="$2"
  local action="$3"
  local expected="$4"
  local require_history="${5:-0}"
  local response=""
  local category=""
  local history_count=0
  for attempt in {1..30}; do
    response=$(engineer_for_trace "$trace_id" "$question" "$action" || true)
    read -r category history_count <<< "$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    root=data.get("root_cause") or {}
    history=sum(1 for item in data.get("evidence", []) if item.get("type") == "history")
    print(root.get("category", ""), history)
except Exception:
    print("", 0)' <<< "$response")"
    if [[ "$category" == "$expected" && "$history_count" -ge "$require_history" ]]; then
      printf '%s' "$response"
      return 0
    fi
    sleep 2
  done
  echo "Expected engineer category $expected (history >= $require_history) but got: $response" >&2
  return 1
}

assert_generic_customer_error() {
  local response="$1"
  if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres|connectexception|resourceaccessexception|127\.0\.0\.1|65530' <<< "$response"; then
    echo "Customer application response leaked diagnostic details: $response" >&2
    exit 1
  fi
}

assert_safe_support_response() {
  local response="$1"
  if grep -qiE 'uk_user_phone|duplicatekey|postgres|jdbc|trace[_-]?id|evidence|engineer_answer|similar incident|incident-memory|connectexception|resourceaccessexception|127\.0\.0\.1|65530' <<< "$response"; then
    echo "Customer-safe ProdMind response leaked technical details: $response" >&2
    exit 1
  fi
}

echo "[1/12] Starting ProdMind demo stack..."
docker compose up -d --build
wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90

# Scenario A: database uniqueness violation + Incident Memory regression.
first_trace=$(new_trace_id)
echo "[2/12] Triggering duplicate-data incident #1..."
first_create=$(trigger_duplicate "$first_trace")
assert_generic_customer_error "$first_create"

echo "[3/12] Diagnosing duplicate-data incident #1..."
first_support=$(poll_customer_category "$first_trace" "Why did creating the user fail?" "create-user" "duplicate_data")
assert_safe_support_response "$first_support"

second_trace=$(new_trace_id)
echo "[4/12] Triggering duplicate-data incident #2..."
second_create=$(trigger_duplicate "$second_trace")
assert_generic_customer_error "$second_create"

echo "[5/12] Verifying database RCA + Incident Memory..."
second_engineer=$(poll_engineer_category "$second_trace" "Why did creating the user fail?" "create-user" "database_unique_violation" 1)
second_support=$(poll_customer_category "$second_trace" "Why did creating the user fail?" "create-user" "duplicate_data")
assert_safe_support_response "$second_support"

echo "[6/12] Database rule independently diagnosed the failure and reused history."

# Scenario B: a completely different root cause through the same engine.
downstream_trace=$(new_trace_id)
echo "[7/12] Triggering downstream dependency outage..."
downstream_create=$(trigger_downstream_outage "$downstream_trace")
assert_generic_customer_error "$downstream_create"

echo "[8/12] Waiting for downstream telemetry ingestion..."
downstream_support=$(poll_customer_category "$downstream_trace" "Why did payment fail?" "charge-payment" "service_unavailable")
assert_safe_support_response "$downstream_support"

echo "[9/12] Verifying the pluggable downstream-unavailable RCA rule..."
downstream_engineer=$(poll_engineer_category "$downstream_trace" "Why did payment fail?" "charge-payment" "downstream_unavailable" 0)

has_dependency_evidence=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    print(1 if any(item.get("type") == "dependency" for item in data.get("evidence", [])) else 0)
except Exception:
    print(0)' <<< "$downstream_engineer")

if [[ "$has_dependency_evidence" != "1" ]]; then
  echo "Downstream investigation lacks dependency evidence." >&2
  echo "$downstream_engineer" >&2
  exit 1
fi

echo "[10/12] Same ProdMind engine diagnosed a second, unrelated failure class."
echo "[11/12] Customer-safe boundary held for both RCA categories."
echo "[12/12] Multi-rule end-to-end test succeeded."

printf '\nDatabase customer response:\n'
python3 -m json.tool <<< "$second_support"
printf '\nDownstream customer response:\n'
python3 -m json.tool <<< "$downstream_support"
