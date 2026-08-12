from app.evidence_graph import build_evidence_graph
from app.investigation import investigate
from app.models import Evidence, InvestigationRequest


def _edge_relations(graph):
    return {(edge.source, edge.target, edge.relation) for edge in graph.edges}


def _nodes_by_kind(graph, kind: str):
    return [node for node in graph.nodes if node.kind == kind]


def test_database_graph_is_deterministic_and_connects_history_to_root():
    result = investigate(
        InvestigationRequest(
            question="Why did creating the user fail?",
            action="create-user",
            trace_id="11111111111111111111111111111111",
            http_status=500,
            exception_type="DuplicateKeyException",
            exception_message="duplicate key value violates unique constraint uk_user_phone",
        )
    )
    result.evidence.extend(
        [
            Evidence(
                type="trace",
                summary="Services in trace: demo-user-service",
                source="tempo",
            ),
            Evidence(
                type="trace",
                summary="Failing span: POST /api/users",
                source="tempo",
            ),
            Evidence(
                type="history",
                summary="Similar incident PM-OLD matched with score 1.00",
                source="incident-memory",
            ),
        ]
    )

    first = build_evidence_graph(result)
    second = build_evidence_graph(result)

    assert first.model_dump() == second.model_dump()
    assert first.root_cause is not None
    assert first.root_cause.category == "database_unique_violation"
    assert first.root_cause_node_id is not None

    database = _nodes_by_kind(first, "database")
    history = _nodes_by_kind(first, "history")
    operations = _nodes_by_kind(first, "operation")
    assert len(database) == 1
    assert len(history) == 1
    assert len(operations) == 1

    relations = _edge_relations(first)
    assert any(
        source == database[0].id
        and target == first.root_cause_node_id
        and relation in {"supports", "diagnoses"}
        for source, target, relation in relations
    )
    assert (
        history[0].id,
        first.root_cause_node_id,
        "similar_to",
    ) in relations


def test_downstream_graph_connects_dependency_evidence_to_root():
    result = investigate(
        InvestigationRequest(
            question="Why did payment fail?",
            action="charge-payment",
            trace_id="22222222222222222222222222222222",
            http_status=500,
            exception_type="ResourceAccessException",
            exception_message="I/O error on POST request: Connection refused",
        )
    )
    result.evidence.extend(
        [
            Evidence(
                type="trace",
                summary="Services in trace: demo-user-service",
                source="tempo",
            ),
            Evidence(
                type="trace",
                summary="Failing span: POST /api/payments/charge",
                source="tempo",
            ),
        ]
    )

    graph = build_evidence_graph(result)

    assert graph.root_cause is not None
    assert graph.root_cause.category == "downstream_unavailable"
    assert graph.root_cause_node_id is not None

    dependencies = _nodes_by_kind(graph, "dependency")
    assert len(dependencies) == 1
    assert any(node.kind == "service" for node in graph.nodes)
    assert any(node.kind == "operation" for node in graph.nodes)

    assert any(
        edge.source == dependencies[0].id
        and edge.target == graph.root_cause_node_id
        and edge.relation in {"supports", "diagnoses"}
        for edge in graph.edges
    )
