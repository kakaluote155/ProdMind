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


def test_memory_matches_previous_incident_and_excludes_current_trace(tmp_path):
    path = tmp_path / "memory.db"
    store = IncidentMemoryStore(str(path))

    store.remember(trace_id="trace-one", action="create-user", result=diagnosed("PM-ONE"))

    matches = store.find_similar(
        category="database_unique_violation",
        action="create-user",
        exclude_trace_id="trace-two",
    )

    assert len(matches) == 1
    assert matches[0].incident_id == "PM-ONE"
    assert matches[0].score == 1.0

    same_trace_matches = store.find_similar(
        category="database_unique_violation",
        action="create-user",
        exclude_trace_id="trace-one",
    )
    assert same_trace_matches == []


def test_memory_deduplicates_trace_and_does_not_store_raw_evidence(tmp_path):
    path = tmp_path / "memory.db"
    store = IncidentMemoryStore(str(path))
    result = diagnosed("PM-ONE")

    store.remember(trace_id="trace-one", action="create-user", result=result)
    store.remember(trace_id="trace-one", action="create-user", result=result)

    assert store.count() == 1
    database_bytes = path.read_bytes()
    assert b"hunter2" not in database_bytes
    assert b"RAW SECRET LOG" not in database_bytes
