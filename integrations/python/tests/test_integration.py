import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from prodmind_integration import PROJECT_ATTRIBUTE, ProdMindASGIMiddleware, validate_project_id


def test_project_id_uses_server_compatible_public_format():
    assert validate_project_id("customer.portal-1") == "customer.portal-1"
    for invalid in ("", "bad project", "../other", "x" * 65):
        with pytest.raises(ValueError):
            validate_project_id(invalid)


def test_asgi_middleware_marks_current_http_span_without_reading_request_data():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    observed_scope = None

    async def app(scope, receive, send):
        nonlocal observed_scope
        observed_scope = scope

    middleware = ProdMindASGIMiddleware(app, project_id="project-a")
    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer must-not-be-collected")],
    }

    async def receive():
        return {"type": "http.request", "body": b"secret-body"}

    async def send(_message):
        return None

    with tracer.start_as_current_span("request"):
        asyncio.run(middleware(scope, receive, send))

    spans = exporter.get_finished_spans()
    assert spans[0].attributes[PROJECT_ATTRIBUTE] == "project-a"
    assert observed_scope is scope
    assert "authorization" not in spans[0].attributes
    assert "secret-body" not in str(spans[0].attributes)


def test_non_http_asgi_scope_is_not_tagged():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    async def app(_scope, _receive, _send):
        return None

    middleware = ProdMindASGIMiddleware(app, project_id="project-a")

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(_message):
        return None

    with tracer.start_as_current_span("startup"):
        asyncio.run(middleware({"type": "lifespan"}, receive, send))

    assert PROJECT_ATTRIBUTE not in exporter.get_finished_spans()[0].attributes
