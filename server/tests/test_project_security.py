import pytest

from app.connectors.tempo import TraceFacts
from app.security import (
    EngineerAuthUnavailable,
    InvalidEngineerKey,
    InvalidProjectId,
    validate_project_id,
    verify_engineer_key,
)
from app.config import ConfigurationError
from app.telemetry_investigation import TraceAccessError, _assert_project_scope


def facts(*, projects=None, unscoped=None):
    return TraceFacts(
        trace_id="abc",
        http_status=500,
        exception_type=None,
        exception_message=None,
        services=["service-a"],
        project_ids=projects or [],
        unscoped_services=unscoped or [],
        failing_operations=[],
    )


def test_trace_scope_accepts_exact_project():
    _assert_project_scope(facts(projects=["demo"]), expected_project_id="demo")


def test_trace_scope_rejects_other_or_unscoped_project():
    with pytest.raises(TraceAccessError):
        _assert_project_scope(facts(projects=["other"]), expected_project_id="demo")

    with pytest.raises(TraceAccessError):
        _assert_project_scope(
            facts(projects=["demo"], unscoped=["legacy-service"]),
            expected_project_id="demo",
        )


def test_project_id_validation():
    assert validate_project_id("customer-prod_01") == "customer-prod_01"
    for invalid in (None, "", " space", "a/b", "x" * 65):
        with pytest.raises(InvalidProjectId):
            validate_project_id(invalid)


def test_engineer_key_fails_closed_and_uses_configured_secret(monkeypatch):
    monkeypatch.setenv("PRODMIND_ENV", "development")
    monkeypatch.delenv("PRODMIND_PROJECT_ENGINEER_KEYS", raising=False)
    monkeypatch.delenv("PRODMIND_ENGINEER_API_KEY", raising=False)
    with pytest.raises(EngineerAuthUnavailable):
        verify_engineer_key("anything")

    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "correct-key")
    with pytest.raises(InvalidEngineerKey):
        verify_engineer_key(None)
    with pytest.raises(InvalidEngineerKey):
        verify_engineer_key("wrong-key")

    verify_engineer_key("correct-key")


def test_project_bound_engineer_keys_do_not_cross_projects(monkeypatch):
    monkeypatch.setenv(
        "PRODMIND_PROJECT_ENGINEER_KEYS",
        '{"project-a":"project-a-secret","project-b":"project-b-secret"}',
    )
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "legacy-global-key")

    verify_engineer_key("project-a-secret", project_id="project-a")
    with pytest.raises(InvalidEngineerKey):
        verify_engineer_key("project-a-secret", project_id="project-b")
    with pytest.raises(InvalidEngineerKey):
        verify_engineer_key("legacy-global-key", project_id="project-a")


def test_production_rejects_legacy_global_engineer_key(monkeypatch):
    monkeypatch.setenv("PRODMIND_ENV", "production")
    monkeypatch.delenv("PRODMIND_PROJECT_ENGINEER_KEYS", raising=False)
    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "legacy-global-key")

    with pytest.raises(EngineerAuthUnavailable):
        verify_engineer_key("legacy-global-key", project_id="project-a")


@pytest.mark.parametrize(
    "project_keys",
    [
        '{"project-a":"short"}',
        (
            '{"project-a":"one-shared-production-secret",'
            '"project-b":"one-shared-production-secret"}'
        ),
    ],
)
def test_production_rejects_weak_or_shared_project_keys(monkeypatch, project_keys):
    monkeypatch.setenv("PRODMIND_ENV", "production")
    monkeypatch.setenv("PRODMIND_PROJECT_ENGINEER_KEYS", project_keys)

    with pytest.raises(EngineerAuthUnavailable):
        verify_engineer_key("short", project_id="project-a")

    from app.security import configured_project_engineer_keys

    with pytest.raises(ConfigurationError):
        configured_project_engineer_keys()
