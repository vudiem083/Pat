"""FastAPI dependencies: service container, authentication, pagination."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import Header, HTTPException, Query, Request

from ..services import BatServices


def get_services(request: Request) -> BatServices:
    services = getattr(request.app.state, "services", None)
    if services is None:  # pragma: no cover - app always sets this
        raise HTTPException(status_code=503, detail="BAT services are not initialised.")
    return services


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Enforce the optional API key.

    When ``BAT_API_KEY`` is unset, authentication is disabled (intended for
    localhost development). When it is set, every /api/v1 request must present it
    as ``X-API-Key`` or ``Authorization: Bearer <key>``.
    """
    services: BatServices = request.app.state.services
    expected = services.settings.api_key
    if not expected:
        return
    presented = x_api_key
    if not presented and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "BAT-INPUT-001",
                "message": "A valid API key is required (X-API-Key or Authorization: Bearer).",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def pagination(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> tuple[int, int]:
    return limit, offset


def json_error(code: str, message: str, status: int, details: dict[str, Any] | None = None) -> dict:
    return {
        "error_code": code,
        "message": message,
        "details": details or {},
    }
