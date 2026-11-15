"""Health reporting for the REST/MCP surface."""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..core.models import HealthReport
from ..runtime.adapter import RuntimeAdapter
from ..version import __version__


class HealthService:
    def __init__(
        self,
        settings: Settings,
        db: Any,
        adapter: RuntimeAdapter,
        jobs: Any | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.adapter = adapter
        self.jobs = jobs

    def report(self) -> HealthReport:
        database_ok = self.db.ping()
        workspace_ok = self.settings.workspace_root.exists()
        runtime_ok = self.adapter.available()
        checks = {
            "database": "OK" if database_ok else "ERROR",
            "workspace": "OK" if workspace_ok else "ERROR",
            "runtime": "OK" if runtime_ok else self.adapter.unavailable_reason(),
            "runtime_root": "OK" if self.settings.runtime_root.exists() else "ERROR",
        }
        active = self.jobs.active_count() if self.jobs is not None else 0
        queued = self.jobs.queued_count() if self.jobs is not None else 0
        degraded = (
            not database_ok
            or not workspace_ok
            or not runtime_ok
            or not self.settings.runtime_root.exists()
        )
        return HealthReport(
            status="DEGRADED" if degraded else "OK",
            version=__version__,
            runtime_adapter=self.adapter.name,
            runtime_available=runtime_ok,
            database="OK" if database_ok else str(self.settings.database_path),
            workspace_root=str(self.settings.workspace_root),
            runtime_root=str(self.settings.runtime_root),
            active_jobs=active,
            queued_jobs=queued,
            checks=checks,
        )
