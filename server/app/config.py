from __future__ import annotations

import os
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """A deployment setting is malformed or unsafe for the selected mode."""


def environment() -> str:
    return os.getenv("PRODMIND_ENV", "development").strip().lower() or "development"


def is_production() -> bool:
    return environment() == "production"


def configured_cors_origins() -> list[str]:
    raw = os.getenv("PRODMIND_CORS_ORIGINS")
    if raw is None:
        if is_production():
            return []
        return ["http://localhost:8090", "http://127.0.0.1:8090"]
    return _csv_values(raw)


def configured_trusted_hosts() -> list[str]:
    raw = os.getenv("PRODMIND_TRUSTED_HOSTS")
    if raw is None:
        return [] if is_production() else ["*"]
    return _csv_values(raw)


def positive_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


def positive_float_env(name: str, default: float, *, minimum: float = 0.1) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be numeric") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


def boolean_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def validated_http_url(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError(f"{name} must be an http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError(f"{name} must not contain credentials, query or fragment")
    return value


def production_readiness_issues() -> list[str]:
    """Return non-secret configuration issue codes used by the readiness endpoint."""

    if not is_production():
        return []

    issues: list[str] = []
    origins = configured_cors_origins()
    if not origins or "*" in origins:
        issues.append("cors_origins")

    hosts = configured_trusted_hosts()
    if not hosts or "*" in hosts:
        issues.append("trusted_hosts")

    try:
        from .security import configured_project_engineer_keys

        project_keys = configured_project_engineer_keys()
        if not project_keys or any(len(secret) < 24 for secret in project_keys.values()):
            issues.append("project_engineer_keys")
    except (ConfigurationError, ValueError):
        issues.append("project_engineer_keys")

    for name, default in (
        ("PRODMIND_TEMPO_URL", "http://tempo:3200"),
        ("PRODMIND_LOKI_URL", "http://loki:3100"),
        ("PRODMIND_PROMETHEUS_URL", "http://prometheus:9090"),
    ):
        try:
            validated_http_url(name, default)
        except ConfigurationError:
            issues.append(name.lower())

    try:
        from .connectors.http import configured_http_options

        for connector in ("TEMPO", "LOKI", "PROMETHEUS"):
            configured_http_options(connector)
    except ConfigurationError:
        issues.append("connector_transport")

    for name, default in (
        ("PRODMIND_MEMORY_RETENTION_DAYS", 90),
        ("PRODMIND_MEMORY_MAX_RECORDS_PER_PROJECT", 2000),
        ("PRODMIND_CHANGE_RETENTION_DAYS", 30),
        ("PRODMIND_CHANGE_MAX_RECORDS_PER_PROJECT", 5000),
    ):
        try:
            positive_int_env(name, default)
        except ConfigurationError:
            issues.append(name.lower())

    return sorted(set(issues))


def _csv_values(raw: str) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
