from app.connectors.tempo import TempoConnector
from app.evidence_graph import build_evidence_graph
from app.investigation import investigate
from app.models import (
    Evidence,
    InvestigationRequest,
    ServiceCallSample,
    ServiceSample,
    ServiceTopology,
    SpanSample,
)
from app.policies import to_customer_response


def test_tempo_derives_cross_service_call_without_exposing_span_ids():
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
                                "spanId": "root-server-span",
                                "name": "POST /api/journey/slow",
                                "kind": "SPAN_KIND_SERVER",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "3650000000",
                                "attributes": [
                                    {"key": "http.response.status_code", "value": {"intValue": "200"}},
                                    {"key": "http.route", "value": {"stringValue": "/api/journey/slow"}},
                                ],
                                "status": {"code": "STATUS_CODE_UNSET"},
                                "events": [],
                            },
                            {
                                "spanId": "client-span-secret-id",
                                "parentSpanId": "root-server-span",
                                "name": "POST",
                                "kind": "SPAN_KIND_CLIENT",
                                "startTimeUnixNano": "1050000000",
                                "endTimeUnixNano": "3550000000",
                                "attributes": [
                                    {"key": "http.request.method", "value": {"stringValue": "POST"}},
                                    {"key": "url.full", "value": {"stringValue": "http://demo-slow-service:8090/api/dependency/slow?secret=ignored"}},
                                ],
                                "status": {"code": "STATUS_CODE_UNSET"},
                                "events": [],
                            },
                        ]
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "demo-slow-service"}},
                        {"key": "service.version", "value": {"stringValue": "slow-v1"}},
                        {"key": "prodmind.project.id", "value": {"stringValue": "demo"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "spanId": "downstream-server-secret-id",
                                "parentSpanId": "client-span-secret-id",
                                "name": "POST /api/dependency/slow",
                                "kind": "SPAN_KIND_SERVER",
                                "startTimeUnixNano": "1100000000",
                                "endTimeUnixNano": "3500000000",
                                "attributes": [
                                    {"key": "http.response.status_code", "value": {"intValue": "200"}},
                                    {"key": "http.route", "value": {"stringValue": "/api/dependency/slow"}},
                                ],
                                "status": {"code": "STATUS_CODE_UNSET"},
                                "events": [],
                            }
                        ]
                    }
                ],
            },
        ]
    }

    facts = TempoConnector.extract_facts("multi-service-trace", payload)

    assert facts.services == ["demo-slow-service", "demo-user-service"]
    assert facts.project_ids == ["demo"]
    assert facts.trace_duration_ms == 2650
    assert facts.service_versions == {
        "demo-user-service": "demo-v2",
        "demo-slow-service": "slow-v1",
    }
    assert len(facts.service_calls) == 1

    call = facts.service_calls[0]
    assert call.caller_service == "demo-user-service"
    assert call.callee_service == "demo-slow-service"
    assert call.operation == "POST /api/dependency/slow"
    assert call.duration_ms == 2500

    normalized = repr(facts.service_calls) + repr(facts.span_samples)
    assert "client-span-secret-id" not in normalized
    assert "downstream-server-secret-id" not in normalized
    assert "secret=ignored" not in normalized


def test_slow_downstream_rule_requires_dominant_verified_service_call():
    result = investigate(
        InvestigationRequest(
            question="Why was this so slow?",
            action="slow-journey",
            http_status=200,
            trace_duration_ms=2650,
            service_calls=[
                ServiceCallSample(
                    caller_service="demo-user-service",
                    callee_service="demo-slow-service",
                    operation="POST /api/dependency/slow",
                    duration_ms=2500,
                    source="tempo",
                )
            ],
        )
    )

    assert result.status == "diagnosed"
    assert result.root_cause is not None
    assert result.root_cause.category == "slow_downstream_service"
    assert result.root_cause.confidence == 0.98
    assert any(item.type == "dependency" for item in result.evidence)

    customer = to_customer_response(result)
    assert customer.category == "slow_operation"
    assert "demo-slow-service" not in customer.answer
    assert "/api/dependency/slow" not in customer.answer


def test_cross_service_critical_path_wins_over_nested_database_latency():
    result = investigate(
        InvestigationRequest(
            question="Why was this so slow?",
            action="slow-journey",
            http_status=200,
            trace_duration_ms=3000,
            service_calls=[
                ServiceCallSample(
                    caller_service="frontend-service",
                    callee_service="report-service",
                    operation="POST /report",
                    duration_ms=2800,
                    source="tempo",
                )
            ],
            span_samples=[
                SpanSample(
                    name="database SELECT",
                    duration_ms=2500,
                    category="database",
                    service_name="report-service",
                    source="tempo",
                )
            ],
        )
    )

    assert result.root_cause is not None
    assert result.root_cause.category == "slow_downstream_service"


def test_non_dominant_service_call_does_not_get_blame():
    result = investigate(
        InvestigationRequest(
            question="Why was this slow?",
            action="slow-journey",
            http_status=200,
            trace_duration_ms=3000,
            service_calls=[
                ServiceCallSample(
                    caller_service="frontend-service",
                    callee_service="small-service",
                    operation="GET /small",
                    duration_ms=800,
                    source="tempo",
                )
            ],
        )
    )

    assert result.status == "insufficient_evidence"
    assert result.root_cause is None


def test_slow_downstream_dependency_is_visible_in_evidence_graph():
    result = investigate(
        InvestigationRequest(
            question="Why was this so slow?",
            action="slow-journey",
            trace_id="66666666666666666666666666666666",
            http_status=200,
            trace_duration_ms=2650,
            service_calls=[
                ServiceCallSample(
                    caller_service="demo-user-service",
                    callee_service="demo-slow-service",
                    operation="POST /api/dependency/slow",
                    duration_ms=2500,
                    source="tempo",
                )
            ],
        )
    )
    result.evidence.extend(
        [
            Evidence(
                type="trace",
                summary="Services in trace: demo-slow-service -> demo-user-service",
                source="tempo",
            ),
            Evidence(
                type="dependency",
                summary=(
                    "Cross-service call: demo-user-service -> demo-slow-service "
                    "via POST /api/dependency/slow took 2500 ms"
                ),
                source="tempo",
            ),
        ]
    )

    graph = build_evidence_graph(result)
    dependency_nodes = [node for node in graph.nodes if node.kind == "dependency"]

    assert graph.root_cause is not None
    assert graph.root_cause.category == "slow_downstream_service"
    assert graph.root_cause_node_id is not None
    assert dependency_nodes
    assert any(
        edge.source in {node.id for node in dependency_nodes}
        and edge.target == graph.root_cause_node_id
        and edge.relation in {"supports", "diagnoses"}
        for edge in graph.edges
    )


def test_layered_graph_separates_services_calls_and_downstream_operations():
    call = ServiceCallSample(
        caller_service="demo-user-service",
        callee_service="demo-slow-service",
        operation="POST /api/dependency/slow",
        duration_ms=2500,
        source="tempo",
    )
    downstream_database = SpanSample(
        name="database SELECT",
        duration_ms=2200,
        category="database",
        service_name="demo-slow-service",
        source="tempo",
    )
    result = investigate(
        InvestigationRequest(
            question="Why was this so slow?",
            action="slow-journey",
            trace_id="77777777777777777777777777777777",
            http_status=200,
            trace_duration_ms=2700,
            service_calls=[call],
            span_samples=[downstream_database],
        )
    )
    result.service_topology = ServiceTopology(
        services=[
            ServiceSample(name="demo-user-service", version="demo-v2", source="tempo"),
            ServiceSample(name="demo-slow-service", version="slow-v1", source="tempo"),
        ],
        calls=[call],
        spans=[downstream_database],
    )
    result.evidence.extend(
        [
            Evidence(
                type="trace",
                summary="Services in trace: demo-slow-service -> demo-user-service",
                source="tempo",
            ),
            Evidence(
                type="dependency",
                service_name="demo-slow-service",
                summary=(
                    "Cross-service call: demo-user-service -> demo-slow-service "
                    "via POST /api/dependency/slow took 2500 ms"
                ),
                source="tempo",
            ),
        ]
    )

    graph = build_evidence_graph(result)
    services = {node.label.split(" · ", 1)[0]: node for node in graph.nodes if node.kind == "service"}
    operations = [node for node in graph.nodes if node.kind == "operation"]
    dependencies = [node for node in graph.nodes if node.kind == "dependency"]

    assert set(services) == {"demo-user-service", "demo-slow-service"}
    assert all("Services in trace:" not in node.label for node in graph.nodes)
    assert any(
        edge.source == services["demo-user-service"].id
        and edge.target == services["demo-slow-service"].id
        and edge.relation == "calls"
        for edge in graph.edges
    )
    assert any(
        edge.source == services["demo-slow-service"].id
        and edge.target in {node.id for node in operations}
        and edge.relation == "contains"
        for edge in graph.edges
    )
    assert any(
        edge.source == services["demo-slow-service"].id
        and edge.target in {node.id for node in dependencies}
        and edge.relation == "contains"
        for edge in graph.edges
    )

    serialized = graph.model_dump_json()
    assert "spanId" not in serialized
    assert "parentSpanId" not in serialized
