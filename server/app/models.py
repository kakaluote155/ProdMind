from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class CustomerInvestigationResponse(BaseModel):
    """Deliberately narrow response contract for embedded customer-facing UIs."""

    incident_id: str
    status: Literal["diagnosed", "insufficient_evidence"]
    category: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    answer: str


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
