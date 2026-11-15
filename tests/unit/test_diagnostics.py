from __future__ import annotations

from pathlib import Path

from bat.core.models import (
    DiagnosticStatus,
    IncidentType,
    ProcessStatus,
    RuntimeSession,
    Severity,
)
from bat.diagnostics.analyzer import analyze
from bat.diagnostics.classifier import classify_text
from bat.diagnostics.correlation import resolve_links
from bat.diagnostics.evidence import EvidenceBundle
from bat.diagnostics.incidents import IncidentService
from bat.services import BatServices


def test_classifier_matches_script_and_memory_signatures():
    script = classify_text("[Scripting][error] main.js:4 ReferenceError: boom")
    assert script.matched
    assert "BAT-SCRIPT-001" in script.codes
    assert script.confidence > 0.5

    memory = classify_text("std::bad_alloc while loading chunk")
    assert memory.matched
    assert any("memory" in cause.lower() for cause in memory.causes)


def test_classifier_no_match_is_explicit():
    classification = classify_text("INFO: everything is fine")
    assert not classification.matched
    assert classification.causes == []
    assert classification.confidence < 0.5


def test_analyzer_never_invents_a_root_cause():
    bundle = EvidenceBundle()
    bundle.add_text("console.log", "INFO: Server started.\nINFO: player joined")
    analysis = analyze(bundle)
    assert analysis.matched is False
    assert analysis.root_cause_known is False
    assert analysis.status is DiagnosticStatus.UNKNOWN_CAUSE
    assert any("UNKNOWN" in note for note in analysis.evidence_notes)
    assert analysis.actions


def test_analyzer_extracts_script_location():
    bundle = EvidenceBundle()
    bundle.add_text(
        "errors.log", "[Scripting][error] scripts/main.js:42 TypeError: undefined is not a function"
    )
    analysis = analyze(bundle)
    assert analysis.matched is True
    assert analysis.file_path == "scripts/main.js"
    assert analysis.line_number == 42
    assert analysis.root_cause_known is False  # a signature is a hypothesis, not proof


def test_analyzer_handles_empty_evidence():
    analysis = analyze(EvidenceBundle())
    assert analysis.matched is False
    assert analysis.confidence <= 0.2
    assert analysis.causes == []


def _incident_service(services: BatServices) -> IncidentService:
    return IncidentService(services.layout, services.db, jobs_log_root=services.settings.jobs_log_root)


def _evidence(text: str) -> EvidenceBundle:
    bundle = EvidenceBundle()
    bundle.add_text("console.log", text)
    return bundle


def test_incident_creation_persists_evidence_and_diagnosis(services: BatServices):
    service = _incident_service(services)
    incident = service.create(
        incident_type=IncidentType.PROCESS_CRASH,
        summary="Runtime process exited unexpectedly with code 3.",
        severity=Severity.CRITICAL,
        details={"exit_code": 3},
        extra_evidence=_evidence(
            "ERROR: [Scripting][error] scripts/main.js:7 ReferenceError: foo is not defined"
        ),
    )
    assert incident.incident_type == IncidentType.PROCESS_CRASH
    assert incident.diagnostic_status == DiagnosticStatus.ANALYZED
    assert incident.confidence > 0.5
    assert incident.suggested_actions
    directory = services.layout.incident_dir(incident.incident_id)
    assert (directory / "incident.json").exists()
    assert (directory / "diagnosis.json").exists()
    assert (directory / "evidence" / "manifest.json").exists()
    assert (directory / "evidence" / "console.log").exists()


def test_incident_without_evidence_reports_unknown_cause(services: BatServices):
    service = _incident_service(services)
    incident = service.create(
        incident_type=IncidentType.UNEXPECTED_EXIT,
        summary="Process exited with code 0 without a stop request.",
    )
    assert incident.diagnostic_status == DiagnosticStatus.UNKNOWN_CAUSE
    assert incident.possible_causes == []
    assert incident.confidence <= 0.2
    assert incident.suggested_actions


def test_incidents_are_listed_and_filtered(services: BatServices, addon_project: str):
    service = _incident_service(services)
    first = service.create(
        incident_type=IncidentType.PROCESS_CRASH,
        summary="crash one",
        project_id=addon_project,
    )
    service.create(incident_type=IncidentType.JOB_FAILURE, summary="other project")
    filtered = service.list(project_id=addon_project)
    assert [i.incident_id for i in filtered] == [first.incident_id]


def test_diagnose_reruns_over_stored_evidence(services: BatServices):
    service = _incident_service(services)
    incident = service.create(
        incident_type=IncidentType.PROCESS_CRASH,
        summary="initial",
        extra_evidence=_evidence("INFO: starting"),
    )
    assert incident.diagnostic_status == DiagnosticStatus.UNKNOWN_CAUSE
    # Replace evidence with a matching signature, then re-diagnose.
    evidence_dir = services.layout.incident_dir(incident.incident_id) / "evidence"
    (evidence_dir / "console.log").write_text(
        "ERROR: out of memory while loading the world", encoding="utf-8"
    )
    report = service.diagnose(incident.incident_id)
    assert report.diagnostic_status == DiagnosticStatus.ANALYZED
    assert report.possible_causes
    assert report.confidence > 0.5


def test_incident_details_include_links(services: BatServices, addon_project: str):
    service = _incident_service(services)
    incident = service.create(
        incident_type=IncidentType.SCRIPT_ERROR,
        summary="script failed",
        project_id=addon_project,
        extra_evidence=_evidence("[Scripting][error] main.js:1 boom"),
    )
    details = service.details(incident.incident_id)
    assert details["incident"]["incident_id"] == incident.incident_id
    assert details["diagnosis"]["incident_id"] == incident.incident_id
    links = resolve_links(services.db, incident.incident_id)
    assert links["project"]["project_id"] == addon_project
    assert links["missing"] == []


def test_session_exit_callback_creates_linked_incident(services: BatServices, addon_project: str):
    session = RuntimeSession(
        environment_id="env_test",
        project_id=addon_project,
        process_status=ProcessStatus.CRASHED,
        exit_code=139,
    )
    services.db.save_session(session)
    incident = services.incidents.record_session_exit(
        session,
        IncidentType.PROCESS_CRASH,
        "Runtime process exited unexpectedly with code 139.",
        {"exit_code": 139},
    )
    assert incident.session_id == session.session_id
    assert incident.project_id == addon_project
    assert incident.severity == Severity.CRITICAL
