from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai_investigator import InvestigatorSessionStore, run_investigator_turn
from app.investigation import investigate
from app.llm import ProviderRequest, ProviderResponseError, ProviderResult
from app.models import (
    Evidence,
    InvestigationRequest,
    InvestigatorDraft,
    InvestigatorTraceRequest,
)


class EvalExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    status: str
    root_cause: str | None = None
    answer_source: str = Field(default="provider", pattern="^(provider|deterministic)$")
    absent_from_provider_payload: list[str] = Field(default_factory=list)


class InvestigatorEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    project_id: str = Field(default="eval-project", min_length=1)
    trace_id: str = Field(default="11111111111111111111111111111111", min_length=16)
    question: str = Field(default="Explain the verified evidence.", min_length=1)
    investigation: dict[str, Any]
    extra_evidence: list[Evidence] = Field(default_factory=list)
    provider_output: dict[str, Any]
    expect: EvalExpectation


@dataclass(slots=True)
class EvalResult:
    name: str
    passed: bool
    detail: str


class FixtureProvider:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        draft = InvestigatorDraft.model_validate(self.output)
        return ProviderResult(provider="eval-fixture", model="deterministic", draft=draft)


async def run_eval_case(case: InvestigatorEvalCase) -> EvalResult:
    provider = FixtureProvider(case.provider_output)
    investigation = investigate(InvestigationRequest.model_validate(case.investigation))
    investigation.evidence.extend(case.extra_evidence)
    actual_error: Exception | None = None
    response = None
    try:
        response = await run_investigator_turn(
            InvestigatorTraceRequest(
                trace_id=case.trace_id,
                question=case.question,
            ),
            project_id=case.project_id,
            investigation=investigation,
            provider=provider,
            session_store=InvestigatorSessionStore(max_sessions=4),
        )
    except (ProviderResponseError, ValidationError) as exc:
        actual_error = exc

    if case.expect.accepted and actual_error is not None:
        return EvalResult(case.name, False, f"unexpected rejection: {actual_error}")
    if not case.expect.accepted and actual_error is None:
        return EvalResult(case.name, False, "unsafe output was accepted")
    if not case.expect.accepted:
        return EvalResult(case.name, True, "rejected as expected")
    if response is None:
        return EvalResult(case.name, False, "accepted case returned no response")
    if response.status != case.expect.status:
        return EvalResult(
            case.name,
            False,
            f"status changed from {case.expect.status} to {response.status}",
        )
    actual_root = response.root_cause.category if response.root_cause else None
    if actual_root != case.expect.root_cause:
        return EvalResult(
            case.name,
            False,
            f"root cause changed from {case.expect.root_cause} to {actual_root}",
        )
    if case.expect.answer_source == "deterministic":
        if response.answer != investigation.engineer_answer:
            return EvalResult(case.name, False, "insufficient-evidence answer was not fixed")
    else:
        expected_answer = case.provider_output.get("answer")
        if response.answer != expected_answer:
            return EvalResult(case.name, False, "provider answer changed unexpectedly")

    payload = json.dumps(provider.requests[0].user_payload, ensure_ascii=False)
    leaked = [marker for marker in case.expect.absent_from_provider_payload if marker in payload]
    if leaked:
        return EvalResult(case.name, False, f"provider payload leaked: {', '.join(leaked)}")
    return EvalResult(case.name, True, "accepted with authority and privacy gates intact")


def load_cases(path: Path) -> list[InvestigatorEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [InvestigatorEvalCase.model_validate(item) for item in payload]


async def run_suite(path: Path) -> list[EvalResult]:
    return [await run_eval_case(case) for case in load_cases(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ProdMind AI safety evaluations.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("ai_eval_cases.json"),
    )
    args = parser.parse_args()
    results = asyncio.run(run_suite(args.cases))
    for result in results:
        state = "PASS" if result.passed else "FAIL"
        print(f"[{state}] {result.name}: {result.detail}")
    failed = [result for result in results if not result.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} AI evaluation gates passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
