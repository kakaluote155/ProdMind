# Quick Start

## Docker

```bash
git clone https://github.com/kakaluote155/ProdMind.git
cd ProdMind
docker compose up --build
```

Open the API docs:

```text
http://localhost:8088/docs
```

## Test the first investigation signature

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

The expected result is a diagnosed `database_unique_violation`, with separate customer and engineer explanations.

## Important

The default Docker demo pulls real OpenTelemetry traces and correlated logs from
Tempo/Loki and queries Prometheus for metric-backed capacity scenarios. For a
non-demo deployment, use `docs/production-deployment.md` and configure external
observability endpoints rather than exposing the demo stack.
