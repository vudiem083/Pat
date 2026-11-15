"""Diagnostic report construction."""

from __future__ import annotations

from ..core.models import DiagnosticReport, DiagnosticStatus, Incident, Severity
from .analyzer import Analysis


def build_diagnostic_report(incident: Incident, analysis: Analysis) -> DiagnosticReport:
    evidence = list(incident.evidence) + analysis.evidence_notes
    causes = analysis.causes
    if not analysis.matched:
        causes = []
        message = (
            "Root cause could not be determined from the available evidence. "
            "The incident is recorded with the evidence BAT collected."
        )
    else:
        message = incident.summary or "Runtime failure detected."
    return DiagnosticReport(
        incident_id=incident.incident_id,
        error_code=(analysis.codes[0] if analysis.codes else incident.error_code),
        severity=Severity(analysis.severity),
        source="bat.diagnostics",
        job_id=incident.job_id,
        project_id=incident.project_id,
        session_id=incident.session_id,
        file_path=analysis.file_path,
        line_number=analysis.line_number,
        message=message,
        evidence=evidence,
        possible_causes=causes,
        suggested_actions=analysis.actions,
        confidence=analysis.confidence,
        root_cause_known=analysis.root_cause_known,
        diagnostic_status=(
            DiagnosticStatus.ANALYZED if analysis.matched else DiagnosticStatus.UNKNOWN_CAUSE
        ),
    )
