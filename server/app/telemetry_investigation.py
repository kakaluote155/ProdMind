from __future__ import annotations

import os

import httpx

from .connectors.loki import LokiConnector
from .connectors.tempo import TempoConnector
from .investigation import investigate
from .models import Evidence, InvestigationRequest, InvestigationResponse, TraceInvestigationRequest


async def investigate_from_trace(request: TraceInvestigationRequest) -> InvestigationResponse:
    tempo = TempoConnector(os.getenv("PRODMIND_TEMPO_URL", "http://tempo:3200"))
    loki = LokiConnector(os.getenv("PRODMIND_LOKI_URL", "http://loki:3100"))

    trace_evidence: list[Evidence] = [
        Evidence(type="trace", summary=f"Trace ID: {request.trace_id}", source="tempo")
    ]

    try:
        trace_payload = await tempo.fetch_trace(request.trace_id)
    except httpx.HTTPError as exc:
        return InvestigationResponse(
            incident_id=f"PM-TRACE-{request.trace_id[:8].upper()}",
            status="insufficient_evidence",
            root_cause=None,
            evidence=trace_evidence,
            customer_answer="ProdMind found the operation identifier but could not retrieve its telemetry yet.",
            engineer_answer=f"Tempo trace lookup failed: {type(exc).__name__}",
            recommended_actions=[
                "Verify that Tempo is reachable from ProdMind.",
                "Confirm that the supplied trace ID has been ingested.",
            ],
        )

    facts = tempo.extract_facts(request.trace_id, trace_payload)
    if facts.services:
        trace_evidence.append(
            Evidence(
                type="trace",
                summary="Services in trace: " + " -> ".join(facts.services),
                source="tempo",
            )
        )
    for operation in facts.failing_operations[:5]:
        trace_evidence.append(
            Evidence(
                type="trace",
                summary=f"Failing span: {operation}",
                source="tempo",
            )
        )

    service_name = facts.services[0] if facts.services else "demo-user-service"
    log_facts = None
    try:
        log_facts = await loki.query_trace_logs(request.trace_id, service_name=service_name)
    except httpx.HTTPError:
        # Trace evidence remains useful even when logs are temporarily unavailable.
        pass

    if log_facts and log_facts.lines:
        trace_evidence.append(
            Evidence(
                type="log",
                summary=f"Found {len(log_facts.lines)} correlated log record(s).",
                source="loki",
            )
        )
        for line in log_facts.lines[:3]:
            trace_evidence.append(
                Evidence(type="log", summary=_shorten(line), source="loki")
            )

    exception_type = facts.exception_type
    exception_message = facts.exception_message
    if log_facts:
        exception_type = exception_type or log_facts.exception_type
        exception_message = exception_message or log_facts.exception_message

    result = investigate(
        InvestigationRequest(
            question=request.question,
            action=request.action,
            page=request.page,
            trace_id=request.trace_id,
            http_status=facts.http_status,
            exception_type=exception_type,
            exception_message=exception_message,
        )
    )

    # Keep the deterministic RCA output, but attach the evidence that came from
    # real telemetry so users can see why the answer was reached.
    result.evidence = _deduplicate(trace_evidence + result.evidence)
    return result


def _shorten(value: str, limit: int = 500) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _deduplicate(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str, str | None]] = set()
    result: list[Evidence] = []
    for item in items:
        key = (item.type, item.summary, item.source)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
