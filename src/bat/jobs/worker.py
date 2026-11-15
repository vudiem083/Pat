"""Job execution context handed to job handlers."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..core.models import Job, JobStatus, utcnow
from .state import JobAborted


@dataclass
class JobContext:
    """Everything a job handler may use. Handlers must stay transport-agnostic."""

    job: Job
    log_path: Path
    cancel_event: threading.Event
    params: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    _session_id: str | None = None
    _environment_id: str | None = None
    _state_updater: Callable[[Job], None] | None = None

    # -- logging -----------------------------------------------------------
    def log(self, message: str, level: str = "INFO") -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "timestamp": utcnow(),
                "level": level,
                "job_id": self.job.job_id,
                "project_id": self.job.project_id,
                "message": message,
            }
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    # -- cancellation ------------------------------------------------------
    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise JobAborted(
                "BAT-JOB-001",
                "Job was cancelled before completion.",
                status=JobStatus.CANCELLED,
                result={"cancelled": True},
            )

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    # -- state -------------------------------------------------------------
    def bind_session(self, session_id: str | None, environment_id: str | None = None) -> None:
        self._session_id = session_id
        if environment_id:
            self._environment_id = environment_id
        self.job.session_id = session_id
        if environment_id:
            self.job.environment_id = environment_id
        if self._state_updater is not None:
            self._state_updater(self.job)

    def progress(self, value: float, message: str | None = None) -> None:
        self.job.progress = max(0.0, min(1.0, float(value)))
        if message:
            self.log(message)
        if self._state_updater is not None:
            self._state_updater(self.job)


JobHandler = Callable[[JobContext], dict[str, Any]]
