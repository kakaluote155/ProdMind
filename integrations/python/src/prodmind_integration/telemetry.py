from __future__ import annotations

import re

from opentelemetry import trace

PROJECT_ATTRIBUTE = "prodmind.project.id"
_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_project_id(value: str) -> str:
    if not _PROJECT_ID.fullmatch(value):
        raise ValueError("invalid ProdMind project ID")
    return value


def mark_current_span(project_id: str) -> bool:
    """Attach server-configured project scope without reading request data."""

    project_id = validate_project_id(project_id)
    span = trace.get_current_span()
    span.set_attribute(PROJECT_ATTRIBUTE, project_id)
    return span.get_span_context().is_valid
