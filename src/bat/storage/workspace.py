"""Runtime directory layout (approved design, identifiers are unique).

    <runtime>/
      environments/<env_id>/{config,server,worlds,behavior_packs,resource_packs,scripts}
      sessions/<session_id>/{session.json,console.log,runtime.log,errors.log,heartbeat.json,report.json}
      incidents/<incident_id>/{incident.json,evidence/,diagnosis.json}
      snapshots/<snapshot_id>/
      cache/

Environments, sessions, incidents and snapshots are retained independently:
destroying an environment removes only its own directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..core.errors import make_error

ENV_SUBDIRS = (
    "config",
    "server",
    "worlds",
    "behavior_packs",
    "resource_packs",
    "scripts",
)


@dataclass(frozen=True)
class RuntimeLayout:
    root: Path

    @classmethod
    def from_settings(cls, settings: Settings) -> "RuntimeLayout":
        return cls(root=settings.runtime_root)

    def ensure(self) -> None:
        for path in (
            self.root,
            self.environments_root,
            self.sessions_root,
            self.incidents_root,
            self.snapshots_root,
            self.cache_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def environments_root(self) -> Path:
        return self.root / "environments"

    @property
    def sessions_root(self) -> Path:
        return self.root / "sessions"

    @property
    def incidents_root(self) -> Path:
        return self.root / "incidents"

    @property
    def snapshots_root(self) -> Path:
        return self.root / "snapshots"

    @property
    def cache_root(self) -> Path:
        return self.root / "cache"

    # -- entity directories -------------------------------------------------
    def environment_dir(self, environment_id: str) -> Path:
        return _child(self.environments_root, environment_id, "environment")

    def session_dir(self, session_id: str) -> Path:
        return _child(self.sessions_root, session_id, "session")

    def incident_dir(self, incident_id: str) -> Path:
        return _child(self.incidents_root, incident_id, "incident")

    def snapshot_dir(self, snapshot_id: str) -> Path:
        return _child(self.snapshots_root, snapshot_id, "snapshot")

    def create_environment(self, environment_id: str) -> Path:
        directory = self.environment_dir(environment_id)
        if directory.exists():
            raise make_error(
                "BAT-SANDBOX-001",
                f"Environment {environment_id} already exists.",
                http_status=409,
            )
        for name in ENV_SUBDIRS:
            (directory / name).mkdir(parents=True, exist_ok=True)
        return directory

    def create_session(self, session_id: str) -> Path:
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def create_incident(self, incident_id: str) -> Path:
        directory = self.incident_dir(incident_id)
        (directory / "evidence").mkdir(parents=True, exist_ok=True)
        return directory


def _child(root: Path, identifier: str, label: str) -> Path:
    """Join an identifier onto a root, refusing separators and traversal."""
    text = str(identifier).strip()
    if not text or "/" in text or "\\" in text or text in (".", "..") or text.startswith("."):
        raise make_error(
            "BAT-PATH-001",
            f"Invalid {label} identifier: {identifier!r}",
            details={"identifier": str(identifier)},
        )
    return root / text
