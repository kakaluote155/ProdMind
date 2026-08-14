# ProdMind Spring Boot Starter

The starter tags the current OpenTelemetry servlet server span using a project
ID from Spring server configuration. It never trusts `X-ProdMind-Project` from
the incoming request and does not inspect request bodies, parameters or headers.

```xml
<dependency>
  <groupId>io.prodmind</groupId>
  <artifactId>prodmind-spring-boot-starter</artifactId>
  <version>0.9.0-RC1</version>
</dependency>
```

```yaml
prodmind:
  project-id: customer-portal
```

Use it with OpenTelemetry Java agent or Spring instrumentation so a server span
is active when the servlet filter runs. Resource-level configuration remains
preferred when available:

```text
OTEL_RESOURCE_ATTRIBUTES=prodmind.project.id=customer-portal
```

Missing or invalid `prodmind.project-id` fails application context creation.
The starter contains no ProdMind RCA logic and exposes no remediation behavior.
