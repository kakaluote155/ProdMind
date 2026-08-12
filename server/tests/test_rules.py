from app.investigation import investigate
from app.models import InvestigationRequest
from app.policies import to_customer_response


def test_database_unique_rule_matches_duplicate_key():
    result = investigate(
        InvestigationRequest(
            question="Why did creating the user fail?",
            action="create-user",
            http_status=500,
            exception_type="org.springframework.dao.DuplicateKeyException",
            exception_message='duplicate key value violates unique constraint "uk_user_phone"',
        )
    )

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "database_unique_violation"
    assert any(item.type == "database" for item in result.evidence)

    customer = to_customer_response(result)
    assert customer.category == "duplicate_data"
    assert "uk_user_phone" not in customer.answer


def test_downstream_unavailable_rule_matches_connection_refused():
    result = investigate(
        InvestigationRequest(
            question="Why did payment fail?",
            action="charge-payment",
            http_status=500,
            exception_type="org.springframework.web.client.ResourceAccessException",
            exception_message=(
                "I/O error on POST request for http://127.0.0.1:65530/charge: "
                "Connection refused"
            ),
        )
    )

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "downstream_unavailable"
    assert any(item.type == "dependency" for item in result.evidence)

    customer = to_customer_response(result)
    assert customer.category == "service_unavailable"
    assert "127.0.0.1" not in customer.answer
    assert "65530" not in customer.answer


def test_unknown_server_failure_is_not_guessed():
    result = investigate(
        InvestigationRequest(
            question="Why did it fail?",
            action="unknown-action",
            http_status=500,
            exception_type="RuntimeException",
            exception_message="unexpected failure",
        )
    )

    assert result.status == "insufficient_evidence"
    assert result.root_cause is None
