"""Runtime endpoints: environments, sessions, world operations, structures."""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, Query

from ...core.errors import make_error
from ...core.models import RuntimeType
from ...services import BatServices
from ..dependencies import get_services, require_api_key
from ..schemas import (
    ConsoleCommandRequest,
    CreateStructureRequest,
    EnvironmentRequest,
    ImportStructureRequest,
    InstallPacksRequest,
    InstallWorldRequest,
    StopServerRequest,
    WorldMetadataRequest,
)

router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(require_api_key)])


@router.get("/health", summary="Runtime health")
def runtime_health(services: BatServices = Depends(get_services)) -> dict:
    return services.runtime_health()


@router.get("/adapter", summary="Active runtime adapter")
def adapter(services: BatServices = Depends(get_services)) -> dict:
    return services.adapter.describe()


# -- environments ----------------------------------------------------------
@router.post("/environments", status_code=201, summary="Create a runtime environment")
def create_environment(
    payload: EnvironmentRequest, services: BatServices = Depends(get_services)
) -> dict:
    environment = services.environments.create(
        project_id=payload.project_id,
        runtime_type=RuntimeType(payload.runtime_type),
    )
    return environment.model_dump()


@router.get("/environments", summary="List runtime environments")
def list_environments(
    project_id: str | None = None, services: BatServices = Depends(get_services)
) -> dict:
    items = services.environments.list(project_id)
    return {"items": [e.model_dump() for e in items], "total": len(items)}


@router.get("/environments/{environment_id}", summary="Get an environment")
def get_environment(environment_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.environments.get(environment_id).model_dump()


@router.post("/environments/{environment_id}/packs", summary="Install project packs")
def install_packs(
    environment_id: str,
    payload: InstallPacksRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.environments.install_packs(environment_id, payload.project_id)


@router.post("/environments/{environment_id}/world", summary="Install a project world")
def install_world(
    environment_id: str,
    payload: InstallWorldRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.environments.install_world(
        environment_id, payload.project_id, world_name=payload.world_name
    )


@router.delete("/environments/{environment_id}", summary="Destroy an environment")
def destroy_environment(environment_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.environments.destroy(environment_id)


# -- sessions --------------------------------------------------------------
@router.get("/sessions", summary="List runtime sessions")
def list_sessions(
    project_id: str | None = None, services: BatServices = Depends(get_services)
) -> dict:
    items = services.servers.list_sessions(project_id)
    return {"items": items, "total": len(items)}


@router.get("/sessions/{session_id}", summary="Runtime session status")
def session_status(session_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.runtime_status(session_id)


@router.get("/sessions/{session_id}/logs", summary="Runtime session logs")
def session_logs(
    session_id: str,
    kind: str = Query(default="console", pattern="^(console|runtime|errors)$"),
    tail: int = Query(default=200, ge=1, le=5000),
    services: BatServices = Depends(get_services),
) -> dict:
    return services.runtime_logs(session_id, kind=kind, tail=tail)


@router.get("/sessions/{session_id}/heartbeat", summary="Runtime session heartbeat")
def session_heartbeat(session_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.runtime_heartbeat(session_id)


@router.get("/sessions/{session_id}/report", summary="Runtime session report")
def session_report(session_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.runtime_report(session_id)


@router.post("/sessions/{session_id}/command", summary="Send a console command")
def session_command(
    session_id: str,
    payload: ConsoleCommandRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.servers.send_command(session_id, payload.command)


@router.post("/sessions/{session_id}/stop", summary="Stop a runtime server")
def session_stop(
    session_id: str,
    payload: StopServerRequest | None = None,
    services: BatServices = Depends(get_services),
) -> dict:
    timeout = payload.timeout if payload else 30.0
    session = services.servers.stop(session_id, timeout=timeout)
    return session.model_dump()


# -- worlds ----------------------------------------------------------------
@router.get("/worlds/{project_id}", summary="Inspect a project world")
def inspect_world(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.inspect_world(project_id)


@router.get("/worlds/{project_id}/chunks", summary="World chunk/LevelDB report")
def world_chunks(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.world.chunks(project_id)


@router.patch("/worlds/{project_id}/metadata", summary="Modify world metadata (backed up)")
def modify_world(
    project_id: str,
    payload: WorldMetadataRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    return services.modify_world_metadata(project_id, **payload.to_kwargs())


@router.post("/worlds/{project_id}/bind-packs", summary="Bind project packs to the world")
def bind_packs(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.bind_world_packs(project_id)


@router.get("/worlds/{project_id}/structures", summary="List world structures")
def list_structures(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    items = services.structures.list_structures(project_id)
    return {"items": items, "total": len(items)}


@router.post("/worlds/{project_id}/structures", status_code=201, summary="Create a structure")
def create_structure(
    project_id: str,
    payload: CreateStructureRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    if len(payload.size) != 3 or len(payload.origin) != 3:
        raise make_error("BAT-INPUT-001", "size and origin must each contain three integers.")
    return services.create_structure(
        project_id,
        name=payload.name,
        size=payload.size,
        block=payload.block,
        origin=payload.origin,
    )


@router.post("/worlds/{project_id}/structures/import", summary="Import a .mcstructure")
def import_structure(
    project_id: str,
    payload: ImportStructureRequest,
    services: BatServices = Depends(get_services),
) -> dict:
    try:
        data = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise make_error("BAT-INPUT-001", f"content_base64 is not valid base64: {exc}") from exc
    if len(data) > services.settings.max_upload_bytes:
        raise make_error("BAT-PATH-002", "Structure upload exceeds the configured size limit.")
    return services.import_structure(project_id, payload.name, data)


@router.get("/worlds/{project_id}/structures/{name}/export", summary="Export a structure")
def export_structure(
    project_id: str, name: str, services: BatServices = Depends(get_services)
) -> dict:
    return services.export_structure(project_id, name)
