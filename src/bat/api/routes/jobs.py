"""Job endpoints: create, poll, wait, cancel, logs, report."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...core.models import JobStatus
from ...services import BatServices
from ..dependencies import get_services, pagination, require_api_key
from ..schemas import JobCreateRequest, WaitRequest

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])

_TERMINAL = {
    JobStatus.COMPLETED.value,
    JobStatus.FAILED.value,
    JobStatus.CRASHED.value,
    JobStatus.TIMED_OUT.value,
    JobStatus.CANCELLED.value,
}


@router.post("", status_code=202, summary="Create a background job")
def create_job(payload: JobCreateRequest, services: BatServices = Depends(get_services)) -> dict:
    params = dict(payload.params)
    if payload.project_id:
        params.setdefault("project_id", payload.project_id)
    job = services.jobs.submit(
        payload.job_type,
        project_id=payload.project_id,
        params=params,
        timeout_seconds=payload.timeout_seconds,
    )
    return {"job": job.model_dump(), "poll": f"/api/v1/jobs/{job.job_id}"}


@router.get("", summary="List jobs")
def list_jobs(
    project_id: str | None = None,
    status: str | None = Query(default=None, pattern="^(QUEUED|STARTING|RUNNING|COMPLETED|FAILED|CRASHED|TIMED_OUT|CANCELLED)$"),
    services: BatServices = Depends(get_services),
    page: tuple[int, int] = Depends(pagination),
) -> dict:
    limit, offset = page
    jobs = services.jobs.list(
        project_id=project_id, status=status, limit=limit, offset=offset
    )
    return {
        "items": [j.model_dump() for j in jobs],
        "limit": limit,
        "offset": offset,
        "total": services.db.count_jobs(status),
    }


@router.get("/{job_id}", summary="Get job status")
def get_job(job_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.jobs.get(job_id).model_dump()


@router.post("/{job_id}/wait", summary="Wait for a job (bounded, does not cancel)")
def wait_for_job(
    job_id: str,
    payload: WaitRequest | None = None,
    services: BatServices = Depends(get_services),
) -> dict:
    timeout = payload.timeout if payload else None
    return services.jobs.wait(job_id, timeout=timeout)


@router.post("/{job_id}/cancel", summary="Cancel a job explicitly")
def cancel_job(job_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.jobs.cancel(job_id).model_dump()


@router.get("/{job_id}/logs", summary="Job logs")
def job_logs(
    job_id: str,
    tail: int = Query(default=200, ge=1, le=2000),
    services: BatServices = Depends(get_services),
) -> dict:
    return services.jobs.logs(job_id, tail=tail)


@router.get("/{job_id}/report", summary="Job report")
def job_report(job_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.jobs.report(job_id)
