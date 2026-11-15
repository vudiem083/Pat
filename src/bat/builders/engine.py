"""Build orchestration: validate, package, record artifacts, write build reports."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core.errors import make_error
from ..core.models import (
    Artifact,
    ArtifactType,
    Project,
    ProjectType,
    ValidationOutcome,
)
from ..core.projects import ProjectManager
from ..generators.world import WorldGenerator
from ..validators.engine import ValidatorEngine
from .inspect import inspect_archive, sha256_file, verify_artifact
from .mcaddon import build_mcaddon
from .mcpack import build_mcpack
from .mcworld import build_mcworld


class BuildEngine:
    def __init__(
        self,
        projects: ProjectManager,
        validators: ValidatorEngine,
        settings: Settings,
        db: Any | None = None,
        world: WorldGenerator | None = None,
    ) -> None:
        self.projects = projects
        self.validators = validators
        self.settings = settings
        self.db = db
        self.world = world

    # -- helpers -----------------------------------------------------------
    def artifact_dir(self, project_id: str, artifact_id: str) -> Path:
        return self.settings.artifacts_root / project_id / artifact_id

    def _record(
        self,
        project: Project,
        path: Path,
        artifact_type: ArtifactType,
        job_id: str | None,
        report: dict[str, Any],
        metadata: dict[str, Any],
    ) -> Artifact:
        artifact = Artifact(
            project_id=project.project_id,
            job_id=job_id,
            artifact_type=artifact_type,
            file_name=path.name,
            storage_path=str(path),
            checksum=sha256_file(path),
            size_bytes=path.stat().st_size,
            metadata=metadata,
        )
        report_path = path.parent / "build_report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if self.db is not None:
            self.db.save_artifact(artifact)
        return artifact

    def _new_target(self, project_id: str, file_name: str) -> tuple[str, Path]:
        from ..core.models import new_uuid

        artifact_id = new_uuid()
        directory = self.artifact_dir(project_id, artifact_id)
        directory.mkdir(parents=True, exist_ok=True)
        return artifact_id, directory / file_name

    # -- builds ------------------------------------------------------------
    def build_project(
        self,
        project_id: str,
        *,
        artifact_type: str | None = None,
        job_id: str | None = None,
        strict: bool = False,
        refresh_bindings: bool = True,
    ) -> dict[str, Any]:
        project = self.projects.require_active(self.projects.get(project_id))
        validation = self.validators.validate_project(project_id, persist=True)
        if strict and ValidationOutcome(validation.status) is ValidationOutcome.FAIL:
            raise make_error(
                "BAT-BUILD-001",
                "Build refused (strict mode): validation reported errors "
                f"{validation.error_codes}.",
                details={
                    "error_codes": validation.error_codes,
                    "report_id": validation.report_id,
                },
            )

        requested = (artifact_type or "").upper() or None
        built: list[dict[str, Any]] = []
        types = self._resolve_types(project, requested, refresh_bindings=refresh_bindings)
        for current in types:
            if current is ArtifactType.MCADDON:
                built.append(self._build_mcaddon(project, job_id, validation))
            elif current is ArtifactType.MCPACK:
                for kind in ("BEHAVIOR", "RESOURCE"):
                    built.append(self._build_mcpack(project, job_id, validation, kind))
            elif current is ArtifactType.MCWORLD:
                built.append(self._build_mcworld(project, job_id, validation))
        if not built:
            raise make_error(
                "BAT-BUILD-002", "No artifact could be produced for this project type."
            )
        return {
            "project_id": project_id,
            "validation": {
                "report_id": validation.report_id,
                "status": validation.status,
                "error_codes": validation.error_codes,
                "finding_count": len(validation.findings),
            },
            "artifacts": built,
        }

    def _resolve_types(
        self, project: Project, requested: str | None, *, refresh_bindings: bool
    ) -> list[ArtifactType]:
        allowed: list[ArtifactType]
        if ProjectType(project.project_type) is ProjectType.ADDON:
            allowed = [ArtifactType.MCADDON, ArtifactType.MCPACK]
        elif ProjectType(project.project_type) is ProjectType.WORLD:
            allowed = [ArtifactType.MCWORLD]
        else:
            allowed = [ArtifactType.MCADDON, ArtifactType.MCWORLD, ArtifactType.MCPACK]
        if requested:
            try:
                requested_type = ArtifactType(requested)
            except ValueError as exc:
                raise make_error(
                    "BAT-INPUT-001",
                    f"Unknown artifact type {requested!r}. Use MCPACK, MCADDON or MCWORLD.",
                ) from exc
            if requested_type not in allowed:
                raise make_error(
                    "BAT-BUILD-002",
                    f"A {project.project_type} project cannot produce {requested_type.value}.",
                    details={"project_type": project.project_type, "artifact_type": requested},
                )
            return [requested_type]
        if ProjectType(project.project_type) is ProjectType.COMBINED:
            if refresh_bindings and self.world is not None:
                self.world.bind_packs(project.project_id)
            return [ArtifactType.MCADDON, ArtifactType.MCWORLD]
        return [allowed[0]]

    def _build_mcaddon(
        self, project: Project, job_id: str | None, validation: Any
    ) -> dict[str, Any]:
        artifact_id, target = self._new_target(project.project_id, f"{_slug(project.name)}.mcaddon")
        result = build_mcaddon(self.projects.files_root(project.project_id), target)
        inspection = inspect_archive(target, ArtifactType.MCADDON)
        report = {
            "artifact_id": artifact_id,
            "project_id": project.project_id,
            "artifact_type": ArtifactType.MCADDON.value,
            "build": result,
            "validation": {
                "report_id": validation.report_id,
                "status": validation.status,
                "error_codes": validation.error_codes,
            },
            "inspection": inspection,
            "integrity_ok": inspection["integrity_ok"],
        }
        artifact = self._record(
            project,
            target,
            ArtifactType.MCADDON,
            job_id,
            report,
            {"packs": result["packs"], "entry_count": result["entry_count"]},
        )
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "file_name": artifact.file_name,
            "storage_path": artifact.storage_path,
            "size_bytes": artifact.size_bytes,
            "checksum": artifact.checksum,
            "integrity_ok": inspection["integrity_ok"],
            "problems": inspection["problems"],
        }

    def _build_mcpack(
        self, project: Project, job_id: str | None, validation: Any, kind: str
    ) -> dict[str, Any]:
        base = "behavior_packs" if kind == "BEHAVIOR" else "resource_packs"
        directory = self.projects.files_root(project.project_id) / base
        packs = (
            sorted(p for p in directory.iterdir() if p.is_dir() and (p / "manifest.json").exists())
            if directory.exists()
            else []
        )
        if not packs:
            raise make_error(
                "BAT-BUILD-002",
                f"Project has no {kind.lower()} pack with a manifest to package.",
            )
        pack = packs[0]
        from ..core.models import PackKind

        artifact_id, target = self._new_target(
            project.project_id, f"{_slug(project.name)}_{pack.name}_{kind.lower()}.mcpack"
        )
        result = build_mcpack(pack, target, kind=PackKind(kind))
        inspection = inspect_archive(target, ArtifactType.MCPACK)
        report = {
            "artifact_id": artifact_id,
            "project_id": project.project_id,
            "artifact_type": ArtifactType.MCPACK.value,
            "build": {k: v for k, v in result.items() if k != "entries"},
            "validation": {
                "report_id": validation.report_id,
                "status": validation.status,
                "error_codes": validation.error_codes,
            },
            "inspection": {k: v for k, v in inspection.items() if k != "entries"},
            "integrity_ok": inspection["integrity_ok"],
        }
        artifact = self._record(
            project,
            target,
            ArtifactType.MCPACK,
            job_id,
            report,
            {"kind": kind, "pack": pack.name, "entry_count": result["entry_count"]},
        )
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "file_name": artifact.file_name,
            "storage_path": artifact.storage_path,
            "size_bytes": artifact.size_bytes,
            "checksum": artifact.checksum,
            "integrity_ok": inspection["integrity_ok"],
            "problems": inspection["problems"],
        }

    def _build_mcworld(
        self, project: Project, job_id: str | None, validation: Any
    ) -> dict[str, Any]:
        world_dir = self.projects.ensure_world_dir(project.project_id)
        artifact_id, target = self._new_target(project.project_id, f"{_slug(project.name)}.mcworld")
        result = build_mcworld(world_dir, target)
        inspection = inspect_archive(target, ArtifactType.MCWORLD)
        report = {
            "artifact_id": artifact_id,
            "project_id": project.project_id,
            "artifact_type": ArtifactType.MCWORLD.value,
            "build": {k: v for k, v in result.items() if k != "entries"},
            "validation": {
                "report_id": validation.report_id,
                "status": validation.status,
                "error_codes": validation.error_codes,
            },
            "inspection": {k: v for k, v in inspection.items() if k != "entries"},
            "integrity_ok": inspection["integrity_ok"],
            "notes": [
                "Chunk data is only present if the world has been loaded by a Minecraft server "
                "or client before export.",
            ],
        }
        artifact = self._record(
            project,
            target,
            ArtifactType.MCWORLD,
            job_id,
            report,
            {
                "level_name": result["level_name"],
                "has_leveldb": result["has_leveldb"],
                "entry_count": result["entry_count"],
            },
        )
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "file_name": artifact.file_name,
            "storage_path": artifact.storage_path,
            "size_bytes": artifact.size_bytes,
            "checksum": artifact.checksum,
            "integrity_ok": inspection["integrity_ok"],
            "problems": inspection["problems"],
        }

    # -- retrieval ---------------------------------------------------------
    def _get_artifact(self, artifact_id: str) -> Artifact:
        if self.db is None:
            raise make_error("BAT-ARTIFACT-001", "Artifact storage is not configured.")
        artifact = self.db.get_artifact(artifact_id)
        if artifact is None:
            raise make_error(
                "BAT-NOTFOUND-004", f"Artifact {artifact_id} not found.", http_status=404
            )
        return artifact

    def inspect_artifact(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._get_artifact(artifact_id)
        return verify_artifact(artifact)

    def artifact_path(self, artifact_id: str) -> tuple[Artifact, Path]:
        artifact = self._get_artifact(artifact_id)
        path = Path(artifact.storage_path)
        if not path.exists():
            raise make_error(
                "BAT-ARTIFACT-001",
                f"Artifact {artifact.file_name} is missing from storage.",
                http_status=404,
            )
        return artifact, path

    def list_artifacts(self, project_id: str | None = None) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        if project_id:
            self.projects.get(project_id)
        return [a.model_dump() for a in self.db.list_artifacts(project_id)]

    def get_build_report(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._get_artifact(artifact_id)
        report_path = Path(artifact.storage_path).parent / "build_report.json"
        if not report_path.exists():
            raise make_error(
                "BAT-NOTFOUND-004",
                f"Build report for artifact {artifact_id} is not available.",
                http_status=404,
            )
        return json.loads(report_path.read_text(encoding="utf-8"))

    def delete_artifact(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._get_artifact(artifact_id)
        directory = Path(artifact.storage_path).parent
        if directory.exists():
            shutil.rmtree(directory)
        return {"artifact_id": artifact_id, "deleted": True}


def _slug(name: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
    return (cleaned or "project")[:64]
