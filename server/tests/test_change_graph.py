from app.evidence_graph import build_evidence_graph
from app.investigation import investigate
from app.models import Evidence, InvestigationRequest


def test_change_node_is_context_for_service_not_causal_root_edge():
    result = investigate(
        InvestigationRequest(
            question="Why did creating the user fail?",
            action="create-user",
            trace_id="55555555555555555555555555555555",
            http_status=500,
            exception_type="DuplicateKeyException",
            exception_message="duplicate key value violates unique constraint uk_user_phone",
        )
    )
    result.evidence.extend(
        [
            Evidence(type="trace", summary="Services in trace: demo-user-service", source="tempo"),
            Evidence(
                type="change",
                summary=(
                    "Recent deployment change CHG-DEMO for demo-user-service version demo-v2; "
                    "trace version matches this change. Temporal context only; not proof of causation."
                ),
                source="change-store",
            ),
        ]
    )

    graph = build_evidence_graph(result)
    change_nodes = [node for node in graph.nodes if node.kind == "change"]
    service_nodes = [node for node in graph.nodes if node.kind == "service"]

    assert len(change_nodes) == 1
    assert change_nodes[0].role == "context"
    assert len(service_nodes) == 1
    assert any(
        edge.source == change_nodes[0].id
        and edge.target == service_nodes[0].id
        and edge.relation == "context_for"
        for edge in graph.edges
    )
    assert not any(
        edge.source == change_nodes[0].id and edge.relation in {"supports", "diagnoses"}
        for edge in graph.edges
    )
