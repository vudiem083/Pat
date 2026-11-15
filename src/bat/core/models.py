"""Shared, typed data contracts used by every BAT interface.

MCP tools and REST routes construct and return these models. Neither transport
defines its own copy of a payload shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> str:
    """Current UTC timestamp as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_uuid() -> str:
    return str(uuid.uuid4())


def short_id(prefix: str) -> str:
    """Readable unique identifier such as ``env_9f3c1a7b2d4e``."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class BatEnum(str, Enum):
    """String enum whose ``str()`` is its value (Python 3.10 compatible)."""

    def __str__(self) -> str:
        return str(self.value)


class ProjectType(BatEnum):
    ADDON = "ADDON"
    WORLD = "WORLD"
    COMBINED = "COMBINED"


class ProjectStatus(BatEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class JobType(BatEnum):
    BUILD = "BUILD"
    VALIDATE = "VALIDATE"
    RUNTIME_TEST = "RUNTIME_TEST"
    RUNTIME_START = "RUNTIME_START"
    RUNTIME_STOP = "RUNTIME_STOP"
    DIAGNOSE = "DIAGNOSE"


class JobStatus(BatEnum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CRASHED = "CRASHED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CRASHED,
        JobStatus.TIMED_OUT,
        JobStatus.CANCELLED,
    }
)


class ArtifactType(BatEnum):
    MCPACK = "MCPACK"
    MCADDON = "MCADDON"
    MCWORLD = "MCWORLD"


class ValidationOutcome(BatEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class TestStatus(BatEnum):
    """Test-result vocabulary used by validation and runtime reports."""

    #: Keep pytest from trying to collect this enum as a test class.
    __test__ = False

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_TESTED = "NOT_TESTED"


class Severity(BatEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CompatibilityStatus(BatEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_TESTED = "NOT_TESTED"


class ProcessStatus(BatEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    EXITED = "EXITED"
    CRASHED = "CRASHED"
    FAILED = "FAILED"


class IncidentType(BatEnum):
    PROCESS_CRASH = "PROCESS_CRASH"
    UNEXPECTED_EXIT = "UNEXPECTED_EXIT"
    STARTUP_FAILURE = "STARTUP_FAILURE"
    UNRESPONSIVE = "UNRESPONSIVE"
    SCRIPT_ERROR = "SCRIPT_ERROR"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    JOB_FAILURE = "JOB_FAILURE"


class DiagnosticStatus(BatEnum):
    PENDING = "PENDING"
    COLLECTING = "COLLECTING"
    ANALYZED = "ANALYZED"
    UNKNOWN_CAUSE = "UNKNOWN_CAUSE"
    FAILED = "FAILED"


class PackKind(BatEnum):
    BEHAVIOR = "BEHAVIOR"
    RESOURCE = "RESOURCE"


class RuntimeType(BatEnum):
    BDS = "BDS"
    CLIENT = "CLIENT"
    UNAVAILABLE = "UNAVAILABLE"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class BatModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Project(BatModel):
    project_id: str = Field(default_factory=new_uuid)
    name: str
    project_type: ProjectType
    target_version: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    description: str | None = None
    pack_uuids: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of logical pack name -> manifest header UUID.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class Job(BatModel):
    job_id: str = Field(default_factory=new_uuid)
    project_id: str | None = None
    job_type: JobType
    status: JobStatus = JobStatus.QUEUED
    created_at: str = Field(default_factory=utcnow)
    started_at: str | None = None
    completed_at: str | None = None
    error_code: str | None = None
    message: str | None = None
    result: dict[str, Any] | None = None
    progress: float = 0.0
    session_id: str | None = None
    environment_id: str | None = None
    timeout_seconds: float | None = None
    cancelled: bool = False

    @property
    def is_terminal(self) -> bool:
        return JobStatus(self.status) in TERMINAL_JOB_STATUSES


class JobLogLine(BatModel):
    timestamp: str = Field(default_factory=utcnow)
    level: str = "INFO"
    message: str


class Artifact(BatModel):
    artifact_id: str = Field(default_factory=new_uuid)
    project_id: str
    job_id: str | None = None
    artifact_type: ArtifactType
    file_name: str
    storage_path: str
    checksum: str
    size_bytes: int = 0
    created_at: str = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BatModel):
    code: str
    severity: Severity
    message: str
    file_path: str | None = None
    line_number: int | None = None
    entity_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CompatibilityInfo(BatModel):
    target_version: str
    checked_features: list["FeatureSupport"] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FeatureSupport(BatModel):
    feature: str
    category: str
    status: CompatibilityStatus
    min_version: str | None = None
    max_version: str | None = None
    evidence: str = ""
    notes: str = ""


class ValidationReport(BatModel):
    report_id: str = Field(default_factory=new_uuid)
    project_id: str
    target_version: str
    status: ValidationOutcome = ValidationOutcome.PASS
    findings: list[Finding] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    compatibility: CompatibilityInfo
    evidence: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utcnow)
    checked_files: int = 0
    validators_run: list[str] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity in (Severity.ERROR, Severity.CRITICAL))


class RuntimeSession(BatModel):
    session_id: str = Field(default_factory=lambda: short_id("session"))
    environment_id: str
    job_id: str | None = None
    #: A session may be started for a bare environment, so the project is optional.
    project_id: str | None = None
    runtime_type: RuntimeType = RuntimeType.UNAVAILABLE
    started_at: str = Field(default_factory=utcnow)
    ended_at: str | None = None
    process_status: ProcessStatus = ProcessStatus.STARTING
    exit_code: int | None = None
    exit_signal: str | None = None
    heartbeat: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, str] = Field(default_factory=dict)
    command_log: list[str] = Field(default_factory=list)
    ready: bool = False
    notes: list[str] = Field(default_factory=list)


class Incident(BatModel):
    incident_id: str = Field(default_factory=lambda: short_id("incident"))
    project_id: str | None = None
    job_id: str | None = None
    session_id: str | None = None
    incident_type: IncidentType
    severity: Severity = Severity.ERROR
    timestamp: str = Field(default_factory=utcnow)
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidence_files: list[str] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    diagnostic_status: DiagnosticStatus = DiagnosticStatus.PENDING
    confidence: float = 0.0
    error_code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DiagnosticReport(BatModel):
    incident_id: str
    error_code: str | None = None
    severity: Severity = Severity.ERROR
    source: str = "bat"
    timestamp: str = Field(default_factory=utcnow)
    job_id: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    message: str = ""
    evidence: list[str] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    root_cause_known: bool = False
    diagnostic_status: DiagnosticStatus = DiagnosticStatus.PENDING


class JobReport(BatModel):
    job_id: str
    project_id: str | None = None
    job_type: JobType
    status: JobStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    error_code: str | None = None
    message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    incidents: list[str] = Field(default_factory=list)
    log_files: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Environment(BatModel):
    environment_id: str = Field(default_factory=lambda: short_id("env"))
    project_id: str | None = None
    path: str
    created_at: str = Field(default_factory=utcnow)
    status: Literal["READY", "IN_USE", "DESTROYED"] = "READY"
    runtime_type: RuntimeType = RuntimeType.UNAVAILABLE
    installed_packs: list[str] = Field(default_factory=list)
    installed_world: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedFile(BatModel):
    path: str
    kind: str
    pack: str | None = None
    description: str = ""
    compatibility_status: CompatibilityStatus = CompatibilityStatus.SUPPORTED
    warnings: list[str] = Field(default_factory=list)


class ProjectTreeNode(BatModel):
    name: str
    path: str
    type: Literal["dir", "file"]
    size: int | None = None
    children: list["ProjectTreeNode"] = Field(default_factory=list)


class HealthReport(BatModel):
    status: Literal["OK", "DEGRADED"] = "OK"
    version: str
    runtime_adapter: str
    runtime_available: bool
    database: str
    workspace_root: str
    runtime_root: str
    active_jobs: int = 0
    queued_jobs: int = 0
    checks: dict[str, str] = Field(default_factory=dict)


class Paginated(BatModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


CompatibilityInfo.model_rebuild()
ProjectTreeNode.model_rebuild()
