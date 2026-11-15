"""Validation and compatibility endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...services import BatServices
from ..dependencies import get_services, require_api_key
from ..schemas import ValidateRequest

router = APIRouter(tags=["validation"], dependencies=[Depends(require_api_key)])


@router.post("/projects/{project_id}/validate", summary="Validate a project")
def validate_project(
    project_id: str,
    payload: ValidateRequest | None = None,
    services: BatServices = Depends(get_services),
) -> dict:
    report = services.validator.validate_project(project_id)
    return report.model_dump()


@router.get("/projects/{project_id}/validation-report", summary="Latest validation report")
def latest_report(project_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.validator.latest_report(project_id).model_dump()


@router.get("/validation-reports/{report_id}", summary="Get a validation report")
def get_report(report_id: str, services: BatServices = Depends(get_services)) -> dict:
    return services.validator.get_report(report_id).model_dump()


@router.get("/compatibility", summary="Feature matrix for a target version")
def compatibility(
    version: str = Query(..., description="Target Bedrock version, e.g. 1.21.80"),
    services: BatServices = Depends(get_services),
) -> dict:
    return services.get_compatibility(version)


@router.get("/compatibility/profiles", summary="Known generation profiles")
def profiles(services: BatServices = Depends(get_services)) -> dict:
    return {"profiles": services.list_profiles()}


@router.get("/error-codes", summary="Documented BAT diagnostic error codes")
def error_codes(services: BatServices = Depends(get_services)) -> dict:
    return {"codes": services.list_error_codes()}
