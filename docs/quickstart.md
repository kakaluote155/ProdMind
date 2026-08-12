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

This first version demonstrates the evidence and response model. It does not yet pull traces or logs from a live production system. That end-to-end telemetry correlation is the primary v0.1 milestone.
