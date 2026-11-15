"""Configuration loading from environment variables.

Settings are immutable once loaded so that the REST app, the MCP server and
background workers always agree on paths and limits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping


def _env_str(env: Mapping[str, str], key: str, default: str = "") -> str:
    value = env.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = _env_str(env, key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - covered by config test
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc


def _env_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = _env_str(env, key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc


def _env_path(env: Mapping[str, str], key: str, default: Path) -> Path:
    raw = _env_str(env, key)
    return Path(raw).expanduser() if raw else default


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    runtime_root: Path
    database_path: Path
    log_root: Path
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str | None = None
    runtime_adapter: str = "auto"
    bedrock_server_path: Path | None = None
    server_start_timeout: float = 120.0
    heartbeat_interval: float = 5.0
    unresponsive_seconds: float = 90.0
    max_file_bytes: int = 10 * 1024 * 1024
    max_upload_bytes: int = 50 * 1024 * 1024
    log_max_bytes: int = 2 * 1024 * 1024
    log_backup_count: int = 5
    job_workers: int = 4
    default_wait_seconds: float = 30.0
    max_wait_seconds: float = 300.0
    extra: dict[str, str] = field(default_factory=dict)

    # Convenience derived paths -------------------------------------------------
    @property
    def projects_root(self) -> Path:
        return self.workspace_root / "projects"

    @property
    def artifacts_root(self) -> Path:
        return self.workspace_root / "artifacts"

    @property
    def jobs_log_root(self) -> Path:
        return self.log_root / "jobs"

    def with_overrides(self, **kwargs: object) -> "Settings":
        return replace(self, **kwargs)  # type: ignore[arg-type]

    def ensure_directories(self) -> None:
        for path in (
            self.workspace_root,
            self.projects_root,
            self.artifacts_root,
            self.database_path.parent,
            self.log_root,
            self.jobs_log_root,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings(env: Mapping[str, str] | None = None, **overrides: object) -> Settings:
    env = dict(os.environ if env is None else env)
    workspace = _env_path(env, "BAT_WORKSPACE", Path("./data"))
    runtime_root = _env_path(env, "BAT_RUNTIME_ROOT", Path("./runtime"))
    database = _env_path(env, "BAT_DATABASE", workspace / "bat.db")
    log_root = _env_path(env, "BAT_LOG_ROOT", workspace / "logs")
    server_raw = _env_str(env, "BAT_BEDROCK_SERVER")
    api_key = _env_str(env, "BAT_API_KEY") or None

    settings = Settings(
        workspace_root=workspace.resolve(),
        runtime_root=runtime_root.resolve(),
        database_path=database.resolve(),
        log_root=log_root.resolve(),
        host=_env_str(env, "BAT_HOST", "127.0.0.1"),
        port=_env_int(env, "BAT_PORT", 8000),
        api_key=api_key,
        runtime_adapter=_env_str(env, "BAT_RUNTIME_ADAPTER", "auto").lower(),
        bedrock_server_path=Path(server_raw).expanduser().resolve() if server_raw else None,
        server_start_timeout=_env_float(env, "BAT_SERVER_START_TIMEOUT", 120.0),
        heartbeat_interval=_env_float(env, "BAT_HEARTBEAT_INTERVAL", 5.0),
        unresponsive_seconds=_env_float(env, "BAT_UNRESPONSIVE_SECONDS", 90.0),
        max_file_bytes=_env_int(env, "BAT_MAX_FILE_BYTES", 10 * 1024 * 1024),
        max_upload_bytes=_env_int(env, "BAT_MAX_UPLOAD_BYTES", 50 * 1024 * 1024),
        log_max_bytes=_env_int(env, "BAT_LOG_MAX_BYTES", 2 * 1024 * 1024),
        log_backup_count=_env_int(env, "BAT_LOG_BACKUP_COUNT", 5),
        job_workers=max(1, _env_int(env, "BAT_JOB_WORKERS", 4)),
        default_wait_seconds=_env_float(env, "BAT_DEFAULT_WAIT_SECONDS", 30.0),
        max_wait_seconds=_env_float(env, "BAT_MAX_WAIT_SECONDS", 300.0),
    )
    if overrides:
        settings = replace(settings, **overrides)  # type: ignore[arg-type]
    return settings
