# Metric Evidence

ProdMind treats metrics as **supporting operational evidence**, not as an unbounded dump of time-series data into the diagnosis engine.

## Normalization boundary

Connector-specific data is normalized into a small vendor-neutral model:

```text
MetricSample
- name
- value
- unit
- source
- labels
```

RCA rules consume normalized names such as:

```text
db_pool_active
db_pool_max
db_pool_pending
```

They do not depend directly on Prometheus response JSON or PromQL syntax. A future Mimir, VictoriaMetrics or Datadog adapter can emit the same facts without changing the pool exhaustion rule.

## Query only what the incident needs

The trace/log path first decides whether a failure looks like a database connection acquisition timeout. Only then does ProdMind query Hikari pool metrics.

```text
Trace + Logs
    ↓
possible pool acquisition timeout?
    ├── no  → skip pool metrics
    └── yes → query recent pool pressure
```

This avoids attaching unrelated metric noise to every incident.

## Scope

Metric queries are constrained by the validated project and the service found in the authorized trace.

The demo uses Prometheus labels:

```text
application="demo-user-service"
prodmind_project="demo"
```

The project ID is never inferred from a user-supplied metric query. It comes from the same project boundary used to authorize the trace.

## Short lookback windows

Resource pressure can disappear before an investigation begins. The Hikari connector therefore reads recent peak values rather than only the current instant.

For the local demo:

```text
max_over_time(...[30s])
```

is used for active, max and pending connections.

This lets the investigation capture the pressure that existed while the customer request was failing, even if the holding requests release their connections a few seconds later.

## Corroboration rule

A connection acquisition timeout alone is ambiguous. `DatabasePoolExhaustedRule` therefore requires recent saturation:

```text
acquisition timeout
AND
db_pool_active >= db_pool_max
```

A pending peak raises confidence further.

Without metric corroboration, ProdMind remains at `insufficient_evidence` instead of overclaiming a root cause.

## Failure isolation

Prometheus is not a hard dependency for unrelated diagnoses. If the metric request fails, duplicate-data and downstream-unavailable investigations still use their existing trace/log evidence.

This is intentional:

```text
observability source failure ≠ application root cause
```

## Customer boundary

Raw metric samples and metric-derived Evidence Graph nodes are engineer-only. Customer responses do not expose:

- Prometheus or PromQL
- Hikari metric names
- pool names
- active/max/pending capacity values
- metric labels
- Evidence Graph nodes/edges
