# Evidence Model

ProdMind diagnoses failures from normalized evidence, not from raw log text alone.

## Evidence properties

Every evidence item should eventually carry:

- type
- summary
- source
- timestamp
- correlation identifiers
- sensitivity classification
- optional raw reference

The current compact `Evidence` model carries `type`, `summary`, `source` and an
optional normalized `service_name`. Timestamp, sensitivity and raw-reference
fields remain planned rather than implemented.

## Initial evidence types

- `user_action`
- `http`
- `trace`
- `log`
- `exception`
- `database`
- `dependency`
- `metric`
- `change`
- `history`

## Service topology

Distributed-trace structure is retained separately from human-readable evidence
in an engineer-only `ServiceTopology`:

```text
ServiceTopology
├── services: ServiceSample[]
├── calls: ServiceCallSample[]
└── spans: SpanSample[]
```

This separation lets the Evidence Graph build distinct service nodes and attach
operations to their owning services without parsing evidence-summary strings.
Raw trace/span relationship IDs remain inside the Tempo connector and are not
part of the normalized model.

Topology is contextual structure. A verified `calls` relationship does not by
itself establish an RCA; current rule evidence must still support the root cause.

## Root-cause rule

A root-cause statement must be supported by evidence. If ProdMind cannot establish a sufficiently strong chain, the result should be `insufficient_evidence`.

Example:

```text
create-user
    ↓
POST /api/users → 500
    ↓
trace abc123
    ↓
DuplicateKeyException
    ↓
PostgreSQL unique constraint uk_user_phone
    ↓
Root cause: duplicate user data
```

Historical incidents may raise a hypothesis but must not by themselves prove the current root cause.
