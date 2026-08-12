import pytest

from app.connectors.tempo import TraceFacts
from app.security import (
    EngineerAuthUnavailable,
    InvalidEngineerKey,
    InvalidProjectId,
    validate_project_id,
    verify_engineer_key,
)
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
    monkeypatch.delenv("PRODMIND_ENGINEER_API_KEY", raising=False)
    with pytest.raises(EngineerAuthUnavailable):
        verify_engineer_key("anything")

    monkeypatch.setenv("PRODMIND_ENGINEER_API_KEY", "correct-key")
    with pytest.raises(InvalidEngineerKey):
        verify_engineer_key(None)
    with pytest.raises(InvalidEngineerKey):
        verify_engineer_key("wrong-key")

    verify_engineer_key("correct-key")
