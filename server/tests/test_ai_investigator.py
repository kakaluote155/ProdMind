import json

import httpx
import pytest

from app.ai_investigator import (
    InvestigatorSessionLimit,
    InvestigatorSessionStore,
    InvestigatorSessionUnavailable,
    build_investigator_evidence,
    run_investigator_turn,
)
from app.investigation import investigate
from app.llm import (
    OpenAIResponsesProvider,
    ProviderRequest,
    ProviderResponseError,
    ProviderResult,
    ProviderUnavailable,
    configured_investigator_provider,
)
from app.models import (
    Evidence,
    InvestigationRequest,
    InvestigatorClaim,
    InvestigatorDraft,
    InvestigatorTraceRequest,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeProvider:
    def __init__(self, draft: InvestigatorDraft) -> None:
        self.draft = draft
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(provider="fake", model="fake-model", draft=self.draft)


def diagnosed_result():
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
                summary="Trace ID: 11111111111111111111111111111111",
                source="tempo",
            ),
            Evidence(
                type="trace",
                summary="Services in trace: user-service",
                source="tempo",
            ),
            Evidence(
                type="log",
                summary="Found 2 correlated log record(s).",
                source="loki",
            ),
            Evidence(
                type="log",
                summary="password=hunter2 raw stack trace",
                source="loki",
            ),
            Evidence(
                type="change",
                summary="Deploy revision secret-sha",
                source="change-store",
                service_name="user-service",
            ),
            Evidence(
                type="history",
                summary="Similar incident PM-SECRET",
                source="incident-memory",
            ),
        ]
    )
    return result


@pytest.mark.anyio
async def test_investigator_is_grounded_and_excludes_sensitive_context_by_default():
    provider = FakeProvider(
        InvestigatorDraft(
            answer="The current evidence confirms a duplicate-data failure.",
            claims=[
                InvestigatorClaim(
                    summary="A database uniqueness rule rejected the operation.",
                    evidence_ids=["E4"],
                )
            ],
            missing_evidence=[],
            next_steps=["inspect_trace"],
        )
    )
    response = await run_investigator_turn(
        InvestigatorTraceRequest(
            trace_id="11111111111111111111111111111111",
            question="Explain the verified cause.",
        ),
        project_id="demo",
        investigation=diagnosed_result(),
        provider=provider,
        session_store=InvestigatorSessionStore(),
    )

    assert response.turn == 1
    assert response.root_cause is not None
    assert response.root_cause.category == "database_unique_violation"
    assert response.provider == "fake"
    serialized = json.dumps(provider.requests[0].user_payload)
    assert "11111111111111111111111111111111" not in serialized
    assert "hunter2" not in serialized
    assert "secret-sha" not in serialized
    assert "PM-SECRET" not in serialized
    assert "Found 2 correlated" in serialized


@pytest.mark.anyio
async def test_multi_turn_history_is_minimal_and_project_scoped():
    store = InvestigatorSessionStore()
    provider = FakeProvider(
        InvestigatorDraft(
            answer="Grounded answer.",
            claims=[InvestigatorClaim(summary="Verified claim.", evidence_ids=["E4"])],
            missing_evidence=[],
            next_steps=["ask_for_context"],
        )
    )
    first = await run_investigator_turn(
        InvestigatorTraceRequest(
            trace_id="11111111111111111111111111111111",
            question="First question",
        ),
        project_id="demo",
        investigation=diagnosed_result(),
        provider=provider,
        session_store=store,
    )
    second = await run_investigator_turn(
        InvestigatorTraceRequest(
            trace_id="11111111111111111111111111111111",
            question="Follow-up question",
            session_id=first.session_id,
        ),
        project_id="demo",
        investigation=diagnosed_result(),
        provider=provider,
        session_store=store,
    )

    assert second.turn == 2
    history = provider.requests[1].user_payload["conversation"]
    assert history == [
        {
            "question": "First question",
            "answer": "Grounded answer.",
            "claims": [{"summary": "Verified claim.", "evidence_ids": ["E4"]}],
        }
    ]
    with pytest.raises(InvestigatorSessionUnavailable):
        store.open(
            project_id="other-project",
            trace_id="11111111111111111111111111111111",
            session_id=first.session_id,
        )


@pytest.mark.anyio
async def test_invalid_evidence_citation_is_rejected_without_consuming_turn():
    store = InvestigatorSessionStore()
    invalid = FakeProvider(
        InvestigatorDraft(
            answer="Unsupported answer.",
            claims=[InvestigatorClaim(summary="Invented claim.", evidence_ids=["E999"])],
            missing_evidence=[],
            next_steps=[],
        )
    )
    request = InvestigatorTraceRequest(
        trace_id="11111111111111111111111111111111",
        question="Explain this.",
    )
    with pytest.raises(ProviderResponseError):
        await run_investigator_turn(
            request,
            project_id="demo",
            investigation=diagnosed_result(),
            provider=invalid,
            session_store=store,
        )

    valid = FakeProvider(
        InvestigatorDraft(
            answer="Grounded answer.",
            claims=[InvestigatorClaim(summary="Verified claim.", evidence_ids=["E4"])],
            missing_evidence=[],
            next_steps=[],
        )
    )
    response = await run_investigator_turn(
        request,
        project_id="demo",
        investigation=diagnosed_result(),
        provider=valid,
        session_store=store,
    )
    assert response.turn == 1


@pytest.mark.anyio
async def test_openai_provider_uses_store_false_and_strict_structured_output():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "answer": "Grounded answer.",
                                        "claims": [
                                            {"summary": "Verified.", "evidence_ids": ["E1"]}
                                        ],
                                        "missing_evidence": [],
                                        "next_steps": ["inspect_trace"],
                                    }
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate(
        ProviderRequest(system_prompt="system", user_payload={"evidence": ["E1"]})
    )

    assert result.draft.answer == "Grounded answer."
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False
    assert captured["input"][0]["role"] == "system"


def test_provider_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("PRODMIND_LLM_PROVIDER", "disabled")
    provider = configured_investigator_provider()
    assert provider.__class__.__name__ == "DisabledProvider"

    monkeypatch.setenv("PRODMIND_LLM_PROVIDER", "openai")
    monkeypatch.delenv("PRODMIND_LLM_API_KEY", raising=False)
    monkeypatch.setenv("PRODMIND_LLM_MODEL", "test-model")
    with pytest.raises(ProviderUnavailable):
        configured_investigator_provider()


def test_provider_draft_cannot_add_a_root_cause_field():
    with pytest.raises(ValueError):
        InvestigatorDraft.model_validate(
            {
                "answer": "Invented answer.",
                "claims": [],
                "missing_evidence": [],
                "next_steps": [],
                "root_cause": "invented_category",
            }
        )


def test_evidence_policy_can_opt_in_change_context(monkeypatch):
    monkeypatch.setenv("PRODMIND_LLM_INCLUDE_CHANGE_CONTEXT", "true")
    references = build_investigator_evidence(diagnosed_result())
    assert any(item.type == "change" for item in references)
    assert all(item.type != "history" for item in references)


@pytest.mark.anyio
async def test_session_turn_limit_is_enforced():
    store = InvestigatorSessionStore(max_turns=1)
    provider = FakeProvider(
        InvestigatorDraft(
            answer="Grounded answer.",
            claims=[InvestigatorClaim(summary="Verified.", evidence_ids=["E4"])],
            missing_evidence=[],
            next_steps=[],
        )
    )
    first = await run_investigator_turn(
        InvestigatorTraceRequest(
            trace_id="11111111111111111111111111111111",
            question="First question",
        ),
        project_id="demo",
        investigation=diagnosed_result(),
        provider=provider,
        session_store=store,
    )
    with pytest.raises(InvestigatorSessionLimit):
        await run_investigator_turn(
            InvestigatorTraceRequest(
                trace_id="11111111111111111111111111111111",
                question="One question too many",
                session_id=first.session_id,
            ),
            project_id="demo",
            investigation=diagnosed_result(),
            provider=provider,
            session_store=store,
        )
