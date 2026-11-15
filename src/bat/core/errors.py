"""Documented BAT diagnostic error-code namespace.

Every code BAT can emit is registered here with a description. Unknown or
invented codes must not be raised: :func:`make_error` refuses unregistered
codes, which keeps MCP/REST error surfaces consistent and documented.

Codes use the ``BAT-<AREA>-<NNN>`` shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"
SEVERITY_CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ErrorDefinition:
    code: str
    area: str
    summary: str
    severity: str = SEVERITY_ERROR
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "area": self.area,
            "summary": self.summary,
            "severity": self.severity,
            "retryable": self.retryable,
        }


_DEFINITIONS: tuple[ErrorDefinition, ...] = (
    # Generic input / lookup
    ErrorDefinition("BAT-INPUT-001", "input", "A request argument is missing or malformed."),
    ErrorDefinition("BAT-NOTFOUND-001", "lookup", "Project not found."),
    ErrorDefinition("BAT-NOTFOUND-002", "lookup", "File not found inside the project."),
    ErrorDefinition("BAT-NOTFOUND-003", "lookup", "Job not found."),
    ErrorDefinition("BAT-NOTFOUND-004", "lookup", "Artifact not found."),
    ErrorDefinition("BAT-NOTFOUND-005", "lookup", "Runtime session or environment not found."),
    ErrorDefinition("BAT-NOTFOUND-006", "lookup", "Incident not found."),
    ErrorDefinition("BAT-NOTFOUND-007", "lookup", "World file or path not found."),
    # Path / filesystem safety
    ErrorDefinition("BAT-PATH-001", "filesystem", "Path escapes its allowed root (path traversal or absolute path rejected)."),
    ErrorDefinition("BAT-PATH-002", "filesystem", "File exceeds the configured size limit."),
    ErrorDefinition("BAT-PATH-003", "filesystem", "Binary or non-UTF-8 content cannot be returned as text."),
    ErrorDefinition("BAT-PATH-004", "filesystem", "Symlink or non-regular file rejected."),
    # Projects
    ErrorDefinition("BAT-PROJECT-001", "project", "Unsupported project type or target version."),
    ErrorDefinition("BAT-PROJECT-002", "project", "A project with that name already exists."),
    ErrorDefinition("BAT-PROJECT-003", "project", "Operation is not valid for this project type."),
    ErrorDefinition("BAT-PROJECT-004", "project", "Project is archived and cannot be modified."),
    # Validation
    ErrorDefinition("BAT-JSON-001", "validation", "A project JSON file is not valid JSON."),
    ErrorDefinition("BAT-MANIFEST-001", "validation", "Pack manifest is missing required fields or is malformed."),
    ErrorDefinition("BAT-MANIFEST-002", "validation", "Duplicate pack UUID detected across packs."),
    ErrorDefinition("BAT-PACK-001", "validation", "Pack directory structure or module configuration is invalid."),
    ErrorDefinition("BAT-ENTITY-001", "validation", "Entity definition is invalid for the target version."),
    ErrorDefinition("BAT-BLOCK-001", "validation", "Block definition is invalid for the target version."),
    ErrorDefinition("BAT-ITEM-001", "validation", "Item definition is invalid for the target version."),
    ErrorDefinition("BAT-RECIPE-001", "validation", "Recipe definition is invalid for the target version."),
    ErrorDefinition("BAT-TEXTURE-001", "validation", "Texture file is missing, unreadable or not a valid PNG."),
    ErrorDefinition("BAT-ANIMATION-001", "validation", "Animation or animation controller is invalid."),
    ErrorDefinition("BAT-WORLD-001", "validation", "World data is missing or invalid."),
    ErrorDefinition("BAT-VALIDATION-001", "validation", "Validation reported one or more errors."),
    # Compatibility
    ErrorDefinition("BAT-COMPAT-001", "compatibility", "Target version is outside the supported range (1.19.0–1.21.80)."),
    ErrorDefinition("BAT-COMPAT-002", "compatibility", "Requested feature is not supported by the target version."),
    ErrorDefinition("BAT-COMPAT-003", "compatibility", "Compatibility could not be established from available evidence."),
    # Build / artifacts
    ErrorDefinition("BAT-BUILD-001", "build", "Build failed before an artifact could be produced."),
    ErrorDefinition("BAT-BUILD-002", "build", "Project has no buildable packs or world for the requested artifact type."),
    ErrorDefinition("BAT-ARTIFACT-001", "artifact", "Artifact file is missing, corrupt or fails its integrity check."),
    ErrorDefinition("BAT-ARTIFACT-002", "artifact", "Artifact contains an unexpected internal structure."),
    # Runtime
    ErrorDefinition("BAT-RUNTIME-001", "runtime", "Runtime process exited unexpectedly.", SEVERITY_CRITICAL),
    ErrorDefinition("BAT-RUNTIME-002", "runtime", "Runtime server did not become ready before the start timeout.", SEVERITY_ERROR, True),
    ErrorDefinition("BAT-RUNTIME-003", "runtime", "No Minecraft Bedrock server executable is available for the runtime adapter."),
    ErrorDefinition("BAT-RUNTIME-004", "runtime", "Runtime process is running but unresponsive (heartbeat stalled).", SEVERITY_CRITICAL),
    ErrorDefinition("BAT-RUNTIME-005", "runtime", "Runtime job exceeded its timeout."),
    ErrorDefinition("BAT-RUNTIME-006", "runtime", "Runtime environment failure (environment missing, unusable or torn down)."),
    ErrorDefinition("BAT-RUNTIME-007", "runtime", "Runtime command or operation is not supported by the active adapter."),
    ErrorDefinition("BAT-SCRIPT-001", "runtime", "Minecraft script (GameTest/Script API) reported an error."),
    # Jobs
    ErrorDefinition("BAT-JOB-001", "jobs", "Job cannot be cancelled in its current state."),
    ErrorDefinition("BAT-JOB-002", "jobs", "Job worker died before recording a terminal state.", SEVERITY_CRITICAL),
    ErrorDefinition("BAT-JOB-003", "jobs", "Job queue rejected the work (queue saturated or shut down).", SEVERITY_WARNING, True),
    ErrorDefinition("BAT-JOB-004", "jobs", "Job handler raised an unhandled error."),
    # Sandbox
    ErrorDefinition("BAT-SANDBOX-001", "sandbox", "Operation would break runtime environment isolation."),
)

ERROR_CODES: dict[str, ErrorDefinition] = {d.code: d for d in _DEFINITIONS}


class BatError(Exception):
    """A domain error carrying a documented BAT diagnostic code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        http_status: int = 400,
    ) -> None:
        definition = ERROR_CODES.get(code)
        if definition is None:
            raise ValueError(f"Unregistered BAT error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.http_status = http_status
        self.definition = definition

    @property
    def severity(self) -> str:
        return self.definition.severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "message": self.message,
            "severity": self.severity,
            "retryable": self.definition.retryable,
            "details": self.details,
        }


def make_error(code: str, message: str, **kwargs: Any) -> BatError:
    """Build a :class:`BatError`, rejecting unregistered codes."""
    return BatError(code, message, **kwargs)


def describe_codes() -> list[dict[str, Any]]:
    """Return every documented error code (used by docs endpoints)."""
    return [d.as_dict() for d in sorted(_DEFINITIONS, key=lambda d: d.code)]


def error_severity(code: str) -> str:
    definition = ERROR_CODES.get(code)
    return definition.severity if definition else SEVERITY_ERROR
