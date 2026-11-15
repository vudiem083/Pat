"""Health, version and capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services import BatServices
from ...version import SUPPORTED_VERSION_MAX, SUPPORTED_VERSION_MIN, __version__
from ..dependencies import get_services

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health report")
def health(services: BatServices = Depends(get_services)) -> dict:
    return services.health.report().model_dump()


@router.get("/version", summary="Version and supported range")
def version(services: BatServices = Depends(get_services)) -> dict:
    return {
        "name": "BAT — Bedrock Agent Toolkit",
        "version": __version__,
        "supported_minecraft": {
            "edition": "Bedrock",
            "min": SUPPORTED_VERSION_MIN,
            "max": SUPPORTED_VERSION_MAX,
        },
        "interfaces": ["MCP", "REST"],
        "runtime_adapter": services.adapter.describe(),
    }
