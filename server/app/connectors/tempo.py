from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..models import SpanSample


@dataclass(slots=True)
class TraceFacts:
    trace_id: str
    http_status: int | None
    exception_type: str | None
    exception_message: str | None
    services: list[str]
    project_ids: list[str]
    unscoped_services: list[str]
    failing_operations: list[str]
    trace_duration_ms: float | None
    span_samples: list[SpanSample]


class TempoConnector:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/api/traces/{trace_id}")
            response.raise_for_status()
            return response.json()

    @staticmethod
    def extract_facts(trace_id: str, payload: dict[str, Any]) -> TraceFacts:
        http_status: int | None = None
        exception_type: str | None = None
        exception_message: str | None = None
        services: set[str] = set()
        project_ids: set[str] = set()
        unscoped_services: set[str] = set()
        failing_operations: list[str] = []
        span_samples: list[SpanSample] = []
        trace_start_ns: int | None = None
        trace_end_ns: int | None = None

        resource_spans = payload.get("batches") or payload.get("resourceSpans") or []
        for resource_span in resource_spans:
            resource = resource_span.get("resource", {})
            resource_attributes = {
                attr.get("key"): _otel_value(attr.get("value"))
                for attr in resource.get("attributes", [])
            }

            service_name_raw = resource_attributes.get("service.name")
            service_name = str(service_name_raw) if service_name_raw else None
            project_id = resource_attributes.get("prodmind.project.id")
            if service_name:
                services.add(service_name)
                if not project_id:
                    unscoped_services.add(service_name)
            if project_id:
                project_ids.add(str(project_id))

            scope_spans = (
                resource_span.get("scopeSpans")
                or resource_span.get("instrumentationLibrarySpans")
                or []
            )
            for scope_span in scope_spans:
                for span in scope_span.get("spans", []):
                    name = span.get("name") or "unknown-operation"
                    attributes = {
                        item.get("key"): _otel_value(item.get("value"))
                        for item in span.get("attributes", [])
                    }

                    start_ns = _int_value(span.get("startTimeUnixNano"))
                    end_ns = _int_value(span.get("endTimeUnixNano"))
                    if start_ns is not None and end_ns is not None and end_ns >= start_ns:
                        trace_start_ns = start_ns if trace_start_ns is None else min(trace_start_ns, start_ns)
                        trace_end_ns = end_ns if trace_end_ns is None else max(trace_end_ns, end_ns)
                        duration_ms = (end_ns - start_ns) / 1_000_000
                        span_samples.append(
                            SpanSample(
                                name=_safe_span_name(str(name), attributes),
                                duration_ms=duration_ms,
                                category=_span_category(span, attributes),
                                service_name=service_name,
                                source="tempo",
                            )
                        )

                    candidate_status = (
                        attributes.get("http.response.status_code")
                        or attributes.get("http.status_code")
                    )
                    if candidate_status is not None:
                        try:
                            status_number = int(candidate_status)
                            if http_status is None or status_number >= http_status:
                                http_status = status_number
                        except (TypeError, ValueError):
                            pass

                    span_status = span.get("status", {})
                    status_code = span_status.get("code")
                    if status_code in (2, "STATUS_CODE_ERROR", "ERROR"):
                        failing_operations.append(str(name))

                    for event in span.get("events", []):
                        event_attributes = {
                            item.get("key"): _otel_value(item.get("value"))
                            for item in event.get("attributes", [])
                        }
                        exception_type = exception_type or event_attributes.get("exception.type")
                        exception_message = exception_message or event_attributes.get("exception.message")

        trace_duration_ms = None
        if trace_start_ns is not None and trace_end_ns is not None:
            trace_duration_ms = (trace_end_ns - trace_start_ns) / 1_000_000

        # Keep the most expensive spans. Rules do not need the entire raw trace.
        span_samples.sort(key=lambda item: item.duration_ms, reverse=True)

        return TraceFacts(
            trace_id=trace_id,
            http_status=http_status,
            exception_type=str(exception_type) if exception_type else None,
            exception_message=str(exception_message) if exception_message else None,
            services=sorted(services),
            project_ids=sorted(project_ids),
            unscoped_services=sorted(unscoped_services),
            failing_operations=failing_operations,
            trace_duration_ms=trace_duration_ms,
            span_samples=span_samples[:50],
        )


def _span_category(span: dict[str, Any], attributes: dict[str, Any]) -> str:
    if any(
        key in attributes
        for key in (
            "db.system",
            "db.system.name",
            "db.operation",
            "db.operation.name",
            "db.namespace",
            "db.name",
        )
    ):
        return "database"

    if any(key.startswith("http.") for key in attributes):
        return "http"

    kind = span.get("kind")
    if kind in (3, "SPAN_KIND_CLIENT", "CLIENT"):
        return "client"
    if kind in (1, "SPAN_KIND_INTERNAL", "INTERNAL"):
        return "internal"
    return "other"


def _safe_span_name(name: str, attributes: dict[str, Any]) -> str:
    if any(
        key in attributes
        for key in ("db.system", "db.system.name", "db.operation", "db.operation.name")
    ):
        operation = attributes.get("db.operation.name") or attributes.get("db.operation")
        if operation:
            return f"database {str(operation).upper()}"
        first = name.strip().split(" ", 1)[0].upper()
        if first in {"SELECT", "INSERT", "UPDATE", "DELETE", "CALL", "EXECUTE"}:
            return f"database {first}"
        return "database operation"
    return name[:300]


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _otel_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in (
        "stringValue",
        "intValue",
        "doubleValue",
        "boolValue",
        "bytesValue",
    ):
        if key in value:
            return value[key]
    return value.get("value")
