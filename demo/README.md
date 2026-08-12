# ProdMind Demo

The demo contains reproducible production-style failures so contributors can test ProdMind without connecting it to a real customer system.

The important point is that the scenarios use the **same investigation pipeline**. Only the diagnostic rule changes.

```text
User action
   ↓
W3C traceparent
   ↓
Real application failure
   ↓
OpenTelemetry
   ↓
Tempo + Loki
   ↓
Normalized evidence
   ↓
Pluggable RCA rules
   ↓
Customer-safe answer / Engineer evidence
   ↓
Incident Memory
```

## Run the demo

From the repository root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8090
```

The page exposes two intentionally broken operations.

## Scenario A — duplicate user

The database is seeded with phone number `13800000000`.

```text
POST /api/users
   ↓
Spring JDBC
   ↓
PostgreSQL
   ↓
unique constraint violation
```

The application returns only:

```json
{"message":"Operation failed"}
```

ProdMind uses the trace and logs to match `DatabaseUniqueViolationRule`.

Engineer category:

```text
database_unique_violation
```

Customer category:

```text
duplicate_data
```

Triggering the scenario a second time also demonstrates Incident Memory: the second failure must still be independently confirmed from current telemetry, then ProdMind adds the previous resolved incident as historical evidence for the engineer.

## Scenario B — unavailable downstream service

The payment endpoint calls an address with no listener inside the demo container:

```text
POST /api/payments/charge
   ↓
RestClient
   ↓
127.0.0.1:65530
   ↓
connection refused
```

Again, the application returns only the same generic customer error:

```json
{"message":"Operation failed"}
```

ProdMind sees a real `ResourceAccessException` / `ConnectException` in the trace and matches `DownstreamUnavailableRule`.

Engineer category:

```text
downstream_unavailable
```

Customer category:

```text
service_unavailable
```

The embedded customer response never includes the target host/port, exception class, stack trace, raw logs, Trace ID, or internal evidence.

## Why two scenarios matter

The first demo could reasonably be criticized as a hard-coded `DuplicateKeyException` example. The second scenario proves that telemetry collection and RCA knowledge are separate concerns:

```text
Tempo/Loki connectors
       ↓
InvestigationRequest
       ↓
RULES registry
   ├── DatabaseUniqueViolationRule
   └── DownstreamUnavailableRule
```

Adding a new failure type should primarily mean adding a new rule and tests, not rewriting telemetry connectors.

## Correlation model

The browser creates a standard W3C `traceparent` before a tracked request is sent. OpenTelemetry-instrumented services continue the same trace, creating a deterministic bridge:

```text
User action → browser-known Trace ID → backend trace → evidence → root cause
```

The customer never needs to see, copy, or paste that identifier.

## Customer / engineer boundary

Customer-facing endpoints return a deliberately narrow response model. Raw evidence is absent from the HTTP response rather than merely hidden in the UI.

Customer responses omit:

- Trace IDs
- raw logs and stack traces
- SQL and database constraint names
- internal IPs, ports and filesystem paths
- internal service topology
- Incident Memory evidence
- engineer remediation details

Engineer endpoints retain authorized technical evidence and must be protected with authentication/authorization in production deployments.

## Useful endpoints

- Demo UI: `http://localhost:8090`
- ProdMind API docs: `http://localhost:8088/docs`
- Customer-safe API: `POST http://localhost:8088/api/v1/support/trace`
- Engineer investigation API: `POST http://localhost:8088/api/v1/investigate/trace`
- Tempo: `http://localhost:3200`
- Loki: `http://localhost:3100`

## Next scenarios

- database connection pool exhaustion
- slow SQL / latency diagnosis with Prometheus metrics
- Redis unavailable
- timeout and retry storms
