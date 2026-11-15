"""Pack structure validation (module/kind consistency, empty packs, dependencies)."""

from __future__ import annotations

import json
from pathlib import Path

from ..core.models import Finding, ProjectType, Severity
from .base import ValidationContext, finding
from .manifest_validator import manifest_paths


def validate_packs(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    if ProjectType(context.project.project_type) is ProjectType.WORLD:
        return findings

    for path in manifest_paths(context.files_root):
        rel = context.rel(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # reported by the manifest validator
        kinds = {
            m.get("type") for m in data.get("modules", []) if isinstance(m, dict)
        }
        is_behavior = "behavior_packs" in path.parts
        if is_behavior and not kinds & {"data", "script"}:
            findings.append(
                finding(
                    "BAT-PACK-001",
                    Severity.ERROR,
                    f"{rel}: a behavior pack needs a 'data' (or 'script') module.",
                    file_path=rel,
                )
            )
        if not is_behavior and "resources" not in kinds:
            findings.append(
                finding(
                    "BAT-PACK-001",
                    Severity.ERROR,
                    f"{rel}: a resource pack needs a 'resources' module.",
                    file_path=rel,
                )
            )
        content = [
            p
            for p in path.parent.rglob("*")
            if p.is_file() and p.name not in {"manifest.json", "pack_icon.png"} and ".lang" not in p.name
        ]
        if not content:
            findings.append(
                finding(
                    "BAT-PACK-001",
                    Severity.WARNING,
                    f"{rel}: pack {path.parent.name!r} declares modules but contains no content.",
                    file_path=rel,
                )
            )

    # Dependency sanity: a behavior pack may depend on a resource pack uuid.
    repo_uuids = set()
    for path in manifest_paths(context.files_root):
        try:
            header = json.loads(path.read_text(encoding="utf-8")).get("header", {})
        except json.JSONDecodeError:
            continue
        if isinstance(header, dict) and isinstance(header.get("uuid"), str):
            repo_uuids.add(header["uuid"].lower())

    for path in manifest_paths(context.files_root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for dependency in data.get("dependencies", []) or []:
            if not isinstance(dependency, dict):
                continue
            if "uuid" in dependency and dependency["uuid"].lower() not in repo_uuids:
                findings.append(
                    finding(
                        "BAT-PACK-001",
                        Severity.WARNING,
                        f"{context.rel(path)}: dependency {dependency['uuid']} is not one of this "
                        "project's packs. Minecraft will fail to resolve it unless the pack is "
                        "installed separately.",
                        file_path=context.rel(path),
                    )
                )
    return findings
