"""SQLite persistence for projects, jobs, artifacts, sessions, incidents.

A single database file backs the whole MVP. Connections are opened per
operation, which keeps the class safe to use from FastAPI request handlers and
from background worker threads without a shared connection lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..core.errors import make_error
from ..core.models import (
    Artifact,
    Environment,
    Incident,
    Job,
    Project,
    RuntimeSession,
    ValidationReport,
)

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY,
        name       TEXT NOT NULL,
        project_type TEXT NOT NULL,
        target_version TEXT NOT NULL,
        status     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id     TEXT PRIMARY KEY,
        project_id TEXT,
        job_type   TEXT NOT NULL,
        status     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        error_code TEXT,
        session_id TEXT,
        environment_id TEXT,
        payload    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL,
        job_id      TEXT,
        artifact_type TEXT NOT NULL,
        file_name   TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        checksum    TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        payload     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_reports (
        report_id  TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        status     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        environment_id TEXT NOT NULL,
        project_id TEXT,
        job_id     TEXT,
        process_status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        payload    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY,
        project_id  TEXT,
        job_id      TEXT,
        session_id  TEXT,
        incident_type TEXT NOT NULL,
        severity    TEXT NOT NULL,
        timestamp   TEXT NOT NULL,
        payload     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS environments (
        environment_id TEXT PRIMARY KEY,
        project_id TEXT,
        status     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_incidents_project ON incidents(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id)",
)


class Database:
    """Thin SQLite wrapper storing typed models as JSON payloads."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    # -- internals ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            for statement in _SCHEMA:
                conn.execute(statement)
            self._migrate_sessions_project_id(conn)
            conn.commit()

    @staticmethod
    def _migrate_sessions_project_id(conn: sqlite3.Connection) -> None:
        """Allow sessions without a project (older schema declared NOT NULL)."""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchone()
        if not row or "project_id TEXT NOT NULL" not in (row[0] or ""):
            return
        conn.executescript(
            """
            ALTER TABLE sessions RENAME TO sessions_legacy;
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                environment_id TEXT NOT NULL,
                project_id TEXT,
                job_id     TEXT,
                process_status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                payload    TEXT NOT NULL
            );
            INSERT INTO sessions (session_id, environment_id, project_id, job_id,
                                  process_status, started_at, payload)
                SELECT session_id, environment_id, project_id, job_id,
                       process_status, started_at, payload FROM sessions_legacy;
            DROP TABLE sessions_legacy;
            """
        )

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(sql, tuple(params))
            conn.commit()

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            return list(conn.execute(sql, tuple(params)).fetchall())

    def ping(self) -> bool:
        try:
            self._query("SELECT 1")
            return True
        except sqlite3.Error:  # pragma: no cover - defensive
            return False

    # -- projects ----------------------------------------------------------
    def save_project(self, project: Project) -> None:
        payload = project.model_dump_json()
        self._execute(
            """
            INSERT INTO projects (project_id, name, project_type, target_version, status,
                                  created_at, updated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                name=excluded.name, project_type=excluded.project_type,
                target_version=excluded.target_version, status=excluded.status,
                updated_at=excluded.updated_at, payload=excluded.payload
            """,
            (
                project.project_id,
                project.name,
                project.project_type,
                project.target_version,
                project.status,
                project.created_at,
                project.updated_at,
                payload,
            ),
        )

    def get_project(self, project_id: str) -> Project | None:
        rows = self._query("SELECT payload FROM projects WHERE project_id = ?", (project_id,))
        return Project.model_validate_json(rows[0]["payload"]) if rows else None

    def find_project_by_name(self, name: str) -> Project | None:
        rows = self._query("SELECT payload FROM projects WHERE lower(name) = lower(?)", (name,))
        return Project.model_validate_json(rows[0]["payload"]) if rows else None

    def list_projects(self, limit: int = 100, offset: int = 0) -> list[Project]:
        rows = self._query(
            "SELECT payload FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [Project.model_validate_json(r["payload"]) for r in rows]

    def count_projects(self) -> int:
        return int(self._query("SELECT COUNT(*) AS c FROM projects")[0]["c"])

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.commit()
            return cur.rowcount > 0

    # -- jobs --------------------------------------------------------------
    def save_job(self, job: Job) -> None:
        self._execute(
            """
            INSERT INTO jobs (job_id, project_id, job_type, status, created_at, started_at,
                              completed_at, error_code, session_id, environment_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status, started_at=excluded.started_at,
                completed_at=excluded.completed_at, error_code=excluded.error_code,
                session_id=excluded.session_id, environment_id=excluded.environment_id,
                payload=excluded.payload
            """,
            (
                job.job_id,
                job.project_id,
                job.job_type,
                job.status,
                job.created_at,
                job.started_at,
                job.completed_at,
                job.error_code,
                job.session_id,
                job.environment_id,
                job.model_dump_json(),
            ),
        )

    def get_job(self, job_id: str) -> Job | None:
        rows = self._query("SELECT payload FROM jobs WHERE job_id = ?", (job_id,))
        return Job.model_validate_json(rows[0]["payload"]) if rows else None

    def list_jobs(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = self._query(
            f"SELECT payload FROM jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        return [Job.model_validate_json(r["payload"]) for r in rows]

    def count_jobs(self, status: str | None = None) -> int:
        if status:
            rows = self._query("SELECT COUNT(*) AS c FROM jobs WHERE status = ?", (status,))
        else:
            rows = self._query("SELECT COUNT(*) AS c FROM jobs")
        return int(rows[0]["c"])

    def stale_jobs(self, active_statuses: tuple[str, ...]) -> list[Job]:
        placeholders = ", ".join("?" for _ in active_statuses)
        rows = self._query(
            f"SELECT payload FROM jobs WHERE status IN ({placeholders})",
            active_statuses,
        )
        return [Job.model_validate_json(r["payload"]) for r in rows]

    # -- artifacts ---------------------------------------------------------
    def save_artifact(self, artifact: Artifact) -> None:
        self._execute(
            """
            INSERT INTO artifacts (artifact_id, project_id, job_id, artifact_type, file_name,
                                   storage_path, checksum, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                storage_path=excluded.storage_path, checksum=excluded.checksum,
                file_name=excluded.file_name, payload=excluded.payload
            """,
            (
                artifact.artifact_id,
                artifact.project_id,
                artifact.job_id,
                artifact.artifact_type,
                artifact.file_name,
                artifact.storage_path,
                artifact.checksum,
                artifact.created_at,
                artifact.model_dump_json(),
            ),
        )

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        rows = self._query("SELECT payload FROM artifacts WHERE artifact_id = ?", (artifact_id,))
        return Artifact.model_validate_json(rows[0]["payload"]) if rows else None

    def list_artifacts(self, project_id: str | None = None, limit: int = 50) -> list[Artifact]:
        if project_id:
            rows = self._query(
                "SELECT payload FROM artifacts WHERE project_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            )
        else:
            rows = self._query(
                "SELECT payload FROM artifacts ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [Artifact.model_validate_json(r["payload"]) for r in rows]

    # -- validation reports ------------------------------------------------
    def save_validation_report(self, report: ValidationReport) -> None:
        self._execute(
            """
            INSERT INTO validation_reports (report_id, project_id, status, created_at, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET payload=excluded.payload, status=excluded.status
            """,
            (
                report.report_id,
                report.project_id,
                report.status,
                report.created_at,
                report.model_dump_json(),
            ),
        )

    def get_validation_report(self, report_id: str) -> ValidationReport | None:
        rows = self._query(
            "SELECT payload FROM validation_reports WHERE report_id = ?", (report_id,)
        )
        return ValidationReport.model_validate_json(rows[0]["payload"]) if rows else None

    def latest_validation_report(self, project_id: str) -> ValidationReport | None:
        rows = self._query(
            "SELECT payload FROM validation_reports WHERE project_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        )
        return ValidationReport.model_validate_json(rows[0]["payload"]) if rows else None

    # -- sessions ----------------------------------------------------------
    def save_session(self, session: RuntimeSession) -> None:
        self._execute(
            """
            INSERT INTO sessions (session_id, environment_id, project_id, job_id,
                                  process_status, started_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                process_status=excluded.process_status, payload=excluded.payload
            """,
            (
                session.session_id,
                session.environment_id,
                session.project_id,
                session.job_id,
                session.process_status,
                session.started_at,
                session.model_dump_json(),
            ),
        )

    def get_session(self, session_id: str) -> RuntimeSession | None:
        rows = self._query("SELECT payload FROM sessions WHERE session_id = ?", (session_id,))
        return RuntimeSession.model_validate_json(rows[0]["payload"]) if rows else None

    def list_sessions(
        self, project_id: str | None = None, limit: int = 50
    ) -> list[RuntimeSession]:
        if project_id:
            rows = self._query(
                "SELECT payload FROM sessions WHERE project_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (project_id, limit),
            )
        else:
            rows = self._query(
                "SELECT payload FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            )
        return [RuntimeSession.model_validate_json(r["payload"]) for r in rows]

    # -- incidents ---------------------------------------------------------
    def save_incident(self, incident: Incident) -> None:
        self._execute(
            """
            INSERT INTO incidents (incident_id, project_id, job_id, session_id,
                                   incident_type, severity, timestamp, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                severity=excluded.severity, payload=excluded.payload
            """,
            (
                incident.incident_id,
                incident.project_id,
                incident.job_id,
                incident.session_id,
                incident.incident_type,
                incident.severity,
                incident.timestamp,
                incident.model_dump_json(),
            ),
        )

    def get_incident(self, incident_id: str) -> Incident | None:
        rows = self._query("SELECT payload FROM incidents WHERE incident_id = ?", (incident_id,))
        return Incident.model_validate_json(rows[0]["payload"]) if rows else None

    def list_incidents(
        self,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("project_id", project_id),
            ("session_id", session_id),
            ("job_id", job_id),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = self._query(
            f"SELECT payload FROM incidents {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params,
        )
        return [Incident.model_validate_json(r["payload"]) for r in rows]

    # -- environments ------------------------------------------------------
    def save_environment(self, environment: Environment) -> None:
        self._execute(
            """
            INSERT INTO environments (environment_id, project_id, status, created_at, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(environment_id) DO UPDATE SET
                status=excluded.status, payload=excluded.payload
            """,
            (
                environment.environment_id,
                environment.project_id,
                environment.status,
                environment.created_at,
                environment.model_dump_json(),
            ),
        )

    def get_environment(self, environment_id: str) -> Environment | None:
        rows = self._query(
            "SELECT payload FROM environments WHERE environment_id = ?", (environment_id,)
        )
        return Environment.model_validate_json(rows[0]["payload"]) if rows else None

    def list_environments(self, project_id: str | None = None) -> list[Environment]:
        if project_id:
            rows = self._query(
                "SELECT payload FROM environments WHERE project_id = ? "
                "ORDER BY created_at DESC",
                (project_id,),
            )
        else:
            rows = self._query("SELECT payload FROM environments ORDER BY created_at DESC")
        return [Environment.model_validate_json(r["payload"]) for r in rows]

    def delete_environment(self, environment_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM environments WHERE environment_id = ?", (environment_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    # -- diagnostics -------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {
            "projects": self.count_projects(),
            "jobs": self.count_jobs(),
            "incidents": int(self._query("SELECT COUNT(*) AS c FROM incidents")[0]["c"]),
            "artifacts": int(self._query("SELECT COUNT(*) AS c FROM artifacts")[0]["c"]),
            "sessions": int(self._query("SELECT COUNT(*) AS c FROM sessions")[0]["c"]),
        }

    def dump_table(self, table: str) -> list[Mapping[str, Any]]:  # pragma: no cover - debug
        allowed = {
            "projects",
            "jobs",
            "artifacts",
            "validation_reports",
            "sessions",
            "incidents",
            "environments",
        }
        if table not in allowed:
            raise make_error("BAT-INPUT-001", f"Unknown table {table!r}")
        return [dict(row) for row in self._query(f"SELECT * FROM {table}")]


def json_dumps(value: Any) -> str:  # pragma: no cover - convenience
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
