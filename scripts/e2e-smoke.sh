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
  if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres|connectexception|resourceaccessexception|127\.0\.0\.1|65530' <<< "$1"; then
    echo "Customer application response leaked diagnostic details: $1" >&2; exit 1
  fi
}

assert_safe_support_response() {
  if grep -qiE 'uk_user_phone|duplicatekey|postgres|jdbc|trace[_-]?id|evidence|engineer_answer|similar incident|incident-memory|connectexception|resourceaccessexception|127\.0\.0\.1|65530|root_cause_node_id|\"nodes\"|\"edges\"' <<< "$1"; then
    echo "Customer support response leaked technical/graph details: $1" >&2; exit 1
  fi
}

echo "[1/19] Starting project-scoped ProdMind stack..."
docker compose up -d --build
wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90
wait_http "http://localhost:8088/engineer" 30

first_trace=$(new_trace_id)
echo "[2/19] Triggering project=demo duplicate-data incident..."
first_create=$(trigger_duplicate "$first_trace"); assert_generic_customer_error "$first_create"

echo "[3/19] Diagnosing with the matching project scope..."
first_support=$(poll_customer_category "$first_trace" "Why did creating the user fail?" "create-user" "duplicate_data")
assert_safe_support_response "$first_support"

echo "[4/19] Verifying the same trace cannot be read as another project..."
wrong_code=$(curl -sS -o /tmp/wrong-project.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/support/trace" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: another-project" \
  -d "{\"trace_id\":\"$first_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$wrong_code" == "404" ]] || { echo "Cross-project trace access returned HTTP $wrong_code" >&2; cat /tmp/wrong-project.json >&2; exit 1; }

echo "[5/19] Verifying engineer evidence is not available without authentication..."
unauth_code=$(curl -sS -o /tmp/unauth-engineer.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/investigate/trace" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: $PROJECT_ID" \
  -d "{\"trace_id\":\"$first_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$unauth_code" == "401" ]] || { echo "Unauthenticated engineer API returned HTTP $unauth_code" >&2; cat /tmp/unauth-engineer.json >&2; exit 1; }

echo "[6/19] Verifying Evidence Graph is also unavailable without engineer authentication..."
unauth_graph_code=$(curl -sS -o /tmp/unauth-graph.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/investigate/trace/graph" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: $PROJECT_ID" \
  -d "{\"trace_id\":\"$first_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$unauth_graph_code" == "401" ]] || { echo "Unauthenticated graph API returned HTTP $unauth_graph_code" >&2; cat /tmp/unauth-graph.json >&2; exit 1; }

second_trace=$(new_trace_id)
echo "[7/19] Triggering duplicate-data incident #2..."
second_create=$(trigger_duplicate "$second_trace"); assert_generic_customer_error "$second_create"

echo "[8/19] Verifying authenticated engineer RCA + same-project Incident Memory..."
second_engineer=$(poll_engineer_category "$second_trace" "Why did creating the user fail?" "create-user" "database_unique_violation" 1)
second_support=$(poll_customer_category "$second_trace" "Why did creating the user fail?" "create-user" "duplicate_data")
assert_safe_support_response "$second_support"

echo "[9/19] Building the database Evidence Graph from the real trace..."
database_graph=$(graph_for_trace "$second_trace" "Why did creating the user fail?" "create-user")
assert_graph_path "$database_graph" "database_unique_violation" "database" 1

echo "[10/19] Verifying graph trace scope cannot cross projects..."
wrong_graph_code=$(curl -sS -o /tmp/wrong-project-graph.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/investigate/trace/graph" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: another-project" \
  -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
  -d "{\"trace_id\":\"$second_trace\",\"question\":\"Why?\",\"action\":\"create-user\"}")
[[ "$wrong_graph_code" == "404" ]] || { echo "Cross-project graph access returned HTTP $wrong_graph_code" >&2; cat /tmp/wrong-project-graph.json >&2; exit 1; }

downstream_trace=$(new_trace_id)
echo "[11/19] Triggering downstream dependency outage..."
downstream_create=$(trigger_downstream_outage "$downstream_trace"); assert_generic_customer_error "$downstream_create"

echo "[12/19] Diagnosing downstream outage through customer-safe API..."
downstream_support=$(poll_customer_category "$downstream_trace" "Why did payment fail?" "charge-payment" "service_unavailable")
assert_safe_support_response "$downstream_support"

echo "[13/19] Verifying authenticated downstream engineer evidence..."
downstream_engineer=$(poll_engineer_category "$downstream_trace" "Why did payment fail?" "charge-payment" "downstream_unavailable" 0)
has_dependency=$(python3 -c 'import json,sys
try: print(1 if any(x.get("type") == "dependency" for x in json.load(sys.stdin).get("evidence", [])) else 0)
except Exception: print(0)' <<< "$downstream_engineer")
[[ "$has_dependency" == "1" ]] || { echo "Missing dependency evidence" >&2; exit 1; }

echo "[14/19] Building the downstream Evidence Graph from the real trace..."
downstream_graph=$(graph_for_trace "$downstream_trace" "Why did payment fail?" "charge-payment")
assert_graph_path "$downstream_graph" "downstream_unavailable" "dependency" 0

echo "[15/19] Database graph contains root-cause + historical support."
echo "[16/19] Dependency graph explains a second unrelated failure class."
echo "[17/19] Trace project scope and engineer authentication protect graph data."
echo "[18/19] Customer-safe API contains no graph/evidence payload."
echo "[19/19] Secure multi-rule + Incident Memory + Evidence Graph E2E succeeded."

printf '\nDatabase graph summary:\n'
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root": (d.get("root_cause") or {}).get("category"), "nodes": len(d.get("nodes", [])), "edges": len(d.get("edges", [])), "history": sum(1 for n in d.get("nodes", []) if n.get("kind") == "history")})' <<< "$database_graph"
printf '\nDownstream graph summary:\n'
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root": (d.get("root_cause") or {}).get("category"), "nodes": len(d.get("nodes", [])), "edges": len(d.get("edges", []))})' <<< "$downstream_graph"
