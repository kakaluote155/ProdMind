# Changelog

## 1.0.0

First stable release of the read-only, evidence-first ProdMind investigation
product.

- froze and gated the `/api/v1` OpenAPI contract;
- added project-bound production engineer authentication and strict readiness;
- hardened Tempo, Loki and Prometheus transport with validated URLs, timeouts,
  response limits, TLS/custom CA support and per-backend bearer tokens;
- added explicit CORS/trusted-host, no-store and browser security boundaries;
- enforced configurable per-project Incident Memory and Change Store retention;
- migrated Incident Memory deduplication to project-and-trace scope without
  discarding existing SQLite records;
- added a pinned non-root production image and hardened production Compose;
- added installable server CLI, stable cross-ecosystem packages, checksums,
  release manifest and tag-driven GitHub Release automation.

Automatic remediation remains outside the v1.0 scope.

## 0.9.0-rc.1

First release-candidate milestone for the evidence-first ProdMind architecture.

- deterministic RCA registry for database, dependency, capacity and latency incidents;
- Tempo, Loki and Prometheus investigation with project isolation;
- customer/engineer response separation, Evidence Graph, Incident Memory and Change Context;
- verified multi-service critical path and layered service topology;
- optional evidence-grounded, read-only AI Investigator with deterministic safety evaluations;
- isolated browser SDK plus Spring Boot and Python OpenTelemetry integrations;
- reproducible Docker demo and cross-platform one-command launcher.

The AI provider remains disabled by default. Automatic production remediation is
outside this release's scope.
