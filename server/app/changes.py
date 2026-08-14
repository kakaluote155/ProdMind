from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from .config import positive_int_env
from .models import ChangeEventCreate, ChangeEventResponse


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)


@lru_cache(maxsize=1)
def configured_change_store() -> "ChangeStore":
    path = os.getenv("PRODMIND_CHANGE_PATH", ".prodmind/prodmind-changes.db")
    return ChangeStore(
        path,
        retention_days=positive_int_env("PRODMIND_CHANGE_RETENTION_DAYS", 30),
        max_records_per_project=positive_int_env(
            "PRODMIND_CHANGE_MAX_RECORDS_PER_PROJECT", 5000
        ),
    )


class ChangeStore:
    """Compact project-scoped deployment/configuration timeline.

    This store deliberately accepts metadata only. It does not persist source
    code, patches, repository contents, request bodies or CI logs.
    """

    def __init__(
        self,
        path: str,
        *,
        retention_days: int = 30,
        max_records_per_project: int = 5000,
    ) -> None:
        if retention_days < 1 or max_records_per_project < 1:
            raise ValueError("change retention and capacity must be positive")
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS change_event (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    version TEXT,
                    revision TEXT,
                    change_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    actor TEXT,
                    source TEXT,
                    occurred_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_change_project_service_time "
                "ON change_event(project_id, service_name, occurred_at DESC)"
            )

    def record(self, *, project_id: str, event: ChangeEventCreate) -> ChangeEventResponse:
        now = datetime.now(UTC)
        occurred_at = _as_utc(event.occurred_at or now)
        change_id = f"CHG-{uuid4().hex[:10].upper()}"
        summary = _safe_text(event.summary, limit=1000)
        actor = _safe_optional(event.actor, limit=200)
        source = _safe_optional(event.source, limit=200)
        version = _safe_optional(event.version, limit=200)
        revision = _safe_optional(event.revision, limit=200)
        service_name = _safe_text(event.service_name, limit=200)

        with self._connect() as connection:
            self._prune(connection, project_id=project_id, now=now)
            connection.execute(
                """
                INSERT INTO change_event(
                    id, project_id, service_name, version, revision,
                    change_type, summary, actor, source, occurred_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    project_id,
                    service_name,
                    version,
                    revision,
                    event.change_type,
                    summary,
                    actor,
                    source,
                    occurred_at.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.execute(
                """
                DELETE FROM change_event
                 WHERE project_id = ?
                   AND id NOT IN (
                       SELECT id FROM change_event
                        WHERE project_id = ?
                        ORDER BY occurred_at DESC, created_at DESC
                        LIMIT ?
                   )
                """,
                (project_id, project_id, self.max_records_per_project),
            )

        return ChangeEventResponse(
            id=change_id,
            project_id=project_id,
            service_name=service_name,
            version=version,
            revision=revision,
            change_type=event.change_type,
            summary=summary,
            actor=actor,
            source=source,
            occurred_at=occurred_at,
            created_at=now,
        )

    def find_recent(
        self,
        *,
        project_id: str,
        service_names: list[str],
        service_versions: dict[str, str],
        incident_at: datetime | None,
        lookback_hours: int = 6,
        limit: int = 5,
    ) -> list[ChangeEventResponse]:
        if not service_names:
            return []

        at = _as_utc(incident_at or datetime.now(UTC))
        since = at - timedelta(hours=max(1, lookback_hours))
        placeholders = ",".join("?" for _ in service_names)
        params: list[object] = [project_id, *service_names, since.isoformat(), at.isoformat(), limit * 4]

        with self._connect() as connection:
            self._prune(connection, project_id=project_id, now=datetime.now(UTC))
            rows = connection.execute(
                f"""
                SELECT id, project_id, service_name, version, revision,
                       change_type, summary, actor, source, occurred_at, created_at
                  FROM change_event
                 WHERE project_id = ?
                   AND service_name IN ({placeholders})
                   AND occurred_at >= ?
                   AND occurred_at <= ?
                 ORDER BY occurred_at DESC
                 LIMIT ?
                """,
                params,
            ).fetchall()

        events = [_row_to_event(row) for row in rows]
        events.sort(
            key=lambda item: (
                0 if item.version and service_versions.get(item.service_name) == item.version else 1,
                -item.occurred_at.timestamp(),
            )
        )
        return events[:limit]

    def count(self, *, project_id: str | None = None) -> int:
        with self._connect() as connection:
            if project_id is not None:
                self._prune(connection, project_id=project_id, now=datetime.now(UTC))
            if project_id is None:
                row = connection.execute("SELECT COUNT(*) AS count FROM change_event").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM change_event WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
        return int(row["count"])

    def _prune(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        now: datetime,
    ) -> None:
        cutoff = _as_utc(now) - timedelta(days=self.retention_days)
        connection.execute(
            "DELETE FROM change_event WHERE project_id = ? AND occurred_at < ?",
            (project_id, cutoff.isoformat()),
        )


def _row_to_event(row: sqlite3.Row) -> ChangeEventResponse:
    return ChangeEventResponse(
        id=row["id"],
        project_id=row["project_id"],
        service_name=row["service_name"],
        version=row["version"],
        revision=row["revision"],
        change_type=row["change_type"],
        summary=row["summary"],
        actor=row["actor"],
        source=row["source"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_optional(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = _safe_text(value, limit=limit)
    return cleaned or None


def _safe_text(value: str, *, limit: int) -> str:
    collapsed = " ".join(value.strip().split())
    redacted = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[redacted]", collapsed)
    return redacted[:limit]
