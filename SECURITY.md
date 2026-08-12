# Security

ProdMind inspects production evidence, so security boundaries are part of the product rather than an optional add-on.

## Current security model

ProdMind is **read-only by default**. It must not automatically execute remediation commands or modify production resources without an explicit future authorization model.

### Project-scoped telemetry

Customer and engineer APIs require `X-ProdMind-Project`.

Instrumented applications must attach the same project identity to OpenTelemetry resources:

```text
prodmind.project.id=<project-id>
```

Before a trace is investigated, ProdMind checks that the trace resolves to the requested project and rejects traces with missing, conflicting or different project scope.

A generic `404` is used for unavailable and cross-project traces to reduce trace-enumeration leakage.

### Engineer API authentication

`/api/v1/investigate*` returns technical evidence and therefore requires:

```text
X-ProdMind-Engineer-Key: <server-configured-key>
```

The key is configured through `PRODMIND_ENGINEER_API_KEY`. If no engineer key is configured, engineer APIs fail closed rather than becoming public.

The current key mechanism is intentionally small and self-hosting friendly. It is a baseline, not a replacement for future SSO/OIDC/RBAC integrations.

### Incident Memory isolation

Incident Memory is partitioned by `project_id`. Similarity searches never cross project boundaries.

The default memory backend stores only compact incident knowledge, not raw telemetry.

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

The browser SDK does not copy arbitrary request bodies or form values into action context by default.

## Response separation

Customer-facing `/support*` responses use a deliberately narrow response schema and must not expose internal hostnames, IP addresses, ports, SQL statements, database constraint names, stack traces, raw logs, secrets, source paths, Incident Memory evidence or infrastructure topology.

Engineer evidence is returned only through authenticated `/investigate*` routes.

## Deployment requirements

Before a non-local deployment:

1. replace the demo engineer key;
2. configure strict CORS origins for the host application;
3. ensure every participating service exports `prodmind.project.id`;
4. put ProdMind behind TLS and the deployment's normal network controls;
5. apply retention/access policies to Tempo, Loki and other telemetry backends;
6. do not expose the demo credentials or demo Compose configuration as production defaults.

## Reporting vulnerabilities

Please do not publish exploitable security issues in a public GitHub issue.

Until a dedicated security contact is configured, open a minimal issue asking for a private security contact without including exploit details.
