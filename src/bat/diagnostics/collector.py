"""Collects incident context from sessions, jobs and projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.models import Incident, RuntimeSession
from ..storage.workspace import RuntimeLayout
from .evidence import EvidenceBundle, collect_job_evidence, collect_session_evidence, merge


class EvidenceCollector:
    def __init__(self, layout: RuntimeLayout, jobs_log_root: Path | None = None) -> None:
        self.layout = layout
        self.jobs_log_root = jobs_log_root

    def for_session(
        self, session: RuntimeSession | None, incident_dir: Path, job_id: str | None = None
    ) -> EvidenceBundle:
        bundles: list[EvidenceBundle] = []
        if session is not None:
            bundles.append(
                collect_session_evidence(self.layout.session_dir(session.session_id), incident_dir)
            )
        if job_id and self.jobs_log_root is not None:
            bundles.append(
                collect_job_evidence(self.jobs_log_root / f"{job_id}.log", incident_dir)
            )
        bundle = merge(*bundles)
        return bundle

    def write_incident_context(
        self, incident: Incident, incident_dir: Path, extra: dict[str, Any] | None = None
    ) -> None:
        payload = {
            "incident_id": incident.incident_id,
            "project_id": incident.project_id,
            "job_id": incident.job_id,
            "session_id": incident.session_id,
            "incident_type": incident.incident_type,
            "timestamp": incident.timestamp,
            **(extra or {}),
        }
        (incident_dir / "evidence" / "context.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
