"""Request bodies for the REST API.

Responses are the shared domain models from :mod:`bat.core.models` (or plain
dictionaries built from them), so REST and MCP always agree.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    project_type: Literal["ADDON", "WORLD", "COMBINED"] = "ADDON"
    target_version: str = "1.21.80"
    description: str | None = None
    world_name: str | None = None


class WriteFileRequest(BaseModel):
    content: str
    create_backup: bool = True


class ValidateRequest(BaseModel):
    strict: bool = False


class BuildRequest(BaseModel):
    artifact_type: Literal["MCPACK", "MCADDON", "MCWORLD"] | None = None
    strict: bool = False


class GenerateContentRequest(BaseModel):
    spec: dict[str, Any] = Field(default_factory=dict)


class WorldMetadataRequest(BaseModel):
    level_name: str | None = None
    game_mode: Literal["survival", "creative", "adventure", "spectator"] | None = None
    difficulty: Literal["peaceful", "easy", "normal", "hard"] | None = None
    seed: int | None = None
    spawn: list[int] | None = None
    commands_enabled: bool | None = None

    def to_kwargs(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_none=True)
        spawn = payload.get("spawn")
        if spawn is not None and len(spawn) != 3:
            raise ValueError("spawn must be [x, y, z]")
        return payload


class CreateStructureRequest(BaseModel):
    name: str
    size: list[int] = Field(default_factory=lambda: [4, 4, 4])
    block: str = "minecraft:stone"
    origin: list[int] = Field(default_factory=lambda: [0, 0, 0])


class ImportStructureRequest(BaseModel):
    name: str
    content_base64: str


class EnvironmentRequest(BaseModel):
    project_id: str | None = None
    runtime_type: Literal["BDS", "CLIENT", "UNAVAILABLE"] = "UNAVAILABLE"


class InstallPacksRequest(BaseModel):
    project_id: str


class InstallWorldRequest(BaseModel):
    project_id: str
    world_name: str | None = None


class ConsoleCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=512)


class StopServerRequest(BaseModel):
    timeout: float = 30.0


class JobCreateRequest(BaseModel):
    job_type: Literal[
        "VALIDATE", "BUILD", "RUNTIME_TEST", "RUNTIME_START", "RUNTIME_STOP", "DIAGNOSE"
    ]
    project_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1, le=86400)


class WaitRequest(BaseModel):
    timeout: float | None = Field(default=None, ge=0)
