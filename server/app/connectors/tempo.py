from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..models import ServiceCallSample, SpanSample
from .http import ConnectorHttpOptions


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
    trace_duration_ms: float | None = None
    span_samples: list[SpanSample] = field(default_factory=list)
    service_versions: dict[str, str] = field(default_factory=dict)
    trace_started_at: datetime | None = None
    service_calls: list[ServiceCallSample] = field(default_factory=list)


@dataclass(slots=True)
class _SpanRef:
    """Internal-only raw relationship data; never leaves the Tempo adapter."""

    span_id: str
    parent_span_id: str | None
    service_name: str | None
    name: str
    kind: Any
    duration_ms: float | None
    attributes: dict[str, Any]


class TempoConnector:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        *,
        http_options: ConnectorHttpOptions | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_options = http_options or ConnectorHttpOptions(timeout_seconds=timeout_seconds)

    async def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        async with self.http_options.client() as client:
            return await self.http_options.get_json(
                client,
                f"{self.base_url}/api/traces/{trace_id}",
            )

    @staticmethod
    def extract_facts(trace_id: str, payload: dict[str, Any]) -> TraceFacts:
        http_status: int | None = None
        exception_type: str | None = None
        exception_message: str | None = None
        services: set[str] = set()
        project_ids: set[str] = set()
        unscoped_services: set[str] = set()
        service_versions: dict[str, str] = {}
        failing_operations: list[str] = []
        span_samples: list[SpanSample] = []
        raw_spans: list[_SpanRef] = []
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
            service_version = resource_attributes.get("service.version")
            resource_project_id = resource_attributes.get("prodmind.project.id")
            batch_project_ids: set[str] = set()
            if resource_project_id:
                batch_project_ids.add(str(resource_project_id))
            if service_name:
                services.add(service_name)
                if service_version:
                    service_versions[service_name] = str(service_version)

            scope_spans = (
                resource_span.get("scopeSpans")
                or resource_span.get("instrumentationLibrarySpans")
                or []
            )
            for scope_span in scope_spans:
                for span in scope_span.get("spans", []):
                    name = str(span.get("name") or "unknown-operation")
                    attributes = {
                        item.get("key"): _otel_value(item.get("value"))
                        for item in span.get("attributes", [])
                    }
                    span_project_id = attributes.get("prodmind.project.id")
                    if span_project_id:
                        batch_project_ids.add(str(span_project_id))

                    start_ns = _int_value(span.get("startTimeUnixNano"))
                    end_ns = _int_value(span.get("endTimeUnixNano"))
                    duration_ms: float | None = None
                    if start_ns is not None and end_ns is not None and end_ns >= start_ns:
                        trace_start_ns = start_ns if trace_start_ns is None else min(trace_start_ns, start_ns)
                        trace_end_ns = end_ns if trace_end_ns is None else max(trace_end_ns, end_ns)
                        duration_ms = (end_ns - start_ns) / 1_000_000
                        span_samples.append(
                            SpanSample(
                                name=_safe_span_name(name, attributes),
                                duration_ms=duration_ms,
                                category=_span_category(span, attributes),
                                service_name=service_name,
                                source="tempo",
                            )
                        )

                    span_id = _id_text(span.get("spanId"))
                    if span_id:
                        raw_spans.append(
                            _SpanRef(
                                span_id=span_id,
                                parent_span_id=_id_text(span.get("parentSpanId")),
                                service_name=service_name,
                                name=name,
                                kind=span.get("kind"),
                                duration_ms=duration_ms,
                                attributes=attributes,
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
                        failing_operations.append(name)

                    for event in span.get("events", []):
                        event_attributes = {
                            item.get("key"): _otel_value(item.get("value"))
                            for item in event.get("attributes", [])
                        }
                        exception_type = exception_type or event_attributes.get("exception.type")
                        exception_message = exception_message or event_attributes.get("exception.message")

            project_ids.update(batch_project_ids)
            if service_name and not batch_project_ids:
                unscoped_services.add(service_name)

        trace_duration_ms = None
        trace_started_at = None
        if trace_start_ns is not None:
            trace_started_at = datetime.fromtimestamp(trace_start_ns / 1_000_000_000, tz=UTC)
        if trace_start_ns is not None and trace_end_ns is not None:
            trace_duration_ms = (trace_end_ns - trace_start_ns) / 1_000_000

        span_samples.sort(key=lambda item: item.duration_ms, reverse=True)
        service_calls = _extract_service_calls(raw_spans)

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
            service_versions=service_versions,
            trace_started_at=trace_started_at,
            service_calls=service_calls[:30],
        )


def _extract_service_calls(raw_spans: list[_SpanRef]) -> list[ServiceCallSample]:
    """Derive verified cross-service calls, then discard raw span identifiers."""

    by_id = {span.span_id: span for span in raw_spans}
    calls: list[ServiceCallSample] = []
    seen: set[tuple[str, str, str, int]] = set()

    for child in raw_spans:
        if not _is_server_kind(child.kind) or not child.parent_span_id:
            continue
        parent = by_id.get(child.parent_span_id)
        if parent is None or not _is_client_kind(parent.kind):
            continue
        if not parent.service_name or not child.service_name:
            continue
        if parent.service_name == child.service_name:
            continue

        duration_ms = parent.duration_ms if parent.duration_ms is not None else child.duration_ms
        if duration_ms is None:
            continue
        operation = _safe_http_operation(parent.name, parent.attributes)
        key = (
            parent.service_name,
            child.service_name,
            operation,
            int(round(duration_ms)),
        )
        if key in seen:
            continue
        seen.add(key)
        calls.append(
            ServiceCallSample(
                caller_service=parent.service_name,
                callee_service=child.service_name,
                operation=operation,
                duration_ms=duration_ms,
                source="tempo",
            )
        )

    calls.sort(key=lambda item: item.duration_ms, reverse=True)
    return calls


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

    if any(key.startswith("http.") or key.startswith("url.") for key in attributes):
        return "http"

    kind = span.get("kind")
    if _is_client_kind(kind):
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
    if any(key.startswith("http.") or key.startswith("url.") for key in attributes):
        return _safe_http_operation(name, attributes)
    return name[:300]


def _safe_http_operation(name: str, attributes: dict[str, Any]) -> str:
    method = attributes.get("http.request.method") or attributes.get("http.method")
    path = attributes.get("url.path") or attributes.get("http.route") or attributes.get("http.target")

    if not path:
        full_url = attributes.get("url.full") or attributes.get("http.url")
        if full_url:
            try:
                path = urlsplit(str(full_url)).path
            except ValueError:
                path = None

    safe_path = None
    if path:
        safe_path = str(path).split("?", 1)[0]
        if not safe_path.startswith("/"):
            safe_path = "/" + safe_path.lstrip("/")
        safe_path = safe_path[:220]

    if method and safe_path:
        return f"{str(method).upper()} {safe_path}"[:300]
    if method:
        return str(method).upper()[:300]

    lowered = name.lower()
    if "http://" not in lowered and "https://" not in lowered:
        return name[:300]
    try:
        parsed = urlsplit(name)
        return parsed.path[:300] or "HTTP request"
    except ValueError:
        return "HTTP request"


def _is_server_kind(value: Any) -> bool:
    return value in (2, "SPAN_KIND_SERVER", "SERVER")


def _is_client_kind(value: Any) -> bool:
    return value in (3, "SPAN_KIND_CLIENT", "CLIENT")


def _id_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


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
