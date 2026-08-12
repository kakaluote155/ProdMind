from app.investigation import investigate
from app.models import InvestigationRequest, MetricSample, SpanSample
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


def test_database_pool_exhaustion_requires_metric_corroboration():
    request = InvestigationRequest(
        question="Why is the database operation failing?",
        action="probe-database-pool",
        http_status=500,
        exception_type="org.springframework.jdbc.CannotGetJdbcConnectionException",
        exception_message=(
            "java.sql.SQLTransientConnectionException: HikariPool-1 - "
            "Connection is not available, request timed out after 2500ms"
        ),
    )

    without_metrics = investigate(request)
    assert without_metrics.status == "insufficient_evidence"
    assert without_metrics.root_cause is None

    request.metric_samples = [
        MetricSample(name="db_pool_active", value=2, unit="connections", source="prometheus"),
        MetricSample(name="db_pool_max", value=2, unit="connections", source="prometheus"),
        MetricSample(name="db_pool_pending", value=1, unit="connections", source="prometheus"),
    ]
    result = investigate(request)

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "database_pool_exhausted"
    assert result.root_cause.confidence == 0.99
    assert any(item.type == "database" for item in result.evidence)
    assert any(item.type == "metric" and item.source == "prometheus" for item in result.evidence)

    customer = to_customer_response(result)
    assert customer.category == "service_busy"
    assert "Hikari" not in customer.answer
    assert "2/2" not in customer.answer


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


def test_successful_slow_operation_requires_dominant_database_span():
    request = InvestigationRequest(
        question="Why was my report so slow?",
        action="generate-report",
        http_status=200,
        trace_duration_ms=3100,
        span_samples=[
            SpanSample(
                name="POST /api/reports/slow",
                duration_ms=3100,
                category="http",
                service_name="demo-user-service",
                source="tempo",
            ),
            SpanSample(
                name="database SELECT",
                duration_ms=3000,
                category="database",
                service_name="demo-user-service",
                source="tempo",
            ),
        ],
    )

    result = investigate(request)

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "slow_database_query"
    assert result.root_cause.confidence == 0.98
    assert any(item.type == "database" and "3000 ms" in item.summary for item in result.evidence)

    customer = to_customer_response(result)
    assert customer.category == "slow_operation"
    assert "SELECT" not in customer.answer
    assert "3000" not in customer.answer


def test_slow_request_without_dominant_database_span_stays_unassigned():
    result = investigate(
        InvestigationRequest(
            question="Why was this slow?",
            action="some-action",
            http_status=200,
            trace_duration_ms=3000,
            span_samples=[
                SpanSample(name="database SELECT", duration_ms=900, category="database", source="tempo"),
                SpanSample(name="other work", duration_ms=2000, category="internal", source="tempo"),
            ],
        )
    )

    assert result.status == "insufficient_evidence"
    assert result.root_cause is None


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
