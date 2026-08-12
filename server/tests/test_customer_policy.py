from app.models import Evidence, InvestigationResponse, RootCause
from app.policies import sanitize_customer_text, to_customer_response


def test_customer_response_omits_engineer_evidence():
    internal = InvestigationResponse(
        incident_id="PM-TEST",
        status="diagnosed",
        root_cause=RootCause(
            category="database_unique_violation",
            summary="PostgreSQL unique constraint uk_user_phone failed",
            confidence=0.98,
        ),
        evidence=[
            Evidence(type="trace", summary="Trace ID: abc", source="tempo"),
            Evidence(type="database", summary="Constraint: uk_user_phone"),
        ],
        customer_answer="The submitted information already exists.",
        engineer_answer="DuplicateKeyException on uk_user_phone at 10.0.0.5",
        recommended_actions=["Inspect SQL"],
    )

    customer = to_customer_response(internal)
    payload = customer.model_dump()

    assert payload["category"] == "duplicate_data"
    assert payload["confidence"] == 0.98
    assert "evidence" not in payload
    assert "engineer_answer" not in payload
    assert "root_cause" not in payload
    assert "uk_user_phone" not in str(payload)
    assert "10.0.0.5" not in str(payload)


def test_customer_text_redacts_sensitive_infrastructure_details():
    unsafe = (
        "Connect to 10.24.1.8 using jdbc:postgresql://10.24.1.8:5432/prod "
        "password=hunter2 and inspect /opt/app/config.yml"
    )

    safe = sanitize_customer_text(unsafe)

    assert "10.24.1.8" not in safe
    assert "jdbc:postgresql" not in safe
    assert "hunter2" not in safe
    assert "/opt/app/config.yml" not in safe
    assert "[redacted" in safe
