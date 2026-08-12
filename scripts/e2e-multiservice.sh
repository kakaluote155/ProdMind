#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="demo"
ENGINEER_KEY="demo-engineer-key"

cleanup() {
  docker compose logs --no-color > /tmp/prodmind-multiservice-e2e.log 2>&1 || true
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

support_for_trace() {
  local trace_id="$1" project_id="${2:-$PROJECT_ID}"
  curl -sS -X POST "http://localhost:8088/api/v1/support/trace" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $project_id" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why was this journey so slow?\",\"action\":\"slow-journey\",\"page\":\"/\"}"
}

engineer_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $PROJECT_ID" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why was this journey so slow?\",\"action\":\"slow-journey\",\"page\":\"/\"}"
}

graph_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace/graph" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $PROJECT_ID" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why was this journey so slow?\",\"action\":\"slow-journey\",\"page\":\"/\"}"
}

echo "[1/11] Starting the two-service ProdMind stack..."
docker compose up -d --build
wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90
wait_http "http://localhost:8091/actuator/health" 90

echo "[2/11] Triggering a real HTTP-200 cross-service operation..."
trace_id=$(new_trace_id)
journey_code=$(curl -sS -o /tmp/slow-journey.json -w '%{http_code}' -X POST \
  "http://localhost:8090/api/journey/slow" \
  -H "traceparent: $(traceparent_for "$trace_id")")
[[ "$journey_code" == "200" ]] || {
  echo "Slow journey should return HTTP 200, got $journey_code" >&2
  cat /tmp/slow-journey.json >&2
  exit 1
}
grep -q 'Journey completed' /tmp/slow-journey.json || {
  echo "Unexpected slow-journey response" >&2
  cat /tmp/slow-journey.json >&2
  exit 1
}

echo "[3/11] Waiting for customer-safe slow-operation diagnosis..."
support=""
for attempt in {1..30}; do
  support=$(support_for_trace "$trace_id" || true)
  category=$(python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("category", ""))
except Exception: print("")' <<< "$support")
  [[ "$category" == "slow_operation" ]] && break
  sleep 2
done
[[ "${category:-}" == "slow_operation" ]] || {
  echo "Customer API did not diagnose the slow journey" >&2
  echo "$support" >&2
  exit 1
}

if grep -qiE 'demo-slow-service|demo-user-service|/api/dependency/slow|critical downstream|cross-service|trace[_-]?id|span[_-]?id|[0-9]+ ms|\"evidence\"|\"nodes\"|\"edges\"' <<< "$support"; then
  echo "Customer-safe response leaked distributed-trace internals: $support" >&2
  exit 1
fi

echo "[4/11] Verifying the same distributed trace cannot cross project boundaries..."
wrong_code=$(curl -sS -o /tmp/wrong-project-multiservice.json -w '%{http_code}' -X POST \
  "http://localhost:8088/api/v1/support/trace" \
  -H "Content-Type: application/json" \
  -H "X-ProdMind-Project: another-project" \
  -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why slow?\",\"action\":\"slow-journey\"}")
[[ "$wrong_code" == "404" ]] || {
  echo "Cross-project multi-service trace access returned HTTP $wrong_code" >&2
  cat /tmp/wrong-project-multiservice.json >&2
  exit 1
}

echo "[5/11] Verifying engineer RCA identifies the critical downstream hop..."
engineer=""
for attempt in {1..30}; do
  engineer=$(engineer_for_trace "$trace_id" || true)
  read -r root dependency_count exception_count <<< "$(python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); r=d.get("root_cause") or {}; ev=d.get("evidence",[])
    dep=sum(1 for x in ev if x.get("type")=="dependency" and "Critical downstream hop" in x.get("summary",""))
    exc=sum(1 for x in ev if x.get("type")=="exception")
    print(r.get("category",""), dep, exc)
except Exception: print("",0,99)' <<< "$engineer")"
  if [[ "$root" == "slow_downstream_service" && "$dependency_count" -ge 1 && "$exception_count" == "0" ]]; then
    break
  fi
  sleep 2
done
[[ "${root:-}" == "slow_downstream_service" && "$dependency_count" -ge 1 && "$exception_count" == "0" ]] || {
  echo "Engineer RCA did not identify the slow downstream service" >&2
  echo "$engineer" >&2
  exit 1
}

if grep -q 'slow_database_query' <<< "$engineer"; then
  echo "Cross-service latency was incorrectly classified as a local slow database query" >&2
  exit 1
fi
if grep -qE 'spanId|parentSpanId|span_id|parent_span_id' <<< "$engineer"; then
  echo "Raw span identifiers leaked from normalized investigation output" >&2
  exit 1
fi

echo "[6/11] Verifying the distributed trace includes both service versions..."
grep -q 'demo-user-service=demo-v2' <<< "$engineer" || {
  echo "Main service version missing from engineer evidence" >&2
  exit 1
}
grep -q 'demo-slow-service=slow-v1' <<< "$engineer" || {
  echo "Slow service version missing from engineer evidence" >&2
  exit 1
}

echo "[7/11] Building the Evidence Graph for the critical path..."
graph=$(graph_for_trace "$trace_id")
python3 -c '
import json,sys
d=json.load(sys.stdin)
root=d.get("root_cause") or {}
if root.get("category") != "slow_downstream_service":
    raise SystemExit(f"unexpected graph root: {root}")
root_id=d.get("root_cause_node_id")
nodes=d.get("nodes") or []; edges=d.get("edges") or []
deps={n.get("id") for n in nodes if n.get("kind")=="dependency" and "demo-slow-service" in n.get("label","")}
if not deps:
    raise SystemExit("graph lacks the critical downstream dependency node")
if not any(e.get("source") in deps and e.get("target")==root_id and e.get("relation") in {"supports","diagnoses"} for e in edges):
    raise SystemExit("critical dependency does not support the graph root cause")
' <<< "$graph"

echo "[8/11] Confirming current RCA is based on trace evidence, not Change Awareness..."
change_count=$(python3 -c 'import json,sys
try: print(sum(1 for x in json.load(sys.stdin).get("evidence",[]) if x.get("type")=="change"))
except Exception: print(99)' <<< "$engineer")
[[ "$change_count" == "0" ]] || {
  echo "Unexpected change evidence exists in an unseeded multi-service test" >&2
  exit 1
}

echo "[9/11] Raw span IDs were discarded before normalized RCA."
echo "[10/11] Project isolation and customer-safe boundaries held across both services."
echo "[11/11] Multi-service critical-path E2E succeeded."
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root":(d.get("root_cause") or {}).get("category"),"dependency_nodes":sum(1 for n in d.get("nodes",[]) if n.get("kind")=="dependency"),"services":sum(1 for n in d.get("nodes",[]) if n.get("kind")=="service")})' <<< "$graph"
