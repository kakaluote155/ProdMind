# Release process

ProdMind uses one repository release version recorded in `VERSION`. Ecosystem
formats differ for the same release candidate:

```text
Repository / npm: 0.9.0-rc.1
Python:           0.9.0rc1
Maven:            0.9.0-RC1
```

## Build and verify

Requirements: Python 3.12, Node.js 20+, npm and Java 21/Maven.

From the repository root:

```bash
python scripts/build-release.py
```

The command:

1. verifies every package version against `VERSION`;
2. runs server tests and deterministic AI quality gates;
3. builds Python wheels and source distributions;
4. type-checks, tests, builds and packs the browser SDK;
5. tests and packages the Spring Boot Starter;
6. writes SHA-256 checksums for all artifacts.

Artifacts are written under `release/0.9.0-rc.1/`, which is ignored by Git.
The script removes only that exact version directory before rebuilding it.

## Publish boundary

Building artifacts does not publish them. Publishing to PyPI, npm, Maven Central,
GitHub Releases or a container registry requires an explicit maintainer action,
registry credentials, signing and a tagged release. Do not reuse local demo
credentials in any published deployment.

Before promoting v1.0, complete provider/model semantic evals, API compatibility
review, production identity/RBAC design and documented upgrade/rollback testing.
The v1 OpenAPI snapshot is already gated in CI, but its final compatibility
audit and freeze remain a v1.0 release task.
