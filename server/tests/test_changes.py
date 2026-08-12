from datetime import UTC, datetime, timedelta

from app.changes import ChangeStore
from app.models import ChangeEventCreate


def change(*, version: str, summary: str, occurred_at: datetime) -> ChangeEventCreate:
    return ChangeEventCreate(
        service_name="demo-user-service",
        version=version,
        revision=f"sha-{version}",
        change_type="deployment",
        summary=summary,
        actor="ci",
        source="github-actions",
        occurred_at=occurred_at,
    )


def test_change_store_is_project_scoped_and_time_bounded(tmp_path):
    store = ChangeStore(str(tmp_path / "changes.db"))
    now = datetime.now(UTC)

    store.record(
        project_id="demo",
        event=change(version="demo-v2", summary="expected deploy", occurred_at=now - timedelta(minutes=20)),
    )
    store.record(
        project_id="other-project",
        event=change(version="demo-v2", summary="must never cross projects", occurred_at=now - timedelta(minutes=5)),
    )
    store.record(
        project_id="demo",
        event=change(version="demo-old", summary="too old", occurred_at=now - timedelta(hours=8)),
    )

    matches = store.find_recent(
        project_id="demo",
        service_names=["demo-user-service"],
        service_versions={"demo-user-service": "demo-v2"},
        incident_at=now,
        lookback_hours=6,
    )

    assert [item.summary for item in matches] == ["expected deploy"]
    assert all(item.project_id == "demo" for item in matches)


def test_exact_trace_version_is_prioritized_over_newer_service_change(tmp_path):
    store = ChangeStore(str(tmp_path / "changes.db"))
    now = datetime.now(UTC)

    store.record(
        project_id="demo",
        event=change(version="demo-v2", summary="matching version", occurred_at=now - timedelta(minutes=30)),
    )
    store.record(
        project_id="demo",
        event=change(version="demo-v3", summary="newer but different version", occurred_at=now - timedelta(minutes=2)),
    )

    matches = store.find_recent(
        project_id="demo",
        service_names=["demo-user-service"],
        service_versions={"demo-user-service": "demo-v2"},
        incident_at=now,
    )

    assert matches[0].version == "demo-v2"
    assert matches[0].summary == "matching version"


def test_change_store_redacts_secret_assignments_and_keeps_only_metadata(tmp_path):
    path = tmp_path / "changes.db"
    store = ChangeStore(str(path))
    now = datetime.now(UTC)

    event = store.record(
        project_id="demo",
        event=change(
            version="demo-v2",
            summary="deploy password=hunter2 token=abc123 completed",
            occurred_at=now,
        ),
    )

    assert "hunter2" not in event.summary
    assert "abc123" not in event.summary
    assert "[redacted]" in event.summary
    database_bytes = path.read_bytes()
    assert b"hunter2" not in database_bytes
    assert b"abc123" not in database_bytes
