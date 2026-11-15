"""Structured JSON logging with secret redaction and size-based rotation.

Correlation fields (``job_id``, ``session_id``, ``project_id``, ``incident_id``)
are added by callers through :meth:`bind`, which is how BAT connects events
across MCP, jobs, runtime and diagnostics.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

from ..core.models import utcnow

_REDACTION_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)mojang|microsoft|live\.com"),
)

_ROTATION_LOCK = threading.RLock()
_CONFIG: dict[str, Any] = {
    "log_dir": None,
    "max_bytes": 2 * 1024 * 1024,
    "backup_count": 5,
    "echo_stdout": False,
    "level": "INFO",
}
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def redact(value: Any) -> Any:
    """Remove obvious secrets from a string before it reaches a log file."""
    if not isinstance(value, str):
        return value
    text = value
    for secret_env in ("BAT_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(secret_env)
        if secret and len(secret) > 3:
            text = text.replace(secret, "***redacted***")
    for pattern in _REDACTION_PATTERNS[:2]:
        text = pattern.sub(lambda m: m.group(1) + "=***redacted***" if m.groups() else "***redacted***", text)
    return text


def configure_logging(
    log_dir: Path,
    *,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 5,
    echo_stdout: bool = False,
    level: str = "INFO",
) -> None:
    with _ROTATION_LOCK:
        log_dir.mkdir(parents=True, exist_ok=True)
        _CONFIG.update(
            {
                "log_dir": log_dir,
                "max_bytes": max_bytes,
                "backup_count": backup_count,
                "echo_stdout": echo_stdout,
                "level": level.upper(),
            }
        )


class StructuredLogger:
    def __init__(self, name: str, context: dict[str, Any] | None = None) -> None:
        self.name = name
        self.context = context or {}

    def bind(self, **fields: Any) -> "StructuredLogger":
        merged = {**self.context, **fields}
        return StructuredLogger(self.name, merged)

    # -- emission ----------------------------------------------------------
    def log(self, level: str, message: str, *args: Any, **fields: Any) -> dict[str, Any]:
        level = level.upper()
        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                message = f"{message} {' '.join(str(a) for a in args)}"
        minimum = _LEVELS.get(str(_CONFIG.get("level", "INFO")).upper(), 20)
        if _LEVELS.get(level, 20) < minimum:
            return {}
        record = {
            "timestamp": utcnow(),
            "level": level,
            "source": self.name,
            "message": redact(message),
            **{key: redact(value) for key, value in self.context.items()},
            **{key: redact(value) for key, value in fields.items()},
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _ROTATION_LOCK:
            log_dir = _CONFIG.get("log_dir")
            if log_dir is not None:
                _rotate_if_needed(Path(log_dir) / "bat.jsonl")
                with (Path(log_dir) / "bat.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            if _CONFIG.get("echo_stdout"):
                stream = sys.stderr if _LEVELS.get(level, 20) >= 30 else sys.stdout
                if stream is not None:
                    stream.write(line + "\n")
        return record

    def debug(self, message: str, *args: Any, **fields: Any) -> dict[str, Any]:
        return self.log("DEBUG", message, *args, **fields)

    def info(self, message: str, *args: Any, **fields: Any) -> dict[str, Any]:
        return self.log("INFO", message, *args, **fields)

    def warning(self, message: str, *args: Any, **fields: Any) -> dict[str, Any]:
        return self.log("WARNING", message, *args, **fields)

    def error(self, message: str, *args: Any, **fields: Any) -> dict[str, Any]:
        return self.log("ERROR", message, *args, **fields)

    def critical(self, message: str, *args: Any, **fields: Any) -> dict[str, Any]:
        return self.log("CRITICAL", message, *args, **fields)


def _rotate_if_needed(path: Path) -> None:
    try:
        if not path.exists():
            return
        max_bytes = int(_CONFIG.get("max_bytes") or 0)
        if max_bytes <= 0 or path.stat().st_size < max_bytes:
            return
        backups = int(_CONFIG.get("backup_count") or 0)
        for index in range(backups - 1, 0, -1):
            older = path.with_suffix(path.suffix + f".{index}")
            newer = path.with_suffix(path.suffix + f".{index + 1}")
            if older.exists():
                if index + 1 > backups:
                    older.unlink(missing_ok=True)
                else:
                    older.replace(newer)
        path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:  # pragma: no cover - rotation must never break logging
        return


def get_logger(name: str, **context: Any) -> StructuredLogger:
    return StructuredLogger(name, context)
