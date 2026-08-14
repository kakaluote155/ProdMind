from app.connectors.loki import _escape_logql, _extract_exception
from app.connectors.http import ConnectorHttpOptions, configured_http_options
from app.connectors.prometheus import _escape_label, _extract_query_value
from app.connectors.tempo import TempoConnector
from app.config import ConfigurationError, validated_http_url
import pytest
import httpx


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_tempo_extracts_service_project_version_http_error_and_exception():
    payload = {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "demo-user-service"}},
                        {"key": "service.version", "value": {"stringValue": "demo-v2"}},
                        {"key": "prodmind.project.id", "value": {"stringValue": "demo"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "POST /api/users",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1100000000",
                                "attributes": [
                                    {"key": "http.response.status_code", "value": {"intValue": "500"}}
                                ],
                                "status": {"code": "STATUS_CODE_ERROR"},
                                "events": [
                                    {
                                        "attributes": [
                                            {"key": "exception.type", "value": {"stringValue": "DuplicateKeyException"}},
                                            {"key": "exception.message", "value": {"stringValue": "duplicate key violates unique constraint uk_user_phone"}},
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    facts = TempoConnector.extract_facts("abc123", payload)

    assert facts.services == ["demo-user-service"]
    assert facts.project_ids == ["demo"]
    assert facts.service_versions == {"demo-user-service": "demo-v2"}
    assert facts.trace_started_at is not None
    assert facts.trace_started_at.timestamp() == 1.0
    assert facts.unscoped_services == []
    assert facts.http_status == 500
    assert facts.exception_type == "DuplicateKeyException"
    assert "uk_user_phone" in facts.exception_message
    assert facts.failing_operations == ["POST /api/users"]


def test_tempo_extracts_successful_trace_timing_without_raw_sql_name():
    payload = {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "demo-user-service"}},
                        {"key": "prodmind.project.id", "value": {"stringValue": "demo"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "POST /api/reports/slow",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "4100000000",
                                "kind": "SPAN_KIND_SERVER",
                                "attributes": [
                                    {"key": "http.response.status_code", "value": {"intValue": "200"}},
                                    {"key": "http.route", "value": {"stringValue": "/api/reports/slow"}},
                                ],
                                "status": {"code": "STATUS_CODE_UNSET"},
                                "events": [],
                            },
                            {
                                "name": "SELECT sensitive_table",
                                "startTimeUnixNano": "1050000000",
                                "endTimeUnixNano": "4050000000",
                                "kind": "SPAN_KIND_CLIENT",
                                "attributes": [
                                    {"key": "db.system.name", "value": {"stringValue": "postgresql"}},
                                    {"key": "db.operation.name", "value": {"stringValue": "SELECT"}},
                                ],
                                "status": {"code": "STATUS_CODE_UNSET"},
                                "events": [],
                            },
                        ]
                    }
                ],
            }
        ]
    }

    facts = TempoConnector.extract_facts("slow-trace", payload)

    assert facts.http_status == 200
    assert facts.trace_duration_ms == 3100
    database = [sample for sample in facts.span_samples if sample.category == "database"]
    assert len(database) == 1
    assert database[0].duration_ms == 3000
    assert database[0].name == "database SELECT"
    assert "sensitive_table" not in database[0].name


def test_tempo_marks_services_without_project_resource_attribute_as_unscoped():
    payload = {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "legacy-service"}}
                    ]
                },
                "scopeSpans": [],
            }
        ]
    }

    facts = TempoConnector.extract_facts("abc123", payload)
    assert facts.project_ids == []
    assert facts.unscoped_services == ["legacy-service"]


def test_tempo_accepts_server_configured_project_span_attribute():
    payload = {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "integrated-service"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "GET /orders",
                                "attributes": [
                                    {
                                        "key": "prodmind.project.id",
                                        "value": {"stringValue": "project-a"},
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    facts = TempoConnector.extract_facts("abc123", payload)

    assert facts.project_ids == ["project-a"]
    assert facts.unscoped_services == []


def test_tempo_preserves_conflicting_resource_and_span_projects_for_fail_closed_check():
    payload = {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "conflicting-service"}},
                        {"key": "prodmind.project.id", "value": {"stringValue": "project-a"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "GET /orders",
                                "attributes": [
                                    {
                                        "key": "prodmind.project.id",
                                        "value": {"stringValue": "project-b"},
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    facts = TempoConnector.extract_facts("abc123", payload)

    assert facts.project_ids == ["project-a", "project-b"]


def test_loki_detects_duplicate_key_signature():
    lines = [
        "trace_id=abc operation=create_user failed org.springframework.dao.DuplicateKeyException: "
        "duplicate key value violates unique constraint uk_user_phone"
    ]

    exception_type, message = _extract_exception(lines)

    assert exception_type == "DuplicateKeyException"
    assert "uk_user_phone" in message


def test_loki_detects_connection_pool_acquisition_timeout():
    lines = [
        "trace_id=abc operation=POST_/api/pool/probe failed "
        "org.springframework.jdbc.CannotGetJdbcConnectionException: "
        "HikariPool-1 - Connection is not available, request timed out after 2500ms"
    ]

    exception_type, message = _extract_exception(lines)

    assert exception_type == "CannotGetJdbcConnectionException"
    assert "HikariPool-1" in message


def test_prometheus_extracts_vector_and_scalar_values():
    vector = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [123, "2"]}],
        },
    }
    scalar = {
        "status": "success",
        "data": {"resultType": "scalar", "result": [123, "1.5"]},
    }

    assert _extract_query_value(vector) == 2.0
    assert _extract_query_value(scalar) == 1.5
    assert _extract_query_value({"status": "success", "data": {"resultType": "vector", "result": []}}) is None
    assert _extract_query_value({"status": "error"}) is None


def test_prometheus_label_values_are_escaped():
    assert _escape_label('demo"service\\node\n') == 'demo\\"service\\\\node\\n'


def test_loki_query_values_are_escaped():
    assert _escape_logql('service"} |= "secret\\node\n') == (
        'service\\"} |= \\"secret\\\\node\\n'
    )


def test_connector_http_options_are_bounded_and_support_bearer_auth(monkeypatch):
    monkeypatch.setenv("PRODMIND_CONNECTOR_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("PRODMIND_CONNECTOR_MAX_RESPONSE_BYTES", "4096")
    monkeypatch.setenv("PRODMIND_TEMPO_BEARER_TOKEN", "tempo-secret")
    options = configured_http_options("tempo")

    assert options.timeout_seconds == 2.5
    assert options.max_response_bytes == 4096
    assert options.bearer_token == "tempo-secret"


def test_connector_base_url_rejects_embedded_credentials_and_query(monkeypatch):
    monkeypatch.setenv("PRODMIND_TEMPO_URL", "https://user:secret@tempo.example/api?tenant=a")
    with pytest.raises(ConfigurationError):
        validated_http_url("PRODMIND_TEMPO_URL", "http://tempo:3200")


@pytest.mark.anyio
async def test_connector_response_limit_is_enforced_while_streaming():
    options = ConnectorHttpOptions(max_response_bytes=8)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b'{"value":"too-large"}', request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.DecodingError, match="exceeds configured limit"):
            await options.get_json(client, "https://tempo.example/api/traces/abc")
