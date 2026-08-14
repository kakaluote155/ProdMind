# ProdMind application integrations

These packages add the configured `prodmind.project.id` attribute to the
current OpenTelemetry server span. They do not contain RCA rules, call engineer
APIs, collect request bodies, or execute remediation.

- `python/`: framework-neutral ASGI middleware and manual span helper.
- `spring-boot-starter/`: Spring Boot auto-configuration and servlet filter.

Resource-level configuration remains preferred when it is available:

```text
OTEL_RESOURCE_ATTRIBUTES=prodmind.project.id=<project-id>
```

The span integrations provide a supported path for applications where telemetry
resource configuration is owned by framework instrumentation. ProdMind rejects
traces with missing or conflicting project identities.
