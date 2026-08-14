# Deployment and Change Awareness

ProdMind can attach recent delivery/configuration changes to an engineer investigation so responders can answer:

> What changed around this incident?

The design deliberately separates **correlation** from **causation**.

> **Recent change ≠ root cause.**

Current trace/log/metric evidence is evaluated first. Only after ProdMind independently reaches a diagnosis does it look up recent changes for the authorized project and services.

## Investigation order

```text
Authorized project trace
        ↓
Trace / Log / Metric evidence
        ↓
RCA rule independently proves root cause
        ↓
Recent project/service change lookup
        ↓
Engineer-only change context
        ↓
Evidence Graph `context_for` edge
```

A deployment event never changes `database_unique_violation` into a synthetic `deployment_regression` merely because it occurred nearby in time.

## Change event model

The first backend stores compact metadata only:

```text
project_id
service_name
version
revision
change_type
summary
actor
source
occurred_at
created_at
```

Supported change types:

```text
deployment
configuration
feature_flag
```

ProdMind does **not** persist source code, Git patches, repository contents, request bodies or raw CI logs in this store.

Common secret assignments such as `password=...`, `token=...`, `secret=...` and `api_key=...` are redacted before the summary is written to SQLite.

## Ingestion API

Delivery tooling can record a change with:

```http
POST /api/v1/changes
X-ProdMind-Project: demo
X-ProdMind-Engineer-Key: <engineer-key>
Content-Type: application/json
```

Example body:

```json
{
  "service_name": "demo-user-service",
  "version": "demo-v2",
  "revision": "abc123",
  "change_type": "deployment",
  "summary": "Deploy demo-v2",
  "actor": "ci",
  "source": "github-actions"
}
```

The project comes from the authenticated request header rather than from the payload, which prevents callers from smuggling an event into another project by changing a JSON field.

## Trace version matching

The demo exports:

```text
service.version=demo-v2
```

as an OpenTelemetry resource attribute. Tempo normalization records safe service-version metadata for the authorized trace.

When recent changes are queried, ProdMind:

1. restricts candidates to the same project;
2. restricts candidates to services present in the trace;
3. restricts candidates to a lookback window before the trace start time;
4. prioritizes an exact trace `service.version` match over a merely newer change for the same service.

The default lookback is six hours and the returned engineer context is intentionally small.

## Project isolation

Change events are indexed and queried by `project_id`. A deployment recorded for `another-project` cannot appear in an investigation for `demo`, even when the service name and version are identical.

Change isolation is independent from Incident Memory isolation. The two stores do not share similarity logic.

## Evidence Graph semantics

A matching change becomes a `change` node with a relationship such as:

```text
Deployment demo-v2 ──context_for──▶ demo-user-service
```

The graph builder intentionally does not emit these relationships from a change node:

```text
supports
diagnoses
caused_by
```

Change context can help an engineer decide what to inspect next, but it is not RCA evidence by itself.

## Customer boundary

Customer-facing `/api/v1/support*` responses contain no:

- deployment/version/revision metadata
- change summaries
- change IDs
- change-store evidence
- Evidence Graph nodes or edges

Only authenticated engineer investigation endpoints can receive this context.

## Local persistence

The local Docker deployment stores change metadata at:

```text
/data/prodmind-changes.db
```

controlled by:

```text
PRODMIND_CHANGE_PATH
PRODMIND_CHANGE_RETENTION_DAYS=30
PRODMIND_CHANGE_MAX_RECORDS_PER_PROJECT=5000
```

The file shares the existing persistent `/data` volume but remains logically separate from the Incident Memory database.
Expired and over-capacity events are pruned per project during normal store
access. These limits bound supporting context and never alter the current-trace
RCA decision.

## CI proof

The dedicated `change-awareness-e2e` job:

1. starts the real Docker observability stack;
2. records a `demo-v2` deployment for project `demo`;
3. records a same-service/version sentinel in another project;
4. triggers a real duplicate-user failure;
5. proves the RCA remains `database_unique_violation`;
6. proves the matching deployment appears only in the engineer investigation;
7. proves the cross-project sentinel never appears;
8. proves the customer response contains no change metadata;
9. proves the Evidence Graph uses only a non-causal `context_for` relationship.

## Future adapters

The storage/ingestion contract is intentionally small so future integrations can submit the same compact event format from:

- GitHub Actions
- GitLab CI
- Jenkins
- Argo CD
- Kubernetes Deployment rollouts
- feature-flag platforms
- configuration management systems

Those integrations should continue to treat changes as contextual evidence unless stronger evidence establishes causation.
