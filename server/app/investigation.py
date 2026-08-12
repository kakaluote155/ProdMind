from __future__ import annotations

from uuid import uuid4

from .models import Evidence, InvestigationRequest, InvestigationResponse, RootCause


def investigate(request: InvestigationRequest) -> InvestigationResponse:
    """Run a deterministic demo investigation.

    v0.1 intentionally starts with evidence-first rules instead of asking an LLM
    to guess from raw logs. Real telemetry connectors will replace these demo
    inputs in later milestones.
    """

    incident_id = f"PM-{uuid4().hex[:8].upper()}"
    evidence: list[Evidence] = []

    if request.action:
        evidence.append(
            Evidence(type="user_action", summary=f"User action: {request.action}")
        )

    if request.http_status is not None:
        evidence.append(
            Evidence(type="http", summary=f"HTTP status: {request.http_status}")
        )

    if request.trace_id:
        evidence.append(
            Evidence(type="trace", summary=f"Trace ID: {request.trace_id}")
        )

    if request.exception_type:
        evidence.append(
            Evidence(
                type="exception",
                summary=f"Exception: {request.exception_type}",
            )
        )

    message = (request.exception_message or "").lower()
    exception_type = (request.exception_type or "").lower()

    if "duplicatekey" in exception_type or "unique constraint" in message or "duplicate key" in message:
        constraint = "unknown unique constraint"
        if "uk_user_phone" in message:
            constraint = "uk_user_phone"

        evidence.append(
            Evidence(
                type="database",
                summary=f"Database unique constraint violation: {constraint}",
            )
        )

        return InvestigationResponse(
            incident_id=incident_id,
            status="diagnosed",
            root_cause=RootCause(
                category="database_unique_violation",
                summary="The operation attempted to create data that violates a database uniqueness rule.",
                confidence=0.98,
            ),
            evidence=evidence,
            customer_answer=(
                "The operation failed because the submitted information already exists. "
                "Please check the existing record or use a different value."
            ),
            engineer_answer=(
                f"A database uniqueness violation was detected ({constraint}). "
                "Map this exception to a business error instead of returning a generic 500 response."
            ),
            recommended_actions=[
                "Return a business-specific conflict response instead of HTTP 500.",
                "Show a clear validation message to the end user.",
                "Confirm whether the duplicate record is expected or caused by a retry/race condition.",
            ],
        )

    if request.http_status and request.http_status >= 500:
        return InvestigationResponse(
            incident_id=incident_id,
            status="insufficient_evidence",
            root_cause=None,
            evidence=evidence,
            customer_answer=(
                "The request failed on the server, but ProdMind does not yet have enough evidence "
                "to identify the exact cause."
            ),
            engineer_answer=(
                "A server-side failure was observed. Connect traces and logs for this request "
                "before assigning a root cause."
            ),
            recommended_actions=[
                "Correlate the request with an OpenTelemetry trace.",
                "Collect related application logs from the same time window.",
            ],
        )

    return InvestigationResponse(
        incident_id=incident_id,
        status="insufficient_evidence",
        root_cause=None,
        evidence=evidence,
        customer_answer="ProdMind does not yet have enough evidence to explain this operation.",
        engineer_answer="No supported failure signature was found in the supplied evidence.",
        recommended_actions=["Provide a trace ID, HTTP status, or exception evidence."],
    )
