from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Evidence, InvestigationRequest, RootCause


@dataclass(slots=True)
class RuleMatch:
    root_cause: RootCause
    evidence: list[Evidence]
    customer_answer: str
    engineer_answer: str
    recommended_actions: list[str]


class DiagnosticRule(Protocol):
    name: str

    def evaluate(self, request: InvestigationRequest) -> RuleMatch | None:
        ...
