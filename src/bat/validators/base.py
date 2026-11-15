"""Shared validation context and finding helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..compatibility.registry import DEFAULT_REGISTRY, CompatibilityRegistry
from ..core.models import Finding, Project, Severity


@dataclass
class ValidationContext:
    project: Project
    files_root: Path
    registry: CompatibilityRegistry | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = DEFAULT_REGISTRY

    @property
    def target_version(self) -> str:
        return self.project.target_version

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.files_root.resolve()).as_posix()
        except ValueError:
            return str(path)

    def iter_json(self) -> list[Path]:
        return sorted(p for p in self.files_root.rglob("*.json") if p.is_file())


ValidatorFn = Callable[[ValidationContext], list[Finding]]


def finding(
    code: str,
    severity: Severity,
    message: str,
    *,
    file_path: str | None = None,
    line_number: int | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        code=code,
        severity=severity,
        message=message,
        file_path=file_path,
        line_number=line_number,
        entity_id=entity_id,
        details=details or {},
    )


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None, int | None]:
    """Parse a JSON file, returning ``(data, error_message, line_number)``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return None, f"File is not valid UTF-8: {exc}", None
    except OSError as exc:
        return None, f"File cannot be read: {exc}", None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc.msg}", exc.lineno
    if not isinstance(data, dict):
        return None, "Top-level JSON value must be an object", 1
    return data, None, None
