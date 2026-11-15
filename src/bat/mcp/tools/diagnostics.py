"""Incident and diagnostic MCP tools."""

from __future__ import annotations

from typing import Any

from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def get_incidents(
        project_id: str | None = None,
        job_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> dict:
        """List recorded incidents (crashes, unexpected exits, unresponsive servers)."""
        incidents = services.incidents.list(
            project_id=project_id, job_id=job_id, session_id=session_id, limit=limit
        )
        return {"items": [i.model_dump() for i in incidents], "total": len(incidents)}

    @mcp.tool()
    @tool
    def get_incident_details(incident_id: str) -> dict:
        """Incident record, diagnosis, evidence files and evidence directory."""
        return services.incidents.details(incident_id)

    @mcp.tool()
    @tool
    def diagnose_incident(incident_id: str) -> dict:
        """Re-run diagnosis over the stored evidence and return a diagnostic report."""
        return services.incidents.diagnose(incident_id).model_dump()
