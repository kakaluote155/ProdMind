from __future__ import annotations

import re

from .models import CustomerInvestigationResponse, InvestigationResponse


_IP_V4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_JDBC_URL = re.compile(r"jdbc:[a-z0-9]+://[^\s]+", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)
_UNIX_PATH = re.compile(r"(?<![\w.-])/(?:opt|var|etc|home|root|srv|app)/[^\s,;]+")
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\[^\r\n]+")


_CUSTOMER_CATEGORY = {
    "database_unique_violation": "duplicate_data",
    "downstream_unavailable": "service_unavailable",
    "database_pool_exhausted": "service_busy",
    "slow_database_query": "slow_operation",
}


def to_customer_response(result: InvestigationResponse) -> CustomerInvestigationResponse:
    """Create the only response shape that may be returned to an embedded customer-facing UI.

    Technical evidence is deliberately omitted rather than merely hidden in the
    frontend. A browser using the support endpoint never receives stack traces,
    SQL, internal service names, metric names, capacity values, raw timings or raw logs.
    """

    category = None
    confidence = None
    if result.root_cause:
        category = _CUSTOMER_CATEGORY.get(result.root_cause.category, "service_failure")
        confidence = result.root_cause.confidence

    return CustomerInvestigationResponse(
        incident_id=result.incident_id,
        status=result.status,
        category=category,
        confidence=confidence,
        answer=sanitize_customer_text(result.customer_answer),
    )


def sanitize_customer_text(value: str) -> str:
    """Defense-in-depth redaction for text that crosses the customer boundary."""

    sanitized = _JDBC_URL.sub("[redacted-database-endpoint]", value)
    sanitized = _IP_V4.sub("[redacted-ip]", sanitized)
    sanitized = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[redacted-secret]", sanitized)
    sanitized = _UNIX_PATH.sub("[redacted-path]", sanitized)
    sanitized = _WINDOWS_PATH.sub("[redacted-path]", sanitized)
    return sanitized
