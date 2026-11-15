"""Validation engine: runs validators and assembles a ValidationReport."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..compatibility.compatibility_checker import CompatibilityChecker
from ..compatibility.feature_matrix import compatibility_info
from ..compatibility.registry import DEFAULT_REGISTRY
from ..compatibility.versions import parse_version
from ..core.errors import make_error
from ..core.filesystem import resolve_within
from ..core.models import (
    Finding,
    Project,
    ProjectType,
    Severity,
    ValidationOutcome,
    ValidationReport,
)
from ..core.projects import ProjectManager
from .base import ValidationContext
from .animation_validator import validate_animations
from .documents import validate_all_documents, validate_document
from .json_validator import validate_json_files
from .manifest_validator import validate_manifests
from .pack_validator import validate_packs
from .texture_validator import validate_textures
from .world_validator import validate_world

PROJECT_VALIDATORS = (
    ("json", validate_json_files),
    ("manifest", validate_manifests),
    ("pack", validate_packs),
    ("documents", validate_all_documents),
    ("texture", validate_textures),
    ("animation", validate_animations),
)


def _context(project: Project, files_root: Path) -> ValidationContext:
    return ValidationContext(project=project, files_root=files_root, registry=DEFAULT_REGISTRY)


def _status(findings: list[Finding]) -> ValidationOutcome:
    severities = {str(f.severity) for f in findings}
    if Severity.ERROR.value in severities or Severity.CRITICAL.value in severities:
        return ValidationOutcome.FAIL
    if Severity.WARNING.value in severities:
        return ValidationOutcome.WARN
    return ValidationOutcome.PASS


def _assemble(
    project: Project,
    findings: list[Finding],
    validators_run: list[str],
    checked_files: int,
    evidence: list[str],
    compatibility: Any = None,
) -> ValidationReport:
    errors = [f for f in findings if str(f.severity) in (Severity.ERROR.value, Severity.CRITICAL.value)]
    warnings = [f.message for f in findings if str(f.severity) == Severity.WARNING.value]
    error_codes = sorted({f.code for f in errors})
    if compatibility is None:
        compatibility = compatibility_info(project.target_version)
    return ValidationReport(
        project_id=project.project_id,
        target_version=parse_version(project.target_version).short,
        status=_status(findings),
        findings=findings,
        error_codes=error_codes,
        warnings=warnings,
        compatibility=compatibility,
        evidence=evidence,
        checked_files=checked_files,
        validators_run=validators_run,
    )


class ValidatorEngine:
    def __init__(self, projects: ProjectManager, db: Any | None = None) -> None:
        self.projects = projects
        self.db = db
        self.checker = CompatibilityChecker()

    # -- project level -----------------------------------------------------
    def validate_project(self, project_id: str, *, persist: bool = True) -> ValidationReport:
        project = self.projects.get(project_id)
        files_root = self.projects.files_root(project_id)
        context = _context(project, files_root)
        findings: list[Finding] = []
        run: list[str] = []

        for name, validator in PROJECT_VALIDATORS:
            findings += validator(context)
            run.append(name)

        if ProjectType(project.project_type) in (ProjectType.WORLD, ProjectType.COMBINED):
            findings += validate_world(context)
            run.append("world")
        else:
            findings.append(
                Finding(
                    code="BAT-WORLD-001",
                    severity=Severity.INFO,
                    message="Project has no world (ADDON project); world validation skipped.",
                )
            )

        json_files = list(files_root.rglob("*.json"))
        compatibility = self.checker.check_project(project, files_root)
        evidence = [
            f"Scanned {len(json_files)} JSON files under the project files root.",
            f"Validators run: {', '.join(run)}.",
            f"Target version {parse_version(project.target_version).short} "
            f"(BAT range 1.19.0–1.21.80).",
            f"Compatibility features evaluated: {len(compatibility.checked_features)}.",
        ]
        if compatibility.notes:
            evidence.extend(compatibility.notes)
        report = _assemble(
            project,
            findings,
            run,
            len(json_files),
            evidence,
            compatibility=compatibility,
        )
        if persist and self.db is not None:
            self.db.save_validation_report(report)
        return report

    # -- targeted validators ----------------------------------------------
    def _single_file_context(self, project_id: str) -> tuple[ValidationContext, Project]:
        project = self.projects.get(project_id)
        return _context(project, self.projects.files_root(project_id)), project

    def validate_file(
        self, project_id: str, relative_path: str, *, kind: str = "manifest"
    ) -> ValidationReport:
        context, project = self._single_file_context(project_id)
        path = resolve_within(
            self.projects.files_root(project_id), relative_path, must_exist=True
        )
        run: list[str] = []
        findings: list[Finding] = []
        if kind == "manifest":
            context = ValidationContext(
                project=project,
                files_root=path.parent.parent,
                registry=DEFAULT_REGISTRY,
            )
            findings = _validate_single_manifest(project, path)
            run.append("manifest")
        elif kind in {"entity", "block", "item", "recipe"}:
            findings = validate_document(context, path, kind)
            run.append(f"document:{kind}")
        elif kind == "texture":
            findings = _validate_single_texture(context, path)
            run.append("texture")
        elif kind == "animation":
            findings = _validate_single_animation(project, path)
            run.append("animation")
        elif kind == "world":
            findings = validate_world(context)
            run.append("world")
        else:
            raise make_error(
                "BAT-INPUT-001",
                f"Unknown validation kind {kind!r}. Use manifest, entity, block, item, recipe, "
                "texture, animation or world.",
            )
        compatibility = self.checker.check_project(project, self.projects.files_root(project_id))
        return _assemble(
            project,
            findings,
            run,
            1,
            [f"Validated single target {relative_path!r} with the {kind} validator."],
            compatibility=compatibility,
        )

    def latest_report(self, project_id: str) -> ValidationReport:
        self.projects.get(project_id)
        if self.db is None:
            raise make_error("BAT-NOTFOUND-005", "Validation report storage is not configured.")
        report = self.db.latest_validation_report(project_id)
        if report is None:
            raise make_error(
                "BAT-NOTFOUND-005",
                f"No validation report has been stored for project {project_id}. Run "
                "validate_project first.",
                http_status=404,
            )
        return report

    def get_report(self, report_id: str) -> ValidationReport:
        if self.db is None:
            raise make_error("BAT-NOTFOUND-005", "Validation report storage is not configured.")
        report = self.db.get_validation_report(report_id)
        if report is None:
            raise make_error(
                "BAT-NOTFOUND-005", f"Validation report {report_id} not found.", http_status=404
            )
        return report


def _validate_single_manifest(project: Project, path: Path) -> list[Finding]:
    from .manifest_validator import validate_manifests

    context = ValidationContext(
        project=project, files_root=path.parent.parent.parent, registry=DEFAULT_REGISTRY
    )
    findings = []
    for candidate in validate_manifests(context):
        if candidate.file_path in (None, context.rel(path)):
            findings.append(candidate)
        elif candidate.file_path is None:
            findings.append(candidate)
    # If filtering removed a global error (e.g. no manifests), keep findings about this file.
    if not findings:
        findings = [
            Finding(
                code="BAT-MANIFEST-001",
                severity=Severity.ERROR,
                message=f"Manifest {context.rel(path)} was not recognised as a pack manifest "
                "(expected behavior_packs/<pack>/manifest.json).",
                file_path=context.rel(path),
            )
        ]
    return findings


def _validate_single_texture(context: ValidationContext, path: Path) -> list[Finding]:
    from .texture_validator import png_dimensions

    rel = context.rel(path)
    dimensions = png_dimensions(path)
    if dimensions is None:
        return [
            Finding(
                code="BAT-TEXTURE-001",
                severity=Severity.ERROR,
                message=f"{rel} is not a valid PNG.",
                file_path=rel,
            )
        ]
    return [
        Finding(
            code="BAT-TEXTURE-001",
            severity=Severity.INFO,
            message=f"{rel} is a valid PNG ({dimensions[0]}x{dimensions[1]}).",
            file_path=rel,
        )
    ]


def _validate_single_animation(project: Project, path: Path) -> list[Finding]:
    from .animation_validator import validate_animations

    context = ValidationContext(
        project=project, files_root=path.parent.parent.parent, registry=DEFAULT_REGISTRY
    )
    rel = context.rel(path)
    findings = [f for f in validate_animations(context) if f.file_path == rel]
    return findings
