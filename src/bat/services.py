"""Service container: one wired object graph shared by MCP and REST.

Both transports call these services. Neither implements its own business logic,
which is what keeps the two interfaces behaviourally identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .builders.engine import BuildEngine
from .compatibility.feature_matrix import matrix_report
from .compatibility.profiles import known_profiles
from .compatibility.registry import DEFAULT_REGISTRY
from .config import Settings, load_settings
from .core.errors import BatError, describe_codes, make_error
from .core.models import (
    ArtifactType,
    IncidentType,
    Job,
    JobStatus,
    JobType,
    Project,
    ProjectType,
    RuntimeType,
    TestStatus,
    utcnow,
)
from .core.projects import ProjectManager
from .diagnostics.incidents import IncidentService
from .generators.addon import AddonGenerator, GenerationContext
from .generators.structure import StructureGenerator
from .generators.world import WorldGenerator
from .jobs.manager import JobManager
from .jobs.scheduler import recover, stale_heartbeats
from .jobs.state import JobAborted
from .jobs.worker import JobContext
from .observability.health import HealthService
from .observability.structured_logger import configure_logging, get_logger
from .runtime.adapter import RuntimeAdapter, select_adapter
from .runtime.environment_manager import EnvironmentManager
from .runtime.server_manager import ServerManager
from .runtime.test_runner import RuntimeTester
from .storage.database import Database
from .storage.workspace import RuntimeLayout
from .validators.engine import ValidatorEngine
from .version import __version__

# Markers of Python argument-binding TypeErrors (facade generators take **kwargs, so the
# required arguments are enforced by the template functions they call).
_BINDING_ERROR_MARKERS = (
    "missing",
    "required argument",
    "unexpected keyword argument",
    "positional argument",
    "keyword-only argument",
)

CONTENT_GENERATORS = {
    "addon": "create_addon",
    "entity": "create_entity",
    "block": "create_block",
    "item": "create_item",
    "recipe": "create_recipe",
    "loot_table": "create_loot_table",
    "spawn_rule": "create_spawn_rule",
    "animation": "create_animation",
    "animation_controller": "create_animation_controller",
    "particle": "create_particle",
    "attachable": "create_attachable",
    "script_module": "create_script_module",
}


class BatServices:
    def __init__(self, settings: Settings) -> None:
        settings.ensure_directories()
        configure_logging(
            settings.log_root,
            max_bytes=settings.log_max_bytes,
            backup_count=settings.log_backup_count,
        )
        self.settings = settings
        self.logger = get_logger("bat")
        self.db = Database(settings.database_path)
        self.layout = RuntimeLayout.from_settings(settings)
        self.layout.ensure()
        self.projects = ProjectManager(settings, self.db)
        self.validator = ValidatorEngine(self.projects, self.db)
        self.world = WorldGenerator(self.projects, self.layout)
        self.structures = StructureGenerator(self.projects)
        self.builders = BuildEngine(
            self.projects, self.validator, settings, self.db, world=self.world
        )
        self.incidents = IncidentService(
            self.layout, self.db, jobs_log_root=settings.jobs_log_root
        )
        adapter = select_adapter(settings)
        self.adapter: RuntimeAdapter = adapter
        self.environments = EnvironmentManager(self.layout, self.projects, self.db)
        self.servers = ServerManager(
            self.layout,
            settings,
            self.db,
            adapter,
            incident_recorder=self.incidents.record_session_exit,
        )
        self.tester = RuntimeTester(
            adapter=adapter,
            environments=self.environments,
            servers=self.servers,
            incidents=self.incidents,
            projects=self.projects,
            layout=self.layout,
            settings=settings,
        )
        self.jobs = JobManager(self.db, settings)
        self.health = HealthService(settings, self.db, adapter, self.jobs)
        self._register_jobs()

    # -- project helpers ---------------------------------------------------
    def _project(self, project_id: str) -> Project:
        return self.projects.get(project_id)

    def create_project(
        self,
        *,
        name: str,
        project_type: str,
        target_version: str,
        description: str | None = None,
        world_name: str | None = None,
    ) -> dict[str, Any]:
        project = self.projects.create(
            name=name,
            project_type=project_type,
            target_version=target_version,
            description=description,
            world_name=world_name,
        )
        packs = self.projects.list_packs(project.project_id)
        result: dict[str, Any] = {
            "project": project.model_dump(),
            "packs": packs,
            "next_steps": [
                "write_project_file to add content, or generate add-on content",
                "validate_project to check the structure",
                "build_project to produce an artifact",
            ],
        }
        if ProjectType(project.project_type) in (ProjectType.WORLD, ProjectType.COMBINED):
            result["world"] = self.world.inspect(project.project_id)
        return result

    def project_tree(self, project_id: str) -> dict[str, Any]:
        tree = self.projects.tree(project_id)
        return tree.model_dump()

    def get_compatibility(self, version: str) -> dict[str, Any]:
        return matrix_report(version)

    def list_profiles(self) -> list[dict[str, object]]:
        return known_profiles()

    def list_error_codes(self) -> list[dict[str, Any]]:
        return describe_codes()

    # -- content generation ------------------------------------------------
    def generate_content(
        self, project_id: str, generator: str, spec: dict[str, Any]
    ) -> dict[str, Any]:
        if generator not in CONTENT_GENERATORS:
            raise make_error(
                "BAT-INPUT-001",
                f"Unknown generator {generator!r}. Available: {', '.join(sorted(CONTENT_GENERATORS))}.",
            )
        project = self.projects.require_active(self._project(project_id))
        context = GenerationContext(project=project, projects=self.projects)
        addon = AddonGenerator(context)
        method = getattr(addon, CONTENT_GENERATORS[generator])
        try:
            generated = method(**spec)
        except TypeError as exc:
            # A malformed spec is caller error, not an internal failure. Generators
            # take **kwargs facades, so argument binding can only be detected from
            # the raised TypeError; anything else keeps propagating as a real bug.
            text = str(exc)
            if not any(marker in text for marker in _BINDING_ERROR_MARKERS):
                raise
            raise make_error(
                "BAT-INPUT-001",
                f"Invalid spec for generator {generator!r}: {text}.",
                details={"generator": generator, "received": sorted(spec)},
            ) from exc
        self.projects.touch(project)
        return {"generator": generator, "generated": generated.model_dump(), "project_id": project_id}

    # -- worlds ------------------------------------------------------------
    def inspect_world(self, project_id: str) -> dict[str, Any]:
        return self.world.inspect(project_id)

    def modify_world_metadata(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.world.modify_metadata(project_id, **kwargs)

    def bind_world_packs(self, project_id: str) -> dict[str, Any]:
        return self.world.bind_packs(project_id)

    def create_structure(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.structures.create(project_id, **kwargs).model_dump()

    def import_structure(self, project_id: str, name: str, data: bytes) -> dict[str, Any]:
        return self.structures.import_structure(project_id, name=name, data=data)

    def export_structure(self, project_id: str, name: str) -> dict[str, Any]:
        destination = (
            self.settings.artifacts_root
            / project_id
            / "structures"
            / f"{name}.mcstructure"
        )
        return self.structures.export_structure(project_id, name=name, destination=destination)

    # -- builds ------------------------------------------------------------
    def build_project(
        self,
        project_id: str,
        *,
        artifact_type: str | None = None,
        job_id: str | None = None,
        strict: bool = False,
    ) -> dict[str, Any]:
        return self.builders.build_project(
            project_id, artifact_type=artifact_type, job_id=job_id, strict=strict
        )

    # -- jobs --------------------------------------------------------------
    def _register_jobs(self) -> None:
        self.jobs.register(JobType.VALIDATE, self._job_validate)
        self.jobs.register(JobType.BUILD, self._job_build)
        self.jobs.register(JobType.RUNTIME_TEST, self.tester.run)
        self.jobs.register(JobType.RUNTIME_START, self._job_runtime_start)
        self.jobs.register(JobType.RUNTIME_STOP, self._job_runtime_stop)
        self.jobs.register(JobType.DIAGNOSE, self._job_diagnose)

    def _job_validate(self, ctx: JobContext) -> dict[str, Any]:
        project_id = ctx.params.get("project_id") or ctx.job.project_id
        if not project_id:
            raise make_error("BAT-INPUT-001", "project_id is required.")
        ctx.log(f"Validating project {project_id}.")
        report = self.validator.validate_project(project_id)
        ctx.progress(1.0)
        return {"report": report.model_dump()}

    def _job_build(self, ctx: JobContext) -> dict[str, Any]:
        project_id = ctx.params.get("project_id") or ctx.job.project_id
        if not project_id:
            raise make_error("BAT-INPUT-001", "project_id is required.")
        ctx.log(f"Building project {project_id}.")
        result = self.build_project(
            project_id,
            artifact_type=ctx.params.get("artifact_type"),
            job_id=ctx.job.job_id,
            strict=bool(ctx.params.get("strict")),
        )
        ctx.progress(1.0)
        return result

    def _job_runtime_start(self, ctx: JobContext) -> dict[str, Any]:
        """Start a server and leave it running; the job completes once ready."""
        project_id = ctx.params.get("project_id") or ctx.job.project_id
        if not project_id:
            raise make_error("BAT-INPUT-001", "project_id is required.")
        result = self.tester.run(ctx)
        return result

    def _job_runtime_stop(self, ctx: JobContext) -> dict[str, Any]:
        session_id = ctx.params.get("session_id")
        if not session_id:
            raise make_error("BAT-INPUT-001", "session_id is required to stop a server.")
        session = self.servers.stop(
            session_id, timeout=float(ctx.params.get("timeout") or 30), reason="job_request"
        )
        ctx.log(f"Stopped session {session_id}.")
        return {"session_id": session_id, "process_status": str(session.process_status)}

    def _job_diagnose(self, ctx: JobContext) -> dict[str, Any]:
        incident_id = ctx.params.get("incident_id")
        if not incident_id:
            raise make_error("BAT-INPUT-001", "incident_id is required.")
        report = self.incidents.diagnose(incident_id)
        ctx.log(f"Diagnosed incident {incident_id}.")
        return {"diagnosis": report.model_dump()}

    # -- runtime convenience ----------------------------------------------
    def runtime_status(self, session_id: str) -> dict[str, Any]:
        return self.servers.status(session_id)

    def runtime_logs(self, session_id: str, *, kind: str = "console", tail: int = 200) -> dict[str, Any]:
        return self.servers.logs(session_id, kind=kind, tail=tail)

    def runtime_heartbeat(self, session_id: str) -> dict[str, Any]:
        return self.servers.heartbeat(session_id)

    def runtime_report(self, session_id: str) -> dict[str, Any]:
        return self.servers.session_report(session_id)

    def runtime_health(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter.describe(),
            "running_sessions": self.servers.running_sessions(),
            "environments": [e.model_dump() for e in self.environments.list()][:50],
            "stale_heartbeats": stale_heartbeats(self.settings.jobs_log_root),
            "jobs": {
                "active": self.jobs.active_count(),
                "queued": self.jobs.queued_count(),
            },
        }

    def run_game_test(self, project_id: str, **params: Any) -> Job:
        return self.jobs.submit(
            JobType.RUNTIME_TEST,
            project_id=project_id,
            params={"project_id": project_id, **params},
            timeout_seconds=params.get("timeout_seconds"),
        )

    # -- startup / shutdown ------------------------------------------------
    def startup(self) -> dict[str, Any]:
        recovery = recover(self.jobs)
        health = self.health.report()
        self.logger.info(
            "BAT started",
            version=__version__,
            runtime_adapter=self.adapter.name,
            recovered_jobs=recovery["count"],
        )
        return {
            "version": __version__,
            "runtime_adapter": self.adapter.name,
            "runtime_available": health.runtime_available,
            "recovered_jobs": recovery["recovered_jobs"],
            "workspace": str(self.settings.workspace_root),
            "runtime_root": str(self.settings.runtime_root),
        }

    def shutdown(self) -> None:
        self.servers.shutdown()
        self.jobs.shutdown(wait=False)
        self.logger.info("BAT stopped")


def build_services(settings: Settings | None = None) -> BatServices:
    return BatServices(settings or load_settings())


def example_payload(project_id: str) -> dict[str, Any]:
    """Small helper used by docs/tests: a representative API payload."""
    return {
        "project_id": project_id,
        "generated_at": utcnow(),
        "note": "example payload",
    }
