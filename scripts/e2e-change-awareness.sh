#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="demo"
ENGINEER_KEY="demo-engineer-key"
CHANGE_SENTINEL="deploy-demo-v2-change-e2e"
CROSS_PROJECT_SENTINEL="cross-project-change-must-not-leak"

cleanup() {
  docker compose logs --no-color > /tmp/prodmind-change-e2e.log 2>&1 || true
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

record_change() {
  local project_id="$1" summary="$2"
  curl -sS -w '\n%{http_code}' -X POST "http://localhost:8088/api/v1/changes" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $project_id" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"service_name\":\"demo-user-service\",\"version\":\"demo-v2\",\"revision\":\"change-e2e-sha\",\"change_type\":\"deployment\",\"summary\":\"$summary\",\"actor\":\"github-actions\",\"source\":\"change-e2e\"}"
}

support_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/support/trace" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $PROJECT_ID" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}"
}

engineer_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $PROJECT_ID" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}"
}

graph_for_trace() {
  local trace_id="$1"
  curl -sS -X POST "http://localhost:8088/api/v1/investigate/trace/graph" \
    -H "Content-Type: application/json" \
    -H "X-ProdMind-Project: $PROJECT_ID" \
    -H "X-ProdMind-Engineer-Key: $ENGINEER_KEY" \
    -d "{\"trace_id\":\"$trace_id\",\"question\":\"Why did creating the user fail?\",\"action\":\"create-user\",\"page\":\"/\"}"
}

echo "[1/10] Starting ProdMind stack..."
docker compose up -d --build
wait_http "http://localhost:8088/health" 90
wait_http "http://localhost:8090/actuator/health" 90

echo "[2/10] Recording an authenticated deployment event for project=demo / demo-v2..."
change_raw=$(record_change "$PROJECT_ID" "$CHANGE_SENTINEL")
change_code=$(tail -n1 <<< "$change_raw")
change_body=$(sed '$d' <<< "$change_raw")
[[ "$change_code" == "201" ]] || { echo "Change ingestion failed with HTTP $change_code" >&2; echo "$change_body" >&2; exit 1; }
change_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))' <<< "$change_body")
[[ "$change_id" == CHG-* ]] || { echo "Unexpected change ID: $change_id" >&2; exit 1; }

echo "[3/10] Recording a same-service change in another project as an isolation sentinel..."
cross_raw=$(record_change "another-project" "$CROSS_PROJECT_SENTINEL")
cross_code=$(tail -n1 <<< "$cross_raw")
[[ "$cross_code" == "201" ]] || { echo "Cross-project sentinel ingestion failed" >&2; exit 1; }

echo "[4/10] Triggering a real duplicate-user failure on service.version=demo-v2..."
trace_id=$(new_trace_id)
app_response=$(curl -sS -X POST "http://localhost:8090/api/users" \
  -H "Content-Type: application/json" \
  -H "traceparent: $(traceparent_for "$trace_id")" \
  -d '{"name":"Change E2E","phone":"13800000000"}')
if grep -qiE 'trace[_-]?id|uk_user_phone|duplicatekey|postgres|demo-v2|deployment' <<< "$app_response"; then
  echo "Customer application response leaked internal details: $app_response" >&2
  exit 1
fi

echo "[5/10] Waiting for customer-safe RCA while ensuring change metadata stays hidden..."
support=""
for attempt in {1..30}; do
  support=$(support_for_trace "$trace_id" || true)
  category=$(python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("category", ""))
except Exception: print("")' <<< "$support")
  [[ "$category" == "duplicate_data" ]] && break
  sleep 2
done
[[ "${category:-}" == "duplicate_data" ]] || { echo "Customer RCA did not diagnose duplicate data" >&2; echo "$support" >&2; exit 1; }
if grep -qiE "$CHANGE_SENTINEL|$CROSS_PROJECT_SENTINEL|demo-v2|change-store|deployment|\"change\"|\"evidence\"" <<< "$support"; then
  echo "Customer-safe response leaked change evidence: $support" >&2
  exit 1
fi

echo "[6/10] Verifying engineer RCA contains only the matching project/version change..."
engineer=""
for attempt in {1..30}; do
  engineer=$(engineer_for_trace "$trace_id" || true)
  read -r root change_count version_match <<< "$(python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); r=d.get("root_cause") or {}; changes=[x for x in d.get("evidence",[]) if x.get("type")=="change"]
    print(r.get("category",""), len(changes), 1 if any("trace version matches this change" in x.get("summary","") for x in changes) else 0)
except Exception: print("",0,0)' <<< "$engineer")"
  if [[ "$root" == "database_unique_violation" && "$change_count" -ge 1 && "$version_match" == "1" ]]; then break; fi
  sleep 2
done
[[ "${root:-}" == "database_unique_violation" && "$change_count" -ge 1 && "$version_match" == "1" ]] || {
  echo "Engineer investigation did not attach matching deployment context" >&2; echo "$engineer" >&2; exit 1;
}
grep -q "$CHANGE_SENTINEL" <<< "$engineer" || { echo "Expected project change is missing" >&2; exit 1; }
if grep -q "$CROSS_PROJECT_SENTINEL" <<< "$engineer"; then
  echo "Cross-project change leaked into engineer investigation" >&2
  exit 1
fi

echo "[7/10] Verifying the RCA itself was not relabeled as a deployment regression..."
if grep -q 'deployment_regression' <<< "$engineer"; then
  echo "Change proximity was incorrectly promoted to a root cause" >&2
  exit 1
fi

echo "[8/10] Building the engineer Evidence Graph..."
graph=$(graph_for_trace "$trace_id")
python3 -c '
import json,sys
d=json.load(sys.stdin)
nodes=d.get("nodes") or []; edges=d.get("edges") or []
changes={n.get("id") for n in nodes if n.get("kind")=="change"}
services={n.get("id") for n in nodes if n.get("kind")=="service"}
if not changes: raise SystemExit("graph has no change node")
if not any(e.get("source") in changes and e.get("target") in services and e.get("relation")=="context_for" for e in edges):
    raise SystemExit("change node is not context_for service")
if any(e.get("source") in changes and e.get("relation") in {"supports","diagnoses"} for e in edges):
    raise SystemExit("change node was given a causal/supporting RCA edge")
' <<< "$graph"

echo "[9/10] Project isolation and non-causal change semantics held."
echo "[10/10] Deployment/change awareness E2E succeeded."
python3 -c 'import json,sys; d=json.load(sys.stdin); print({"root":(d.get("root_cause") or {}).get("category"),"change_nodes":sum(1 for n in d.get("nodes",[]) if n.get("kind")=="change"),"context_edges":sum(1 for e in d.get("edges",[]) if e.get("relation")=="context_for")})' <<< "$graph"
