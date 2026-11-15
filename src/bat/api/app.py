"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..core.errors import BatError
from ..services import BatServices, build_services
from ..version import SUPPORTED_VERSION_MAX, SUPPORTED_VERSION_MIN, __version__
from .routes import ROUTERS
from .routes import content as content_routes

DESCRIPTION = f"""
BAT (Bedrock Agent Toolkit) REST API — Minecraft Bedrock {SUPPORTED_VERSION_MIN}–{SUPPORTED_VERSION_MAX}.

The same service layer backs this API and the MCP server, so both interfaces
return the same data models and error codes.

**Asynchronous jobs**: long-running operations (runtime tests, builds, diagnosis)
run as background jobs. Create a job, then poll `/api/v1/jobs/{{job_id}}` or call
`POST /api/v1/jobs/{{job_id}}/wait` with a bounded timeout. A wait that times out
does **not** cancel the job.

**Authentication**: when `BAT_API_KEY` is set, send it as `X-API-Key` or
`Authorization: Bearer <key>`. When unset, authentication is disabled and the API
should only be exposed on localhost.

**Paths**: project file paths are always relative to the project files root.
Absolute paths, `..` traversal and symlinks are rejected.
"""


def create_app(services: BatServices | None = None) -> FastAPI:
    service_layer = services

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = service_layer or build_services()
        app.state.startup = app.state.services.startup()
        try:
            yield
        finally:
            app.state.services.shutdown()

    app = FastAPI(
        title="BAT — Bedrock Agent Toolkit",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    if services is not None:
        # Test/client usage: no lifespan required, services are provided.
        app.state.services = services
        app.state.startup = {"version": __version__, "provided": True}

    @app.exception_handler(BatError)
    async def bat_error_handler(_request: Request, exc: BatError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "error_code": "BAT-INPUT-001",
                    "message": "Request validation failed.",
                    "severity": "ERROR",
                    "details": {"errors": _clean_errors(exc.errors())},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "error_code": "BAT-JOB-004",
                    "message": f"Unhandled error: {type(exc).__name__}: {exc}",
                    "severity": "ERROR",
                    "details": {},
                }
            },
        )

    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")
    app.include_router(content_routes.router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {
            "name": "BAT — Bedrock Agent Toolkit",
            "version": __version__,
            "api": "/api/v1",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


def _clean_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for error in errors:
        cleaned.append(
            {
                "location": [str(part) for part in error.get("loc", [])],
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return cleaned

