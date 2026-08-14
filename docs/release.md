# Release process

ProdMind uses one repository release version recorded in `VERSION`. Stable
versions use the same value in every ecosystem:

```text
Repository / npm: 1.0.0
Python:           1.0.0
Maven:            1.0.0
```

The build also accepts release-candidate versions (`X.Y.Z-rc.N`) and maps them
to PEP 440 (`X.Y.ZrcN`) and Maven (`X.Y.Z-RCN`) syntax.

## Build and verify

Requirements: Python 3.12, Node.js 20+, npm and Java 21/Maven.

From the repository root:

```bash
python scripts/build-release.py
```

For an environment-independent toolchain with pinned Python 3.12, Node 22 and
Java 21/Maven:

```bash
docker build -f scripts/release.Dockerfile -t prodmind-release-tools .
docker run --rm -v "$PWD:/work" prodmind-release-tools
```

The command:

1. verifies every package version against `VERSION`;
2. runs server tests and deterministic AI quality gates;
3. builds Python wheels and source distributions;
4. type-checks, tests, builds and packs the browser SDK;
5. tests and packages the Spring Boot Starter;
6. writes SHA-256 checksums for all artifacts.

Artifacts are written under `release/1.0.0/`, which is ignored by Git.
The script removes only that exact version directory before rebuilding it.

## Publish boundary

Building artifacts does not publish them to PyPI, npm, Maven Central or a
container registry. Those channels require explicit maintainer actions,
registry credentials and signing. A pushed tag exactly matching `v$(cat
VERSION)` triggers the repository Release workflow, rebuilds the checksummed
artifacts and attaches them to a GitHub Release.

The v1 OpenAPI snapshot is audited and frozen in `docs/openapi-v1.json`. CI also
runs deterministic AI evaluations, package builds, production Compose parsing
and customer/engineer boundary tests. See `production-deployment.md` for the
upgrade and rollback procedure. Never reuse local demo credentials in a
published deployment.
