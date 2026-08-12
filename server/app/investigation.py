from __future__ import annotations

from uuid import uuid4

from .models import Evidence, InvestigationRequest, InvestigationResponse
from .rules import RULES


def investigate(request: InvestigationRequest) -> InvestigationResponse:
    """Diagnose structured evidence with deterministic, pluggable rules.

    Telemetry connectors gather and normalize evidence. Diagnostic rules decide
    whether that evidence is strong enough to assign a root cause. This keeps
    vendor-specific collection logic separate from reusable RCA knowledge.
    """

    incident_id = f"PM-{uuid4().hex[:8].upper()}"
    evidence = _base_evidence(request)

    for rule in RULES:
        match = rule.evaluate(request)
        if match is None:
            continue
        return InvestigationResponse(
            incident_id=incident_id,
            status="diagnosed",
            root_cause=match.root_cause,
            evidence=evidence + match.evidence,
            customer_answer=match.customer_answer,
            engineer_answer=match.engineer_answer,
            recommended_actions=match.recommended_actions,
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
        engineer_answer="No diagnostic rule matched the supplied evidence.",
        recommended_actions=["Provide a trace ID, HTTP status, or exception evidence."],
    )


def _base_evidence(request: InvestigationRequest) -> list[Evidence]:
    evidence: list[Evidence] = []
    if request.action:
        evidence.append(Evidence(type="user_action", summary=f"User action: {request.action}"))
    if request.http_status is not None:
        evidence.append(Evidence(type="http", summary=f"HTTP status: {request.http_status}"))
    if request.trace_id:
        evidence.append(Evidence(type="trace", summary=f"Trace ID: {request.trace_id}"))
    if request.exception_type:
        evidence.append(Evidence(type="exception", summary=f"Exception: {request.exception_type}"))
    return evidence
