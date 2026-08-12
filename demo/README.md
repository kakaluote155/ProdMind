# ProdMind Demo

The demo contains reproducible production-style failures so contributors can test ProdMind without connecting it to a real customer system.

All demo telemetry is explicitly scoped to project `demo`:

```text
OTel resource attribute: prodmind.project.id=demo
API header:              X-ProdMind-Project: demo
```

ProdMind verifies those values match before it uses the trace or Incident Memory.

## Run the demo

```bash
docker compose up --build
```

Open `http://localhost:8090` and choose either failure scenario.

## Shared investigation pipeline

```text
User action
   ↓
W3C traceparent
   ↓
Real application failure
   ↓
OpenTelemetry resource: prodmind.project.id=demo
   ↓
Tempo + Loki
   ↓
Project-scope validation
   ↓
Normalized evidence
   ↓
Pluggable RCA rules
   ↓
Customer-safe answer / authenticated engineer evidence
   ↓
Project-scoped Incident Memory
```

## Scenario A — duplicate user

Phone `13800000000` is pre-seeded in PostgreSQL.

```text
POST /api/users → PostgreSQL unique violation
```

Engineer category: `database_unique_violation`

Customer category: `duplicate_data`

Triggering this scenario twice also proves Incident Memory: current telemetry must independently diagnose the second failure before same-project history is added as engineer evidence.

## Scenario B — unavailable downstream service

The payment endpoint calls an address with no listener:

```text
POST /api/payments/charge → 127.0.0.1:65530 → connection refused
```

Engineer category: `downstream_unavailable`

Customer category: `service_unavailable`

Both application endpoints still return only:

```json
{"message":"Operation failed"}
```

## Customer API

Customer support requests include the project header but no secret engineer credential:

```http
X-ProdMind-Project: demo
```

A Trace ID belonging to another project, a trace with missing project scope, or a mismatched project header is rejected with the same generic not-found response.

Customer responses omit Trace IDs, raw logs, stack traces, database constraint names, internal IPs/ports, Incident Memory evidence and engineer remediation details.

## Engineer API

Technical investigation endpoints additionally require:

```http
X-ProdMind-Project: demo
X-ProdMind-Engineer-Key: demo-engineer-key
```

The demo key exists only for local Compose usage. Replace `PRODMIND_ENGINEER_API_KEY` before any real deployment.

Without the engineer key, `/api/v1/investigate*` fails closed and returns no evidence.

## Useful endpoints

- Demo UI: `http://localhost:8090`
- ProdMind API docs: `http://localhost:8088/docs`
- Customer-safe API: `POST http://localhost:8088/api/v1/support/trace`
- Engineer API: `POST http://localhost:8088/api/v1/investigate/trace`
- Tempo: `http://localhost:3200`
- Loki: `http://localhost:3100`

## Next scenarios

- database connection pool exhaustion
- slow SQL / latency diagnosis with Prometheus metrics
- Redis unavailable
- timeout and retry storms
