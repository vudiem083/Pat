"""Evidence collection for incidents.

Evidence is copied into ``runtime/incidents/<id>/evidence/`` so it survives the
deletion of an environment or session directory. Large logs are truncated to
their tail (the part that explains a crash) and the truncation is recorded.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

MAX_EVIDENCE_BYTES = 512 * 1024

SESSION_ARTIFACTS = ("console.log", "errors.log", "runtime.log", "report.json", "heartbeat.json")


@dataclass
class EvidenceBundle:
    files: list[str] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add_text(self, name: str, text: str) -> None:
        self.files.append(name)
        self.texts[name] = text

    def summary(self) -> str:
        if not self.files:
            return "No evidence files were available."
        return f"Collected {len(self.files)} evidence file(s): {', '.join(self.files)}."


def read_tail(path: Path, max_bytes: int = MAX_EVIDENCE_BYTES) -> tuple[str, bool]:
    """Read the tail of a text file and report whether it was truncated."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            data = handle.read()
            return data.decode("utf-8", errors="replace"), True
        return handle.read().decode("utf-8", errors="replace"), False


def collect_session_evidence(session_dir: Path, incident_dir: Path) -> EvidenceBundle:
    bundle = EvidenceBundle()
    evidence_dir = incident_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not session_dir.exists():
        bundle.notes.append(f"Session directory {session_dir} does not exist; no logs to collect.")
        return bundle
    for name in SESSION_ARTIFACTS:
        source = session_dir / name
        if not source.exists():
            continue
        text, truncated = read_tail(source)
        destination = evidence_dir / f"session_{name}"
        destination.write_text(text, encoding="utf-8")
        bundle.files.append(f"evidence/{destination.name}")
        bundle.texts[destination.name] = text
        if truncated:
            bundle.notes.append(
                f"{name} was truncated to its last {MAX_EVIDENCE_BYTES} bytes for evidence."
            )
    if not bundle.files:
        bundle.notes.append("Session directory contained none of the expected log files.")
    return bundle


def collect_job_evidence(job_log: Path, incident_dir: Path) -> EvidenceBundle:
    bundle = EvidenceBundle()
    if not job_log.exists():
        bundle.notes.append(f"Job log {job_log} is unavailable.")
        return bundle
    evidence_dir = incident_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    text, truncated = read_tail(job_log)
    destination = evidence_dir / "job.log"
    destination.write_text(text, encoding="utf-8")
    bundle.files.append(f"evidence/{destination.name}")
    bundle.texts["job.log"] = text
    if truncated:
        bundle.notes.append("Job log was truncated to its tail for evidence.")
    return bundle


def merge(*bundles: EvidenceBundle) -> EvidenceBundle:
    merged = EvidenceBundle()
    for bundle in bundles:
        for name in bundle.files:
            if name not in merged.files:
                merged.files.append(name)
        merged.texts.update(bundle.texts)
        merged.notes.extend(bundle.notes)
    return merged


def copy_file_into_evidence(source: Path, incident_dir: Path, name: str | None = None) -> str | None:
    if not source.exists():
        return None
    evidence_dir = incident_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    destination = evidence_dir / (name or source.name)
    shutil.copy2(source, destination)
    return f"evidence/{destination.name}"


def write_manifest(incident_dir: Path, payload: dict) -> None:
    (incident_dir / "evidence" / "manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
