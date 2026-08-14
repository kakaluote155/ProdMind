from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import InvestigationResponse


@dataclass(slots=True)
class SimilarIncident:
    incident_id: str
    trace_id: str
    project_id: str
    category: str
    action: str | None
    root_summary: str
    resolution_summary: str
    score: float
    created_at: str


class IncidentMemoryStore:
    """Compact operational memory scoped to one project at query time."""

    def __init__(
        self,
        path: str,
        *,
        retention_days: int = 90,
        max_records_per_project: int = 2000,
    ) -> None:
        if retention_days < 1 or max_records_per_project < 1:
            raise ValueError("memory retention and capacity must be positive")
        self.path = Path(path)
        self.retention_days = retention_days
        self.max_records_per_project = max_records_per_project
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            self._create_table(connection)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(incident_memory)").fetchall()
            }
            if "project_id" not in columns:
                connection.execute(
                    "ALTER TABLE incident_memory ADD COLUMN project_id TEXT NOT NULL DEFAULT 'legacy'"
                )
            if self._has_global_trace_unique_constraint(connection):
                self._migrate_project_trace_uniqueness(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_incident_memory_project_category
                ON incident_memory(project_id, category, created_at DESC)
                """
            )

    @staticmethod
    def _create_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'legacy',
                category TEXT NOT NULL,
                action TEXT,
                root_summary TEXT NOT NULL,
                resolution_summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, trace_id)
            )
            """
        )

    @staticmethod
    def _has_global_trace_unique_constraint(connection: sqlite3.Connection) -> bool:
        for index in connection.execute("PRAGMA index_list(incident_memory)").fetchall():
            if not index["unique"]:
                continue
            columns = [
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM pragma_index_info(?)",
                    (index["name"],),
                ).fetchall()
            ]
            if columns == ["trace_id"]:
                return True
        return False

    def _migrate_project_trace_uniqueness(self, connection: sqlite3.Connection) -> None:
        connection.execute("DROP INDEX IF EXISTS idx_incident_memory_project_category")
        connection.execute("ALTER TABLE incident_memory RENAME TO incident_memory_v0")
        self._create_table(connection)
        connection.execute(
            """
            INSERT INTO incident_memory(
                id, incident_id, trace_id, project_id, category, action,
                root_summary, resolution_summary, created_at
            )
            SELECT id, incident_id, trace_id, project_id, category, action,
                   root_summary, resolution_summary, created_at
              FROM incident_memory_v0
            """
        )
        connection.execute("DROP TABLE incident_memory_v0")

    def remember(
        self,
        *,
        project_id: str,
        trace_id: str,
        action: str | None,
        result: InvestigationResponse,
    ) -> None:
        if result.status != "diagnosed" or result.root_cause is None:
            return

        resolution_summary = " ".join(result.recommended_actions[:3])
        with self._connect() as connection:
            self._prune(connection, project_id=project_id)
            connection.execute(
                """
                INSERT INTO incident_memory(
                    incident_id, trace_id, project_id, category, action,
                    root_summary, resolution_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, trace_id) DO NOTHING
                """,
                (
                    result.incident_id,
                    trace_id,
                    project_id,
                    result.root_cause.category,
                    action,
                    result.root_cause.summary,
                    resolution_summary,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.execute(
                """
                DELETE FROM incident_memory
                 WHERE project_id = ?
                   AND id NOT IN (
                       SELECT id FROM incident_memory
                        WHERE project_id = ?
                        ORDER BY created_at DESC, id DESC
                        LIMIT ?
                   )
                """,
                (project_id, project_id, self.max_records_per_project),
            )

    def find_similar(
        self,
        *,
        project_id: str,
        category: str,
        action: str | None,
        exclude_trace_id: str,
        limit: int = 3,
    ) -> list[SimilarIncident]:
        with self._connect() as connection:
            self._prune(connection, project_id=project_id)
            rows = connection.execute(
                """
                SELECT incident_id, trace_id, project_id, category, action,
                       root_summary, resolution_summary, created_at
                  FROM incident_memory
                 WHERE project_id = ? AND category = ? AND trace_id <> ?
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (project_id, category, exclude_trace_id, limit),
            ).fetchall()

        matches: list[SimilarIncident] = []
        for row in rows:
            score = 1.0 if action and row["action"] == action else 0.82
            matches.append(
                SimilarIncident(
                    incident_id=row["incident_id"],
                    trace_id=row["trace_id"],
                    project_id=row["project_id"],
                    category=row["category"],
                    action=row["action"],
                    root_summary=row["root_summary"],
                    resolution_summary=row["resolution_summary"],
                    score=score,
                    created_at=row["created_at"],
                )
            )
        return matches

    def count(self, project_id: str | None = None) -> int:
        with self._connect() as connection:
            if project_id is not None:
                self._prune(connection, project_id=project_id)
            if project_id is None:
                row = connection.execute("SELECT COUNT(*) AS count FROM incident_memory").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM incident_memory WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
        return int(row["count"])

    def _prune(self, connection: sqlite3.Connection, *, project_id: str) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        connection.execute(
            "DELETE FROM incident_memory WHERE project_id = ? AND created_at < ?",
            (project_id, cutoff.isoformat()),
        )
