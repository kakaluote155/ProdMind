import sqlite3
from datetime import UTC, datetime, timedelta

from app.memory import IncidentMemoryStore
from app.models import Evidence, InvestigationResponse, RootCause


def diagnosed(incident_id: str) -> InvestigationResponse:
    return InvestigationResponse(
        incident_id=incident_id,
        status="diagnosed",
        root_cause=RootCause(
            category="database_unique_violation",
            summary="The operation violates a uniqueness rule.",
            confidence=0.98,
        ),
        evidence=[
            Evidence(
                type="log",
                summary="RAW SECRET LOG password=hunter2 trace payload should not be persisted",
            )
        ],
        customer_answer="The submitted information already exists.",
        engineer_answer="Constraint uk_user_phone failed.",
        recommended_actions=[
            "Return a business-specific conflict response instead of HTTP 500.",
            "Show a clear validation message.",
        ],
    )


def test_memory_matches_only_inside_same_project_and_excludes_current_trace(tmp_path):
    path = tmp_path / "memory.db"
    store = IncidentMemoryStore(str(path))

    store.remember(
        project_id="project-a",
        trace_id="trace-one",
        action="create-user",
        result=diagnosed("PM-ONE"),
    )

    matches = store.find_similar(
        project_id="project-a",
        category="database_unique_violation",
        action="create-user",
        exclude_trace_id="trace-two",
    )
    assert len(matches) == 1
    assert matches[0].incident_id == "PM-ONE"
    assert matches[0].project_id == "project-a"
    assert matches[0].score == 1.0

    other_project = store.find_similar(
        project_id="project-b",
        category="database_unique_violation",
        action="create-user",
        exclude_trace_id="trace-two",
    )
    assert other_project == []

    same_trace = store.find_similar(
        project_id="project-a",
        category="database_unique_violation",
        action="create-user",
        exclude_trace_id="trace-one",
    )
    assert same_trace == []


def test_memory_deduplicates_trace_and_does_not_store_raw_evidence(tmp_path):
    path = tmp_path / "memory.db"
    store = IncidentMemoryStore(str(path))
    result = diagnosed("PM-ONE")

    for _ in range(2):
        store.remember(
            project_id="project-a",
            trace_id="trace-one",
            action="create-user",
            result=result,
        )

    assert store.count() == 1
    assert store.count("project-a") == 1
    assert store.count("project-b") == 0
    database_bytes = path.read_bytes()
    assert b"hunter2" not in database_bytes
    assert b"RAW SECRET LOG" not in database_bytes


def test_memory_enforces_retention_and_project_capacity(tmp_path):
    path = tmp_path / "memory.db"
    store = IncidentMemoryStore(
        str(path),
        retention_days=7,
        max_records_per_project=2,
    )
    for number in range(3):
        store.remember(
            project_id="project-a",
            trace_id=f"trace-{number}",
            action="create-user",
            result=diagnosed(f"PM-{number}"),
        )
    store.remember(
        project_id="project-b",
        trace_id="other-trace",
        action="create-user",
        result=diagnosed("PM-OTHER"),
    )

    assert store.count("project-a") == 2
    assert store.count("project-b") == 1

    expired = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE incident_memory SET created_at = ? WHERE project_id = ?",
            (expired, "project-a"),
        )

    assert store.count("project-a") == 0
    assert store.count("project-b") == 1


def test_same_trace_id_is_deduplicated_only_within_each_project(tmp_path):
    store = IncidentMemoryStore(str(tmp_path / "memory.db"))

    for project_id in ("project-a", "project-b"):
        store.remember(
            project_id=project_id,
            trace_id="shared-trace-id",
            action="create-user",
            result=diagnosed(f"PM-{project_id}"),
        )

    assert store.count("project-a") == 1
    assert store.count("project-b") == 1


def test_legacy_global_trace_constraint_is_migrated_without_data_loss(tmp_path):
    path = tmp_path / "legacy-memory.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE incident_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                trace_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL DEFAULT 'legacy',
                category TEXT NOT NULL,
                action TEXT,
                root_summary TEXT NOT NULL,
                resolution_summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO incident_memory(
                incident_id, trace_id, project_id, category, action,
                root_summary, resolution_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PM-OLD",
                "shared-trace-id",
                "project-a",
                "database_unique_violation",
                "create-user",
                "old root",
                "old resolution",
                datetime.now(UTC).isoformat(),
            ),
        )

    store = IncidentMemoryStore(str(path))
    store.remember(
        project_id="project-b",
        trace_id="shared-trace-id",
        action="create-user",
        result=diagnosed("PM-NEW"),
    )

    assert store.count("project-a") == 1
    assert store.count("project-b") == 1
