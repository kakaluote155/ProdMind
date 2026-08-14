from fastapi.testclient import TestClient

import app.main as main_module
from app.changes import configured_change_store
from app.investigation import investigate
from app.main import app
from app.models import InvestigationRequest

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_reports_stable_version() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"


def test_v1_api_responses_declare_contract_version() -> None:
    response = client.post(
        "/api/v1/support",
        headers={"X-ProdMind-Project": "demo"},
        json={"question": "Why did this fail?", "http_status": 500},
    )
    assert response.status_code == 200
    assert response.headers["X-ProdMind-API-Version"] == "v1"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_readiness_is_ready_in_development() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_trace_endpoint_rejects_non_w3c_trace_identifier() -> None:
    response = client.post(
        "/api/v1/support/trace",
        headers={"X-ProdMind-Project": "demo"},
        json={"trace_id": '"} |= "attacker"', "question": "Why?"},
    )
    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"


def test_project_bound_engineer_key_is_enforced_by_route(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENV", "development")
    monkeypatch.setenv(
        "PRODMIND_PROJECT_ENGINEER_KEYS",
        '{"project-a":"project-a-secret","project-b":"project-b-secret"}',
    )
    response = client.post(
        "/api/v1/investigate",
        headers={
            "X-ProdMind-Project": "project-b",
            "X-ProdMind-Engineer-Key": "project-a-secret",
        },
        json={"question": "Why did this fail?", "http_status": 500},
    )
    assert response.status_code == 401
    assert "evidence" not in response.text.lower()


def test_engineer_viewer_is_an_empty_shell() -> None:
    response = client.get("/engineer")
    assert response.status_code == 200
    assert "Engineer Evidence Graph" in response.text
    assert "X-ProdMind-Engineer-Key" in response.text
    assert "/api/v1/investigator/trace" in response.text
    assert "Deterministic RCA remains authoritative" in response.text
    assert "uk_user_phone" not in response.text
    assert "incident-memory" not in response.text


def test_customer_api_requires_project_header() -> None:
    response = client.post(
        "/api/v1/support",
        json={"question": "Why did this fail?", "http_status": 500},
    )
    assert response.status_code == 400


def test_engineer_api_rejects_missing_key(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    response = client.post(
        "/api/v1/investigate",
        headers={"X-ProdMind-Project": "demo"},
        json={"question": "Why did this fail?", "http_status": 500},
    )
    assert response.status_code == 401
    assert "evidence" not in response.text.lower()


def test_change_ingestion_rejects_missing_engineer_key(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    response = client.post(
        "/api/v1/changes",
        headers={"X-ProdMind-Project": "demo"},
        json={
            "service_name": "demo-user-service",
            "version": "demo-v2",
            "change_type": "deployment",
            "summary": "Deploy demo-v2",
        },
    )
    assert response.status_code == 401


def test_change_ingestion_uses_header_project_and_redacts_secrets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    monkeypatch.setenv("PRODMIND_CHANGE_PATH", str(tmp_path / "changes.db"))
    configured_change_store.cache_clear()

    response = client.post(
        "/api/v1/changes",
        headers={
            "X-ProdMind-Project": "demo",
            "X-ProdMind-Engineer-Key": "test-engineer-key",
        },
        json={
            "service_name": "demo-user-service",
            "version": "demo-v2",
            "revision": "abc123",
            "change_type": "deployment",
            "summary": "Deploy demo-v2 token=secret-value",
            "actor": "ci",
            "source": "github-actions",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == "demo"
    assert body["version"] == "demo-v2"
    assert "secret-value" not in body["summary"]
    assert "[redacted]" in body["summary"]
    configured_change_store.cache_clear()


def test_evidence_graph_api_rejects_missing_engineer_key(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    response = client.post(
        "/api/v1/investigate/trace/graph",
        headers={"X-ProdMind-Project": "demo"},
        json={
            "trace_id": "11111111111111111111111111111111",
            "question": "Why did this fail?",
        },
    )
    assert response.status_code == 401
    assert "nodes" not in response.text.lower()
    assert "edges" not in response.text.lower()


def test_duplicate_key_engineer_investigation_with_auth(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    response = client.post(
        "/api/v1/investigate",
        headers={
            "X-ProdMind-Project": "demo",
            "X-ProdMind-Engineer-Key": "test-engineer-key",
        },
        json={
            "question": "Why did creating the user fail?",
            "action": "create-user",
            "http_status": 500,
            "exception_type": "DuplicateKeyException",
            "exception_message": "duplicate key value violates unique constraint uk_user_phone",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "diagnosed"
    assert body["root_cause"]["category"] == "database_unique_violation"
    assert body["root_cause"]["confidence"] == 0.98
    assert "uk_user_phone" in body["engineer_answer"]


def test_ai_investigator_rejects_missing_engineer_key(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    response = client.post(
        "/api/v1/investigator/trace",
        headers={"X-ProdMind-Project": "demo"},
        json={
            "trace_id": "11111111111111111111111111111111",
            "question": "Explain this incident.",
        },
    )
    assert response.status_code == 401
    assert "evidence" not in response.text.lower()


def test_ai_investigator_fails_closed_when_provider_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "test-engineer-key")
    monkeypatch.setenv("PRODMIND_LLM_PROVIDER", "disabled")

    async def fake_investigation(request, *, project_id):
        _ = request, project_id
        return investigate(
            InvestigationRequest(
                question="Why did this fail?",
                http_status=500,
                exception_type="DuplicateKeyException",
                exception_message="duplicate key violates unique constraint uk_user_phone",
            )
        )

    monkeypatch.setattr(main_module, "investigate_from_trace", fake_investigation)
    response = client.post(
        "/api/v1/investigator/trace",
        headers={
            "X-ProdMind-Project": "demo",
            "X-ProdMind-Engineer-Key": "test-engineer-key",
        },
        json={
            "trace_id": "11111111111111111111111111111111",
            "question": "Explain this incident.",
        },
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "AI Investigator provider is not configured or available."
    }
