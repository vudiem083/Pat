"""JSON syntax validation for every .json file in a project."""

from __future__ import annotations

from ..core.models import Finding, Severity
from .base import ValidationContext, finding


def validate_json_files(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    files = context.iter_json()
    if not files:
        findings.append(
            finding(
                "BAT-JSON-001",
                Severity.WARNING,
                "The project contains no JSON files to validate.",
            )
        )
    for path in files:
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append(
                finding(
                    "BAT-JSON-001",
                    Severity.ERROR,
                    f"{context.rel(path)} is not valid UTF-8: {exc}",
                    file_path=context.rel(path),
                )
            )
            continue
        import json

        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            findings.append(
                finding(
                    "BAT-JSON-001",
                    Severity.ERROR,
                    f"{context.rel(path)} is not valid JSON: {exc.msg}",
                    file_path=context.rel(path),
                    line_number=exc.lineno,
                    details={"column": exc.colno, "position": exc.pos},
                )
            )
    return findings
