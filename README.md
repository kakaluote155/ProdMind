# ProdMind

> **Software that knows why it broke — or why it got slow.**

ProdMind is an open-source, embeddable **AI Production Support Engineer** for software already running in production.

A customer should be able to ask:

> **Why did my last operation fail?**
>
> **Why was my last operation so slow?**

ProdMind correlates the user's exact action with real production evidence — **traces, logs, metrics and historical incidents** — and deliberately produces two separated views:

- a safe explanation for the customer;
- an authenticated technical Evidence Graph for authorized engineers.

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

## Live demo: four real operational classes

The Docker demo now proves three failures **and one successful-but-slow request** end to end.

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

D. Report succeeds but is slow
HTTP 200 after a real PostgreSQL operation
        ↓
Tempo trace timing + dominant JDBC span
        ↓
slow_database_query
        ↓
slow_operation
```

The customer never receives or enters a Trace ID. The browser creates trace context before the request leaves the page, and OpenTelemetry continues it through the backend.

## Performance RCA without exceptions

ProdMind does not assume every slow request is a database problem.

`slow_database_query` requires all of the following:

```text
request is not HTTP 5xx
AND trace duration >= 1.5s
AND dominant database span >= 1s
AND database span >= 70% of total trace duration
```

For the demo, a report returns HTTP 200 after a real PostgreSQL operation consumes almost the entire trace. No exception is needed.

Tempo span timestamps are normalized into vendor-neutral `SpanSample` facts. Raw SQL, span IDs and table names are intentionally not copied into the normalized model.

## Why metrics matter

A connection-acquisition timeout alone does **not** prove the pool was exhausted. ProdMind refuses to assign `database_pool_exhausted` until current failure evidence is corroborated by recent, project/service-scoped Prometheus metrics:

```text
Connection acquisition timeout
            +
recent db_pool_active >= db_pool_max
            ↓
database_pool_exhausted
```

Prometheus is supporting evidence. If it is unavailable, unrelated Trace/Loki diagnoses continue to work.

## Evidence Graph

Authorized engineers can see **why** a diagnosis was assigned.

A successful slow report can become:

```text
generate-report
      ↓
HTTP 200 / Trace
      ↓
demo-user-service
      ↓
Slow span: database SELECT
      ↓
Dominant database evidence
      ↓
slow_database_query
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

Lightweight viewer:

```text
http://localhost:8088/engineer
```

## Core principles

### Evidence first

ProdMind does not dump random logs into an LLM and ask it to guess. Investigation starts from correlated, normalized evidence.

### Pluggable diagnosis

```text
Tempo / Loki / Prometheus / future connectors
                    ↓
             normalized facts
        MetricSample / SpanSample / ...
                    ↓
               Rule Registry
          ├── database unique
          ├── downstream unavailable
          ├── database pool exhausted
          ├── slow database query
          └── future rules...
                    ↓
             RootCause + Evidence
```

### Project-isolated evidence

Telemetry is tagged with `prodmind.project.id`. Trace investigations require `X-ProdMind-Project`; metric queries are additionally scoped by project and service. Cross-project traces are rejected before logs, metrics, RCA or Incident Memory are used.

### Customer-safe by design

Customer APIs do not return:

- Trace IDs or span IDs
- raw SQL or database/table names
- raw logs or stack traces
- internal hosts or ports
- Prometheus metric names/capacity values
- raw engineer timing evidence
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
- [x] Vendor-neutral `MetricSample`
- [x] Vendor-neutral `SpanSample` + trace latency normalization
- [x] Database unique-violation RCA
- [x] Downstream-unavailable RCA
- [x] Prometheus-backed database-pool-exhaustion RCA
- [x] Successful slow-database-operation RCA
- [x] Interactive four-scenario demo
- [x] Automatic browser action → request/trace correlation
- [x] Project-scoped telemetry isolation
- [x] Customer / engineer response isolation
- [x] Engineer API authentication
- [x] Privacy-conscious, project-scoped Incident Memory
- [x] Secure deterministic Evidence Graph API
- [x] Lightweight engineer Evidence Graph viewer
- [x] E2E proof for four real operational classes
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
│   spans / logs / metrics      │
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
4. **Generate slow report** — HTTP 200, then ask ProdMind why it was slow.

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

- [`demo/README.md`](demo/README.md) — reproducible scenarios
- [`docs/incident-memory.md`](docs/incident-memory.md) — operational memory
- [`docs/evidence-graph.md`](docs/evidence-graph.md) — graph design/security
- [`docs/metrics.md`](docs/metrics.md) — normalized metrics/Prometheus strategy
- [`docs/trace-latency.md`](docs/trace-latency.md) — successful-operation latency RCA

## Roadmap

### v0.1 — Explain the last failed action

User action → evidence → root cause → customer answer → engineer report.

### v0.2 — Generalize, isolate and remember

Pluggable RCA rules, multiple failures, project isolation, engineer authentication and Incident Memory.

### v0.3 — Explain the diagnosis visually

Deterministic Evidence Graph API and engineer investigation view.

### v0.4 — Add capacity evidence

Prometheus, normalized metrics and metric-corroborated resource/capacity RCA.

### v0.5 — Explain slow successful operations

Trace timing normalization and dominant-span performance RCA without requiring an exception.

### Next — Production connectors and deployment awareness

Docker, PostgreSQL/MySQL, Redis, Git/release/configuration changes, Kafka and Kubernetes.

### v1.0 — Human-approved remediation

```text
Detect → Investigate → Explain → Recommend → Approve → Repair → Verify → Learn
```

## What ProdMind is not

ProdMind is not another chatbot for your logs.

It is an attempt to build **software that can explain its own production failures and performance problems using real evidence**.

## Status

🚧 **Early development** — APIs and architecture may change quickly.

## License

MIT
