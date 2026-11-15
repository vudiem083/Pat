"""Pack manifest validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..compatibility.versions import parse_version
from ..core.models import Finding, Severity
from .base import ValidationContext, finding

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
MODULE_TYPES = {"data", "resources", "script", "javascript", "skin_pack", "world_template"}


def manifest_paths(files_root: Path) -> list[Path]:
    paths: list[Path] = []
    for base in ("behavior_packs", "resource_packs"):
        directory = files_root / base
        if not directory.exists():
            continue
        paths.extend(sorted(directory.glob("*/manifest.json")))
    return paths


def validate_manifests(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    paths = manifest_paths(context.files_root)
    if not paths:
        findings.append(
            finding(
                "BAT-MANIFEST-001",
                Severity.ERROR,
                "No pack manifests found. Add-on packs need behavior_packs/<pack>/manifest.json "
                "and/or resource_packs/<pack>/manifest.json.",
            )
        )
        return findings

    seen_header_uuids: dict[str, str] = {}
    seen_module_uuids: dict[str, str] = {}

    for path in paths:
        rel = context.rel(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                finding(
                    "BAT-MANIFEST-001",
                    Severity.ERROR,
                    f"{rel} is not valid JSON: {exc.msg}",
                    file_path=rel,
                    line_number=exc.lineno,
                )
            )
            continue
        if not isinstance(data, dict):
            findings.append(
                finding(
                    "BAT-MANIFEST-001", Severity.ERROR, f"{rel} must be a JSON object.", file_path=rel
                )
            )
            continue

        format_version = data.get("format_version")
        if format_version not in (1, 2):
            findings.append(
                finding(
                    "BAT-MANIFEST-001",
                    Severity.ERROR,
                    f"{rel}: format_version must be 1 or 2 (got {format_version!r}).",
                    file_path=rel,
                )
            )

        header = data.get("header")
        if not isinstance(header, dict):
            findings.append(
                finding(
                    "BAT-MANIFEST-001",
                    Severity.ERROR,
                    f"{rel}: header object is required.",
                    file_path=rel,
                )
            )
            continue

        for field in ("name", "description", "uuid", "version"):
            if field not in header:
                findings.append(
                    finding(
                        "BAT-MANIFEST-001",
                        Severity.ERROR,
                        f"{rel}: header.{field} is required.",
                        file_path=rel,
                    )
                )
        header_uuid = header.get("uuid")
        if isinstance(header_uuid, str):
            if not UUID_RE.match(header_uuid):
                findings.append(
                    finding(
                        "BAT-MANIFEST-001",
                        Severity.ERROR,
                        f"{rel}: header.uuid {header_uuid!r} is not a valid UUID.",
                        file_path=rel,
                    )
                )
            elif header_uuid.lower() in seen_header_uuids:
                findings.append(
                    finding(
                        "BAT-MANIFEST-002",
                        Severity.ERROR,
                        f"{rel}: header.uuid duplicates {seen_header_uuids[header_uuid.lower()]}.",
                        file_path=rel,
                    )
                )
            else:
                seen_header_uuids[header_uuid.lower()] = rel

        header_version = header.get("version")
        if not _is_semver(header_version):
            findings.append(
                finding(
                    "BAT-MANIFEST-001",
                    Severity.ERROR,
                    f"{rel}: header.version must be a list of three integers.",
                    file_path=rel,
                )
            )

        engine = header.get("min_engine_version")
        if engine is not None:
            if not _is_semver(engine):
                findings.append(
                    finding(
                        "BAT-MANIFEST-001",
                        Severity.ERROR,
                        f"{rel}: header.min_engine_version must be a list of three integers.",
                        file_path=rel,
                    )
                )
            else:
                engine_version = ".".join(str(int(v)) for v in engine)
                try:
                    if parse_version(engine_version) > parse_version(context.target_version):
                        findings.append(
                            finding(
                                "BAT-COMPAT-002",
                                Severity.ERROR,
                                f"{rel}: min_engine_version {engine_version} is newer than the "
                                f"project target {context.target_version}; the pack will not load.",
                                file_path=rel,
                                details={
                                    "min_engine_version": engine_version,
                                    "target": context.target_version,
                                },
                            )
                        )
                except Exception:  # noqa: BLE001 - invalid versions reported above
                    pass

        modules = data.get("modules")
        if not isinstance(modules, list) or not modules:
            findings.append(
                finding(
                    "BAT-MANIFEST-001",
                    Severity.ERROR,
                    f"{rel}: at least one module is required.",
                    file_path=rel,
                )
            )
            continue
        for index, module in enumerate(modules):
            if not isinstance(module, dict):
                findings.append(
                    finding(
                        "BAT-MANIFEST-001",
                        Severity.ERROR,
                        f"{rel}: modules[{index}] must be an object.",
                        file_path=rel,
                    )
                )
                continue
            module_type = module.get("type")
            if module_type not in MODULE_TYPES:
                findings.append(
                    finding(
                        "BAT-PACK-001",
                        Severity.ERROR,
                        f"{rel}: modules[{index}].type {module_type!r} is not a known module type.",
                        file_path=rel,
                    )
                )
            module_uuid = module.get("uuid")
            if not isinstance(module_uuid, str) or not UUID_RE.match(module_uuid):
                findings.append(
                    finding(
                        "BAT-MANIFEST-001",
                        Severity.ERROR,
                        f"{rel}: modules[{index}].uuid must be a valid UUID.",
                        file_path=rel,
                    )
                )
            elif module_uuid.lower() in seen_module_uuids:
                findings.append(
                    finding(
                        "BAT-MANIFEST-002",
                        Severity.ERROR,
                        f"{rel}: modules[{index}].uuid duplicates "
                        f"{seen_module_uuids[module_uuid.lower()]}.",
                        file_path=rel,
                    )
                )
            else:
                seen_module_uuids[module_uuid.lower()] = rel
            if not _is_semver(module.get("version")):
                findings.append(
                    finding(
                        "BAT-MANIFEST-001",
                        Severity.ERROR,
                        f"{rel}: modules[{index}].version must be a list of three integers.",
                        file_path=rel,
                    )
                )
            if module_type == "script":
                entry = module.get("entry")
                if not isinstance(entry, str) or not entry.endswith(".js"):
                    findings.append(
                        finding(
                            "BAT-PACK-001",
                            Severity.ERROR,
                            f"{rel}: script module needs an 'entry' .js path.",
                            file_path=rel,
                        )
                    )
                elif not (path.parent / entry).exists():
                    findings.append(
                        finding(
                            "BAT-PACK-001",
                            Severity.ERROR,
                            f"{rel}: script entry {entry!r} does not exist in the pack.",
                            file_path=rel,
                        )
                    )

        dependencies = data.get("dependencies")
        if dependencies is not None and not isinstance(dependencies, list):
            findings.append(
                finding(
                    "BAT-MANIFEST-001",
                    Severity.ERROR,
                    f"{rel}: dependencies must be a list.",
                    file_path=rel,
                )
            )

    return findings


def _is_semver(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in value)
    )
