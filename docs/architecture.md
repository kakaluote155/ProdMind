# ProdMind Architecture

## Goal

ProdMind should answer a user-facing question such as:

> Why did my last operation fail?

without asking an LLM to guess from unstructured production data.

The architecture therefore separates **evidence collection**, **root-cause reasoning**, and **natural-language explanation**.

## Core flow

```text
User Action
   ↓
Action Context
   ↓
Investigation Planner
   ↓
Telemetry Connectors
   ↓
Evidence Graph
   ↓
Root Cause Engine
   ↓
Response Policy
   ↓
Customer Answer / Engineer Report
```

## 1. User Action Context

The client SDK captures only the minimum context needed to identify the operation:

- project ID
- page / route
- action name
- request ID
- trace ID
- HTTP status
- timestamp

Sensitive form values, passwords, tokens and credentials must not be captured by default.

## 2. Investigation Planner

The planner decides which evidence is required. Example:

```text
HTTP 500
  → fetch trace
  → identify failing span
  → fetch logs around span time
  → inspect correlated metric anomalies
```

The planner may later use an LLM, but tools must remain read-only unless an explicit remediation workflow is introduced.

## 3. Connectors

Planned v0.x connectors:

- OpenTelemetry
- Tempo
- Loki
- Prometheus
- Docker
- PostgreSQL / MySQL
- Redis

Every connector returns normalized evidence instead of raw provider-specific payloads.

## 4. Evidence Graph

Evidence is represented as relationships rather than a flat log dump.

```text
User Action
   ↓
HTTP Request
   ↓
Trace
   ↓
Service
   ↓
Exception
   ↓
Database Constraint
   ↓
Root Cause
```

Each root-cause claim must be traceable back to one or more evidence nodes.

## 5. Root Cause Engine

The root-cause engine combines deterministic signatures, correlation rules and later model-assisted reasoning.

A root cause contains:

- category
- human-readable summary
- confidence score
- supporting evidence

If evidence is insufficient, ProdMind must say so instead of fabricating a diagnosis.

## 6. Response Policy

The same incident can produce different views.

### Customer

Safe business explanation and next action. No internal infrastructure details.

### Support

Incident category, affected feature and safe troubleshooting information.

### Engineer

Trace IDs, exception types, service names, code/deployment metadata and detailed evidence.

### Admin

Full authorized operational details.

## 7. Incident Memory

Resolved incidents will eventually be stored as structured operational knowledge:

```text
symptom + evidence + root cause + resolution + affected version
```

A future incident may retrieve similar historical incidents, but historical similarity is only a hypothesis. Current evidence must still confirm the diagnosis.

## Safety boundary

ProdMind v0.1 is read-only.

It must not automatically:

- execute shell commands
- restart services
- delete containers or pods
- write to production databases
- modify configuration
- push source-code changes

Future remediation should require explicit authorization, verification and rollback support.
