"""Isolated runtime environments.

Each environment is a directory under ``runtime/environments`` with its own
config, server, worlds, packs and scripts. Installing project content copies it
in, so a test never mutates the project itself. Destroying an environment
removes only that environment: sessions, incidents and snapshots survive.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.filesystem import resolve_within
from ..core.models import Environment, Project, ProjectType, RuntimeType, utcnow
from ..core.projects import ProjectManager
from ..storage.workspace import RuntimeLayout


class EnvironmentManager:
    def __init__(self, layout: RuntimeLayout, projects: ProjectManager, db: Any) -> None:
        self.layout = layout
        self.projects = projects
        self.db = db
        layout.ensure()

    # -- creation ----------------------------------------------------------
    def create(
        self,
        *,
        project_id: str | None = None,
        runtime_type: RuntimeType = RuntimeType.UNAVAILABLE,
        metadata: dict[str, Any] | None = None,
    ) -> Environment:
        if project_id:
            self.projects.get(project_id)
        environment = Environment(
            project_id=project_id,
            path="",
            runtime_type=runtime_type,
            metadata=metadata or {},
        )
        directory = self.layout.create_environment(environment.environment_id)
        environment.path = str(directory)
        config = {
            "environment_id": environment.environment_id,
            "project_id": project_id,
            "created_at": environment.created_at,
            "runtime_type": runtime_type.value,
            "notes": [
                "Environment directories are isolated. Packs and worlds are copied in, never "
                "linked, so destructive tests cannot touch project files.",
            ],
        }
        (directory / "config" / "environment.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )
        self.db.save_environment(environment)
        return environment

    def get(self, environment_id: str) -> Environment:
        environment = self.db.get_environment(environment_id)
        if environment is None:
            raise make_error(
                "BAT-NOTFOUND-005",
                f"Environment {environment_id} was not found.",
                http_status=404,
            )
        return environment

    def dir(self, environment_id: str) -> Path:
        environment = self.get(environment_id)
        directory = Path(environment.path)
        if not directory.exists():
            raise make_error(
                "BAT-RUNTIME-006",
                f"Environment {environment_id} is recorded but its directory is missing.",
                http_status=410,
            )
        # Isolation guard: the directory must live under the environments root.
        try:
            directory.resolve().relative_to(self.layout.environments_root.resolve())
        except ValueError as exc:
            raise make_error(
                "BAT-SANDBOX-001",
                f"Environment path for {environment_id} is outside the runtime environments root.",
            ) from exc
        return directory

    def list(self, project_id: str | None = None) -> list[Environment]:
        return self.db.list_environments(project_id)

    # -- content installation ---------------------------------------------
    def install_packs(self, environment_id: str, project_id: str) -> dict[str, Any]:
        environment = self.get(environment_id)
        project = self.projects.get(project_id)
        if ProjectType(project.project_type) is ProjectType.WORLD:
            raise make_error(
                "BAT-PROJECT-003",
                "This project has no add-on packs to install.",
                http_status=409,
            )
        directory = self.dir(environment_id)
        installed: list[dict[str, str]] = []
        for base, target_base in (
            ("behavior_packs", "behavior_packs"),
            ("resource_packs", "resource_packs"),
        ):
            source = self.projects.files_root(project_id) / base
            if not source.exists():
                continue
            for pack in sorted(p for p in source.iterdir() if p.is_dir()):
                destination = directory / target_base / pack.name
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(pack, destination)
                installed.append(
                    {
                        "pack": pack.name,
                        "kind": target_base,
                        "destination": str(destination),
                    }
                )
        if not installed:
            raise make_error(
                "BAT-BUILD-002",
                "Project has no packs to install into the runtime environment.",
            )
        # Bind installed packs into every world inside the environment.
        for world in sorted((directory / "worlds").iterdir()) if (directory / "worlds").exists() else []:
            if world.is_dir():
                _bind_world_packs(world, installed)
        environment.installed_packs = [item["pack"] for item in installed]
        environment.status = "IN_USE"
        self.db.save_environment(environment)
        return {"environment_id": environment_id, "installed": installed}

    def install_world(
        self, environment_id: str, project_id: str, *, world_name: str | None = None
    ) -> dict[str, Any]:
        project = self.projects.get(project_id)
        if ProjectType(project.project_type) not in (ProjectType.WORLD, ProjectType.COMBINED):
            raise make_error(
                "BAT-PROJECT-003",
                "This project has no world to install.",
                http_status=409,
            )
        source = self.projects.ensure_world_dir(project_id)
        directory = self.dir(environment_id)
        name = world_name or _slug(project.name)
        destination = resolve_within(directory / "worlds", name)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        environment = self.get(environment_id)
        environment.installed_world = name
        self.db.save_environment(environment)
        return {
            "environment_id": environment_id,
            "world_name": name,
            "destination": str(destination),
            "has_leveldb": (destination / "db").is_dir(),
            "notes": [
                "World copied into the environment. The project's own world files are untouched.",
            ],
        }

    def bind_world_packs(self, environment_id: str, world_name: str, project_id: str) -> dict[str, Any]:
        directory = self.dir(environment_id)
        world = resolve_within(directory / "worlds", world_name)
        installed = [
            {"pack": p.name, "kind": "behavior_packs", "destination": str(p)}
            for p in sorted((directory / "behavior_packs").iterdir())
            if p.is_dir()
        ] + [
            {"pack": p.name, "kind": "resource_packs", "destination": str(p)}
            for p in sorted((directory / "resource_packs").iterdir())
            if p.is_dir()
        ]
        _bind_world_packs(world, installed)
        return {"environment_id": environment_id, "world_name": world_name, "packs": len(installed)}

    # -- lifecycle ---------------------------------------------------------
    def destroy(self, environment_id: str) -> dict[str, Any]:
        environment = self.get(environment_id)
        directory = Path(environment.path)
        removed = False
        if directory.exists():
            try:
                directory.resolve().relative_to(self.layout.environments_root.resolve())
            except ValueError as exc:
                raise make_error(
                    "BAT-SANDBOX-001",
                    "Refusing to delete an environment directory outside the runtime root.",
                ) from exc
            shutil.rmtree(directory)
            removed = True
        self.db.delete_environment(environment_id)
        return {
            "environment_id": environment_id,
            "removed": removed,
            "retained": [
                "runtime sessions and their logs",
                "runtime incidents and their evidence",
                "snapshots",
            ],
            "note": "Incident evidence and session logs are never deleted with an environment.",
        }

    def snapshot(self, environment_id: str) -> Path:
        directory = self.dir(environment_id)
        snapshot_id = f"snapshot_{utcnow().replace(':', '').replace('-', '')[:15]}_{environment_id[-6:]}"
        target = self.layout.snapshot_dir(snapshot_id)
        shutil.copytree(directory, target / "environment")
        (target / "snapshot.json").write_text(
            json.dumps(
                {
                    "snapshot_id": snapshot_id,
                    "environment_id": environment_id,
                    "created_at": utcnow(),
                    "source": "environment",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return target


def _bind_world_packs(world: Path, installed: list[dict[str, str]]) -> None:
    behavior: list[dict[str, Any]] = []
    resource: list[dict[str, Any]] = []
    for item in installed:
        manifest = Path(item["destination"]) / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        header = data.get("header", {})
        uuid_value = header.get("uuid")
        if not isinstance(uuid_value, str):
            continue
        version = header.get("version", [1, 0, 0])
        entry = {"pack_id": uuid_value, "version": version}
        (behavior if item["kind"] == "behavior_packs" else resource).append(entry)
    world.mkdir(parents=True, exist_ok=True)
    (world / "world_behavior_packs.json").write_text(
        json.dumps(behavior, indent=2) + "\n", encoding="utf-8"
    )
    (world / "world_resource_packs.json").write_text(
        json.dumps(resource, indent=2) + "\n", encoding="utf-8"
    )


def _slug(name: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
    return (cleaned or "world")[:48]
