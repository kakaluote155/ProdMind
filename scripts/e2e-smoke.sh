#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="demo"
ENGINEER_KEY="demo-engineer-key"

cleanup() {
  docker compose logs --no-color > /tmp/prodmind-compose.log 2>&1 || true
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_http() {
  local url="$1" attempts="${2:-60}"
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

wait_prometheus_pool_metric() {
  local response="" count=0
  for attempt in {1..30}; do
    response=$(curl -sS -G "http://localhost:9090/api/v1/query" \
      --data-urlencode 'query=hikaricp_connections_max{application="demo-user-service",prodmind_project="demo"}' || true)
    count=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    print(len((data.get("data") or {}).get("result") or []))
except Exception:
    print(0)' <<< "$response")
    if [[ "$count" -ge 1 ]]; then return 0; fi
    sleep 1
  done
  echo "Prometheus did not scrape the project-scoped Hikari metric in time: $response" >&2
  return 1
}

new_trace_id() { python3 -c 'import secrets; print(secrets.token_hex(16))'; }
new_span_id() { python3 -c 'import secrets; print(secrets.token_hex(8))'; }
traceparent_for() { printf '00-%s-%s-01' "$1" "$(new_span_id)"; }

trigger_duplicate() {
  curl -sS -X POST "http://localhost:8090/api/users" \
    -H "Content-Type: application/json" \
    -H "traceparent: $(traceparent_for "$1")" \
    -d '{"name":"CI Duplicate","phone":"13800000000"}'
}

trigger_downstream_outage() {
  curl -sS -X POST "http://localhost:8090/api/payments/charge" \
    -H "traceparent: $(traceparent_for "$1")"
}

trigger_pool_probe() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8090/api/pool/probe" \
    -H "traceparent: $(traceparent_for "$trace_id")"
}

start_pool_holders() {
  curl -sS -X POST "http://localhost:8090/api/pool/hold?seconds=8" >/tmp/pool-holder-1.json &
  HOLDER_PID_1=$!
  curl -sS -X POST "http://localhost:8090/api/pool/hold?seconds=8" >/tmp/pool-holder-2.json &
  HOLDER_PID_2=$!
  export HOLDER_PID_1 HOLDER_PID_2
}

trigger_slow_report() {
  local trace_id="$1"
  curl -sS -o /tmp/slow-report.json -w '%{http_code}' -X POST \
    "http://localhost:8090/api/reports/slow" \
    -H "traceparent: $(traceparent_for "$trace_id")"
}

support_for_trace() {
  local trace_id="$1" question="$2" action="$3" project_id="${4:-$PROJECT_ID}"
  curl -sS -X POST "http://localhost:8088/api/v1/support/trace" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $project_id" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"$question\",\"action\":\"$action\",\"page\":\"/\"}"
}

engineer_for_trace() {
  local trace_id="$1" question="$2" action="$3"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $PROJECT_ID" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"$question\",\"action\":\"$action\",\"page\":\"/\"}"
}

graph_for_trace() {
  local trace_id="$1" question="$2" action="$3" project_id="${4:-$PROJECT_ID}"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace/graph" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $project_id" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"$question\",\"action\":\"$action\",\"page\":\"/\"}"
}

poll_customer_category() {
  local trace_id="$1" question="$2" action="$3" expected="$4" response="" category=""
  for attempt in {1..30}; do
    response=$(support_for_trace "$trace_id" "$question" "$action" || true)
    category=$(python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("category", ""))
except Exception: print("")' <<< "$response")
    if [[ "$category" == "$expected" ]]; then printf '%s' "$response"; return 0; fi
    sleep 2
  done
  echo "Expected customer category $expected but got: $response" >&2
  return 1
}

poll_engineer_category() {
  local trace_id="$1" question="$2" action="$3" expected="$4" require_history="${5:-0}"
  local response="" category="" history_count=0
  for attempt in {1..30}; do
    response=$(engineer_for_trace "$trace_id" "$question" "$action" || true)
    read -r category history_count <<< "$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin); root=data.get("root_cause") or {}
    history=sum(1 for item in data.get("evidence", []) if item.get("type") == "history")
    print(root.get("category", ""), history)
except Exception: print("", 0)' <<< "$response")"
    if [[ "$category" == "$expected" && "$history_count" -ge "$require_history" ]]; then
      printf '%s' "$response"; return 0
    fi
    sleep 2
  done
  echo "Expected engineer category $expected but got: $response" >&2
  return 1
}

assert_graph_path() {
  local graph_json="$1" expected_root="$2" expected_kind="$3" require_history="${4:-0}"
  python3 -c '
import json, sys
expected_root, expected_kind, require_history = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = json.load(sys.stdin)
root = data.get("root_cause") or {}
if root.get("category") != expected_root:
    raise SystemExit(f"unexpected root cause: {root}")
nodes = data.get("nodes") or []
edges = data.get("edges") or []
root_id = data.get("root_cause_node_id")
by_id = {n.get("id"): n for n in nodes}
if not root_id or by_id.get(root_id, {}).get("kind") != "root_cause":
    raise SystemExit("invalid root_cause_node_id")
evidence_ids = {n.get("id") for n in nodes if n.get("kind") == expected_kind}
if not evidence_ids:
    raise SystemExit(f"missing {expected_kind} node")
if not any(e.get("source") in evidence_ids and e.get("target") == root_id and e.get("relation") in {"supports", "diagnoses"} for e in edges):
    raise SystemExit(f"missing {expected_kind} -> root cause edge")
history_ids = {n.get("id") for n in nodes if n.get("kind") == "history"}
if len(history_ids) < require_history:
    raise SystemExit(f"expected >= {require_history} history nodes, got {len(history_ids)}")
if require_history and not any(e.get("source") in history_ids and e.get("target") == root_id and e.get("relation") == "similar_to" for e in edges):
    raise SystemExit("missing history -> root cause edge")
' "$expected_root" "$expected_kind" "$require_history" <<< "$graph_json"
}

assert_generic_customer_error() {
  if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres|connectexception|resourceaccessexception|cannotgetjdbc|hikari|hikaricp|127\.0\.0\.1|65530' <<< "$1"; then
    echo "Customer application response leaked diagnostic details: $1" >&2; exit 1
  fi
}

assert_safe_support_response() {
  if grep -qiE 'uk_user_phone|duplicatekey|postgres|jdbc|trace[_-]?id|evidence|engineer_answer|similar incident|incident-memory|connectexception|resourceaccessexception|cannotgetjdbc|hikari|hikaricp|prometheus|db_pool_|active peak|pending peak|pg_sleep|database select|trace duration|database contribution|dominant database|[0-9]+ ms|127\.0\.0\.1|65530|root_cause_node_id|\"nodes\"|\"edges\"' <<< "$1"; then
    echo "Customer support response leaked technical/timing/metric/graph details: $1" >&2; exit 1
  fi
}

echo "[1/33] Starting project-scoped ProdMind stack with Prometheus..."
docker compose up -d --build
wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90
wait_http "http://localhost:8090/actuator/prometheus" 30
wait_http "http://localhost:9090/-/ready" 60
wait_http "http://localhost:8088/engineer" 30
wait_prometheus_pool_metric

echo "[2/33] Prometheus is scraping project/service-scoped Hikari metrics."

first_trace=$(new_trace_id)
echo "[3/33] Triggering project=demo duplicate-data incident..."
first_create=$(trigger_duplicate "$first_trace"); assert_generic_customer_error "$first_create"

echo "[4/33] Diagnosing with the matching project scope..."
first_support=$(poll_customer_category "$first_trace" "Why did creating the user fail?" "create-user" "duplicate_data")
assert_safe_support_response "$first_support"

echo "[5/33] Verifying the same trace cannot be read as another project..."
wrong_code=$(curl -sS -o /tmp/wrong-project.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/support/trace" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: another-project" \
  -d "{\"trace_id\":\"$first_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$wrong_code" == "404" ]] || { echo "Cross-project trace access returned HTTP $wrong_code" >&2; cat /tmp/wrong-project.json >&2; exit 1; }

echo "[6/33] Verifying engineer evidence is unavailable without authentication..."
unauth_code=$(curl -sS -o /tmp/unauth-engineer.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/investigate/trace" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: $PROJECT_ID" \
  -d "{\"trace_id\":\"$first_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$unauth_code" == "401" ]] || { echo "Unauthenticated engineer API returned HTTP $unauth_code" >&2; cat /tmp/unauth-engineer.json >&2; exit 1; }

echo "[7/33] Verifying Evidence Graph is also unavailable without engineer authentication..."
unauth_graph_code=$(curl -sS -o /tmp/unauth-graph.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/investigate/trace/graph" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: $PROJECT_ID" \
  -d "{\"trace_id\":\"$first_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$unauth_graph_code" == "401" ]] || { echo "Unauthenticated graph API returned HTTP $unauth_graph_code" >&2; cat /tmp/unauth-graph.json >&2; exit 1; }

second_trace=$(new_trace_id)
echo "[8/33] Triggering duplicate-data incident #2..."
second_create=$(trigger_duplicate "$second_trace"); assert_generic_customer_error "$second_create"

echo "[9/33] Verifying authenticated engineer RCA + same-project Incident Memory..."
second_engineer=$(poll_engineer_category "$second_trace" "Why did creating the user fail?" "create-user" "database_unique_violation" 1)
second_support=$(poll_customer_category "$second_trace" "Why did creating the user fail?" "create-user" "duplicate_data")
assert_safe_support_response "$second_support"

echo "[10/33] Building the database Evidence Graph from the real trace..."
database_graph=$(graph_for_trace "$second_trace" "Why did creating the user fail?" "create-user")
assert_graph_path "$database_graph" "database_unique_violation" "database" 1

echo "[11/33] Verifying graph trace scope cannot cross projects..."
wrong_graph_code=$(curl -sS -o /tmp/wrong-project-graph.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/investigate/trace/graph" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: another-project" \
  -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
  -d "{\"trace_id\":\"$second_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$wrong_graph_code" == "404" ]] || { echo "Cross-project graph access returned HTTP $wrong_graph_code" >&2; cat /tmp/wrong-project-graph.json >&2; exit 1; }

downstream_trace=$(new_trace_id)
echo "[12/33] Triggering downstream dependency outage..."
downstream_create=$(trigger_downstream_outage "$downstream_trace"); assert_generic_customer_error "$downstream_create"

echo "[13/33] Diagnosing downstream outage through customer-safe API..."
downstream_support=$(poll_customer_category "$downstream_trace" "Why did payment fail?" "charge-payment" "service_unavailable")
assert_safe_support_response "$downstream_support"

echo "[14/33] Verifying authenticated downstream engineer evidence..."
downstream_engineer=$(poll_engineer_category "$downstream_trace" "Why did payment fail?" "charge-payment" "downstream_unavailable" 0)
has_dependency=$(python3 -c 'import json,sys
try: print(1 if any(x.get("type") == "dependency" for x in json.load(sys.stdin).get("evidence", [])) else 0)
except Exception: print(0)' <<< "$downstream_engineer")
[[ "$has_dependency" == "1" ]] || { echo "Missing dependency evidence" >&2; exit 1; }

echo "[15/33] Building the downstream Evidence Graph from the real trace..."
downstream_graph=$(graph_for_trace "$downstream_trace" "Why did payment fail?" "charge-payment")
assert_graph_path "$downstream_graph" "downstream_unavailable" "dependency" 0

echo "[16/33] Starting two real requests that hold the entire Hikari pool..."
start_pool_holders
sleep 3

pool_trace=$(new_trace_id)
echo "[17/33] Triggering a third DB operation while all pool connections are occupied..."
pool_create=$(trigger_pool_probe "$pool_trace"); assert_generic_customer_error "$pool_create"

echo "[18/33] Diagnosing pool exhaustion through the customer-safe API..."
pool_support=$(poll_customer_category "$pool_trace" "Why was the database operation unable to run?" "probe-database-pool" "service_busy")
assert_safe_support_response "$pool_support"

echo "[19/33] Verifying engineer RCA contains Prometheus metric evidence..."
pool_engineer=$(poll_engineer_category "$pool_trace" "Why was the database operation unable to run?" "probe-database-pool" "database_pool_exhausted" 0)
pool_metric_count=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    print(sum(1 for x in data.get("evidence", []) if x.get("type") == "metric" and x.get("source") == "prometheus"))
except Exception:
    print(0)' <<< "$pool_engineer")
[[ "$pool_metric_count" -ge 3 ]] || { echo "Pool RCA did not include the expected Prometheus metric evidence" >&2; echo "$pool_engineer" >&2; exit 1; }

echo "[20/33] Building the pool-exhaustion Evidence Graph..."
pool_graph=$(graph_for_trace "$pool_trace" "Why was the database operation unable to run?" "probe-database-pool")
assert_graph_path "$pool_graph" "database_pool_exhausted" "metric" 0

wait "$HOLDER_PID_1" "$HOLDER_PID_2" || true

slow_trace=$(new_trace_id)
echo "[21/33] Triggering a successful request with a deliberately slow PostgreSQL operation..."
slow_code=$(trigger_slow_report "$slow_trace")
[[ "$slow_code" == "200" ]] || { echo "Slow report should succeed with HTTP 200, got $slow_code" >&2; cat /tmp/slow-report.json >&2; exit 1; }

echo "[22/33] Confirming the slow customer operation really succeeded..."
grep -q 'Report generated' /tmp/slow-report.json || { echo "Unexpected slow report response" >&2; cat /tmp/slow-report.json >&2; exit 1; }

echo "[23/33] Asking ProdMind why the successful operation was slow..."
slow_support=$(poll_customer_category "$slow_trace" "Why was my report so slow?" "generate-report" "slow_operation")
assert_safe_support_response "$slow_support"

echo "[24/33] Verifying engineer RCA identifies a dominant database span without an exception..."
slow_engineer=$(poll_engineer_category "$slow_trace" "Why was my report so slow?" "generate-report" "slow_database_query" 0)
slow_db_evidence=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    print(1 if any(x.get("type") == "database" and "Dominant database span" in x.get("summary", "") for x in data.get("evidence", [])) else 0)
except Exception:
    print(0)' <<< "$slow_engineer")
[[ "$slow_db_evidence" == "1" ]] || { echo "Slow operation lacks dominant database evidence" >&2; echo "$slow_engineer" >&2; exit 1; }

echo "[25/33] Confirming the successful latency diagnosis contains no exception dependency..."
slow_exception_count=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    print(sum(1 for x in data.get("evidence", []) if x.get("type") == "exception"))
except Exception:
    print(99)' <<< "$slow_engineer")
[[ "$slow_exception_count" == "0" ]] || { echo "Slow HTTP-200 scenario unexpectedly depends on exception evidence" >&2; exit 1; }

echo "[26/33] Building the successful slow-operation Evidence Graph..."
slow_graph=$(graph_for_trace "$slow_trace" "Why was my report so slow?" "generate-report")
assert_graph_path "$slow_graph" "slow_database_query" "database" 0

echo "[27/33] Verifying a normalized database operation node is visible to engineers..."
slow_operation_nodes=$(python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
    print(sum(1 for n in data.get("nodes", []) if n.get("kind") == "operation" and n.get("label", "").startswith("database ")))
except Exception:
    print(0)' <<< "$slow_graph")
[[ "$slow_operation_nodes" -ge 1 ]] || { echo "Evidence Graph lacks a normalized database operation node" >&2; echo "$slow_graph" >&2; exit 1; }

echo "[28/33] Database uniqueness RCA + Incident Memory remain green."
echo "[29/33] Downstream dependency RCA remains green."
echo "[30/33] Prometheus-backed database pool RCA remains green."
echo "[31/33] HTTP-200 slow database RCA succeeded from real trace timing."
echo "[32/33] Project scope, engineer auth and customer-safe boundaries remain green."
echo "[33/33] Four-class production-style E2E succeeded."

printf '\nDatabase graph summary:\n'
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root": (d.get("root_cause") or {}).get("category"), "nodes": len(d.get("nodes", [])), "edges": len(d.get("edges", [])), "history": sum(1 for n in d.get("nodes", []) if n.get("kind") == "history")})' <<< "$database_graph"
printf '\nDownstream graph summary:\n'
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root": (d.get("root_cause") or {}).get("category"), "nodes": len(d.get("nodes", [])), "edges": len(d.get("edges", []))})' <<< "$downstream_graph"
printf '\nPool graph summary:\n'
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root": (d.get("root_cause") or {}).get("category"), "nodes": len(d.get("nodes", [])), "edges": len(d.get("edges", [])), "metric_nodes": sum(1 for n in d.get("nodes", []) if n.get("kind") == "metric")})' <<< "$pool_graph"
printf '\nSlow-success graph summary:\n'
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root": (d.get("root_cause") or {}).get("category"), "nodes": len(d.get("nodes", [])), "edges": len(d.get("edges", [])), "operation_nodes": sum(1 for n in d.get("nodes", []) if n.get("kind") == "operation")})' <<< "$slow_graph"
