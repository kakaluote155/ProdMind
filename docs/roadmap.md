# Roadmap

The roadmap follows one constraint throughout: evidence must establish the
current incident before AI, history, or change context may help explain it.

## Completed foundations

### v0.1 — Explain failures

- [x] Action Context SDK prototype
- [x] Real duplicate-user demo
- [x] OpenTelemetry propagation
- [x] Tempo and Loki correlation
- [x] Evidence normalization
- [x] Customer / engineer response separation

### v0.2 — Generalize, isolate and remember

- [x] Pluggable RCA registry
- [x] Multiple failure classes
- [x] Project isolation
- [x] Engineer authentication
- [x] Project-scoped Incident Memory

### v0.3 — Explain the diagnosis visually

- [x] Deterministic Evidence Graph API
- [x] Authenticated engineer viewer

### v0.4 — Add capacity evidence

- [x] Prometheus connector
- [x] Vendor-neutral metrics
- [x] Metric-corroborated database-pool-exhaustion RCA

### v0.5 — Explain slow successful operations

- [x] Trace timing normalization
- [x] Dominant database-span RCA without exception evidence

### v0.6 — Understand what changed

- [x] Project-scoped Change Store
- [x] Authenticated change ingestion
- [x] Service-version-aware matching
- [x] Non-causal `context_for` graph semantics

### v0.7 — Diagnose multi-service critical paths

- [x] Verified caller → callee reconstruction
- [x] Vendor-neutral `ServiceCallSample`
- [x] Dominant downstream-service RCA
- [x] Two-service demo and independent E2E

### v0.8 — Build layered service topology

- [x] Typed engineer-only `ServiceTopology`
- [x] Separate service nodes in the Evidence Graph
- [x] Verified service-to-service `calls` edges
- [x] Service-owned normalized operation nodes
- [x] Topology relationships kept separate from RCA causality
- [x] Layered topology unit and Docker E2E assertions

## Current release candidate

### v0.9 — AI investigation and productization

- [x] Evidence-grounded AI Investigator API foundation
- [x] Fail-closed LLM provider abstraction
- [x] Bounded project/trace-scoped multi-turn state
- [x] Strict Evidence-ID claim validation
- [x] Read-only next-step planning contract
- [x] Engineer viewer follow-up panel
- [x] AI investigation evaluations and quality gates
- [x] Improved embeddable JavaScript SDK
- [x] Spring Boot Starter and Python integration paths
- [x] Polished one-command demo and Quick Start
- [x] README demo GIF
- [x] Release-candidate packaging

The AI layer may plan investigations and explain verified facts. It must not
invent telemetry, silently cross project boundaries, or assign unsupported root
causes.

All planned v0.9 items are implemented in the `0.9.0-rc.1` worktree. This means
the feature milestone is complete, not that the project has reached the v1.0
production-stability bar below.

## Release target

### v1.0 — Stable Production Support

- [ ] Stable and documented APIs
  - [x] Versioned v1 header, compatibility policy and OpenAPI contract gate
  - [ ] Final v1.0 compatibility audit and freeze
- [ ] Production-ready integration paths
- [ ] Reproducible deployment
- [ ] Core production connectors
- [ ] Documented security and data-retention boundaries
- [ ] Reliable customer / engineer separation
- [ ] Installable release artifacts

```text
User Action → Investigate → Evidence → Root Cause → Explain → Recommend
```

## Future — Human-approved remediation

Execution remains outside the current product boundary. Any future remediation
must require explicit human approval, auditing, verification and rollback.

Potential later integrations include Docker, PostgreSQL/MySQL, Redis,
Git/release systems, Nginx, Kafka and Kubernetes.
