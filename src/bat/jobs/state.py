"""Job state machine and control-flow exception."""

from __future__ import annotations

from typing import Any

from ..core.models import JobStatus, TERMINAL_JOB_STATUSES

#: Allowed transitions. Anything else is a programming error and is rejected.
TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.STARTING, JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.STARTING: frozenset(
        {
            JobStatus.RUNNING,
            JobStatus.FAILED,
            JobStatus.CRASHED,
            JobStatus.TIMED_OUT,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CRASHED,
            JobStatus.TIMED_OUT,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CRASHED: frozenset(),
    JobStatus.TIMED_OUT: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


def can_transition(current: JobStatus | str, target: JobStatus | str) -> bool:
    current_status = JobStatus(current)
    target_status = JobStatus(target)
    if current_status is target_status:
        return True
    return target_status in TRANSITIONS.get(current_status, frozenset())


def is_terminal(status: JobStatus | str) -> bool:
    return JobStatus(status) in TERMINAL_JOB_STATUSES


class JobAborted(Exception):
    """Raised by job handlers to record a specific non-success outcome.

    ``status`` distinguishes a genuine process crash (``CRASHED``) from an
    unsupported environment (``FAILED``) and from an explicit cancellation.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: JobStatus | str = JobStatus.FAILED,
        result: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = JobStatus(status)
        self.result = result or {}
