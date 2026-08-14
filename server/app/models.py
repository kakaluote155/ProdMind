from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetricSample(BaseModel):
    """Vendor-neutral metric fact normalized by an observability connector."""

    name: str = Field(min_length=1, max_length=200)
    value: float
    unit: str | None = None
    source: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


SpanCategory = Literal["http", "database", "client", "internal", "other"]


class SpanSample(BaseModel):
    """Vendor-neutral timing fact extracted from a distributed trace.

    The model intentionally excludes raw SQL statements and span identifiers.
    """

    name: str = Field(min_length=1, max_length=300)
    duration_ms: float = Field(ge=0.0)
    category: SpanCategory
    service_name: str | None = None
    source: str | None = None


class ServiceCallSample(BaseModel):
    """Verified cross-service call derived from distributed-trace relationships.

    Raw span IDs are used only inside the Tempo adapter while reconstructing the
    relationship and are discarded before this model is created.
    """

    caller_service: str = Field(min_length=1, max_length=200)
    callee_service: str = Field(min_length=1, max_length=200)
    operation: str = Field(min_length=1, max_length=300)
    duration_ms: float = Field(ge=0.0)
    source: str | None = None


class ServiceSample(BaseModel):
    """A project-authorized service participating in the current trace."""

    name: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    source: str | None = None


class ServiceTopology(BaseModel):
    """Vendor-neutral service topology retained for engineer graph rendering.

    The topology contains only already-authorized, normalized trace facts. Raw
    trace/span relationship identifiers are deliberately excluded.
    """

    services: list[ServiceSample] = Field(default_factory=list)
    calls: list[ServiceCallSample] = Field(default_factory=list)
    spans: list[SpanSample] = Field(default_factory=list)


ChangeType = Literal["deployment", "configuration", "feature_flag"]


class ChangeEventCreate(BaseModel):
    """Compact change metadata accepted from authenticated delivery tooling."""

    service_name: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    revision: str | None = Field(default=None, max_length=200)
    change_type: ChangeType
    summary: str = Field(min_length=1, max_length=1000)
    actor: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None


class ChangeEventResponse(BaseModel):
    id: str
    project_id: str
    service_name: str
    version: str | None = None
    revision: str | None = None
    change_type: ChangeType
    summary: str
    actor: str | None = None
    source: str | None = None
    occurred_at: datetime
    created_at: datetime


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    action: str | None = None
    page: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    http_status: int | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    trace_duration_ms: float | None = Field(default=None, ge=0.0)
    span_samples: list[SpanSample] = Field(default_factory=list)
    service_calls: list[ServiceCallSample] = Field(default_factory=list)
    metric_samples: list[MetricSample] = Field(default_factory=list)


class TraceInvestigationRequest(BaseModel):
    trace_id: str = Field(min_length=16, max_length=64)
    question: str = Field(default="Why did my last operation fail?", min_length=1, max_length=2000)
    action: str | None = None
    page: str | None = None


class Evidence(BaseModel):
    type: Literal[
        "user_action",
        "http",
        "trace",
        "log",
        "exception",
        "database",
        "dependency",
        "metric",
        "change",
        "history",
    ]
    summary: str
    source: str | None = None
    service_name: str | None = None


class RootCause(BaseModel):
    category: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class InvestigationResponse(BaseModel):
    """Internal/engineer investigation result. Never expose this whole model to customers."""

    incident_id: str
    status: Literal["diagnosed", "insufficient_evidence"]
    root_cause: RootCause | None
    evidence: list[Evidence]
    customer_answer: str
    engineer_answer: str
    recommended_actions: list[str]
    service_topology: ServiceTopology | None = None


class CustomerInvestigationResponse(BaseModel):
    """Deliberately narrow response contract for embedded customer-facing UIs."""

    incident_id: str
    status: Literal["diagnosed", "insufficient_evidence"]
    category: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    answer: str


ReadOnlyInvestigationStep = Literal[
    "inspect_trace",
    "inspect_logs",
    "inspect_metrics",
    "inspect_changes",
    "inspect_history",
    "ask_for_context",
]


class InvestigatorTraceRequest(BaseModel):
    trace_id: str = Field(min_length=16, max_length=64)
    question: str = Field(min_length=1, max_length=2000)
    action: str | None = Field(default=None, max_length=300)
    page: str | None = Field(default=None, max_length=500)
    session_id: str | None = Field(default=None, min_length=8, max_length=100)


class InvestigatorEvidenceReference(BaseModel):
    id: str = Field(pattern=r"^E[0-9]+$")
    type: str
    summary: str
    source: str | None = None
    service_name: str | None = None


class InvestigatorClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)


class InvestigatorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=3000)
    claims: list[InvestigatorClaim] = Field(default_factory=list, max_length=8)
    missing_evidence: list[str] = Field(default_factory=list, max_length=8)
    next_steps: list[ReadOnlyInvestigationStep] = Field(default_factory=list, max_length=6)


class AIInvestigatorResponse(BaseModel):
    """Authenticated engineer-only AI explanation grounded in an existing RCA result."""

    session_id: str
    turn: int = Field(ge=1)
    incident_id: str
    status: Literal["diagnosed", "insufficient_evidence"]
    root_cause: RootCause | None
    provider: str
    model: str | None = None
    answer: str
    claims: list[InvestigatorClaim]
    missing_evidence: list[str]
    next_steps: list[ReadOnlyInvestigationStep]
    evidence: list[InvestigatorEvidenceReference]


GraphNodeKind = Literal[
    "user_action",
    "http",
    "trace",
    "service",
    "operation",
    "log",
    "exception",
    "database",
    "dependency",
    "metric",
    "change",
    "root_cause",
    "history",
]


class GraphNode(BaseModel):
    id: str
    kind: GraphNodeKind
    label: str
    source: str | None = None
    role: Literal["context", "evidence", "diagnosis", "history"]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: Literal[
        "leads_to",
        "contains",
        "calls",
        "observed_at",
        "supports",
        "diagnoses",
        "context_for",
        "similar_to",
    ]


class EvidenceGraph(BaseModel):
    """Engineer-only explanation graph built from an existing investigation."""

    incident_id: str
    status: Literal["diagnosed", "insufficient_evidence"]
    root_cause: RootCause | None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    entry_node_id: str | None = None
    root_cause_node_id: str | None = None
    recommended_actions: list[str]
