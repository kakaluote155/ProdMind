from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import InvestigationResponse


@dataclass(slots=True)
class SimilarIncident:
    incident_id: str
    trace_id: str
    category: str
    action: str | None
    root_summary: str
    resolution_summary: str
    score: float
    created_at: str


class IncidentMemoryStore:
    """Compact operational memory.

    The default backend deliberately stores no raw logs, stack traces, request
    bodies or telemetry payloads. Those remain in the observability systems with
    their own retention/access policies. ProdMind stores only enough structured
    knowledge to recognize a previously solved class of incident.
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    action TEXT,
                    root_summary TEXT NOT NULL,
                    resolution_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_incident_memory_category ON incident_memory(category, created_at DESC)"
            )

    def remember(
        self,
        *,
        trace_id: str,
        action: str | None,
        result: InvestigationResponse,
    ) -> None:
        if result.status != "diagnosed" or result.root_cause is None:
            return

        resolution_summary = " ".join(result.recommended_actions[:3])
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO incident_memory(
                    incident_id,
                    trace_id,
                    category,
                    action,
                    root_summary,
                    resolution_summary,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO NOTHING
                """,
                (
                    result.incident_id,
                    trace_id,
                    result.root_cause.category,
                    action,
                    result.root_cause.summary,
                    resolution_summary,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def find_similar(
        self,
        *,
        category: str,
        action: str | None,
        exclude_trace_id: str,
        limit: int = 3,
    ) -> list[SimilarIncident]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT incident_id, trace_id, category, action,
                       root_summary, resolution_summary, created_at
                  FROM incident_memory
                 WHERE category = ? AND trace_id <> ?
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (category, exclude_trace_id, limit),
            ).fetchall()

        matches: list[SimilarIncident] = []
        for row in rows:
            score = 1.0 if action and row["action"] == action else 0.82
            matches.append(
                SimilarIncident(
                    incident_id=row["incident_id"],
                    trace_id=row["trace_id"],
                    category=row["category"],
                    action=row["action"],
                    root_summary=row["root_summary"],
                    resolution_summary=row["resolution_summary"],
                    score=score,
                    created_at=row["created_at"],
                )
            )
        return matches

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM incident_memory").fetchone()
        return int(row["count"])
