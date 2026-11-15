"""Add-on content generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services import CONTENT_GENERATORS, BatServices
from ..dependencies import get_services, require_api_key
from ..schemas import GenerateContentRequest

router = APIRouter(
    prefix="/projects/{project_id}/content",
    tags=["content"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", summary="List available content generators")
def list_generators() -> dict:
    return {"generators": sorted(CONTENT_GENERATORS)}


@router.post("/{generator}", status_code=201, summary="Generate add-on content")
def generate(
    project_id: str,
    generator: str,
    payload: GenerateContentRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.generate_content(project_id, generator, payload.spec)
