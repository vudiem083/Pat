"""Job MCP tools."""

from __future__ import annotations

from typing import Any

from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def start_runtime_job(
        project_id: str,
        job_type: str = "RUNTIME_TEST",
        params: dict | None = None,
        timeout_seconds: float | None = None,
    ) -> dict:
        """Start a background job (VALIDATE, BUILD, RUNTIME_TEST, RUNTIME_START, DIAGNOSE)."""
        payload = {"project_id": project_id, **(params or {})}
        job = services.jobs.submit(
            job_type.upper(),
            project_id=project_id,
            params=payload,
            timeout_seconds=timeout_seconds,
        )
        return {"job": job.model_dump()}

    @mcp.tool()
    @tool
    def get_job_status(job_id: str) -> dict:
        """Get a job's current state, progress and (when finished) result."""
        return services.jobs.get(job_id).model_dump()

    @mcp.tool()
    @tool
    def wait_for_job(job_id: str, timeout_seconds: float = 30.0) -> dict:
        """Wait for a job with a bounded timeout.

        A timed-out wait does NOT cancel the job; it keeps running and can be
        polled again.
        """
        return services.jobs.wait(job_id, timeout=timeout_seconds)

    @mcp.tool()
    @tool
    def cancel_job(job_id: str) -> dict:
        """Explicitly cancel a job that has not reached a terminal state."""
        return services.jobs.cancel(job_id).model_dump()

    @mcp.tool()
    @tool
    def get_job_logs(job_id: str, tail: int = 200) -> dict:
        """Read a job's structured log lines."""
        return services.jobs.logs(job_id, tail=tail)

    @mcp.tool()
    @tool
    def get_job_report(job_id: str) -> dict:
        """Read a job's final report (status, error code, result, incidents)."""
        return services.jobs.report(job_id)

    @mcp.tool()
    @tool
    def get_runtime_health() -> dict:
        """Runtime adapter availability, running sessions, environments and job counts."""
        return services.runtime_health()

    @mcp.tool()
    @tool
    def get_runtime_heartbeat(session_id: str) -> dict:
        """Read the latest heartbeat for a runtime session."""
        return services.runtime_heartbeat(session_id)
