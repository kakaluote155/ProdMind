# ProdMind

> **Software that knows why it broke.**

ProdMind is an open-source, embeddable **AI Production Support Engineer** for software that is already running in production.

When a customer encounters an error, they should not need to take screenshots, open a ticket, wait for support, and then wait again for a developer to inspect logs.

They should be able to ask one question:

> **Why did my last operation fail?**

ProdMind correlates the user's action with real production evidence — traces, logs, metrics and historical incidents — and produces two answers:

- a safe, understandable explanation for the customer;
- a technical evidence chain for engineers.

## The idea

Traditional support:

```text
Customer
   ↓
Screenshot / Ticket
   ↓
Support
   ↓
Ops
   ↓
Developer
   ↓
Logs / Traces / Database
   ↓
Root Cause
```

With ProdMind:

```text
Customer
   ↓
Ask ProdMind
   ↓
User Action Context
   ↓
Trace + Logs + Metrics
   ↓
Evidence Graph
   ↓
Root Cause
   ↓
Customer Answer + Engineer Report
```

## Example

A customer creates a user and receives `Operation failed`.

They ask:

```text
Why did creating the user fail?
```

ProdMind investigates:

```text
POST /api/users
      ↓
user-service
      ↓
UserService.create()
      ↓
PostgreSQL
      ↓
SQLSTATE 23505
      ↓
Unique constraint: uk_user_phone
```

**Customer view**

```text
The phone number already belongs to an existing user.
Please search for the existing account or use another phone number.
```

**Engineer view**

```text
Endpoint:   POST /api/users
Service:    user-service
Exception:  DuplicateKeyException
SQLSTATE:   23505
Constraint: uk_user_phone
Confidence: 98%
```

## Core principles

### Evidence first

ProdMind does not dump random logs into an LLM and ask it to guess. Investigation is based on structured evidence and correlation first; language models are used for planning and explanation.

### User-aware investigation

The entry point is the user's actual failed action: page, operation, request ID, trace ID and time window.

### Customer-safe by design

Infrastructure details, internal hostnames, SQL, secrets and source-code information must never be exposed to normal end users.

### Read-only by default

The first versions of ProdMind investigate production systems. They do **not** automatically restart services, execute shell commands, change databases or modify production resources.

### Incident memory

Resolved incidents can become reusable operational knowledge for diagnosing similar failures later.

## v0.1 scope

The first milestone intentionally stays small:

- [x] FastAPI service skeleton
- [x] Health endpoint
- [x] Structured investigation request/response models
- [x] Evidence-first demo investigation engine
- [ ] Embedded JavaScript widget
- [ ] User-action context capture
- [ ] OpenTelemetry trace correlation
- [ ] Loki log connector
- [ ] Prometheus metric connector
- [ ] Tempo trace connector
- [ ] Customer / engineer response policy
- [ ] Incident memory

## Architecture

```text
Customer / User
      ↓
ProdMind Widget / SDK
      ↓
User Action Context
      ↓
┌──────────────────────────┐
│     ProdMind Server      │
│                          │
│  Investigation Planner   │
│          ↓               │
│     Evidence Graph       │
│          ↓               │
│    Root Cause Engine     │
│          ↓               │
│    Response Policy       │
└──────────┬───────────────┘
           │
    ┌──────┼──────┐
    ↓      ↓      ↓
  Traces  Logs  Metrics
    ↓      ↓      ↓
  Tempo   Loki Prometheus
```

## Quick start

```bash
git clone https://github.com/kakaluote155/ProdMind.git
cd ProdMind
docker compose up --build
```

Then open:

```text
http://localhost:8088/docs
```

Health check:

```bash
curl http://localhost:8088/health
```

Demo investigation:

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

## Roadmap

### v0.1 — Explain the last failed action

User action → evidence → root cause → customer answer → engineer report.

### v0.2 — Remember incidents

Historical incident similarity, evidence graph UI and incident knowledge.

### v0.3 — Real production connectors

OpenTelemetry, Loki, Prometheus, Tempo, Docker, PostgreSQL/MySQL and Redis.

### v0.4 — Deployment awareness

Git changes, release versions, configuration changes, Kafka and Kubernetes.

### v1.0 — Human-approved remediation

```text
Detect → Investigate → Explain → Recommend → Approve → Repair → Verify → Learn
```

## What ProdMind is not

ProdMind is not another chatbot for your logs.

It is an attempt to build **software that can explain its own production failures using real evidence**.

## Status

🚧 **Early development / v0.1**

The project is being built in public. APIs and architecture may change quickly.

## License

MIT
