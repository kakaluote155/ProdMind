# ProdMind

> **Software that knows why it broke.**

ProdMind is an open-source, embeddable **AI Production Support Engineer** for software that is already running in production.

When a customer encounters an error, they should not need to take screenshots, open a ticket, wait for support, and then wait again for a developer to inspect logs.

They should be able to ask one question:

> **Why did my last operation fail?**

ProdMind correlates the user's action with real production evidence — traces, logs, metrics and historical incidents — and produces two deliberately separated views:

- a safe, understandable explanation for the customer;
- a technical evidence chain for authorized engineers.

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

## Live v0.1 demo path

The repository contains a reproducible duplicate-user failure that exercises real telemetry:

```text
Browser action
   ↓
W3C traceparent created silently
   ↓
POST /api/users
   ↓
Spring Boot
   ↓
PostgreSQL unique constraint
   ↓
HTTP 500: "Operation failed"
   ↓
OpenTelemetry
   ↓
Tempo + Loki
   ↓
ProdMind
   ↓
Customer-safe answer / Engineer evidence
```

The customer never receives or enters a Trace ID. The browser knows the trace context before the request leaves the page, and OpenTelemetry continues that trace through the backend.

## Example

A customer creates a user and receives only:

```text
Operation failed
```

They ask:

```text
Why did creating the user fail?
```

ProdMind internally reconstructs:

```text
POST /api/users
      ↓
demo-user-service
      ↓
JDBC
      ↓
PostgreSQL
      ↓
Unique constraint: uk_user_phone
```

But the embedded customer UI receives only:

```json
{
  "status": "diagnosed",
  "category": "duplicate_data",
  "confidence": 0.98,
  "answer": "The operation failed because the submitted information already exists. Please check the existing record or use a different value."
}
```

Authorized engineer investigations retain the technical evidence chain, including spans, logs, exception class and database constraint.

## Core principles

### Evidence first

ProdMind does not dump random logs into an LLM and ask it to guess. Investigation is based on structured evidence and correlation first; language models are used for planning and explanation.

### User-aware investigation

The entry point is the user's actual failed action. The browser can associate an action with a W3C trace before the request is sent, so the customer never needs to copy a diagnostic identifier.

### Customer-safe by design

The customer and engineer APIs use different response contracts. Raw evidence is not merely hidden in the frontend — it is absent from the customer HTTP response.

### Read-only by default

The first versions of ProdMind investigate production systems. They do **not** automatically restart services, execute shell commands, change databases or modify production resources.

### Incident memory

Resolved incidents can become reusable operational knowledge for diagnosing similar failures later.

## v0.1 scope

- [x] FastAPI service skeleton
- [x] Health endpoint
- [x] Structured investigation request/response models
- [x] Evidence-first deterministic RCA engine
- [x] OpenTelemetry demo instrumentation
- [x] Tempo trace connector
- [x] Loki correlated log connector
- [x] Trace-based investigation endpoint
- [x] Interactive duplicate-user demo
- [x] Automatic browser action → request/trace correlation
- [x] Customer / engineer response isolation and redaction tests
- [ ] Prometheus metric connector
- [ ] Incident memory
- [ ] README demo GIF

## Architecture

```text
Customer / User
      ↓
ProdMind Widget / SDK
      ↓
W3C Trace Context + User Action
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

Customer-facing route:

```text
Evidence → RCA → Response Policy → /api/v1/support/... → safe schema only
```

Engineer route:

```text
Evidence → RCA → /api/v1/investigate/... → full evidence chain
```

## Quick start

```bash
git clone https://github.com/kakaluote155/ProdMind.git
cd ProdMind
docker compose up --build
```

Open the end-to-end demo:

```text
http://localhost:8090
```

Keep the seeded phone number `13800000000`, click **Create user**, then click **Ask ProdMind: Why did this fail?**.

ProdMind API documentation:

```text
http://localhost:8088/docs
```

Health check:

```bash
curl http://localhost:8088/health
```

See [`demo/README.md`](demo/README.md) for the full scenario and troubleshooting notes.

## Roadmap

### v0.1 — Explain the last failed action

User action → evidence → root cause → customer answer → engineer report.

### v0.2 — Remember incidents

Historical incident similarity, evidence graph UI and incident knowledge.

### v0.3 — Production connectors

Prometheus, Docker, PostgreSQL/MySQL, Redis and broader OpenTelemetry environments.

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
