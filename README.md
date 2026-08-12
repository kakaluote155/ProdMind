# ProdMind

> **Software that knows why it broke.**

ProdMind is an open-source, embeddable **AI Production Support Engineer** for software that is already running in production.

When a customer encounters an error, they should not need to take screenshots, open a ticket, wait for support, and then wait again for a developer to inspect logs.

They should be able to ask one question:

> **Why did my last operation fail?**

ProdMind correlates the user's action with real production evidence — traces, logs, metrics and historical incidents — and deliberately produces two separated views:

- a safe, understandable explanation for the customer;
- an authenticated technical evidence graph for authorized engineers.

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
Customer action
      ↓
W3C Trace Context
      ↓
Project-scoped telemetry
      ↓
Tempo + Loki
      ↓
Normalized Evidence
      ↓
Pluggable RCA Rules
      ↓
Root Cause
   ↙        ↘
Customer    Engineer Evidence Graph
answer      + Incident Memory
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

The customer never receives or enters a Trace ID. The browser creates the trace context before the request leaves the page, and OpenTelemetry continues that trace through the backend.

The important part is not the two demos: evidence collection is separate from diagnosis. Each root-cause signature is implemented as a small diagnostic rule that can be added without rewriting the Tempo/Loki connectors.

## Evidence Graph

Authorized engineers can see **why** ProdMind assigned a root cause instead of reading a flat evidence list.

A database incident can become:

```text
create-user
    ↓
HTTP 500
    ↓
Trace
    ↓
demo-user-service
    ↓
POST /api/users
    ↓
DuplicateKeyException
    ↓
Database unique violation
    ↓
database_unique_violation
    ↑
Similar previous incident
```

A downstream outage uses the same graph model:

```text
charge-payment
    ↓
Trace
    ↓
POST /api/payments/charge
    ↓
Connection refused
    ↓
Dependency unavailable
    ↓
downstream_unavailable
```

The graph is deterministic and built only from the existing investigation result. It **explains a diagnosis; it does not create one**.

Engineer graph API:

```text
POST /api/v1/investigate/trace/graph
```

Required headers:

```text
X-ProdMind-Project: <project-id>
X-ProdMind-Engineer-Key: <engineer-key>
```

Lightweight graph viewer:

```text
http://localhost:8088/engineer
```

The viewer HTML itself contains no incident evidence. It requests data only after the engineer supplies a project, API key and Trace ID.

## Core principles

### Evidence first

ProdMind does not dump random logs into an LLM and ask it to guess. Investigation is based on structured evidence and correlation first; language models can be used for planning and explanation.

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

### Project-isolated evidence

Telemetry is tagged with `prodmind.project.id`. Trace investigations require `X-ProdMind-Project`, and ProdMind rejects unscoped or cross-project telemetry before RCA or Incident Memory is used.

Incident Memory is project-scoped as well, so historical matches do not cross project boundaries.

### Customer-safe by design

Customer and engineer APIs use different response contracts. Raw evidence is not merely hidden in the frontend — it is absent from customer HTTP responses.

Customer APIs do not return:

- Trace IDs
- raw logs or stack traces
- database constraint names
- internal hosts or ports
- engineer remediation details
- Evidence Graph nodes/edges
- Incident Memory evidence

### Engineer authentication

Engineer investigation and graph APIs require `X-ProdMind-Engineer-Key`. If server-side engineer authentication is not configured, the engineer API fails closed.

The built-in key is only for the local Docker demo. Production deployments should replace it with a real secret and can later swap the adapter for OIDC/SSO/RBAC.

### Read-only by default

The first versions of ProdMind investigate production systems. They do **not** automatically restart services, execute shell commands, change databases or modify production resources.

### Incident Memory

A diagnosed incident can become reusable operational knowledge.

ProdMind's default memory backend intentionally stores only a compact fingerprint such as project ID, root-cause category, user action, safe root-cause summary and recommended resolution. Raw logs, stack traces and request bodies remain in the observability systems.

A later incident must first be independently diagnosed from current telemetry before historical matches are attached as supporting engineer evidence.

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
- [x] Project-scoped telemetry isolation
- [x] Engineer API authentication
- [x] Privacy-conscious, project-scoped Incident Memory
- [x] Secure Evidence Graph API
- [x] Lightweight engineer Evidence Graph viewer
- [x] E2E proof for multiple real root-cause categories
- [ ] Prometheus metric connector
- [ ] README demo GIF

## Architecture

```text
Customer / User
      ↓
ProdMind Widget / SDK
      ↓
W3C Trace Context + Project
      ↓
┌──────────────────────────────┐
│        ProdMind Server       │
│                              │
│   Project Scope Validation   │
│           ↓                  │
│   Telemetry Normalization    │
│           ↓                  │
│      Evidence Model          │
│           ↓                  │
│     RCA Rule Registry        │
│           ↓                  │
│      Root Cause Engine       │
│        ↙          ↘          │
│ Response Policy  Evidence    │
│       ↓          Graph       │
│ Customer API       ↓         │
│              Incident Memory │
└────────────┬─────────────────┘
             │
      ┌──────┼──────┐
      ↓      ↓      ↓
    Traces  Logs  Metrics
      ↓      ↓      ↓
    Tempo   Loki Prometheus
```

Customer-facing route:

```text
Project → Evidence → RCA → Response Policy → /api/v1/support/... → safe schema only
```

Engineer route:

```text
Engineer Auth → Project → Evidence → RCA → Incident Memory → Evidence Graph
```

## Quick start

```bash
git clone https://github.com/kakaluote155/ProdMind.git
cd ProdMind
docker compose up --build
```

Open the customer demo:

```text
http://localhost:8090
```

Try either:

1. **Create duplicate user** — PostgreSQL uniqueness violation.
2. **Charge payment** — unreachable downstream dependency.

Then click **Ask ProdMind: Why did this fail?**.

Open the engineer graph viewer:

```text
http://localhost:8088/engineer
```

For the local Docker demo use:

```text
Project: demo
Engineer key: demo-engineer-key
```

Paste the Trace ID only into the engineer viewer when testing the engineer flow. Real embedded customer flows do not expose Trace IDs to customers.

ProdMind API documentation:

```text
http://localhost:8088/docs
```

Health check:

```bash
curl http://localhost:8088/health
```

See:

- [`demo/README.md`](demo/README.md) for the failure scenarios
- [`docs/incident-memory.md`](docs/incident-memory.md) for operational memory
- [`docs/evidence-graph.md`](docs/evidence-graph.md) for graph design and security

## Roadmap

### v0.1 — Explain the last failed action

User action → evidence → root cause → customer answer → engineer report.

### v0.2 — Generalize, isolate and remember

Pluggable RCA rules, multiple real failure classes, project isolation, engineer authentication and project-scoped Incident Memory.

### v0.3 — Explain the diagnosis visually

Deterministic Evidence Graph API, engineer investigation view and richer production evidence.

### v0.4 — Production connectors and deployment awareness

Prometheus, Docker, PostgreSQL/MySQL, Redis, Git changes, release versions, configuration changes, Kafka and Kubernetes.

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
