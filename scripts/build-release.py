from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str, cwd: Path = ROOT) -> None:
    print(f"+ ({cwd.relative_to(ROOT) or '.'}) {' '.join(command)}", flush=True)
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError(f"required executable is not available: {command[0]}")
    subprocess.run((executable, *command[1:]), cwd=cwd, check=True)


def read_versions() -> tuple[str, str, str]:
    release = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)-rc\.(\d+)", release)
    if match is None:
        raise RuntimeError("VERSION must use X.Y.Z-rc.N format")
    major, minor, patch, candidate = match.groups()
    return release, f"{major}.{minor}.{patch}rc{candidate}", f"{major}.{minor}.{patch}-RC{candidate}"


def verify_versions(release: str, python_version: str, maven_version: str) -> None:
    server = tomllib.loads((ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8"))
    integration = tomllib.loads(
        (ROOT / "integrations" / "python" / "pyproject.toml").read_text(encoding="utf-8")
    )
    widget = json.loads((ROOT / "widget" / "package.json").read_text(encoding="utf-8"))
    pom = (ROOT / "integrations" / "spring-boot-starter" / "pom.xml").read_text(
        encoding="utf-8"
    )
    app_version = (ROOT / "server" / "app" / "version.py").read_text(encoding="utf-8")
    actual = {
        "server": server["project"]["version"],
        "python integration": integration["project"]["version"],
        "widget": widget["version"],
    }
    for name, version in actual.items():
        expected = release if name == "widget" else python_version
        if version != expected:
            raise RuntimeError(f"{name} version {version!r} does not match {expected!r}")
    if f"<version>{maven_version}</version>" not in pom:
        raise RuntimeError(f"Spring Boot Starter does not use {maven_version}")
    if f'RELEASE_VERSION = "{release}"' not in app_version:
        raise RuntimeError(f"FastAPI application does not use {release}")


def reset_output(release: str) -> Path:
    release_root = (ROOT / "release").resolve()
    output = (release_root / release).resolve()
    if output.parent != release_root or not output.name.startswith("0."):
        raise RuntimeError(f"refusing to replace unsafe release path: {output}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    return output


def artifacts_under(output: Path) -> list[Path]:
    return sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )


def write_checksums(output: Path) -> None:
    artifacts = artifacts_under(output)
    if len(artifacts) < 5:
        raise RuntimeError(f"expected at least five release artifacts, found {len(artifacts)}")
    lines = []
    for artifact in artifacts:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        lines.append(f"{digest}  {artifact.relative_to(output).as_posix()}")
    (output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def only_artifact(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {pattern} artifact in {directory}, found {len(matches)}"
        )
    return matches[0]


def verify_artifact_contents(
    *,
    server_output: Path,
    integration_output: Path,
    npm_output: Path,
    maven_output: Path,
) -> None:
    server_wheel = only_artifact(server_output, "*.whl")
    with zipfile.ZipFile(server_wheel) as archive:
        names = set(archive.namelist())
        required = {"app/main.py", "app/ai_eval.py", "app/ai_eval_cases.json"}
        if not required.issubset(names):
            raise RuntimeError(f"server wheel is missing: {sorted(required - names)}")

    integration_wheel = only_artifact(integration_output, "*.whl")
    with zipfile.ZipFile(integration_wheel) as archive:
        names = set(archive.namelist())
        required = {
            "prodmind_integration/__init__.py",
            "prodmind_integration/asgi.py",
            "prodmind_integration/telemetry.py",
        }
        if not required.issubset(names):
            raise RuntimeError(f"integration wheel is missing: {sorted(required - names)}")

    npm_package = only_artifact(npm_output, "*.tgz")
    with tarfile.open(npm_package, "r:gz") as archive:
        names = set(archive.getnames())
        required = {
            "package/package.json",
            "package/dist/index.js",
            "package/dist/index.cjs",
            "package/dist/index.d.ts",
        }
        if not required.issubset(names):
            raise RuntimeError(f"npm package is missing: {sorted(required - names)}")

    starter_jar = only_artifact(maven_output, "*.jar")
    with zipfile.ZipFile(starter_jar) as archive:
        names = set(archive.namelist())
        metadata = (
            "META-INF/spring/"
            "org.springframework.boot.autoconfigure.AutoConfiguration.imports"
        )
        if metadata not in names:
            raise RuntimeError("Spring Boot Starter jar has no auto-configuration metadata")


def main() -> int:
    release, python_version, maven_version = read_versions()
    verify_versions(release, python_version, maven_version)
    output = reset_output(release)

    server_output = output / "python-server"
    integration_output = output / "python-integration"
    npm_output = output / "npm"
    maven_output = output / "maven"
    for directory in (server_output, integration_output, npm_output, maven_output):
        directory.mkdir()

    run(sys.executable, "-m", "pytest", "-q", cwd=ROOT / "server")
    run(sys.executable, "-m", "app.ai_eval", cwd=ROOT / "server")
    run(sys.executable, "-m", "build", "--outdir", str(server_output), cwd=ROOT / "server")

    python_integration = ROOT / "integrations" / "python"
    run(sys.executable, "-m", "pytest", "-q", cwd=python_integration)
    run(
        sys.executable,
        "-m",
        "build",
        "--outdir",
        str(integration_output),
        cwd=python_integration,
    )

    widget = ROOT / "widget"
    run("npm", "ci", cwd=widget)
    run("npm", "run", "typecheck", cwd=widget)
    run("npm", "test", cwd=widget)
    run("npm", "run", "build", cwd=widget)
    run("npm", "pack", "--pack-destination", str(npm_output), cwd=widget)

    starter = ROOT / "integrations" / "spring-boot-starter"
    run("mvn", "-q", "test", "package", cwd=starter)
    jar = starter / "target" / f"prodmind-spring-boot-starter-{maven_version}.jar"
    if not jar.is_file():
        raise RuntimeError(f"missing Maven artifact: {jar}")
    shutil.copy2(jar, maven_output / jar.name)

    verify_artifact_contents(
        server_output=server_output,
        integration_output=integration_output,
        npm_output=npm_output,
        maven_output=maven_output,
    )
    write_checksums(output)
    print(f"\nRelease candidate built at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
