from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
