"""Project and project-file endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...core.models import Project
from ...services import BatServices
from ..dependencies import get_services, pagination, require_api_key
from ..schemas import CreateProjectRequest, WriteFileRequest

router = APIRouter(
    prefix="/projects", tags=["projects"], dependencies=[Depends(require_api_key)]
)


@router.post("", status_code=201, summary="Create a project")
def create_project(
    payload: CreateProjectRequest, services: BatServices = Depends(get_services)
) -> dict:
    return services.create_project(
        name=payload.name,
        project_type=payload.project_type,
        target_version=payload.target_version,
        description=payload.description,
        world_name=payload.world_name,
    )


@router.get("", summary="List projects")
def list_projects(
    services: BatServices = Depends(get_services),
    page: tuple[int, int] = Depends(pagination),
) -> dict:
    limit, offset = page
    projects = services.projects.list(limit=limit, offset=offset)
    return {
        "items": [p.model_dump() for p in projects],
        "total": services.db.count_projects(),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{project_id}", summary="Get a project")
def get_project(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    project: Project = services.projects.get(project_id)
    return {
        "project": project.model_dump(),
        "packs": services.projects.list_packs(project_id),
    }


@router.delete("/{project_id}", summary="Delete a project")
def delete_project(
    project_id: str,
    purge_artifacts: bool = False,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.projects.delete(project_id, purge_artifacts=purge_artifacts)


@router.get("/{project_id}/tree", summary="Project file tree")
def project_tree(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.project_tree(project_id)


@router.get("/{project_id}/files/{file_path:path}", summary="Read a project file")
def read_file(
    project_id: str, file_path: str, services: BatServices = Depends(get_services)
) -> dict:
    return services.projects.read_file(project_id, file_path)


@router.put("/{project_id}/files/{file_path:path}", summary="Write a project file")
def write_file(
    project_id: str,
    file_path: str,
    payload: WriteFileRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.projects.write_file(
        project_id, file_path, payload.content, create_backup=payload.create_backup
    )


@router.delete("/{project_id}/files/{file_path:path}", summary="Delete a project file")
def delete_file(
    project_id: str, file_path: str, services: BatServices = Depends(get_services)
) -> dict:
    return services.projects.delete_file(project_id, file_path)
