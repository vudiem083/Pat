"""Minecraft/BDS log classification.

Patterns are deliberately conservative: a line is only an error when the log
clearly says so. Unrecognised lines are INFO, never errors, so BAT does not
invent failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

READY_PATTERNS = (
    re.compile(r"Server started\.?", re.IGNORECASE),
    re.compile(r"IPv4 supported, port", re.IGNORECASE),
    re.compile(r"Server started on port", re.IGNORECASE),
)

ERROR_PATTERNS = (
    re.compile(r"\[error\]", re.IGNORECASE),
    re.compile(r"\bERROR\b"),
    re.compile(r"\bFATAL\b"),
    re.compile(r"Failed to (load|start|open|parse)", re.IGNORECASE),
    re.compile(r"Uncaught exception", re.IGNORECASE),
    re.compile(r"Segmentation fault", re.IGNORECASE),
)

WARNING_PATTERNS = (
    re.compile(r"\[warning\]", re.IGNORECASE),
    re.compile(r"\bWARN(ING)?\b"),
    re.compile(r"deprecated", re.IGNORECASE),
)

SCRIPT_PATTERNS = (
    re.compile(r"\[Scripting\]", re.IGNORECASE),
    re.compile(r"@minecraft/server", re.IGNORECASE),
    re.compile(r"\.js:\d+", re.IGNORECASE),
)

PACK_PATTERNS = (
    re.compile(r"pack", re.IGNORECASE),
    re.compile(r"manifest", re.IGNORECASE),
)

OOM_PATTERNS = (
    re.compile(r"out of memory", re.IGNORECASE),
    re.compile(r"MemoryError", re.IGNORECASE),
    re.compile(r"bad_alloc", re.IGNORECASE),
)


def is_ready_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in READY_PATTERNS)


def classify(line: str) -> str:
    if any(pattern.search(line) for pattern in ERROR_PATTERNS):
        return "ERROR"
    if any(pattern.search(line) for pattern in WARNING_PATTERNS):
        return "WARNING"
    return "INFO"


def is_script_error(line: str) -> bool:
    return classify(line) == "ERROR" and any(p.search(line) for p in SCRIPT_PATTERNS)


def is_pack_error(line: str) -> bool:
    return classify(line) == "ERROR" and any(p.search(line) for p in PACK_PATTERNS)


def is_oom(line: str) -> bool:
    return any(pattern.search(line) for pattern in OOM_PATTERNS)


@dataclass
class LogScan:
    total_lines: int = 0
    error_lines: list[str] = field(default_factory=list)
    warning_lines: list[str] = field(default_factory=list)
    script_errors: list[str] = field(default_factory=list)
    pack_errors: list[str] = field(default_factory=list)
    oom_lines: list[str] = field(default_factory=list)
    ready_lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "total_lines": self.total_lines,
            "error_count": len(self.error_lines),
            "warning_count": len(self.warning_lines),
            "script_error_count": len(self.script_errors),
            "pack_error_count": len(self.pack_errors),
            "oom_detected": bool(self.oom_lines),
            "server_ready": bool(self.ready_lines),
            "errors": self.error_lines[:50],
            "warnings": self.warning_lines[:50],
            "script_errors": self.script_errors[:20],
            "pack_errors": self.pack_errors[:20],
            "ready_lines": self.ready_lines[:5],
        }


def scan_lines(lines: Iterable[str]) -> LogScan:
    scan = LogScan()
    for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            continue
        scan.total_lines += 1
        level = classify(line)
        if level == "ERROR":
            scan.error_lines.append(line)
        elif level == "WARNING":
            scan.warning_lines.append(line)
        if is_script_error(line):
            scan.script_errors.append(line)
        if is_pack_error(line):
            scan.pack_errors.append(line)
        if is_oom(line):
            scan.oom_lines.append(line)
        if is_ready_line(line):
            scan.ready_lines.append(line)
    return scan
