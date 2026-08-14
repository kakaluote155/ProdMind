# Distributed Critical Path

ProdMind can explain a successful-but-slow operation across a real service boundary.

The first multi-service rule answers a narrow question:

> Which verified downstream service hop consumed most of the end-to-end trace latency?

## Why this is different from a slow local span

A request may look like:

```text
Customer request
      ↓
Service A
      ↓ 2.5s
Service B
      ↓
HTTP 200
```

From Service A's perspective, the critical finding is that the request spent most of its time waiting for Service B.

Service B may itself be slow because of a database query, queue, external API or lock. That is a deeper investigation layer.

ProdMind intentionally keeps these levels separate:

```text
Entry investigation:
A → B dominates trace
      ↓
slow_downstream_service

Deeper investigation of B:
B → database SELECT dominates B
      ↓
slow_database_query
```

This avoids presenting an internal implementation detail of a downstream service as though it were a local root cause in the caller.

## Relationship reconstruction

Tempo/OTLP contains raw span identifiers needed to reconstruct a distributed trace. ProdMind uses them only inside the Tempo adapter:

```text
Service A CLIENT span
  spanId = X
        ↓ parent relationship
Service B SERVER span
  parentSpanId = X
```

Once the relationship is verified, raw identifiers are discarded.

The RCA engine receives only a vendor-neutral fact:

```text
ServiceCallSample
- caller_service
- callee_service
- operation
- duration_ms
- source
```

No `spanId` or `parentSpanId` is part of the normalized RCA model.

## Safe operation naming

HTTP client telemetry can contain full internal URLs. ProdMind reduces those to safe engineer operation labels before normalization.

For example:

```text
http://demo-slow-service:8090/api/dependency/slow?token=abc
```

becomes:

```text
POST /api/dependency/slow
```

Hosts and query strings are not copied into `ServiceCallSample.operation`.

Customer-safe APIs do not expose even that internal route or the caller/callee service names.

## Diagnosis threshold

`SlowDownstreamServiceRule` requires:

```text
request is not HTTP 5xx
AND trace duration >= 1500 ms
AND a verified cross-service call exists
AND dominant downstream call >= 1000 ms
AND downstream call / total trace >= 70%
```

At >=85% contribution the deterministic confidence is higher.

A short or non-dominant downstream call remains `insufficient_evidence` rather than becoming a convenient scapegoat.

## Rule precedence

At an entry service, a verified cross-service critical path is evaluated before nested database latency.

Consider:

```text
Service A total trace                 3000 ms
└── A → Service B                     2800 ms
    └── Service B database SELECT     2500 ms
```

For the entry request, the first RCA is:

```text
slow_downstream_service
```

because Service A spent almost all of the request waiting on Service B.

A subsequent investigation focused on Service B can diagnose its internal `slow_database_query`.

## Project isolation

Every instrumented service participating in the distributed trace must carry the same authorized:

```text
prodmind.project.id
```

A missing project resource attribute on any participating service causes the trace investigation to fail closed. A trace resolving to another project is rejected with the same generic not-found behavior used by existing trace APIs.

## Evidence Graph

The engineer graph keeps topology and diagnosis as separate relationship layers:

```text
slow-journey
      ↓
Distributed trace
      ├──contains──▶ Service A
      └──contains──▶ Service B

Service A ──calls──▶ Service B
                         └──contains──▶ downstream operation

Critical dependency evidence ──supports──▶ slow_downstream_service
```

`calls` describes a verified trace relationship. It is not a causal RCA edge. The
root cause remains supported by the separately evaluated rule evidence.

The graph consumes a vendor-neutral `ServiceTopology` containing participating
services, verified `ServiceCallSample` facts and normalized `SpanSample` facts.
Raw span identifiers are never returned by the engineer API or rendered by the
viewer. Slow operations are attached to the service identified by normalized
trace evidence, allowing a downstream database operation to remain visibly
owned by the downstream service even when the entry RCA is
`slow_downstream_service`.

## Demo topology

The local Docker stack runs two OpenTelemetry-instrumented Spring Boot containers:

```text
demo-user-service   service.version=demo-v2
        ↓ RestClient
demo-slow-service   service.version=slow-v1
```

The slow service deliberately waits before returning HTTP 200. Spring `RestClient` plus the OpenTelemetry Java Agent propagates the same distributed trace automatically.

The dedicated `multiservice-e2e` CI job verifies that the real Java Agent trace can be reconstructed into a cross-service call and diagnosed without exception evidence.

## Future work

The normalized topology model can support richer critical-path reasoning:

- A → B → C multi-hop paths
- parallel fan-out / fan-in
- retry amplification
- queue producer/consumer latency
- downstream version-change correlation
- per-service SLO regression baselines

Those extensions should continue to derive topology from trace relationships rather than hard-coded service names.
