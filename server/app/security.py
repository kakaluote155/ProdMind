from __future__ import annotations

import hmac
import os
import re

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


def verify_engineer_key(provided: str | None) -> None:
    configured = os.getenv("PRODMIND_ENGINEER_API_KEY", "")
    if not configured:
        # Failing closed is safer than accidentally exposing engineer evidence
        # because an operator forgot to configure authentication.
        raise EngineerAuthUnavailable("engineer API key is not configured")
    if provided is None or not hmac.compare_digest(provided, configured):
        raise InvalidEngineerKey("invalid engineer API key")
