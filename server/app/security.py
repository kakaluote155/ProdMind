from __future__ import annotations

import hmac
import json
import os
import re

from .config import ConfigurationError, is_production

_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InvalidProjectId(ValueError):
    pass


class EngineerAuthUnavailable(RuntimeError):
    pass


class InvalidEngineerKey(PermissionError):
    pass


def validate_project_id(value: str | None) -> str:
    if value is None or not _PROJECT_ID.fullmatch(value):
        raise InvalidProjectId("invalid or missing project ID")
    return value


def configured_project_engineer_keys() -> dict[str, str]:
    raw = os.getenv("PRODMIND_PROJECT_ENGINEER_KEYS", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("PRODMIND_PROJECT_ENGINEER_KEYS must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError("PRODMIND_PROJECT_ENGINEER_KEYS must be a JSON object")

    result: dict[str, str] = {}
    for project_id, secret in payload.items():
        if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
            raise ConfigurationError("PRODMIND_PROJECT_ENGINEER_KEYS contains an invalid project")
        if not isinstance(secret, str) or not secret or len(secret) > 4096:
            raise ConfigurationError("PRODMIND_PROJECT_ENGINEER_KEYS contains an invalid secret")
        result[project_id] = secret
    if is_production():
        if any(len(secret) < 24 for secret in result.values()):
            raise ConfigurationError("production project engineer secrets must be at least 24 characters")
        if len(set(result.values())) != len(result):
            raise ConfigurationError("production projects must not share engineer secrets")
    return result


def verify_engineer_key(provided: str | None, *, project_id: str | None = None) -> None:
    try:
        project_keys = configured_project_engineer_keys()
    except ConfigurationError as exc:
        raise EngineerAuthUnavailable("project engineer keys are invalid") from exc

    if project_keys:
        configured = project_keys.get(project_id or "")
        if configured is None or provided is None or not hmac.compare_digest(provided, configured):
            raise InvalidEngineerKey("invalid engineer API key")
        return

    if is_production():
        raise EngineerAuthUnavailable("project-bound engineer API keys are required in production")

    configured = os.getenv("PRODMIND_ENGINEER_API_KEY", "")
    if not configured:
        # Failing closed is safer than accidentally exposing engineer evidence
        # because an operator forgot to configure authentication.
        raise EngineerAuthUnavailable("engineer API key is not configured")
    if provided is None or not hmac.compare_digest(provided, configured):
        raise InvalidEngineerKey("invalid engineer API key")
