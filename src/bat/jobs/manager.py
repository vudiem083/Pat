"""SQLite-backed background job manager.

Guarantees encoded here:

* every job is persisted before work starts,
* a job that raises still reaches a terminal state with an error code,
* a handler that dies silently is detected and marked ``BAT-JOB-002``,
* waiting for a job never cancels it; only ``cancel_job`` does,
* job logs are append-only files so a crash cannot erase evidence,
* a worker timeout records ``TIMED_OUT`` and signals cooperative cancellation.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..core.errors import BatError, make_error
from ..core.models import (
    Job,
    JobReport,
    JobStatus,
    JobType,
    TERMINAL_JOB_STATUSES,
    utcnow,
)
from ..observability.structured_logger import get_logger
from .heartbeat import JobHeartbeat
from .state import JobAborted, can_transition, is_terminal
from .worker import JobContext, JobHandler


class JobManager:
    def __init__(self, db: Any, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._handlers: dict[str, JobHandler] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.job_workers), thread_name_prefix="bat-job"
        )
        self._cancel_events: dict[str, threading.Event] = {}
        self._futures: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        self.logger = get_logger("jobs")
        self.settings.jobs_log_root.mkdir(parents=True, exist_ok=True)

    # -- registration ------------------------------------------------------
    def register(self, job_type: JobType | str, handler: JobHandler) -> None:
        self._handlers[str(job_type)] = handler

    def registered_types(self) -> list[str]:
        return sorted(self._handlers)

    # -- paths -------------------------------------------------------------
    def log_path(self, job_id: str) -> Path:
        return self.settings.jobs_log_root / f"{job_id}.log"

    def heartbeat_path(self, job_id: str) -> Path:
        return self.settings.jobs_log_root / f"{job_id}.heartbeat.json"

    def report_path(self, job_id: str) -> Path:
        return self.settings.jobs_log_root / f"{job_id}.report.json"

    # -- lifecycle ---------------------------------------------------------
    def recover_orphans(self) -> list[str]:
        """Mark jobs left RUNNING/STARTING by a previous BAT process as CRASHED."""
        recovered: list[str] = []
        for job in self.db.stale_jobs(("STARTING", "RUNNING", "QUEUED")):
            job.status = JobStatus.CRASHED.value
            job.completed_at = utcnow()
            job.error_code = "BAT-JOB-002"
            job.message = (
                "Job was left non-terminal by a previous BAT process (worker failure or host "
                "restart). No result was recorded, so the job is marked CRASHED."
            )
            job.result = {"recovered_on_startup": True}
            self.db.save_job(job)
            self._write_report(job, notes=[job.message])
            recovered.append(job.job_id)
        if recovered:
            self.logger.warning("Recovered %d orphaned job(s)", len(recovered))
        return recovered

    def submit(
        self,
        job_type: JobType | str,
        *,
        project_id: str | None = None,
        params: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> Job:
        job_type_value = str(job_type)
        if job_type_value not in self._handlers:
            raise make_error(
                "BAT-INPUT-001",
                f"No handler registered for job type {job_type_value!r}. "
                f"Known types: {', '.join(self.registered_types())}.",
            )
        if self._shutdown.is_set():
            raise make_error("BAT-JOB-003", "Job queue is shut down.")
        job = Job(
            project_id=project_id,
            job_type=JobType(job_type_value),
            timeout_seconds=timeout_seconds,
        )
        self.db.save_job(job)
        cancel_event = threading.Event()
        self._cancel_events[job.job_id] = cancel_event
        self.log_path(job.job_id).parent.mkdir(parents=True, exist_ok=True)
        future = self._executor.submit(self._run, job.job_id, params or {}, cancel_event)
        self._futures[job.job_id] = future
        future.add_done_callback(lambda _f, jid=job.job_id: self._on_done(jid))
        self.logger.info("Submitted job %s (%s)", job.job_id, job_type_value)
        return job

    def _run(self, job_id: str, params: dict[str, Any], cancel_event: threading.Event) -> None:
        job = self._require(job_id)
        handler = self._handlers[str(job.job_type)]
        context = JobContext(
            job=job,
            log_path=self.log_path(job_id),
            cancel_event=cancel_event,
            params=params,
            _state_updater=self._save,
        )
        heartbeat = JobHeartbeat(
            self.heartbeat_path(job_id),
            interval=max(1.0, min(5.0, self.settings.heartbeat_interval)),
            metadata={"job_id": job_id, "job_type": str(job.job_type)},
        )
        heartbeat.start()
        self._transition(job, JobStatus.STARTING)
        timeout_thread = self._start_timeout_watchdog(job, cancel_event)
        context.log("Job started.")
        result: dict[str, Any] = {}
        status = JobStatus.COMPLETED
        error_code: str | None = None
        message: str | None = None
        try:
            self._transition(job, JobStatus.RUNNING)
            result = handler(context) or {}
            if cancel_event.is_set():
                status = JobStatus.CANCELLED
                error_code = "BAT-JOB-001"
                message = "Job was cancelled."
                result.setdefault("cancelled", True)
            context.log("Job handler finished successfully.")
        except JobAborted as exc:
            status = JobStatus(exc.status)
            error_code = exc.code
            message = exc.message
            result = exc.result
            context.log(f"Job aborted: {exc.code} {exc.message}", level="ERROR")
        except BatError as exc:
            status = JobStatus.FAILED
            error_code = exc.code
            message = exc.message
            result = {"error": exc.to_dict()}
            context.log(f"Job failed: {exc.code} {exc.message}", level="ERROR")
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
            status = JobStatus.FAILED
            error_code = "BAT-JOB-004"
            message = f"Unhandled error in job handler: {type(exc).__name__}: {exc}"
            result = {"error": {"type": type(exc).__name__, "message": str(exc)}}
            context.log(message, level="ERROR")
        finally:
            if timeout_thread is not None:
                timeout_thread.set()
            current = self.db.get_job(job_id)
            if current is not None and is_terminal(current.status):
                # A timeout/cancel already recorded a terminal state; keep it.
                heartbeat.stop(final_state=str(current.status))
                return
            job.result = result
            job.error_code = error_code
            job.message = message
            job.completed_at = utcnow()
            job.progress = 1.0
            job.status = status.value
            self.db.save_job(job)
            self._write_report(job)
            heartbeat.stop(final_state=str(status))
            context.log(f"Job finished with status {status.value}.")

    def _start_timeout_watchdog(
        self, job: Job, cancel_event: threading.Event
    ) -> threading.Event | None:
        timeout = job.timeout_seconds or 0
        if timeout <= 0:
            return None
        done = threading.Event()

        def watch() -> None:
            if done.wait(timeout):
                return
            current = self.db.get_job(job.job_id)
            if current is None or is_terminal(current.status):
                return
            current.status = JobStatus.TIMED_OUT.value
            current.completed_at = utcnow()
            current.error_code = "BAT-RUNTIME-005"
            current.message = (
                f"Job exceeded its timeout of {timeout:g}s. The worker was signalled to stop; "
                "its result is not trusted."
            )
            current.result = {"timed_out": True, "timeout_seconds": timeout}
            self.db.save_job(current)
            self._write_report(current, notes=[current.message])
            cancel_event.set()
            self.logger.warning("Job %s timed out after %ss", job.job_id, timeout)

        thread = threading.Thread(target=watch, name=f"bat-timeout-{job.job_id}", daemon=True)
        thread.start()
        return done

    def _on_done(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job is None:
            return
        if not is_terminal(job.status):
            job.status = JobStatus.CRASHED.value
            job.completed_at = utcnow()
            job.error_code = "BAT-JOB-002"
            job.message = (
                "Job worker ended without recording a terminal state (worker failure). The job is "
                "marked CRASHED instead of being left RUNNING."
            )
            job.result = {"worker_failure": True}
            self.db.save_job(job)
            self._write_report(job, notes=[job.message])
            self.logger.error("Worker for job %s ended without a terminal state", job_id)
        with self._lock:
            self._futures.pop(job_id, None)

    # -- access ------------------------------------------------------------
    def _require(self, job_id: str) -> Job:
        job = self.db.get_job(job_id)
        if job is None:
            raise make_error("BAT-NOTFOUND-003", f"Job {job_id} not found.", http_status=404)
        return job

    def get(self, job_id: str) -> Job:
        return self._require(job_id)

    def list(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return self.db.list_jobs(
            project_id=project_id, status=status, limit=limit, offset=offset
        )

    def wait(self, job_id: str, timeout: float | None = None) -> dict[str, Any]:
        """Wait for a job with a bounded timeout.

        The wait is observational: hitting the timeout does not cancel the job.
        """
        job = self._require(job_id)
        budget = self.settings.default_wait_seconds if timeout is None else float(timeout)
        budget = max(0.0, min(budget, self.settings.max_wait_seconds))
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            job = self._require(job_id)
            if is_terminal(job.status):
                return {"job": job.model_dump(), "waited_seconds": round(budget - (deadline - time.monotonic()), 2), "completed": True}
            time.sleep(0.15)
        job = self._require(job_id)
        return {
            "job": job.model_dump(),
            "completed": is_terminal(job.status),
            "waited_seconds": round(budget, 2),
            "note": (
                "Wait timed out. The job is still running and was NOT cancelled; call get_job_status "
                "or wait_for_job again."
            ),
        }

    def cancel(self, job_id: str) -> Job:
        job = self._require(job_id)
        if is_terminal(job.status):
            raise make_error(
                "BAT-JOB-001",
                f"Job {job_id} is already {job.status} and cannot be cancelled.",
                http_status=409,
            )
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        job.cancelled = True
        if job.status == JobStatus.QUEUED.value:
            job.status = JobStatus.CANCELLED.value
            job.completed_at = utcnow()
            job.error_code = "BAT-JOB-001"
            job.message = "Job was cancelled before it started."
            self.db.save_job(job)
            self._write_report(job, notes=[job.message])
        else:
            job.message = (
                "Cancellation requested. The worker stops at its next checkpoint; the job is "
                "marked CANCELLED."
            )
            job.status = JobStatus.CANCELLED.value
            job.completed_at = utcnow()
            job.error_code = "BAT-JOB-001"
            self.db.save_job(job)
            self._write_report(job, notes=[job.message])
        return job

    def logs(self, job_id: str, *, tail: int = 200) -> dict[str, Any]:
        self._require(job_id)
        path = self.log_path(job_id)
        if not path.exists():
            return {"job_id": job_id, "lines": [], "path": str(path)}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = max(1, min(int(tail), 2000))
        parsed: list[dict[str, Any]] = []
        for raw in lines[-tail:]:
            try:
                parsed.append(json.loads(raw))
            except json.JSONDecodeError:
                parsed.append({"message": raw})
        return {
            "job_id": job_id,
            "path": str(path),
            "total_lines": len(lines),
            "lines": parsed,
        }

    def report(self, job_id: str) -> dict[str, Any]:
        job = self._require(job_id)
        path = self.report_path(job_id)
        if not path.exists():
            return self._report_payload(job).model_dump()
        return json.loads(path.read_text(encoding="utf-8"))

    # -- internals ---------------------------------------------------------
    def _save(self, job: Job) -> None:
        self.db.save_job(job)

    def _transition(self, job: Job, target: JobStatus) -> None:
        if not can_transition(job.status, target):
            self.logger.warning(
                "Rejected job transition %s -> %s for %s", job.status, target.value, job.job_id
            )
            return
        job.status = target.value
        if target is JobStatus.STARTING:
            job.started_at = utcnow()
        self.db.save_job(job)

    def _report_payload(self, job: Job, notes: list[str] | None = None) -> JobReport:
        started = job.started_at
        duration = None
        if started and job.completed_at:
            from datetime import datetime

            try:
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(job.completed_at.replace("Z", "+00:00"))
                duration = round((end_dt - start_dt).total_seconds(), 2)
            except ValueError:
                duration = None
        incidents = []
        try:
            if job.session_id:
                incidents = [
                    i.incident_id
                    for i in self.db.list_incidents(job_id=job.job_id, limit=100)
                ]
        except Exception:  # noqa: BLE001 - report must not fail on missing tables
            incidents = []
        return JobReport(
            job_id=job.job_id,
            project_id=job.project_id,
            job_type=JobType(job.job_type),
            status=JobStatus(job.status),
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            duration_seconds=duration,
            error_code=job.error_code,
            message=job.message,
            result=job.result or {},
            session_id=job.session_id,
            incidents=incidents,
            log_files=[str(self.log_path(job.job_id))],
            notes=notes or [],
        )

    def _write_report(self, job: Job, notes: list[str] | None = None) -> None:
        report = self._report_payload(job, notes)
        path = self.report_path(job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def active_count(self) -> int:
        return len([s for s in (JobStatus.RUNNING.value, JobStatus.STARTING.value) if self.db.count_jobs(s)])

    def queued_count(self) -> int:
        return self.db.count_jobs(JobStatus.QUEUED.value)

    def shutdown(self, wait: bool = False) -> None:
        self._shutdown.set()
        for event in self._cancel_events.values():
            event.set()
        self._executor.shutdown(wait=wait, cancel_futures=True)


def job_is_terminal(status: JobStatus | str) -> bool:
    return JobStatus(status) in TERMINAL_JOB_STATUSES
