"""Correlation between projects, jobs, sessions and incidents."""

from __future__ import annotations

from typing import Any


def correlation_ids(
    *,
    project_id: str | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    incident_id: str | None = None,
    environment_id: str | None = None,
) -> dict[str, str]:
    """Build the correlation fields attached to every structured log record."""
    identifiers = {
        "project_id": project_id,
        "job_id": job_id,
        "session_id": session_id,
        "incident_id": incident_id,
        "environment_id": environment_id,
    }
    return {key: value for key, value in identifiers.items() if value}


def resolve_links(db: Any, incident_id: str) -> dict[str, Any]:
    """Return the linked records for an incident, missing links named explicitly."""
    incident = db.get_incident(incident_id)
    if incident is None:
        return {"incident_id": incident_id, "found": False}
    links: dict[str, Any] = {
        "incident": incident.model_dump(),
        "project": None,
        "job": None,
        "session": None,
        "missing": [],
    }
    if incident.project_id:
        project = db.get_project(incident.project_id)
        links["project"] = project.model_dump() if project else None
        if project is None:
            links["missing"].append(f"project {incident.project_id}")
    if incident.job_id:
        job = db.get_job(incident.job_id)
        links["job"] = job.model_dump() if job else None
        if job is None:
            links["missing"].append(f"job {incident.job_id}")
    if incident.session_id:
        session = db.get_session(incident.session_id)
        links["session"] = session.model_dump() if session else None
        if session is None:
            links["missing"].append(f"session {incident.session_id}")
    return links
