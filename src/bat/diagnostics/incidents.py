"""Incident lifecycle: record, persist evidence, diagnose, retrieve."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.models import (
    DiagnosticReport,
    DiagnosticStatus,
    Incident,
    IncidentType,
    RuntimeSession,
    Severity,
    utcnow,
)
from ..observability.structured_logger import get_logger
from ..storage.workspace import RuntimeLayout
from .analyzer import analyze
from .collector import EvidenceCollector
from .evidence import EvidenceBundle, write_manifest
from .report import build_diagnostic_report


_SEVERITY_RANK = {
    Severity.INFO.value: 0,
    Severity.WARNING.value: 1,
    Severity.ERROR.value: 2,
    Severity.CRITICAL.value: 3,
}


def _max_severity(left: Severity | str, right: Severity | str) -> Severity:
    left_value = str(left)
    right_value = str(right)
    return Severity(
        left_value
        if _SEVERITY_RANK.get(left_value, 2) >= _SEVERITY_RANK.get(right_value, 2)
        else right_value
    )


class IncidentService:
    def __init__(
        self,
        layout: RuntimeLayout,
        db: Any,
        *,
        jobs_log_root: Path | None = None,
    ) -> None:
        self.layout = layout
        self.db = db
        self.collector = EvidenceCollector(layout, jobs_log_root)
        self.logger = get_logger("diagnostics.incidents")

    # -- creation ----------------------------------------------------------
    def create(
        self,
        *,
        incident_type: IncidentType,
        summary: str,
        project_id: str | None = None,
        job_id: str | None = None,
        session_id: str | None = None,
        severity: Severity = Severity.ERROR,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        extra_evidence: EvidenceBundle | None = None,
    ) -> Incident:
        incident = Incident(
            project_id=project_id,
            job_id=job_id,
            session_id=session_id,
            incident_type=incident_type,
            severity=severity,
            summary=summary,
            error_code=error_code,
            details=details or {},
        )
        directory = self.layout.create_incident(incident.incident_id)
        session = self.db.get_session(session_id) if session_id else None
        bundle = self.collector.for_session(session, directory, job_id=job_id)
        if extra_evidence is not None:
            from .evidence import merge

            bundle = merge(bundle, extra_evidence)
        for name, text in bundle.texts.items():
            (directory / "evidence" / name).write_text(text, encoding="utf-8")

        analysis = analyze(bundle)
        report = build_diagnostic_report(incident, analysis)
        # Escalate only on a matched signature: an unmatched analysis must not
        # silently upgrade a WARNING (e.g. "unresponsive") to an error.
        merged = (
            _max_severity(severity, report.severity) if analysis.matched else Severity(severity)
        )
        report.severity = merged
        incident.severity = merged
        incident.evidence = report.evidence
        incident.evidence_files = bundle.files
        incident.possible_causes = report.possible_causes
        incident.suggested_actions = report.suggested_actions
        incident.confidence = report.confidence
        incident.diagnostic_status = report.diagnostic_status
        incident.error_code = incident.error_code or report.error_code

        write_manifest(
            directory,
            {
                "incident_id": incident.incident_id,
                "created_at": incident.timestamp,
                "files": bundle.files,
                "notes": bundle.notes,
                "signatures": analysis.signature_keys,
            },
        )
        self.collector.write_incident_context(
            incident, directory, extra={"details": incident.details}
        )
        (directory / "incident.json").write_text(
            incident.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (directory / "diagnosis.json").write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        self.db.save_incident(incident)
        self.logger.error(
            "Incident recorded: %s",
            summary,
            incident_id=incident.incident_id,
            incident_type=str(incident_type),
            project_id=project_id,
            job_id=job_id,
            session_id=session_id,
            error_code=incident.error_code,
        )
        return incident

    def record_session_exit(
        self,
        session: RuntimeSession,
        incident_type: IncidentType,
        summary: str,
        details: dict[str, Any],
        severity: Severity = Severity.CRITICAL,
    ) -> Incident:
        """Callback used by the server manager when a process dies unexpectedly."""
        return self.create(
            incident_type=incident_type,
            summary=summary,
            project_id=session.project_id,
            job_id=session.job_id,
            session_id=session.session_id,
            severity=severity,
            details=details,
        )

    # -- retrieval ---------------------------------------------------------
    def get(self, incident_id: str) -> Incident:
        incident = self.db.get_incident(incident_id)
        if incident is None:
            raise make_error(
                "BAT-NOTFOUND-006",
                f"Incident {incident_id} not found.",
                http_status=404,
            )
        return incident

    def list(
        self,
        *,
        project_id: str | None = None,
        job_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        return self.db.list_incidents(
            project_id=project_id,
            job_id=job_id,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )

    def details(self, incident_id: str) -> dict[str, Any]:
        incident = self.get(incident_id)
        directory = self.layout.incident_dir(incident_id)
        diagnosis_path = directory / "diagnosis.json"
        report = (
            json.loads(diagnosis_path.read_text(encoding="utf-8"))
            if diagnosis_path.exists()
            else None
        )
        return {
            "incident": incident.model_dump(),
            "diagnosis": report,
            "evidence_directory": str(directory / "evidence"),
            "evidence_files": incident.evidence_files,
        }

    def diagnose(self, incident_id: str) -> DiagnosticReport:
        incident = self.get(incident_id)
        directory = self.layout.incident_dir(incident_id)
        bundle = EvidenceBundle()
        evidence_dir = directory / "evidence"
        if evidence_dir.exists():
            for path in sorted(evidence_dir.glob("*")):
                if path.is_file() and path.name != "manifest.json":
                    try:
                        bundle.texts[path.name] = path.read_text(encoding="utf-8", errors="replace")
                        bundle.files.append(f"evidence/{path.name}")
                    except OSError:
                        continue
        if not bundle.texts:
            bundle.notes.append("No evidence files were found for this incident.")
        analysis = analyze(bundle)
        report = build_diagnostic_report(incident, analysis)
        incident.possible_causes = report.possible_causes
        incident.suggested_actions = report.suggested_actions
        incident.confidence = report.confidence
        incident.diagnostic_status = (
            DiagnosticStatus.ANALYZED if analysis.matched else DiagnosticStatus.UNKNOWN_CAUSE
        )
        (directory / "diagnosis.json").write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (directory / "incident.json").write_text(
            incident.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        self.db.save_incident(incident)
        return report
