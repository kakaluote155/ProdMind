from __future__ import annotations

import re

from ..models import Evidence, InvestigationRequest, RootCause
from .base import RuleMatch


_CONSTRAINT_PATTERNS = [
    re.compile(r'unique constraint[ "]+([a-zA-Z0-9_.-]+)', re.IGNORECASE),
    re.compile(r'constraint[ "]+([a-zA-Z0-9_.-]+)', re.IGNORECASE),
]


class DatabaseUniqueViolationRule:
    name = "database_unique_violation"

    def evaluate(self, request: InvestigationRequest) -> RuleMatch | None:
        message = request.exception_message or ""
        lowered_message = message.lower()
        exception_type = (request.exception_type or "").lower()

        matched = (
            "duplicatekey" in exception_type
            or "unique constraint" in lowered_message
            or "duplicate key" in lowered_message
            or "sqlstate 23505" in lowered_message
        )
        if not matched:
            return None

        constraint = _extract_constraint(message)
        label = constraint or "unknown unique constraint"

        return RuleMatch(
            root_cause=RootCause(
                category="database_unique_violation",
                summary="The operation attempted to create data that violates a database uniqueness rule.",
                confidence=0.98,
            ),
            evidence=[
                Evidence(
                    type="database",
                    summary=f"Database unique constraint violation: {label}",
                    source="rca-rule:database-unique",
                )
            ],
            customer_answer=(
                "The operation failed because the submitted information already exists. "
                "Please check the existing record or use a different value."
            ),
            engineer_answer=(
                f"A database uniqueness violation was detected ({label}). "
                "Map this exception to a business error instead of returning a generic 500 response."
            ),
            recommended_actions=[
                "Return a business-specific conflict response instead of HTTP 500.",
                "Show a clear validation message to the end user.",
                "Confirm whether the duplicate record is expected or caused by a retry/race condition.",
            ],
        )


def _extract_constraint(message: str) -> str | None:
    for pattern in _CONSTRAINT_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1).strip('"')
    if "uk_user_phone" in message.lower():
        return "uk_user_phone"
    return None
