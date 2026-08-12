from __future__ import annotations

from collections import defaultdict
from hashlib import sha1

from .models import Evidence, EvidenceGraph, GraphEdge, GraphNode, InvestigationResponse


def build_evidence_graph(result: InvestigationResponse) -> EvidenceGraph:
    """Build a deterministic explanation graph from an existing investigation.

    The graph never performs diagnosis and never reads telemetry directly. It can
    only arrange facts already present in the engineer investigation result.
    """

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_by_key: dict[tuple[str, str], GraphNode] = {}
    groups: dict[str, list[GraphNode]] = defaultdict(list)

    for evidence in result.evidence:
        kind = _graph_kind(evidence)
        label = evidence.summary.strip()
        key = (kind, label)
        node = node_by_key.get(key)
        if node is None:
            node = GraphNode(
                id=_stable_id("node", kind, label),
                kind=kind,
                label=label,
                source=evidence.source,
                role=_role_for(kind),
            )
            node_by_key[key] = node
            nodes.append(node)
            groups[kind].append(node)

    root_node: GraphNode | None = None
    if result.root_cause is not None:
        root_node = GraphNode(
            id=_stable_id("root", result.root_cause.category, result.root_cause.summary),
            kind="root_cause",
            label=(
                f"{result.root_cause.category}: {result.root_cause.summary} "
                f"(confidence {result.root_cause.confidence:.0%})"
            ),
            source=_rule_source(result.evidence),
            role="diagnosis",
        )
        nodes.append(root_node)
        groups["root_cause"].append(root_node)

    spine = _first_existing(
        groups,
        [
            "user_action",
            "http",
            "trace",
            "service",
            "operation",
            "exception",
            "database",
            "dependency",
            "metric",
            "root_cause",
        ],
    )
    for source, target in zip(spine, spine[1:]):
        _add_edge(edges, source, target, _spine_relation(source.kind, target.kind))

    root_target = root_node
    operation_target = _first(groups.get("operation"))
    trace_target = _first(groups.get("trace"))

    for node in groups.get("log", []):
        target = operation_target or root_target or trace_target
        if target is not None and target.id != node.id:
            _add_edge(edges, node, target, "supports")

    selected = {node.id for node in spine}
    for kind in ("exception", "database", "dependency", "metric"):
        for node in groups.get(kind, []):
            if node.id in selected:
                continue
            target = root_target or operation_target
            if target is not None and target.id != node.id:
                _add_edge(edges, node, target, "supports")

    for node in groups.get("history", []):
        target = root_target or operation_target or trace_target
        if target is not None and target.id != node.id:
            _add_edge(edges, node, target, "similar_to")

    entry = _first(groups.get("user_action")) or _first(groups.get("http")) or trace_target

    return EvidenceGraph(
        incident_id=result.incident_id,
        status=result.status,
        root_cause=result.root_cause,
        nodes=nodes,
        edges=edges,
        entry_node_id=entry.id if entry else None,
        root_cause_node_id=root_node.id if root_node else None,
        recommended_actions=result.recommended_actions,
    )


def _graph_kind(evidence: Evidence) -> str:
    if evidence.type == "trace":
        lowered = evidence.summary.lower().strip()
        if lowered.startswith("services in trace:"):
            return "service"
        if lowered.startswith("failing span:"):
            return "operation"
    return evidence.type


def _role_for(kind: str) -> str:
    if kind in {"user_action", "http", "trace", "service"}:
        return "context"
    if kind == "history":
        return "history"
    if kind == "root_cause":
        return "diagnosis"
    return "evidence"


def _rule_source(evidence: list[Evidence]) -> str | None:
    for item in evidence:
        if item.source and item.source.startswith("rca-rule:"):
            return item.source
    return None


def _first_existing(groups: dict[str, list[GraphNode]], ordered_kinds: list[str]) -> list[GraphNode]:
    result: list[GraphNode] = []
    for kind in ordered_kinds:
        node = _first(groups.get(kind))
        if node is not None:
            result.append(node)
    return result


def _first(items: list[GraphNode] | None) -> GraphNode | None:
    return items[0] if items else None


def _spine_relation(source_kind: str, target_kind: str) -> str:
    pair = (source_kind, target_kind)
    if pair == ("http", "trace"):
        return "observed_at"
    if pair in {("trace", "service"), ("service", "operation")}:
        return "contains"
    if target_kind == "root_cause":
        return "diagnoses"
    if source_kind in {"exception", "database", "dependency", "metric"}:
        return "supports"
    return "leads_to"


def _add_edge(edges: list[GraphEdge], source: GraphNode, target: GraphNode, relation: str) -> None:
    edge_id = _stable_id("edge", source.id, relation, target.id)
    if any(edge.id == edge_id for edge in edges):
        return
    edges.append(GraphEdge(id=edge_id, source=source.id, target=target.id, relation=relation))


def _stable_id(prefix: str, *parts: str) -> str:
    value = "|".join(parts).encode("utf-8")
    return f"{prefix}-{sha1(value).hexdigest()[:12]}"
