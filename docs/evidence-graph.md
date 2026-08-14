# Evidence Graph

ProdMind represents an authorized engineer investigation as a small directed graph built from evidence that has already been normalized and diagnosed.

> **Design rule: the Evidence Graph explains a diagnosis; it does not create one.**

The existing path remains the source of truth:

```text
Project-scoped telemetry
        ↓
Tempo / Loki connectors
        ↓
Normalized Evidence
        ↓
Pluggable RCA Rules
        ↓
InvestigationResponse
        ↓
Evidence Graph
```

No graph node is allowed to invent infrastructure, services, exceptions, dependencies, database facts, or historical incidents that are absent from the investigation result.

## Why a graph

A flat evidence list is useful for machines but slow for a developer to scan during an incident. The graph makes the explanation path explicit:

```text
User action
    ↓
HTTP / Trace
    ↓
Service
    ↓
Failing operation
    ↓
Exception / Database / Dependency evidence
    ↓
Root cause
    ↑
Historical similar incident (optional)
```

For the current demo, the same graph model explains both supported real failure classes:

```text
Database evidence  ──supports/diagnoses──▶ database_unique_violation
Dependency evidence ─supports/diagnoses──▶ downstream_unavailable
History evidence   ─────similar_to───────▶ current root cause
```

## Stable graph model

The engineer API returns an `EvidenceGraph` containing:

- `incident_id`
- investigation `status`
- diagnosed `root_cause`
- deterministic `nodes`
- deterministic `edges`
- `entry_node_id`
- `root_cause_node_id`
- `recommended_actions`

Node IDs and edge IDs are derived from normalized content, so rendering and tests remain stable for the same investigation result.

Current node kinds:

```text
user_action
http
trace
service
operation
log
exception
database
dependency
metric
root_cause
history
```

Current edge relations:

```text
leads_to
contains
calls
observed_at
supports
diagnoses
similar_to
```

## Layered service topology

For an authorized distributed trace, the graph receives a typed
`ServiceTopology` rather than reconstructing services from display strings.
Each participating service is rendered as a separate node. Verified
OpenTelemetry CLIENT → SERVER relationships become `calls` edges, while slow
normalized spans are attached to their owning service with `contains`.

```text
Trace ──contains──▶ Service A ──calls──▶ Service B
                                           └──contains──▶ database SELECT
```

Topology relationships remain distinct from diagnosis:

- `calls` means the distributed trace verified a caller/callee relationship;
- `contains` means an authorized trace/service owns normalized evidence;
- `supports` and `diagnoses` are reserved for the RCA explanation path;
- `context_for` remains non-causal Change Awareness context;
- `similar_to` remains historical supporting context.

The engineer response may include the normalized topology. Customer response
models omit it completely.

## Security boundary

Evidence Graph is engineer-only data. It can contain internal service names, failure operations, database evidence, dependency evidence, and historical incident context.

The graph endpoint therefore uses the same security boundary as the full engineer investigation API:

```text
POST /api/v1/investigate/trace/graph

X-ProdMind-Project: <project-id>
X-ProdMind-Engineer-Key: <engineer-key>
```

The request is processed in this order conceptually:

```text
Engineer authentication
        ↓
Project validation
        ↓
Project-scoped trace authorization
        ↓
Telemetry investigation + RCA
        ↓
Evidence Graph construction
```

Missing/invalid engineer authentication is rejected. Missing, unscoped, or cross-project traces use the same generic not-found behavior as the existing trace investigation API.

Customer-facing `/api/v1/support*` responses do not contain graph nodes, edges, raw evidence, engineer answers, or Incident Memory details.

## Engineer viewer

A lightweight viewer is served at:

```text
http://localhost:8088/engineer
```

The HTML page itself is only an empty visualization shell and contains no incident evidence. To load a graph, the engineer enters:

- Project ID
- Engineer API key
- Trace ID
- optional user action

The browser then calls the authenticated graph endpoint. The key is not embedded into the HTML or repository.

No Neo4j, graph database, or frontend framework is required for the first milestone. The viewer renders the returned graph with browser HTML/CSS/SVG.

## Testing

Unit tests verify that:

- database unique-violation evidence reaches the database root cause;
- downstream connectivity evidence reaches the dependency root cause;
- historical Incident Memory evidence links to the current root cause;
- graph IDs are deterministic;
- the graph API rejects missing engineer authentication.
- participating services become separate deterministic nodes;
- verified service calls use `calls` without becoming causal RCA edges;
- downstream operations remain attached to their owning service;
- raw span relationship identifiers do not enter the graph.

The Docker E2E test additionally starts the real Postgres + OpenTelemetry + Tempo + Loki stack, triggers both failures, and verifies graph paths from the real traces while preserving project isolation and customer-safe responses.
