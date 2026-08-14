# Incident Memory

ProdMind's Incident Memory is a compact operational knowledge layer for reusing previously resolved production incidents.

The design deliberately avoids turning the memory store into another copy of production telemetry.

## Design rule

**Current telemetry proves the current root cause. Historical memory only supports it.**

ProdMind does not diagnose an incident only because it looks similar to an older incident. The current trace/log evidence must independently reach a diagnosis first. Only then does the memory layer search for relevant historical cases.

```text
Current user action
      ↓
Current trace + logs
      ↓
Current root cause verified
      ↓
Incident Memory lookup
      ↓
Historical match added as engineer evidence
```

## What is stored

The default SQLite backend stores a deliberately small incident fingerprint:

- incident ID
- trace ID used for deduplication
- root-cause category
- user action, when available
- compact root-cause summary
- compact resolution summary
- creation timestamp

## What is not stored by default

- raw log bodies
- complete stack traces
- request or response bodies
- form values
- secrets or access tokens
- database credentials
- complete telemetry payloads

Those data remain in the observability systems that already own their retention and access-control policies.

## Matching

The first implementation is intentionally deterministic and explainable.

A candidate must share the same root-cause category. An incident with the same user action receives a higher match score than a category-only match.

This gives the project a stable baseline before adding optional semantic or vector-based matching later.

## Self-match prevention

Customer and engineer APIs may investigate the same trace more than once. The trace ID is unique in the memory store and the current trace is excluded from similarity searches, so one incident cannot become evidence for itself.

## Customer boundary

Incident Memory is an engineer-side capability. Historical incident IDs, previous technical resolutions and `history` evidence are not returned by the customer-safe API.

The customer receives only the already-sanitized support response.

## Persistence

The Docker Compose environment stores the SQLite database in the named volume `prodmind-memory` and configures:

```text
PRODMIND_MEMORY_PATH=/data/prodmind-memory.db
```

The lightweight backend keeps the local demo simple. The storage interface can later evolve toward PostgreSQL and optional pgvector-based retrieval without changing the evidence-first rule.

v1.0 bounds the default SQLite store per project:

```text
PRODMIND_MEMORY_RETENTION_DAYS=90
PRODMIND_MEMORY_MAX_RECORDS_PER_PROJECT=2000
```

Expired and over-capacity records are pruned during normal store access. These
defaults prevent unbounded compact metadata growth, but operators must still
back up, protect and monitor the persistent volume according to their policy.

Trace deduplication is scoped by `(project_id, trace_id)`. On first v1.0 start,
the SQLite backend migrates the earlier global Trace ID uniqueness constraint
transactionally and preserves existing records. Identical Trace IDs in two
projects cannot suppress one another.

## End-to-end proof

The CI smoke test now creates the same real database failure twice with different W3C trace IDs.

The second failure must satisfy both conditions:

1. current Tempo/Loki evidence independently identifies `database_unique_violation`;
2. engineer evidence contains at least one `history` item from `incident-memory`.

The same test verifies that the customer-safe response contains no historical or technical evidence.
