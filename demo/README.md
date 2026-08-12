# ProdMind Demo

The demo contains reproducible production-style failures so contributors can test ProdMind without connecting it to a real customer system.

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

The page exposes three real failure scenarios.

## Shared investigation pipeline

```text
User action
   ↓
W3C traceparent
   ↓
Real application failure
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
Customer-safe answer / authenticated engineer evidence graph
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
127.0.0.1:65530
        ↓
connection refused
```

Engineer: `downstream_unavailable`

Customer: `service_unavailable`

## Scenario C — database pool exhausted

The demo intentionally configures HikariCP with only two connections and a 2.5-second acquisition timeout.

Clicking **Exhaust DB pool and probe** starts two requests that each execute `pg_sleep`, holding both real PostgreSQL connections. A third traced request then tries:

```text
POST /api/pool/probe
        ↓
JdbcTemplate
        ↓
Hikari pool: 2 active / 2 max
        ↓
waiter appears while pool is saturated
        ↓
connection acquisition timeout
```

Prometheus scrapes Micrometer every second. ProdMind queries the recent project/service-scoped peak for:

```text
hikaricp_connections_active
hikaricp_connections_max
hikaricp_connections_pending
```

Those vendor metrics are normalized before RCA as:

```text
db_pool_active
db_pool_max
db_pool_pending
```

The rule deliberately does **not** diagnose pool exhaustion from the timeout exception alone. It requires saturation evidence such as `active >= max`.

Engineer: `database_pool_exhausted`

Customer: `service_busy`

The engineer Evidence Graph contains metric evidence supporting the root cause. Customer responses contain none of the metric names, pool size, pending count or Prometheus details.

## Application error boundary

All three failed customer operations still return only:

```json
{"message":"Operation failed"}
```

## Customer API

Customer support requests include:

```http
X-ProdMind-Project: demo
```

A trace belonging to another project, a trace with missing project scope, or a mismatched project header is rejected with the same generic not-found response.

Customer responses omit Trace IDs, raw logs, stack traces, database constraint names, internal IPs/ports, Prometheus metrics, Incident Memory evidence, graph data and engineer remediation details.

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

- slow SQL / latency diagnosis
- Redis unavailable
- retry storms / cascading saturation
- deployment/configuration regression correlation
