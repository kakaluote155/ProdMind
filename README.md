# ProdMind

> **Software that knows why it broke.**

ProdMind is an open-source, embeddable **AI Production Support Engineer** for software already running in production.

When a customer encounters an error, they should be able to ask one question:

> **Why did my last operation fail?**

ProdMind correlates the user's action with real production evidence — **traces, logs, metrics and historical incidents** — and deliberately produces two separated views:

- a safe, understandable explanation for the customer;
- an authenticated technical evidence graph for authorized engineers.

## The idea

```text
Customer action
      ↓
W3C Trace Context + Project
      ↓
Project-scoped telemetry
      ↓
Tempo + Loki + Prometheus
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

## Live demo: three different production failures

Every scenario is a real failure in the local Docker stack, not a mocked RCA response.

```text
A. Duplicate user
PostgreSQL unique violation
        ↓
database_unique_violation
        ↓
duplicate_data

B. Payment dependency unavailable
Connection refused
        ↓
downstream_unavailable
        ↓
service_unavailable

C. Database pool exhausted
2 requests hold a 2-connection Hikari pool
        ↓
3rd request times out acquiring a connection
        ↓
Trace/Log + Prometheus active/max/pending
        ↓
database_pool_exhausted
        ↓
service_busy
```

The customer never receives or enters a Trace ID. The browser creates trace context before the request leaves the page, and OpenTelemetry continues it through the backend.

## Why metrics matter

A connection-acquisition timeout by itself does **not** prove the pool was exhausted. It may have another cause.

ProdMind therefore refuses to assign `database_pool_exhausted` until current failure evidence is corroborated by recent, project/service-scoped Prometheus metrics:

```text
Connection acquisition timeout
            +
recent db_pool_active >= db_pool_max
            ↓
database_pool_exhausted
```

The demo queries a short lookback window because pool pressure may disappear by the time an engineer investigates. Prometheus is supporting evidence: if it is unavailable, unrelated Trace/Loki diagnoses continue to work.

## Evidence Graph

Authorized engineers can see **why** a root cause was assigned instead of reading a flat evidence list.

For pool exhaustion:

```text
probe-database-pool
        ↓
HTTP 500 / Trace
        ↓
POST /api/pool/probe
        ↓
DB connection acquisition timeout
        ↓
Database evidence
        ↓
Prometheus metric evidence
        ↓
database_pool_exhausted
```

The graph is deterministic and built only from an existing investigation result. It **explains a diagnosis; it does not create one**.

Engineer graph API:

```text
POST /api/v1/investigate/trace/graph
```

Required headers:

```text
X-ProdMind-Project: <project-id>
X-ProdMind-Engineer-Key: <engineer-key>
```

Lightweight viewer:

```text
http://localhost:8088/engineer
```

## Core principles

### Evidence first

ProdMind does not dump random logs into an LLM and ask it to guess. Investigation is based on structured evidence and correlation first.

### Pluggable diagnosis

```text
Tempo / Loki / Prometheus / future connectors
                    ↓
             normalized facts
                    ↓
               Rule Registry
          ├── database unique
          ├── downstream unavailable
          ├── database pool exhausted
          └── future rules...
                    ↓
             RootCause + Evidence
```

### Project-isolated evidence

Telemetry is tagged with `prodmind.project.id`. Trace investigations require `X-ProdMind-Project`; Prometheus queries additionally scope by project and service. Cross-project traces are rejected before logs, metrics, RCA or Incident Memory are used.

### Customer-safe by design

Customer APIs do not return:

- Trace IDs
- raw logs or stack traces
- database constraint names
- internal hosts or ports
- Prometheus metric names or capacity values
- engineer remediation details
- Evidence Graph nodes/edges
- Incident Memory evidence

### Engineer authentication

Engineer investigation and graph APIs require `X-ProdMind-Engineer-Key`. If engineer authentication is not configured, those APIs fail closed.

### Read-only by default

ProdMind investigates production systems. It does **not** automatically restart services, execute shell commands, change databases or modify production resources.

### Incident Memory

Diagnosed incidents can become project-scoped reusable operational knowledge. The default backend stores compact root-cause/resolution facts rather than copying raw logs, stack traces or request bodies.

## Current scope

- [x] FastAPI investigation service
- [x] Evidence-first deterministic RCA engine
- [x] Pluggable RCA rule registry
- [x] OpenTelemetry demo instrumentation
- [x] Tempo trace connector
- [x] Loki correlated log connector
- [x] Prometheus metric connector
- [x] Vendor-neutral normalized `MetricSample`
- [x] Database unique-violation RCA
- [x] Downstream-unavailable RCA
- [x] Prometheus-backed database-pool-exhaustion RCA
- [x] Interactive three-failure demo
- [x] Automatic browser action → request/trace correlation
- [x] Project-scoped telemetry isolation
- [x] Customer / engineer response isolation
- [x] Engineer API authentication
- [x] Privacy-conscious, project-scoped Incident Memory
- [x] Secure deterministic Evidence Graph API
- [x] Lightweight engineer Evidence Graph viewer
- [x] E2E proof for all three real root-cause categories
- [ ] README demo GIF

## Architecture

```text
Customer / User
      ↓
ProdMind Widget / SDK
      ↓
W3C Trace Context + Project
      ↓
┌───────────────────────────────┐
│         ProdMind Server       │
│                               │
│   Project Scope Validation    │
│            ↓                  │
│   Telemetry Normalization     │
│            ↓                  │
│       Evidence Model          │
│            ↓                  │
│      RCA Rule Registry        │
│            ↓                  │
│       Root Cause Engine       │
│         ↙          ↘          │
│  Response Policy  Evidence    │
│        ↓          Graph       │
│  Customer API       ↓         │
│               Incident Memory │
└─────────────┬─────────────────┘
              │
       ┌──────┼────────┐
       ↓      ↓        ↓
     Traces  Logs    Metrics
       ↓      ↓        ↓
     Tempo   Loki  Prometheus
```

## Quick start

```bash
git clone https://github.com/kakaluote155/ProdMind.git
cd ProdMind
docker compose up --build
```

Customer demo:

```text
http://localhost:8090
```

Try:

1. **Create duplicate user** — PostgreSQL uniqueness violation.
2. **Charge payment** — unreachable dependency.
3. **Exhaust DB pool and probe** — real Hikari saturation + Prometheus evidence.

Engineer graph viewer:

```text
http://localhost:8088/engineer
```

Local demo credentials:

```text
Project: demo
Engineer key: demo-engineer-key
```

API docs:

```text
http://localhost:8088/docs
```

See:

- [`demo/README.md`](demo/README.md) — reproducible failure scenarios
- [`docs/incident-memory.md`](docs/incident-memory.md) — operational memory
- [`docs/evidence-graph.md`](docs/evidence-graph.md) — graph design/security
- [`docs/metrics.md`](docs/metrics.md) — normalized metrics and Prometheus strategy

## Roadmap

### v0.1 — Explain the last failed action

User action → evidence → root cause → customer answer → engineer report.

### v0.2 — Generalize, isolate and remember

Pluggable RCA rules, multiple failures, project isolation, engineer authentication and Incident Memory.

### v0.3 — Explain the diagnosis visually

Deterministic Evidence Graph API and engineer investigation view.

### v0.4 — Add capacity evidence

Prometheus, normalized metrics and metric-corroborated resource/capacity RCA.

### Next — Production connectors and deployment awareness

Docker, PostgreSQL/MySQL, Redis, Git/release/configuration changes, Kafka and Kubernetes.

### v1.0 — Human-approved remediation

```text
Detect → Investigate → Explain → Recommend → Approve → Repair → Verify → Learn
```

## What ProdMind is not

ProdMind is not another chatbot for your logs.

It is an attempt to build **software that can explain its own production failures using real evidence**.

## Status

🚧 **Early development** — APIs and architecture may change quickly.

## License

MIT
