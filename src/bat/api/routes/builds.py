"""Build endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services import BatServices
from ..dependencies import get_services, require_api_key
from ..schemas import BuildRequest

router = APIRouter(tags=["builds"], dependencies=[Depends(require_api_key)])


@router.post("/projects/{project_id}/build", summary="Build artifacts synchronously")
def build_project(
    project_id: str,
    payload: BuildRequest | None = None,
    services: BatServices = Depends(get_services),
) -> dict:
    payload = payload or BuildRequest()
    return services.build_project(
        project_id, artifact_type=payload.artifact_type, strict=payload.strict
    )


@router.post("/projects/{project_id}/build/jobs", status_code=202, summary="Build as a job")
def build_job(
    project_id: str,
    payload: BuildRequest | None = None,
    services: BatServices = Depends(get_services),
) -> dict:
    payload = payload or BuildRequest()
    job = services.jobs.submit(
        "BUILD",
        project_id=project_id,
        params={
            "project_id": project_id,
            "artifact_type": payload.artifact_type,
            "strict": payload.strict,
        },
    )
    return {"job": job.model_dump(), "poll": f"/api/v1/jobs/{job.job_id}"}


@router.get("/projects/{project_id}/artifacts", summary="List project artifacts")
def list_artifacts(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    items = services.builders.list_artifacts(project_id)
    return {"items": items, "total": len(items)}
