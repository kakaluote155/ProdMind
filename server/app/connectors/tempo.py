from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class TraceFacts:
    trace_id: str
    http_status: int | None
    exception_type: str | None
    exception_message: str | None
    services: list[str]
    failing_operations: list[str]


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
        failing_operations: list[str] = []

        resource_spans = payload.get("batches") or payload.get("resourceSpans") or []
        for resource_span in resource_spans:
            resource = resource_span.get("resource", {})
            for attr in resource.get("attributes", []):
                if attr.get("key") == "service.name":
                    value = _otel_value(attr.get("value"))
                    if value:
                        services.add(str(value))

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

        return TraceFacts(
            trace_id=trace_id,
            http_status=http_status,
            exception_type=str(exception_type) if exception_type else None,
            exception_message=str(exception_message) if exception_message else None,
            services=sorted(services),
            failing_operations=failing_operations,
        )


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
