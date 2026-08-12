from app.connectors.loki import _extract_exception
from app.connectors.tempo import TempoConnector


def test_tempo_extracts_service_project_http_error_and_exception():
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
                                "name": "POST /api/users",
                                "attributes": [
                                    {
                                        "key": "http.response.status_code",
                                        "value": {"intValue": "500"},
                                    }
                                ],
                                "status": {"code": "STATUS_CODE_ERROR"},
                                "events": [
                                    {
                                        "attributes": [
                                            {
                                                "key": "exception.type",
                                                "value": {"stringValue": "DuplicateKeyException"},
                                            },
                                            {
                                                "key": "exception.message",
                                                "value": {
                                                    "stringValue": "duplicate key violates unique constraint uk_user_phone"
                                                },
                                            },
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
    assert facts.unscoped_services == []
    assert facts.http_status == 500
    assert facts.exception_type == "DuplicateKeyException"
    assert "uk_user_phone" in facts.exception_message
    assert facts.failing_operations == ["POST /api/users"]


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


def test_loki_detects_duplicate_key_signature():
    lines = [
        "trace_id=abc operation=create_user failed org.springframework.dao.DuplicateKeyException: "
        "duplicate key value violates unique constraint uk_user_phone"
    ]

    exception_type, message = _extract_exception(lines)

    assert exception_type == "DuplicateKeyException"
    assert "uk_user_phone" in message
