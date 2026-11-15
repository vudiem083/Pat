"""Shared generator plumbing: pack resolution, naming, atomic JSON writes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..compatibility.registry import DEFAULT_REGISTRY, CompatibilityRegistry
from ..compatibility.versions import format_version, parse_version
from ..core.errors import make_error
from ..core.models import (
    CompatibilityStatus,
    GeneratedFile,
    PackKind,
    Project,
    ProjectType,
)
from ..core.projects import ProjectManager

_NAMESPACE_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_NAME_RE = re.compile(r"^[a-z0-9_\.\-]{1,64}$")


@dataclass
class GenerationContext:
    project: Project
    projects: ProjectManager
    registry: CompatibilityRegistry | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = DEFAULT_REGISTRY

    # -- validation --------------------------------------------------------
    @property
    def fmt(self) -> str:
        return format_version(self.project.target_version)

    @property
    def supports_packs(self) -> bool:
        return ProjectType(self.project.project_type) in (ProjectType.ADDON, ProjectType.COMBINED)

    def require_packs(self) -> None:
        if not self.supports_packs:
            raise make_error(
                "BAT-PROJECT-003",
                "Add-on content can only be generated for ADDON or COMBINED projects.",
                details={"project_type": self.project.project_type},
                http_status=409,
            )

    def feature(self, key: str) -> CompatibilityStatus:
        assert self.registry is not None
        support = self.registry.require(key, self.project.target_version)
        return CompatibilityStatus(support.status)

    def check_feature(self, key: str) -> dict[str, str]:
        assert self.registry is not None
        support = self.registry.check(key, self.project.target_version)
        return support.model_dump()

    @staticmethod
    def namespace(namespace: str | None) -> str:
        value = (namespace or "bat").strip().lower()
        if not _NAMESPACE_RE.match(value):
            raise make_error(
                "BAT-INPUT-001",
                f"Invalid namespace {namespace!r}. Use lowercase letters, digits and underscores.",
            )
        return value

    @staticmethod
    def identifier(namespace: str | None, name: str) -> str:
        cleaned = (name or "").strip().lower().replace(" ", "_")
        if not _NAME_RE.match(cleaned):
            raise make_error(
                "BAT-INPUT-001",
                f"Invalid identifier name {name!r}. Use lowercase letters, digits, '_', '-' or '.'.",
            )
        return f"{GenerationContext.namespace(namespace)}:{cleaned}"

    @staticmethod
    def slugify_suffix(identifier: str) -> str:
        return identifier.split(":", 1)[-1].replace(".", "_").replace("-", "_")

    # -- packs -------------------------------------------------------------
    def primary_pack(self, kind: PackKind) -> Path:
        self.require_packs()
        base = self.projects.files_root(self.project.project_id) / (
            "behavior_packs" if kind is PackKind.BEHAVIOR else "resource_packs"
        )
        base.mkdir(parents=True, exist_ok=True)
        existing = sorted(p for p in base.iterdir() if p.is_dir() and (p / "manifest.json").exists())
        if existing:
            return existing[0]
        slug = re.sub(r"[^a-z0-9_]+", "_", self.project.name.lower()).strip("_") or "pack"
        pack = base / slug[:48]
        pack.mkdir(parents=True, exist_ok=True)
        manifest = self.projects.build_manifest(self.project, kind, pack.name)
        (pack / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.projects.touch(self.project)
        return pack

    def write_json(
        self,
        kind: PackKind,
        relative_path: str,
        payload: dict[str, Any],
        *,
        description: str,
        feature: str,
    ) -> GeneratedFile:
        pack = self.primary_pack(kind)
        target = pack / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        support = self.check_feature(feature)
        return GeneratedFile(
            path=(target.relative_to(self.projects.files_root(self.project.project_id))).as_posix(),
            kind=feature,
            pack=pack.name,
            description=description,
            compatibility_status=CompatibilityStatus(support["status"]),
            warnings=[] if support["status"] != "UNSUPPORTED" else [support["notes"]],
        )

    def write_text(
        self,
        kind: PackKind,
        relative_path: str,
        content: str,
        *,
        description: str,
        feature: str,
    ) -> GeneratedFile:
        pack = self.primary_pack(kind)
        target = pack / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        support = self.check_feature(feature)
        return GeneratedFile(
            path=target.relative_to(self.projects.files_root(self.project.project_id)).as_posix(),
            kind=feature,
            pack=pack.name,
            description=description,
            compatibility_status=CompatibilityStatus(support["status"]),
        )

    def touch(self) -> None:
        self.projects.touch(self.project)


def try_compat(context: GenerationContext, feature: str) -> CompiledCheck:
    return CompiledCheck(context, feature)


@dataclass
class CompiledCheck:
    """Result of a pre-flight compatibility check for an optional generator."""

    context: GenerationContext
    feature: str

    @property
    def status(self) -> CompatibilityStatus:
        assert self.context.registry is not None
        return CompatibilityStatus(
            self.context.registry.check(self.feature, self.context.project.target_version).status
        )

    @property
    def reason(self) -> str:
        assert self.context.registry is not None
        return self.context.registry.check(self.feature, self.context.project.target_version).notes


def version_parts(version: str) -> list[int]:
    return list(parse_version(version).parts[:3])
