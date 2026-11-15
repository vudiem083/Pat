"""Evidence analysis: turns collected logs into possible causes.

The analyzer never invents a root cause. When no signature matches it returns an
explicit "unknown" analysis with low confidence and says what evidence would be
needed to diagnose further.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.models import DiagnosticStatus, Severity
from .classifier import Classification, classify_text
from .evidence import EvidenceBundle

_SCRIPT_LOCATION = re.compile(r"(?P<file>[A-Za-z0-9_\-./\\]+\.js):(?P<line>\d+)")


@dataclass
class Analysis:
    matched: bool
    causes: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    confidence: float = 0.0
    severity: str = Severity.ERROR.value
    root_cause_known: bool = False
    status: DiagnosticStatus = DiagnosticStatus.UNKNOWN_CAUSE
    file_path: str | None = None
    line_number: int | None = None
    evidence_notes: list[str] = field(default_factory=list)
    signature_keys: list[str] = field(default_factory=list)


def analyze(bundle: EvidenceBundle) -> Analysis:
    combined = "\n".join(bundle.texts.values())
    if not combined.strip():
        return Analysis(
            matched=False,
            causes=[],
            actions=[
                "Re-run the operation with BAT logging enabled to capture console output.",
                "Check that the runtime environment and session directories still exist.",
            ],
            codes=[],
            confidence=0.05,
            severity=Severity.ERROR.value,
            root_cause_known=False,
            status=DiagnosticStatus.UNKNOWN_CAUSE,
            evidence_notes=["No log content was available to analyse."] + bundle.notes,
        )

    classification: Classification = classify_text(combined)
    notes = list(bundle.notes)
    file_path, line_number = _script_location(combined)

    if not classification.matched:
        return Analysis(
            matched=False,
            causes=[],
            actions=[
                "Inspect the console log manually: BAT found no known failure signature.",
                "Reproduce the operation with a smaller project to isolate the trigger.",
                "If the process exited, compare the exit code with your server build's behaviour.",
            ],
            codes=[],
            confidence=0.15,
            severity=Severity.ERROR.value,
            root_cause_known=False,
            status=DiagnosticStatus.UNKNOWN_CAUSE,
            evidence_notes=[
                "No known failure signature matched the collected evidence, so the root cause is "
                "UNKNOWN. BAT does not guess.",
                *notes,
            ],
        )

    return Analysis(
        matched=True,
        causes=classification.causes,
        actions=classification.actions,
        codes=classification.codes,
        confidence=classification.confidence,
        severity=classification.severity,
        root_cause_known=False,  # log signatures narrow causes; they rarely prove one
        status=DiagnosticStatus.ANALYZED,
        file_path=file_path,
        line_number=line_number,
        evidence_notes=[
            f"Matched signatures: {', '.join(m.key for m in classification.matches)}.",
            "Causes are ranked hypotheses derived from log signatures, not proven root causes.",
            *notes,
        ],
        signature_keys=[m.key for m in classification.matches],
    )


def _script_location(text: str) -> tuple[str | None, int | None]:
    match = _SCRIPT_LOCATION.search(text)
    if not match:
        return None, None
    try:
        return match.group("file"), int(match.group("line"))
    except (ValueError, IndexError):  # pragma: no cover - defensive
        return match.group("file"), None
