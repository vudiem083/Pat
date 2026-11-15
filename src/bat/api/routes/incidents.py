"""Incident endpoints: list, details, diagnosis, correlation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...diagnostics.correlation import resolve_links
from ...services import BatServices
from ..dependencies import get_services, pagination, require_api_key

router = APIRouter(
    prefix="/incidents", tags=["incidents"], dependencies=[Depends(require_api_key)]
)


@router.get("", summary="List incidents")
def list_incidents(
    project_id: str | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    services: BatServices = Depends(get_services),
    page: tuple[int, int] = Depends(pagination),
) -> dict:
    limit, offset = page
    incidents = services.incidents.list(
        project_id=project_id,
        job_id=job_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [i.model_dump() for i in incidents],
        "limit": limit,
        "offset": offset,
        "total": len(incidents),
    }


@router.get("/{incident_id}", summary="Incident details and diagnosis")
def incident_details(incident_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.incidents.details(incident_id)


@router.get("/{incident_id}/links", summary="Cross-referenced records")
def incident_links(incident_id: str, services: BatServices = Depends(get_services)) -> dict:
    services.incidents.get(incident_id)
    return resolve_links(services.db, incident_id)


@router.post("/{incident_id}/diagnose", summary="Re-run diagnosis on stored evidence")
def diagnose(incident_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.incidents.diagnose(incident_id).model_dump()
