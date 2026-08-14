# AGENTS.md

This file defines the repository-wide working rules for coding agents and human contributors using agents in ProdMind.

## Project mission

ProdMind is an embeddable AI Production Support Engineer for software that is already running in production. It starts from a user's actual operation, correlates that operation with production telemetry, builds evidence, assigns a root cause only when the evidence is sufficient, and produces separate customer-safe and engineer-facing responses.

The intended flow is:

```text
User Action
  -> Request / Distributed Trace
  -> Logs / Metrics / Traces
  -> Normalized Evidence
  -> RCA
  -> Customer-safe Explanation
  -> Engineer Evidence
```

ProdMind is not a generic chatbot over raw logs. Preserve that distinction in implementation, documentation, tests, and product language.

## Non-negotiable product principles

1. **Evidence First, AI Second**
   - Do not assign a root cause from an LLM guess, a vague symptom, or historical similarity alone.
   - Deterministic and normalized current-incident evidence must remain the source of truth.
   - If evidence is insufficient, return `insufficient_evidence`.

2. **User-aware Investigation**
   - Prefer the user's recent action and its request/trace context as the investigation entry point.
   - Do not redesign the primary flow around alerts alone.

3. **Dual Response**
   - Customer APIs return only coarse, sanitized business explanations and safe next steps.
   - Technical evidence belongs only in authenticated engineer APIs.
   - Never rely on the frontend to hide engineer-only fields; enforce separation in server response models and policies.

4. **Read Only by Default**
   - Investigation may read telemetry and write ProdMind's own compact metadata stores.
   - It must not restart services, execute production commands, mutate customer databases, change infrastructure, or apply remediation automatically.

5. **Project Isolation**
   - Trace, log, metric, Incident Memory, and Change Evidence access must be scoped to the authorized project.
   - Missing, conflicting, unscoped, or cross-project telemetry must fail closed.
   - Never infer project scope from an untrusted metric/log query supplied by a caller.

6. **Incident Memory Is Supporting Evidence**
   - Diagnose the current incident before looking up history.
   - Historical similarity must never create or replace the current RCA.
   - Do not persist raw logs, stack traces, request bodies, credentials, or arbitrary telemetry in the default memory store.

7. **Change Awareness Is Non-causal Context**
   - Diagnose from current trace/log/metric evidence before querying recent changes.
   - Temporal proximity does not prove causation.
   - Change graph relationships must remain `context_for`, never `supports`, `diagnoses`, or an invented causal edge unless a future evidence model explicitly proves causality.

## Repository map and ownership

- `server/` is the ProdMind core. It contains the FastAPI APIs, telemetry connectors, normalized models, RCA rules, security policies, Incident Memory, Change Store, and Evidence Graph.
- `server/app/rules/` contains deterministic, pluggable RCA knowledge. Rules consume normalized models, not Tempo/Loki/Prometheus response formats.
- `server/app/connectors/` contains vendor-specific collection and normalization. Raw provider details should stop at this boundary.
- `widget/` is the embeddable browser SDK. It captures minimal action/correlation context and must not collect arbitrary form or request-body values.
- `demo/` is a realistic customer-system simulator. Its Spring Boot code is not the ProdMind core and must not become the place where RCA logic lives.
- `deploy/` contains local/demo observability configuration for OpenTelemetry Collector, Tempo, Loki, and Prometheus.
- `scripts/` contains Docker-based end-to-end proofs.
- `docs/` describes architecture, evidence semantics, security boundaries, and supported scenarios.
- `.github/workflows/` defines CI verification.

When a change crosses these boundaries, keep provider-specific parsing in connectors, diagnosis in rules, response filtering in policies, and demo-only fault generation in `demo/`.

## Current investigation pipeline

Preserve the following ordering unless a design change explicitly justifies and tests a new order:

1. Validate the project identifier and required engineer authentication.
2. Fetch the trace from Tempo.
3. Verify all participating telemetry belongs to the requested project.
4. Normalize trace status, exceptions, timing, spans, services, versions, and verified service calls.
5. Fetch correlated Loki logs without making Loki a hard dependency for unrelated diagnoses.
6. Query Prometheus only when the suspected incident class needs metric corroboration.
7. Run the RCA rule registry against normalized current evidence.
8. Only after a current RCA exists, attach project-scoped Change Context and Incident Memory.
9. Return either the narrow customer response, the authenticated engineer response, or an Evidence Graph built from the completed investigation.

The Evidence Graph explains an existing diagnosis. It must not perform diagnosis or invent missing evidence.

## Privacy and security requirements

Customer-facing responses must not expose:

- trace IDs or span IDs;
- raw SQL, database/table/constraint names;
- raw logs or stack traces;
- internal service names, hosts, IPs, ports, paths, or topology;
- exception implementation details;
- Prometheus/PromQL names, labels, or capacity values;
- raw timing evidence;
- deployment versions, revisions, actors, or change summaries;
- Incident Memory evidence;
- engineer recommendations, graph nodes, or graph edges;
- passwords, tokens, cookies, authorization headers, API keys, or credentials.

Additional rules:

- Treat all telemetry and change metadata as untrusted input.
- Validate identifiers with allowlists where practical and escape connector query values correctly.
- Engineer endpoints must fail closed when authentication is not configured.
- Use constant-time secret comparison.
- Keep local demo credentials and unauthenticated observability ports clearly demo-only.
- Do not add secrets to source, fixtures, logs, docs, screenshots, or test artifacts.
- Prefer compact references to raw evidence over copying sensitive payloads into new stores.

## RCA rule requirements

Every new RCA rule must:

- have one narrow, well-defined category;
- consume vendor-neutral `InvestigationRequest` facts;
- state the minimum positive evidence required;
- include negative and near-threshold tests;
- avoid matching a convenient correlate as the root cause;
- return a customer-safe fixed/coarse explanation;
- return engineer evidence that identifies why the rule matched;
- define deterministic confidence behavior;
- be registered in an intentional precedence order;
- document interactions with existing rules when more than one could match.

Capacity diagnoses require metric corroboration when an exception alone is ambiguous. Performance diagnoses require a verified dominant span or service call; total latency alone is insufficient. Multi-service conclusions must come from verified trace relationships rather than service-name heuristics.

## Evidence and graph modeling

- Prefer typed fields over parsing human-readable evidence summaries.
- Do not place raw SQL or raw span relationship identifiers in normalized RCA models.
- Keep enough provenance to explain which connector or rule produced an evidence item.
- Graph node and edge construction must be deterministic for the same investigation result.
- Historical evidence uses `similar_to`; recent changes use `context_for`.
- A graph must remain project-scoped and engineer-only.

## Coding conventions

### Python core

- Target Python 3.12 and use type annotations.
- Keep FastAPI route functions thin; orchestration, policy, connector, storage, and rule behavior should remain separable.
- Do not make RCA rules depend directly on HTTP clients, environment variables, PromQL, LogQL, or Tempo payload shapes.
- Avoid blocking I/O in async request paths; if unavoidable for a small local backend, make the limitation explicit and do not spread it.
- Use Pydantic response models to enforce security boundaries.
- Prefer explicit failure states over broad exception swallowing. Optional telemetry sources may degrade gracefully, but the resulting evidence gap must not become a diagnosis.

### TypeScript widget

- Keep collection minimal and in-memory/session-scoped unless persistence is explicitly designed.
- Generate valid W3C trace context before the host request leaves the browser.
- Do not capture arbitrary bodies, form values, headers, cookies, tokens, or credentials.
- Call only customer-safe APIs from embedded customer code.

### Java demo

- Keep Java changes focused on generating realistic application behavior and OpenTelemetry signals.
- Do not implement ProdMind investigation or RCA logic in the demo service.
- Failed demo operations should return generic customer errors while recording useful trace/log evidence internally.

## Testing and verification

Use the smallest relevant checks first, then broaden based on the change.

Python core:

```bash
cd server
python -m pytest -q
```

Widget build:

```bash
cd widget
npm install
npm run build
```

Java demo build:

```bash
cd demo/user-service
mvn -q -DskipTests package
```

Compose validation:

```bash
docker compose config
```

End-to-end suites are expensive and start/remove Docker volumes. Run the relevant suite when the change affects real telemetry, Docker topology, project isolation, customer/engineer boundaries, Change Awareness, Incident Memory, or critical-path reconstruction:

```bash
bash scripts/e2e-smoke.sh
bash scripts/e2e-change-awareness.sh
bash scripts/e2e-multiservice.sh
```

Do not claim a test passed unless it was actually run successfully. If dependencies or Docker are unavailable, report that limitation. Tests must cover both the diagnosis and the safety boundary; a correct engineer RCA with a leaking customer response is a failed change.

## Documentation requirements

Update documentation in the same change when behavior, APIs, categories, thresholds, response fields, security boundaries, demo scenarios, environment variables, or deployment topology change.

At minimum, check the relevant portions of:

- `README.md`;
- `docs/architecture.md`;
- the feature-specific document under `docs/`;
- `demo/README.md` for demo/E2E changes;
- `SECURITY.md` for authentication, isolation, collection, or exposure changes;
- `docs/roadmap.md` when shipped/planned status changes.

Documentation must distinguish implemented behavior, demo-only behavior, planned behavior, and production recommendations. Do not describe correlation as causation or a CI definition as a currently verified passing run.

## Change discipline

- Inspect existing behavior and tests before editing.
- Keep changes focused; do not mix unrelated refactors with a feature or security fix.
- Preserve user changes in a dirty worktree.
- Do not change public response schemas, RCA categories, rule precedence, evidence semantics, or storage compatibility accidentally.
- Do not commit, push, create branches, or open pull requests unless the user explicitly asks.
- Never perform destructive production or repository actions as part of an investigation task.
- At handoff, summarize changed behavior, security implications, tests actually run, tests not run, and documentation updated.

## Review checklist

Before considering work complete, verify:

- Is the conclusion supported by current evidence?
- Does project isolation hold across every data source and store involved?
- Can the customer response expose any new technical or sensitive detail?
- Is engineer-only data protected by authentication?
- Are history and changes still supporting/non-causal context?
- Does the rule behave safely when a connector is unavailable?
- Are precedence and threshold edge cases tested?
- Is provider-specific logic confined to its connector?
- Are the README, feature docs, demo docs, and code consistent?
- Were only the intended files changed, and were reported tests actually run?
