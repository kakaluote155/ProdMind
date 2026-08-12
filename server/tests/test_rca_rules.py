from app.investigation import investigate
from app.models import InvestigationRequest
from app.policies import to_customer_response


def test_database_unique_violation_rule():
    result = investigate(
        InvestigationRequest(
            question="Why did this fail?",
            action="create-user",
            http_status=500,
            exception_type="org.springframework.dao.DuplicateKeyException",
            exception_message='ERROR: duplicate key value violates unique constraint "uk_user_phone"',
        )
    )

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "database_unique_violation"
    assert any(item.type == "database" for item in result.evidence)
    assert to_customer_response(result).category == "duplicate_data"


def test_downstream_unavailable_rule():
    result = investigate(
        InvestigationRequest(
            question="Why did payment fail?",
            action="charge-payment",
            http_status=500,
            exception_type="org.springframework.web.client.ResourceAccessException",
            exception_message="I/O error on POST request: Connection refused",
        )
    )

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "downstream_unavailable"
    assert result.root_cause.confidence == 0.96
    assert any(item.type == "dependency" for item in result.evidence)

    customer = to_customer_response(result)
    assert customer.category == "service_unavailable"
    assert "127.0.0.1" not in customer.answer
    assert "temporarily unavailable" in customer.answer


def test_unknown_500_still_requires_more_evidence():
    result = investigate(
        InvestigationRequest(
            question="Why did this fail?",
            action="unknown-action",
            http_status=500,
            exception_type="UnexpectedException",
            exception_message="Something unsupported happened",
        )
    )

    assert result.status == "insufficient_evidence"
    assert result.root_cause is None
