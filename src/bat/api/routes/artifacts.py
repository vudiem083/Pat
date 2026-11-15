"""Artifact endpoints: metadata, inspection, download, build report."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ...services import BatServices
from ..dependencies import get_services, require_api_key

router = APIRouter(
    prefix="/artifacts", tags=["artifacts"], dependencies=[Depends(require_api_key)]
)


@router.get("", summary="List artifacts")
def list_artifacts(
    project_id: str | None = None, services: BatServices = Depends(get_services)
) -> dict:
    items = services.builders.list_artifacts(project_id)
    return {"items": items, "total": len(items)}


@router.get("/{artifact_id}", summary="Inspect an artifact")
def inspect_artifact(artifact_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.builders.inspect_artifact(artifact_id)


@router.get("/{artifact_id}/report", summary="Build report for an artifact")
def build_report(artifact_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.builders.get_build_report(artifact_id)


@router.get("/{artifact_id}/download", summary="Download the artifact file")
def download_artifact(artifact_id: str, services: BatServices = Depends(get_services)):
    artifact, path = services.builders.artifact_path(artifact_id)
    media = {
        "MCADDON": "application/zip",
        "MCPACK": "application/zip",
        "MCWORLD": "application/zip",
    }.get(str(artifact.artifact_type), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=artifact.file_name)


@router.delete("/{artifact_id}", summary="Delete an artifact")
def delete_artifact(artifact_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.builders.delete_artifact(artifact_id)
