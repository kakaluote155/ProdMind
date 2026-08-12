# ProdMind Demo

The demo application contains reproducible production-style failures so contributors can test investigation behavior without connecting ProdMind to a real customer system.

## Scenario 1: duplicate user

This scenario exercises the v0.1 evidence path without exposing diagnostic identifiers to the customer:

```text
Browser action
   ↓
Browser creates W3C traceparent
   ↓
POST /api/users
   ↓
Spring Boot + OpenTelemetry Java agent
   ↓
PostgreSQL unique constraint violation
   ↓
HTTP 500: {"message":"Operation failed"}
   ↓
OTLP traces/logs
   ↓
OpenTelemetry Collector
   ├── Tempo (traces)
   └── Loki (logs)
   ↓
ProdMind
   ├── /api/v1/support/trace       customer-safe response
   └── /api/v1/investigate/trace   engineer evidence
```

The database is seeded with the phone number `13800000000`. Creating another user with that phone triggers the incident.

## Run the demo

From the repository root:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8090
```

1. Keep the pre-filled phone number `13800000000`.
2. Click **Create user**.
3. The page receives only the generic customer error `Operation failed`.
4. The browser has already associated that action with a W3C Trace ID; the user never sees or enters it.
5. Click **Ask ProdMind: Why did this fail?**.
6. ProdMind queries Tempo and Loki using the remembered context.
7. The embedded UI receives only a customer-safe response such as `duplicate_data` plus a plain-language explanation.

Useful endpoints:

- Demo UI: `http://localhost:8090`
- ProdMind API: `http://localhost:8088/docs`
- Customer-safe API: `POST http://localhost:8088/api/v1/support/trace`
- Engineer investigation API: `POST http://localhost:8088/api/v1/investigate/trace`
- Tempo API: `http://localhost:3200`
- Loki API: `http://localhost:3100`

## Correlation model

The SDK does not copy form values or request bodies into ProdMind context. Before a tracked request is sent, it creates a standard W3C `traceparent` header. OpenTelemetry-instrumented services continue the same trace, giving ProdMind a deterministic bridge:

```text
User action → browser-known Trace ID → backend Trace → logs/spans → root cause
```

This is intentionally different from returning a Trace ID in an error response or asking a customer to paste a diagnostic identifier.

## Customer / engineer boundary

The customer endpoint returns a separate narrow schema. Raw evidence is not merely hidden by CSS or JavaScript; it is absent from the HTTP response.

Customer-facing responses omit:

- raw logs and stack traces
- SQL and database constraint names
- internal IPs and paths
- service topology
- engineer recommendations
- Trace IDs

The engineer investigation endpoint retains the evidence chain and must be protected by authentication/authorization in production deployments.

## Planned scenarios

1. **Duplicate user** — database unique constraint violation. *(working end to end)*
2. **Redis unavailable** — login or session operation fails.
3. **Database pool exhausted** — request latency and timeout.
4. **Downstream service unavailable** — connection refused / 5xx propagation.
5. **Slow SQL query** — user-visible page latency with trace and metric evidence.
