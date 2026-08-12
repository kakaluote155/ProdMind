# Trace Latency Evidence

ProdMind can investigate an operation even when it eventually succeeds.

The first performance RCA answers a narrow question:

> Did a database operation dominate the latency of this successful request?

## Normalization

Tempo/OTLP trace payloads are normalized into a small vendor-neutral timing model:

```text
SpanSample
- name
- duration_ms
- category
- service_name
- source
```

The investigation also receives the overall `trace_duration_ms`.

The normalized model intentionally excludes:

- span IDs
- trace topology internals not needed by the rule
- raw SQL statements
- table names copied from span names

Database spans are recognized from OpenTelemetry database semantic attributes. Their names are reduced to safe operation labels such as:

```text
database SELECT
database UPDATE
database operation
```

## Why not diagnose from total latency alone

A three-second request can be slow for many reasons: application code, a downstream HTTP call, queueing, database work or deliberate waiting.

`SlowDatabaseQueryRule` therefore requires a dominant database span:

```text
HTTP status < 500
AND
trace duration >= 1500 ms
AND
dominant database span >= 1000 ms
AND
dominant DB duration / trace duration >= 70%
```

At >=85% contribution the current deterministic confidence is higher.

If those conditions are not met, ProdMind stays at `insufficient_evidence` rather than blaming the database.

## Successful-operation evidence

A real demo trace looks conceptually like:

```text
POST /api/reports/slow        ~3.1s
└── database SELECT           ~3.0s
```

The HTTP request returns 200. There is no exception requirement.

The engineer evidence can safely state the normalized operation duration and contribution ratio, while the customer API returns only a coarse explanation such as:

```text
Most of the delay occurred while processing data in the backend.
```

## Evidence Graph

Slow trace evidence is rendered as an engineer `operation` node:

```text
User action
   ↓
Trace
   ↓
Slow span: database SELECT
   ↓
Dominant database evidence
   ↓
slow_database_query
```

The graph remains an explanation layer. The RCA rule is evaluated before graph construction.

## Future extensions

The same normalized span timing model can support additional rules without changing the Tempo adapter contract, for example:

- slow downstream HTTP dependency
- queue/consumer delay
- fan-out critical-path analysis
- lock-wait-dominated database operations
- service-to-service latency regression
