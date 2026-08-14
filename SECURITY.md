# Security

ProdMind inspects production evidence, so security boundaries are part of the product rather than an optional add-on.

## Current security model

ProdMind is **read-only by default**. It must not automatically execute remediation commands or modify production resources without an explicit future authorization model.

### Project-scoped telemetry

Customer and engineer APIs require `X-ProdMind-Project`.

Instrumented applications must attach the same project identity to OpenTelemetry
resources, which is the preferred deployment configuration:

```text
prodmind.project.id=<project-id>
```

The supported Spring Boot and Python integrations may instead attach the same
server-configured attribute to the active HTTP server span. They do not read
project identity from request headers. Traces with conflicting resource/span
values retain every value and fail the project-isolation check.

Before a trace is investigated, ProdMind checks that the trace resolves to the requested project and rejects traces with missing, conflicting or different project scope.

A generic `404` is used for unavailable and cross-project traces to reduce trace-enumeration leakage.

### Engineer API authentication

`/api/v1/investigate*` returns technical evidence and therefore requires:

```text
X-ProdMind-Engineer-Key: <server-configured-key>
```

Local development may configure a single key through
`PRODMIND_ENGINEER_API_KEY`. If no engineer key is configured, engineer APIs
fail closed rather than becoming public.

For production, configure a JSON map of project IDs to independent secrets:

```text
PRODMIND_PROJECT_ENGINEER_KEYS={"project-a":"<random-secret>","project-b":"<different-random-secret>"}
```

The authenticated key must belong to the exact `X-ProdMind-Project` value.
Constant-time comparison is used, and the legacy global
`PRODMIND_ENGINEER_API_KEY` is rejected in `PRODMIND_ENV=production`. It remains
available only for local/demo compatibility. Keep production secrets at least
24 characters and supply the JSON through a secret manager, not source control.

This mechanism is intentionally self-hosting friendly. It provides
project-bound authorization, but is not a replacement for future SSO/OIDC/RBAC,
key rotation or per-user audit identity.

### Incident Memory isolation

Incident Memory is partitioned by `project_id`. Similarity searches never cross project boundaries.

The default memory backend stores only compact incident knowledge, not raw telemetry.

SQLite memory records default to 90-day retention and 2,000 records per project.
Change events default to 30-day retention and 5,000 records per project. The
limits are enforced per project on normal reads/writes and are configurable with
the `PRODMIND_MEMORY_*` and `PRODMIND_CHANGE_*` settings. They do not replace
retention and access policy in Tempo, Loki or Prometheus.

## Sensitive data

Connectors and client SDKs should minimize collection and redact sensitive values before persistence or model access.

Examples include:

- passwords
- access tokens
- API keys
- cookies and authorization headers
- database credentials
- private keys
- personal data not required for diagnosis

The browser SDK copies only its explicit action-context allowlist and does not
copy arbitrary request bodies, form values, cookies or headers. Separate SDK
client instances keep the latest action and project configuration isolated.

## Response separation

Customer-facing `/support*` responses use a deliberately narrow response schema and must not expose internal hostnames, IP addresses, ports, SQL statements, database constraint names, stack traces, raw logs, secrets, source paths, Incident Memory evidence or infrastructure topology.

Normalized service topology, service versions, caller/callee relationships and
service-owned operation timing are engineer-only. They are omitted by the
customer response model rather than hidden by the frontend.

Engineer evidence is returned only through authenticated investigation, graph and
AI Investigator routes.

All `/api/v1` responses use `Cache-Control: no-store` and expose the API version
header. Browser origins and accepted Host headers are explicit production
configuration; wildcard or missing values make `/ready` fail in production.

### Optional external AI provider

The AI Investigator is disabled by default and is available only through an
authenticated engineer endpoint. Enabling a provider causes the engineer's
question and a minimized normalized evidence packet to leave the ProdMind
deployment, so operators must review provider data handling and organizational
policy first.

By default, ProdMind excludes Trace IDs, raw log lines, Change Event details and
Incident Memory from provider requests. Change and history context require
separate explicit opt-in settings. API keys are read from server configuration
and are never returned in API responses.

Provider output cannot replace deterministic RCA. Claims must reference supplied
Evidence IDs, and diagnosed responses must cite authoritative RCA-rule evidence
rather than symptoms alone. When current evidence is insufficient, provider
claims are rejected and the deterministic explanation is returned. Proposed
investigation steps are restricted to a fixed read-only enum, and no
production/remediation tools are exposed to the model.

Multi-turn state is kept in bounded process memory with project and trace
binding. It contains compact questions and structured output, not raw telemetry,
and expires after the configured TTL. It is not shared across server replicas.

## Deployment requirements

Before a non-local deployment:

1. set `PRODMIND_ENV=production` and configure distinct project-bound engineer keys;
2. configure strict CORS origins and trusted reverse-proxy Host values;
3. ensure every participating service exports `prodmind.project.id`;
4. put ProdMind behind TLS and the deployment's normal network controls;
5. use HTTPS, bearer tokens and a trusted CA for Tempo, Loki and Prometheus;
6. set connector timeout/response-size bounds and storage retention/capacity limits;
7. verify `/ready` returns 200 before routing traffic;
8. do not expose demo credentials, observability ports or demo Compose as production defaults.

The production Compose profile drops Linux capabilities, runs as a non-root
user with a read-only root filesystem, binds to loopback by default and keeps
only the compact ProdMind SQLite stores on a persistent volume. Connector
responses are rejected above the configured acceptance limit. ProdMind does not
stream unlimited connector data into downstream diagnosis.

## Reporting vulnerabilities

Please do not publish exploitable security issues in a public GitHub issue.

Until a dedicated security contact is configured, open a minimal issue asking for a private security contact without including exploit details.
