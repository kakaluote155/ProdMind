from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    action: str | None = None
    page: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    http_status: int | None = None
    exception_type: str | None = None
    exception_message: str | None = None


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
