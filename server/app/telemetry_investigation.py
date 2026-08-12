from __future__ import annotations

import os
from functools import lru_cache

import httpx

from .connectors.loki import LokiConnector
from .connectors.prometheus import PrometheusConnector
from .connectors.tempo import TempoConnector, TraceFacts
from .investigation import investigate
from .memory import IncidentMemoryStore
from .models import Evidence, InvestigationRequest, InvestigationResponse, MetricSample, TraceInvestigationRequest


class TraceAccessError(Exception):
    """The requested trace is unavailable inside the declared project boundary."""


@lru_cache(maxsize=1)
def _memory_store() -> IncidentMemoryStore:
    path = os.getenv("PRODMIND_MEMORY_PATH", ".prodmind/prodmind-memory.db")
    return IncidentMemoryStore(path)


async def investigate_from_trace(
    request: TraceInvestigationRequest,
    *,
    project_id: str,
) -> InvestigationResponse:
    tempo = TempoConnector(os.getenv("PRODMIND_TEMPO_URL", "http://tempo:3200"))
    loki = LokiConnector(os.getenv("PRODMIND_LOKI_URL", "http://loki:3100"))
    prometheus = PrometheusConnector(
        os.getenv("PRODMIND_PROMETHEUS_URL", "http://prometheus:9090")
    )

    trace_evidence: list[Evidence] = [
        Evidence(type="trace", summary=f"Trace ID: {request.trace_id}", source="tempo")
    ]

    try:
        trace_payload = await tempo.fetch_trace(request.trace_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise TraceAccessError("trace not available") from exc
        return _telemetry_unavailable(request, trace_evidence, exc)
    except httpx.HTTPError as exc:
        return _telemetry_unavailable(request, trace_evidence, exc)

    facts = tempo.extract_facts(request.trace_id, trace_payload)
    _assert_project_scope(facts, expected_project_id=project_id)

    if facts.services:
        trace_evidence.append(
            Evidence(
                type="trace",
                summary="Services in trace: " + " -> ".join(facts.services),
                source="tempo",
            )
        )
    if facts.trace_duration_ms is not None:
        trace_evidence.append(
            Evidence(
                type="trace",
                summary=f"Trace duration: {facts.trace_duration_ms:.0f} ms",
                source="tempo",
            )
        )
    for operation in facts.failing_operations[:5]:
        trace_evidence.append(
            Evidence(type="trace", summary=f"Failing span: {operation}", source="tempo")
        )
    for sample in facts.span_samples[:5]:
        if sample.duration_ms < 500:
            continue
        trace_evidence.append(
            Evidence(
                type="trace",
                summary=(
                    f"Slow span: {sample.category} {sample.name} "
                    f"took {sample.duration_ms:.0f} ms"
                ),
                source="tempo",
            )
        )

    service_name = facts.services[0] if facts.services else "unknown-service"
    log_facts = None
    try:
        log_facts = await loki.query_trace_logs(request.trace_id, service_name=service_name)
    except httpx.HTTPError:
        # Current trace evidence remains useful even when log delivery is delayed.
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
            trace_evidence.append(Evidence(type="log", summary=_shorten(line), source="loki"))

    exception_type = facts.exception_type
    exception_message = facts.exception_message
    if log_facts:
        exception_type = exception_type or log_facts.exception_type
        exception_message = exception_message or log_facts.exception_message

    metric_samples: list[MetricSample] = []
    if _looks_like_pool_acquisition_timeout(exception_type, exception_message):
        try:
            metric_samples = await prometheus.query_hikari_pool_snapshot(
                project_id=project_id,
                service_name=service_name,
            )
        except (httpx.HTTPError, ValueError):
            # Prometheus is supporting evidence. Existing trace/log diagnoses must
            # continue working when metrics are unavailable.
            metric_samples = []

    result = investigate(
        InvestigationRequest(
            question=request.question,
            action=request.action,
            page=request.page,
            trace_id=request.trace_id,
            http_status=facts.http_status,
            exception_type=exception_type,
            exception_message=exception_message,
            trace_duration_ms=facts.trace_duration_ms,
            span_samples=facts.span_samples,
            metric_samples=metric_samples,
        )
    )
    result.evidence = _deduplicate(trace_evidence + result.evidence)

    if result.status == "diagnosed" and result.root_cause is not None:
        memory = _memory_store()
        matches = memory.find_similar(
            project_id=project_id,
            category=result.root_cause.category,
            action=request.action,
            exclude_trace_id=request.trace_id,
        )
        for match in matches:
            result.evidence.append(
                Evidence(
                    type="history",
                    source="incident-memory",
                    summary=(
                        f"Similar incident {match.incident_id} matched with score {match.score:.2f}; "
                        f"previous root cause: {match.root_summary}; "
                        f"previous resolution: {match.resolution_summary}"
                    ),
                )
            )

        memory.remember(
            project_id=project_id,
            trace_id=request.trace_id,
            action=request.action,
            result=result,
        )

    result.evidence = _deduplicate(result.evidence)
    return result


def _looks_like_pool_acquisition_timeout(
    exception_type: str | None,
    exception_message: str | None,
) -> bool:
    type_text = (exception_type or "").lower()
    message = (exception_message or "").lower()
    return (
        "cannotgetjdbcconnectionexception" in type_text
        or "sqltransientconnectionexception" in type_text
        or "connection is not available" in message
        or ("hikaripool" in message and "timed out" in message)
    )


def _assert_project_scope(facts: TraceFacts, *, expected_project_id: str) -> None:
    if facts.unscoped_services:
        raise TraceAccessError("trace contains unscoped services")
    if facts.project_ids != [expected_project_id]:
        raise TraceAccessError("trace does not belong to requested project")


def _telemetry_unavailable(
    request: TraceInvestigationRequest,
    evidence: list[Evidence],
    exc: Exception,
) -> InvestigationResponse:
    return InvestigationResponse(
        incident_id=f"PM-TRACE-{request.trace_id[:8].upper()}",
        status="insufficient_evidence",
        root_cause=None,
        evidence=evidence,
        customer_answer="ProdMind found the operation identifier but could not retrieve its telemetry yet.",
        engineer_answer=f"Tempo trace lookup failed: {type(exc).__name__}",
        recommended_actions=[
            "Verify that Tempo is reachable from ProdMind.",
            "Confirm that the supplied trace ID has been ingested.",
        ],
    )


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
