from __future__ import annotations

from collections import defaultdict
from hashlib import sha1

from .models import (
    Evidence,
    EvidenceGraph,
    GraphEdge,
    GraphNode,
    InvestigationResponse,
    ServiceTopology,
    SpanSample,
)


def build_evidence_graph(result: InvestigationResponse) -> EvidenceGraph:
    """Build a deterministic explanation graph from an existing investigation.

    The graph never performs diagnosis and never reads telemetry directly. It can
    only arrange facts already present in the engineer investigation result.
    """

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_by_key: dict[tuple[str, str], GraphNode] = {}
    groups: dict[str, list[GraphNode]] = defaultdict(list)

    layered = result.service_topology is not None
    for evidence in result.evidence:
        if layered and _is_legacy_topology_summary(evidence):
            continue
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

    service_nodes: dict[str, GraphNode] = {}
    operation_services: dict[str, str] = {}
    if result.service_topology is not None:
        service_nodes, operation_services = _add_topology_nodes(
            result.service_topology,
            nodes=nodes,
            groups=groups,
        )

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

    if result.service_topology is not None:
        spine = _add_layered_topology_edges(
            result.service_topology,
            groups=groups,
            service_nodes=service_nodes,
            operation_services=operation_services,
            edges=edges,
        )
    else:
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
    service_target = _first(groups.get("service"))
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
            evidence = _evidence_for_node(result.evidence, node)
            scoped_service = service_nodes.get(evidence.service_name) if evidence else None
            if scoped_service is not None:
                _add_edge(edges, scoped_service, node, "contains")
            target = root_target or operation_target
            if target is not None and target.id != node.id:
                _add_edge(edges, node, target, "supports")

    # Change proximity is operational context only. A context_for edge must never
    # be interpreted as a causal relationship or substitute for RCA evidence.
    for node in groups.get("change", []):
        evidence = _evidence_for_node(result.evidence, node)
        target = (
            service_nodes.get(evidence.service_name)
            if evidence and evidence.service_name
            else None
        ) or service_target or root_target or trace_target
        if target is not None and target.id != node.id:
            _add_edge(edges, node, target, "context_for")

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
        if lowered.startswith("failing span:") or lowered.startswith("slow span:"):
            return "operation"
    return evidence.type


def _is_legacy_topology_summary(evidence: Evidence) -> bool:
    if evidence.type != "trace":
        return False
    lowered = evidence.summary.lower().strip()
    return lowered.startswith("services in trace:") or lowered.startswith("slow span:")


def _add_topology_nodes(
    topology: ServiceTopology,
    *,
    nodes: list[GraphNode],
    groups: dict[str, list[GraphNode]],
) -> tuple[dict[str, GraphNode], dict[str, str]]:
    service_nodes: dict[str, GraphNode] = {}
    operation_services: dict[str, str] = {}

    for service in sorted(topology.services, key=lambda item: item.name):
        label = service.name
        if service.version:
            label += f" · {service.version}"
        node = GraphNode(
            id=_stable_id("service", service.name, service.version or ""),
            kind="service",
            label=label,
            source=service.source,
            role="context",
        )
        nodes.append(node)
        groups["service"].append(node)
        service_nodes[service.name] = node

    for sample in topology.spans:
        if not sample.service_name or sample.service_name not in service_nodes:
            continue
        if sample.duration_ms < 500:
            continue
        label = _operation_label(sample)
        node_id = _stable_id(
            "operation",
            sample.service_name,
            sample.category,
            sample.name,
            f"{sample.duration_ms:.3f}",
        )
        if node_id in operation_services:
            continue
        node = GraphNode(
            id=node_id,
            kind="operation",
            label=label,
            source=sample.source,
            role="evidence",
        )
        nodes.append(node)
        groups["operation"].append(node)
        operation_services[node.id] = sample.service_name

    return service_nodes, operation_services


def _add_layered_topology_edges(
    topology: ServiceTopology,
    *,
    groups: dict[str, list[GraphNode]],
    service_nodes: dict[str, GraphNode],
    operation_services: dict[str, str],
    edges: list[GraphEdge],
) -> list[GraphNode]:
    context_spine = _first_existing(groups, ["user_action", "http", "trace"])
    for source, target in zip(context_spine, context_spine[1:]):
        _add_edge(edges, source, target, _spine_relation(source.kind, target.kind))

    trace_node = _first(groups.get("trace"))
    if trace_node is not None:
        for service in service_nodes.values():
            _add_edge(edges, trace_node, service, "contains")

    for call in topology.calls:
        caller = service_nodes.get(call.caller_service)
        callee = service_nodes.get(call.callee_service)
        if caller is not None and callee is not None:
            _add_edge(edges, caller, callee, "calls")

    operations = {node.id: node for node in groups.get("operation", [])}
    for operation_id, service_name in operation_services.items():
        service = service_nodes.get(service_name)
        operation = operations.get(operation_id)
        if service is not None and operation is not None:
            _add_edge(edges, service, operation, "contains")

    return context_spine


def _operation_label(sample: SpanSample) -> str:
    return f"{sample.name} · {sample.duration_ms:.0f} ms"


def _evidence_for_node(evidence: list[Evidence], node: GraphNode) -> Evidence | None:
    for item in evidence:
        if item.summary.strip() == node.label and _graph_kind(item) == node.kind:
            return item
    return None


def _role_for(kind: str) -> str:
    if kind in {"user_action", "http", "trace", "service", "change"}:
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
