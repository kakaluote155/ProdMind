# ProdMind Demo

The demo application will intentionally contain reproducible production-style failures so contributors can test investigation behavior without connecting ProdMind to a real customer system.

## Planned scenarios

1. **Duplicate user** — database unique constraint violation.
2. **Redis unavailable** — login or session operation fails.
3. **Database pool exhausted** — request latency and timeout.
4. **Downstream service unavailable** — connection refused / 5xx propagation.
5. **Slow SQL query** — user-visible page latency with trace and metric evidence.

## First scenario

The API skeleton already supports the first investigation signature directly.

Start ProdMind:

```bash
docker compose up --build
```

Then run:

```bash
curl -X POST http://localhost:8088/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why did creating the user fail?",
    "action": "create-user",
    "http_status": 500,
    "exception_type": "DuplicateKeyException",
    "exception_message": "duplicate key value violates unique constraint uk_user_phone"
  }'
```

This is currently a deterministic demonstration. The next milestone will replace manually supplied exception evidence with correlated telemetry from OpenTelemetry, Loki and Tempo.
