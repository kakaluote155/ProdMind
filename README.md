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
Normalized Evidence
   ↓
Pluggable RCA Rules
   ↓
Root Cause
   ↓
Customer Answer + Engineer Report
```

## Live demo: two unrelated failures

The demo deliberately returns the same generic customer error for two different backend failures:

```text
Scenario A                                  Scenario B
Duplicate user                              Payment dependency unavailable
     ↓                                              ↓
PostgreSQL unique violation                 Connection refused
     └──────────────────┬───────────────────────────┘
                        ↓
                 "Operation failed"
                        ↓
             W3C trace + Tempo + Loki
                        ↓
                 ProdMind RCA rules
                  ↙             ↘
 database_unique_violation   downstream_unavailable
          ↓                         ↓
     duplicate_data           service_unavailable
```

The customer never receives or enters a Trace ID. The browser knows the trace context before the request leaves the page, and OpenTelemetry continues that trace through the backend.

The important part is not the two hard-coded demos: evidence collection is separate from diagnosis. Each root-cause signature is implemented as a small diagnostic rule that can be added without rewriting the Tempo/Loki connectors.

## Example

A customer clicks **Charge payment** and sees only:

```text
Operation failed
```

ProdMind internally finds exception evidence such as a failed downstream connection and returns a customer-safe answer:

```json
{
  "status": "diagnosed",
  "category": "service_unavailable",
  "confidence": 0.96,
  "answer": "The operation could not be completed because a required service is temporarily unavailable. Please try again shortly."
}
```

The authorized engineer endpoint retains the technical evidence and the internal root-cause category `downstream_unavailable`.

## Core principles

### Evidence first

ProdMind does not dump random logs into an LLM and ask it to guess. Investigation is based on structured evidence and correlation first; language models are used for planning and explanation.

### Pluggable diagnosis

Telemetry connectors gather facts. RCA rules decide whether those facts are sufficient to assign a root cause.

```text
Tempo / Loki / future connectors
            ↓
     InvestigationRequest
            ↓
       Rule Registry
       ├── database unique violation
       ├── downstream unavailable
       └── future rules...
            ↓
       RootCause + Evidence
```

This keeps vendor-specific telemetry code separate from reusable operational knowledge.

### User-aware investigation

The entry point is the user's actual failed action. The browser can associate an action with a W3C trace before the request is sent, so the customer never needs to copy a diagnostic identifier.

### Customer-safe by design

The customer and engineer APIs use different response contracts. Raw evidence is not merely hidden in the frontend — it is absent from the customer HTTP response.

### Read-only by default

The first versions of ProdMind investigate production systems. They do **not** automatically restart services, execute shell commands, change databases or modify production resources.

### Incident Memory

A diagnosed incident can become reusable operational knowledge.

ProdMind's default memory backend intentionally stores only a compact fingerprint such as root-cause category, user action, safe root-cause summary and recommended resolution. Raw logs, stack traces and request bodies remain in the observability systems instead of being copied into the memory database.

When a later incident is independently diagnosed from current telemetry, ProdMind can attach a prior match as `history` evidence for engineers.

Historical evidence never crosses the customer-safe API boundary.

## Current scope

- [x] FastAPI service skeleton
- [x] Health endpoint
- [x] Structured investigation request/response models
- [x] Evidence-first deterministic RCA engine
- [x] Pluggable RCA rule registry
- [x] Database unique-violation rule
- [x] Downstream-unavailable rule
- [x] OpenTelemetry demo instrumentation
- [x] Tempo trace connector
- [x] Loki correlated log connector
- [x] Trace-based investigation endpoint
- [x] Interactive two-failure demo
- [x] Automatic browser action → request/trace correlation
- [x] Customer / engineer response isolation and redaction tests
- [x] Privacy-conscious Incident Memory
- [x] Persistent memory volume in Docker Compose
- [x] E2E proof for multiple root-cause categories
- [ ] Prometheus metric connector
- [ ] Evidence Graph UI
- [ ] README demo GIF

## Architecture

```text
Customer / User
      ↓
ProdMind Widget / SDK
      ↓
W3C Trace Context + User Action
      ↓
┌─────────────────────────────┐
│       ProdMind Server       │
│                             │
│  Telemetry Normalization    │
│          ↓                  │
│     Evidence Model          │
│          ↓                  │
│    RCA Rule Registry        │
│          ↓                  │
│    Root Cause Engine        │
│          ↓                  │
│    Response Policy          │
│          ↓                  │
│    Incident Memory          │
└───────────┬─────────────────┘
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
Evidence → RCA → Incident Memory → /api/v1/investigate/... → full evidence chain
```

## Quick start

```bash
git clone https://github.com/kakaluote155/ProdMind.git
cd ProdMind
docker compose up --build
```

Open the demo:

```text
http://localhost:8090
```

Try either:

1. **Create duplicate user** — PostgreSQL uniqueness violation.
2. **Charge payment** — unreachable downstream dependency.

Then click **Ask ProdMind: Why did this fail?**.

ProdMind API documentation:

```text
http://localhost:8088/docs
```

Health check:

```bash
curl http://localhost:8088/health
```

See [`demo/README.md`](demo/README.md) for the scenarios and [`docs/incident-memory.md`](docs/incident-memory.md) for the memory design.

## Roadmap

### v0.1 — Explain the last failed action

User action → evidence → root cause → customer answer → engineer report.

### v0.2 — Generalize and remember

Pluggable RCA rules, multiple real failure classes, compact operational memory and historical incident matching.

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

🚧 **Early development**

The project is being built in public. APIs and architecture may change quickly.

## License

MIT
