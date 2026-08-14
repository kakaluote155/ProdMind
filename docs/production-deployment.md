# Production deployment

ProdMind v1.0 ships a conservative production baseline for the read-only API.
It deploys the Python core only; Tempo, Loki and Prometheus remain separately
operated systems with their own retention, tenancy and access controls.

## Prepare configuration

Copy `.env.production.example` to a deployment-specific protected file. Replace
every example hostname and secret. In particular:

- create a different random engineer secret for every project;
- set exact browser origins and reverse-proxy Host values;
- use HTTPS observability endpoints and configure backend bearer tokens;
- set `PRODMIND_OBSERVABILITY_CA_FILE` when an internal CA is required;
- keep TLS verification enabled outside isolated local testing;
- review per-project memory/change retention and capacity limits;
- leave the optional LLM provider disabled until its data policy is approved.

Do not put the real environment file in Git. Prefer a platform secret manager
that renders the settings only for the service process.

## Validate and start

```bash
docker compose --env-file .env.production \
  -f docker-compose.production.yml config

docker compose --env-file .env.production \
  -f docker-compose.production.yml up -d --build
```

The API binds to `127.0.0.1:8088` by default. Terminate public TLS and enforce
normal network policy at a trusted reverse proxy. Do not expose Tempo, Loki,
Prometheus or the demo stack through this Compose profile.

Verify both probes before routing traffic:

```bash
curl --fail http://127.0.0.1:8088/health
curl --fail http://127.0.0.1:8088/ready
```

`/health` proves the process is alive. `/ready` additionally checks production
configuration and returns only non-secret issue codes. It does not probe or
leak observability backend contents.

## Runtime boundaries

The container runs as a non-root user, drops Linux capabilities, uses a
read-only root filesystem and persists only the compact Incident Memory and
Change Store databases under `/data`. Connector redirects are disabled. URL
shape, request timeout, maximum accepted response size, TLS verification and
optional bearer authentication are configured centrally.

Production authentication is project-bound. A credential configured for one
project cannot authorize a request whose `X-ProdMind-Project` names another.
The legacy global development key is rejected in production.

## Upgrade and rollback

1. Back up the `prodmind-data` volume using the platform's supported snapshot
   mechanism. It contains compact SQLite metadata, not raw telemetry.
2. Review `CHANGELOG.md`, `docs/api-compatibility.md` and configuration changes.
3. Pull/build the exact version and run `docker compose config`.
4. Start the replacement, wait for `/ready`, then route traffic.
5. Run one customer-safe and one authenticated engineer investigation for a
   known project and confirm project isolation.

To roll back, route traffic away, restore the prior image/version and, only if a
future release documents an incompatible storage migration, restore the volume
snapshot. v1.0 introduces no external schema migration tool and does not mutate
telemetry or customer production systems.

## Release artifacts

`python scripts/build-release.py` creates versioned Python, npm and Maven
artifacts, a manifest and SHA-256 checksums under `release/<version>/`. A Git tag
matching `v<VERSION>` rebuilds and attaches those artifacts to a GitHub Release.
Publishing to language registries or a container registry remains an explicit
maintainer action.
