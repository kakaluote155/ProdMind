# ProdMind Demo

The demo application contains reproducible production-style failures so contributors can test investigation behavior without connecting ProdMind to a real customer system.

## Scenario 1: duplicate user

This scenario now exercises the real v0.1 evidence path:

```text
Browser action
   ↓
POST /api/users
   ↓
Spring Boot + OpenTelemetry Java agent
   ↓
PostgreSQL unique constraint violation
   ↓
HTTP 500 with a generic customer message
   ↓
OTLP traces/logs
   ↓
OpenTelemetry Collector
   ├── Tempo (traces)
   └── Loki (logs)
   ↓
ProdMind /api/v1/investigate/trace
   ↓
Customer-safe explanation + engineer evidence
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
3. The page should only show the generic customer error `Operation failed`.
4. Click **Ask ProdMind: Why did this fail?**.
5. ProdMind uses the returned trace ID to query Tempo and correlated logs in Loki.
6. The customer view explains the duplicate-data problem without exposing infrastructure details.
7. Expand **Engineer evidence** to inspect the technical chain.

Useful endpoints:

- Demo UI: `http://localhost:8090`
- ProdMind API: `http://localhost:8088/docs`
- Tempo API: `http://localhost:3200`
- Loki API: `http://localhost:3100`

## Why the demo returns a trace ID

The first end-to-end milestone deliberately uses the trace ID returned with the failed request as the bridge between the user's action and telemetry. The browser SDK will later capture this correlation automatically so the customer does not need to know or enter a trace ID.

## Planned scenarios

1. **Duplicate user** — database unique constraint violation. *(in progress)*
2. **Redis unavailable** — login or session operation fails.
3. **Database pool exhausted** — request latency and timeout.
4. **Downstream service unavailable** — connection refused / 5xx propagation.
5. **Slow SQL query** — user-visible page latency with trace and metric evidence.
