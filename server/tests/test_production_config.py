from app.config import production_readiness_issues
from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_production_readiness_fails_closed_without_security_configuration(monkeypatch):
    monkeypatch.setenv("PRODMIND_ENV", "production")
    monkeypatch.delenv("PRODMIND_PROJECT_ENGINEER_KEYS", raising=False)
    monkeypatch.delenv("PRODMIND_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("PRODMIND_TRUSTED_HOSTS", raising=False)

    issues = production_readiness_issues()

    assert "project_engineer_keys" in issues
    assert "cors_origins" in issues
    assert "trusted_hosts" in issues


def test_production_readiness_accepts_explicit_project_and_network_boundaries(monkeypatch):
    monkeypatch.setenv("PRODMIND_ENV", "production")
    monkeypatch.setenv(
        "PRODMIND_PROJECT_ENGINEER_KEYS",
        '{"project-a":"a-random-project-secret-at-least-24-chars"}',
    )
    monkeypatch.setenv("PRODMIND_CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("PRODMIND_TRUSTED_HOSTS", "support.example.com")

    assert production_readiness_issues() == []


def test_readiness_exposes_only_non_secret_issue_codes(monkeypatch):
    monkeypatch.setenv("PRODMIND_ENV", "production")
    monkeypatch.delenv("PRODMIND_PROJECT_ENGINEER_KEYS", raising=False)
    monkeypatch.delenv("PRODMIND_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("PRODMIND_TRUSTED_HOSTS", raising=False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "issues": ["cors_origins", "project_engineer_keys", "trusted_hosts"],
    }
