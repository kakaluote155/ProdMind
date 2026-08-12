# ProdMind Demo

The demo contains reproducible production-style incidents so contributors can test ProdMind without connecting it to a real customer system.

All demo telemetry is scoped to project `demo`:

```text
OTel resource attribute: prodmind.project.id=demo
API header:              X-ProdMind-Project: demo
Prometheus label:        prodmind_project="demo"
```

ProdMind verifies project scope before using traces, metrics or Incident Memory.

## Run

```bash
docker compose up --build
```

Open:

```text
http://localhost:8090
```

The page exposes four real scenarios: three failures and one successful-but-slow operation.

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
Project-scoped Incident Memory
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

Only then does it assign:

Engineer: `slow_database_query`

Customer: `slow_operation`

The engineer response includes the safe normalized database operation, trace duration and contribution ratio. The customer response only says that most of the delay occurred in backend data processing.

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

Customer responses omit Trace IDs, span IDs, raw SQL, raw logs, stack traces, database constraint names, internal IPs/ports, raw timing evidence, Prometheus metrics, Incident Memory evidence, graph data and engineer remediation details.

## Engineer API

Technical investigation endpoints additionally require:

```http
X-ProdMind-Project: demo
X-ProdMind-Engineer-Key: demo-engineer-key
```

The demo key exists only for local Compose usage. Replace `PRODMIND_ENGINEER_API_KEY` before any real deployment.

## Useful endpoints

- Customer demo: `http://localhost:8090`
- Engineer graph viewer: `http://localhost:8088/engineer`
- ProdMind API docs: `http://localhost:8088/docs`
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
- deployment/configuration regression correlation
- slow downstream dependency with multi-service critical-path analysis
