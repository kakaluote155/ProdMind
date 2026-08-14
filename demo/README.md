# ProdMind Demo

The demo contains reproducible production-style incidents so contributors can test ProdMind without connecting it to a real customer system.

All demo telemetry is scoped to project `demo`:

```text
OTel resource attribute: prodmind.project.id=demo
OTel service version:     service.version=demo-v2
API header:               X-ProdMind-Project: demo
Prometheus label:         prodmind_project="demo"
```

ProdMind verifies project scope before using traces, metrics, Incident Memory or Change Events.

## Run

```bash
bash scripts/demo-up.sh
```

On Windows PowerShell:

```powershell
.\scripts\demo-up.ps1
```

The launcher builds in the background and waits for ProdMind, the customer demo
and Prometheus to become ready. Use `--no-build` (`-NoBuild` on PowerShell) when
images are already current.

The README animation is captured from this real customer page with
`scripts/capture-readme-demo.cjs` and assembled with
`scripts/build-demo-gif.py`. The capture script rejects known engineer-only
identifiers before writing frames.

Open:

```text
http://localhost:8090
```

The main page exposes four real scenarios: three failures and one
successful-but-slow database operation. A focused multi-service page additionally
proves a successful request whose latency is dominated by a downstream service:

```text
http://localhost:8090/multiservice.html
```

Stop while preserving data with `bash scripts/demo-down.sh`, or reset all local
demo volumes with `bash scripts/demo-down.sh --volumes`. PowerShell equivalents
are `.\scripts\demo-down.ps1` and `.\scripts\demo-down.ps1 -Volumes`.

## Shared investigation pipeline

```text
User action
   ↓
W3C traceparent
   ↓
Real application behavior
   ↓
OpenTelemetry + application metrics
   ↓
Tempo / Loki / Prometheus
   ↓
Project-scope validation
   ↓
Normalized evidence
   ↓
Pluggable RCA rules
   ↓
Customer-safe answer / authenticated engineer Evidence Graph
   ↓
Incident Memory + recent Change Context
```

## Scenario A — duplicate user

Phone `13800000000` is pre-seeded in PostgreSQL.

```text
POST /api/users → PostgreSQL unique violation
```

Engineer: `database_unique_violation`

Customer: `duplicate_data`

Triggering this twice also proves Incident Memory: current telemetry must independently diagnose the second failure before same-project history is attached.

## Scenario B — unavailable downstream service

```text
POST /api/payments/charge
        ↓
connection refused
```

Engineer: `downstream_unavailable`

Customer: `service_unavailable`

## Scenario C — database pool exhausted

The demo configures HikariCP with only two connections and a 2.5-second acquisition timeout.

Clicking **Exhaust DB pool and probe** starts two requests that each hold a real PostgreSQL connection. A third traced request then tries:

```text
POST /api/pool/probe
        ↓
Hikari pool: 2 active / 2 max
        ↓
waiter appears while pool is saturated
        ↓
connection acquisition timeout
```

Prometheus scrapes Micrometer every second. ProdMind queries recent project/service-scoped peaks for Hikari active, max and pending connections, then normalizes them into vendor-neutral metric facts.

The rule deliberately does **not** diagnose pool exhaustion from the timeout exception alone. It requires saturation evidence.

Engineer: `database_pool_exhausted`

Customer: `service_busy`

## Scenario D — successful but slow report

This scenario proves that ProdMind is not limited to exceptions or HTTP 5xx responses.

Click **Generate slow report**. The endpoint performs a deliberately slow PostgreSQL operation, then returns:

```text
HTTP 200
{"message":"Report generated","rows":42}
```

OpenTelemetry captures both the request span and the JDBC/database span. ProdMind normalizes their timing without copying raw SQL or span IDs into the RCA input.

The performance rule requires:

```text
request is not HTTP 5xx
trace duration >= 1.5s
dominant DB span >= 1s
dominant DB span >= 70% of trace duration
```

Engineer: `slow_database_query`

Customer: `slow_operation`

## Deployment / Change Awareness

The demo service exports:

```text
service.version=demo-v2
```

Trusted delivery tooling can record a compact change event before an incident:

```bash
curl -X POST http://localhost:8088/api/v1/changes \
  -H 'Content-Type: application/json' \
  -H 'X-ProdMind-Project: demo' \
  -H 'X-ProdMind-Engineer-Key: demo-engineer-key' \
  -d '{
    "service_name":"demo-user-service",
    "version":"demo-v2",
    "revision":"abc123",
    "change_type":"deployment",
    "summary":"Deploy demo-v2",
    "actor":"ci",
    "source":"github-actions"
  }'
```

When a later trace is independently diagnosed, ProdMind can attach a recent same-project/same-service change as engineer context. An exact `service.version` match is prioritized.

The semantics are intentionally non-causal:

```text
Deployment demo-v2 ──context_for──▶ demo-user-service
```

The change does **not** replace the real RCA and does not create a synthetic `deployment_regression` category merely because it happened nearby in time.

The dedicated `change-awareness-e2e` CI job proves:

- authenticated change ingestion
- exact version matching
- cross-project change isolation
- customer-side change redaction
- `context_for` graph semantics
- the original root cause remains unchanged

## Application error boundary

The three failed customer operations return only:

```json
{"message":"Operation failed"}
```

The slow-report scenario is different on purpose: it returns HTTP 200 and still remains diagnosable from its trace.

## Customer API

Customer support requests include:

```http
X-ProdMind-Project: demo
```

A trace belonging to another project, a trace with missing project scope, or a mismatched project header is rejected with the same generic not-found response.

Customer responses omit Trace IDs, span IDs, raw SQL, raw logs, stack traces, database constraint names, internal IPs/ports, raw timing evidence, Prometheus metrics, deployment/change metadata, Incident Memory evidence, graph data and engineer remediation details.

## Engineer API

Technical investigation, graph and change-ingestion endpoints additionally require:

```http
X-ProdMind-Project: demo
X-ProdMind-Engineer-Key: demo-engineer-key
```

The demo key exists only for local Compose usage. Replace `PRODMIND_ENGINEER_API_KEY` before any real deployment.

## Useful endpoints

- Customer demo: `http://localhost:8090`
- Engineer graph viewer: `http://localhost:8088/engineer`
- ProdMind API docs: `http://localhost:8088/docs`
- Change ingestion API: `POST http://localhost:8088/api/v1/changes`
- Customer-safe API: `POST http://localhost:8088/api/v1/support/trace`
- Engineer API: `POST http://localhost:8088/api/v1/investigate/trace`
- Engineer graph API: `POST http://localhost:8088/api/v1/investigate/trace/graph`
- Spring metrics: `http://localhost:8090/actuator/prometheus`
- Prometheus: `http://localhost:9090`
- Tempo: `http://localhost:3200`
- Loki: `http://localhost:3100`

## Next scenarios

- Redis unavailable
- retry storms / cascading saturation
- GitHub/GitLab/Argo deployment adapters
- Kubernetes rollout/configuration correlation
- multi-hop and parallel distributed critical paths
