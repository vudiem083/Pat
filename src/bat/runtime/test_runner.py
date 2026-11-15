"""Runs a Minecraft runtime test as a background job.

The test is deliberately scoped and honest:

1. create an isolated environment,
2. install the project's packs and (when present) its world,
3. start the operator's Bedrock server,
4. wait for readiness, run an optional console command,
5. stop the server gracefully,
6. scan the captured logs and report PASS/FAIL/NOT_TESTED with evidence.

A crash is reported as ``CRASHED`` with an incident, never as a timeout or a
pass. Without a server binary the result is ``NOT_TESTED``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core.errors import BatError, make_error
from ..core.models import (
    IncidentType,
    ProcessStatus,
    Project,
    ProjectType,
    RuntimeSession,
    RuntimeType,
    TestStatus,
    short_id,
)
from ..core.projects import ProjectManager
from ..diagnostics.incidents import IncidentService
from ..jobs.state import JobAborted
from ..jobs.worker import JobContext
from ..storage.workspace import RuntimeLayout
from .adapter import RuntimeAdapter
from .environment_manager import EnvironmentManager
from .log_parser import scan_lines
from .report import build_runtime_report
from .server_manager import ServerManager


class RuntimeTester:
    def __init__(
        self,
        *,
        adapter: RuntimeAdapter,
        environments: EnvironmentManager,
        servers: ServerManager,
        incidents: IncidentService,
        projects: ProjectManager,
        layout: RuntimeLayout,
        settings: Settings,
    ) -> None:
        self.adapter = adapter
        self.environments = environments
        self.servers = servers
        self.incidents = incidents
        self.projects = projects
        self.layout = layout
        self.settings = settings

    # -- entry point -------------------------------------------------------
    def run(self, ctx: JobContext) -> dict[str, Any]:
        project_id = ctx.params.get("project_id") or ctx.job.project_id
        if not project_id:
            raise make_error("BAT-INPUT-001", "A project_id is required for a runtime test.")
        project = self.projects.get(project_id)
        ctx.log(f"Runtime test requested for project {project.name!r} ({project_id}).")

        if not self.adapter.available():
            reason = self.adapter.unavailable_reason()
            ctx.log(f"Runtime unavailable: {reason}", level="WARNING")
            raise JobAborted(
                "BAT-RUNTIME-003",
                reason,
                status="FAILED",
                result={
                    "test_status": TestStatus.NOT_TESTED.value,
                    "scope": "SERVER_SIDE",
                    "verified": [],
                    "not_verified": [
                        "No Minecraft runtime was available, so NO runtime behaviour was verified.",
                    ],
                    "notes": [reason],
                },
            )

        ctx.check_cancelled()
        environment = self.environments.create(
            project_id=project_id,
            runtime_type=self.adapter.runtime_type,
            metadata={"purpose": "runtime_test", "job_id": ctx.job.job_id},
        )
        ctx.log(f"Created environment {environment.environment_id}.")
        ctx.progress(0.1)

        world_name: str | None = None
        if ProjectType(project.project_type) in (ProjectType.WORLD, ProjectType.COMBINED):
            installed = self.environments.install_world(
                environment.environment_id, project_id, world_name=ctx.params.get("world_name")
            )
            world_name = installed["world_name"]
            ctx.log(f"Installed world {world_name!r} into the environment.")
        if ProjectType(project.project_type) in (ProjectType.ADDON, ProjectType.COMBINED):
            packs = self.environments.install_packs(environment.environment_id, project_id)
            ctx.log(f"Installed {len(packs['installed'])} pack(s).")
        if world_name is None:
            world_name = self._create_test_world(environment.environment_id, project)
            self.environments.bind_world_packs(environment.environment_id, world_name, project_id)
            ctx.log(f"Created a clean test world {world_name!r} for an add-on test.")
        else:
            self.environments.bind_world_packs(environment.environment_id, world_name, project_id)
        ctx.progress(0.25)
        ctx.check_cancelled()

        session = RuntimeSession(
            session_id=short_id("session"),
            environment_id=environment.environment_id,
            job_id=ctx.job.job_id,
            project_id=project_id,
            runtime_type=self.adapter.runtime_type,
            heartbeat={"world_name": world_name},
        )
        ctx.bind_session(session.session_id, environment.environment_id)
        ctx.log(f"Starting runtime session {session.session_id}.")
        ctx.progress(0.35)

        start_timeout = float(
            ctx.params.get("start_timeout") or min(self.settings.server_start_timeout, 900)
        )
        try:
            self.servers.start(
                session,
                environment_dir=Path(environment.path),
                world_name=world_name,
                start_timeout=start_timeout,
            )
        except BatError as exc:
            ctx.log(f"Server start failed: {exc.code} {exc.message}", level="ERROR")
            scan = self._scan_session(session.session_id)
            raise JobAborted(
                exc.code,
                exc.message,
                status="FAILED",
                result={
                    "test_status": TestStatus.FAILED.value,
                    "scope": "SERVER_SIDE",
                    "session_id": session.session_id,
                    "environment_id": environment.environment_id,
                    "log_scan": scan,
                    "verified": [],
                    "not_verified": ["The server never reported readiness."],
                    "notes": [exc.message],
                },
            ) from exc

        ctx.log("Server reported readiness.")
        ctx.progress(0.6)
        ctx.check_cancelled()

        command = ctx.params.get("command")
        command_result: dict[str, Any] | None = None
        if command:
            try:
                command_result = self.servers.send_command(session.session_id, str(command))
                ctx.log(f"Executed console command {command!r}.")
                time.sleep(float(ctx.params.get("command_settle_seconds") or 2.0))
            except BatError as exc:
                ctx.log(f"Console command failed: {exc.message}", level="WARNING")
                command_result = {"error": exc.to_dict()}

        keep_running = bool(ctx.params.get("keep_running"))
        if keep_running:
            ctx.log("keep_running=True: leaving the server running after the job completes.")
            session = self.servers.get_session(session.session_id)
        else:
            ctx.check_cancelled()
            session = self.servers.stop(session.session_id, timeout=float(ctx.params.get("stop_timeout") or 30))
            ctx.log(f"Server stopped with status {session.process_status}.")
        ctx.progress(0.85)

        scan = self._scan_session(session.session_id)
        incidents = [
            i.incident_id for i in self.incidents.list(session_id=session.session_id, limit=20)
        ]
        evidence = [
            f"session {session.session_id} console.log captured",
            f"{scan['total_lines']} console lines scanned",
            f"exit code {session.exit_code!r}",
            f"process status {session.process_status}",
        ]
        if keep_running:
            evidence.append("server intentionally left running (keep_running=True)")

        if session.process_status == ProcessStatus.CRASHED:
            report = build_runtime_report(
                session=session,
                environment_id=environment.environment_id,
                log_scan=scan,
                incidents=incidents,
                test_status=TestStatus.FAIL,
                evidence=evidence,
            )
            self._write_session_report(session.session_id, report)
            raise JobAborted(
                "BAT-RUNTIME-001",
                "Runtime process crashed during the test.",
                status="CRASHED",
                result=report,
            )

        if scan.get("pack_error_count"):
            report = build_runtime_report(
                session=session,
                environment_id=environment.environment_id,
                log_scan=scan,
                incidents=incidents,
                test_status=TestStatus.FAIL,
                evidence=evidence,
                extra_notes=["Minecraft reported pack/manifest errors; see log_scan.pack_errors."],
            )
            self._write_session_report(session.session_id, report)
            raise JobAborted(
                "BAT-PACK-001",
                "The server reported pack errors while loading the installed packs.",
                status="FAILED",
                result=report,
            )

        if scan.get("script_error_count"):
            report = build_runtime_report(
                session=session,
                environment_id=environment.environment_id,
                log_scan=scan,
                incidents=incidents,
                test_status=TestStatus.FAIL,
                evidence=evidence,
                extra_notes=["Script errors were reported; see log_scan.script_errors."],
            )
            self._write_session_report(session.session_id, report)
            raise JobAborted(
                "BAT-SCRIPT-001",
                "The server reported script errors while running the installed packs.",
                status="FAILED",
                result=report,
            )

        if not scan.get("server_ready"):
            report = build_runtime_report(
                session=session,
                environment_id=environment.environment_id,
                log_scan=scan,
                incidents=incidents,
                test_status=TestStatus.NOT_TESTED,
                evidence=evidence,
                extra_notes=[
                    "Readiness was assumed from the start handshake but no readiness line was found "
                    "in the captured logs.",
                ],
            )
            self._write_session_report(session.session_id, report)
            raise JobAborted(
                "BAT-RUNTIME-002",
                "Server readiness could not be confirmed from its logs.",
                status="FAILED",
                result=report,
            )

        report = build_runtime_report(
            session=session,
            environment_id=environment.environment_id,
            log_scan=scan,
            incidents=incidents,
            test_status=TestStatus.PASS,
            evidence=evidence,
            extra_notes=[
                "PASS covers server-side loading only. It does not prove gameplay correctness.",
                "Environment retained for inspection; destroy it with destroy_test_environment.",
            ],
        )
        report["command_result"] = command_result
        self._write_session_report(session.session_id, report)
        ctx.progress(1.0)
        ctx.log("Runtime test finished: PASS (server-side load).")
        return report

    # -- helpers -----------------------------------------------------------
    def _create_test_world(self, environment_id: str, project: Project) -> str:
        directory = self.environments.dir(environment_id)
        name = "bat_test_world"
        world = directory / "worlds" / name
        (world / "db").mkdir(parents=True, exist_ok=True)
        (world / "levelname.txt").write_text(f"BAT test — {project.name}\n", encoding="utf-8")
        (world / "world_behavior_packs.json").write_text("[]\n", encoding="utf-8")
        (world / "world_resource_packs.json").write_text("[]\n", encoding="utf-8")
        return name

    def _scan_session(self, session_id: str) -> dict[str, Any]:
        console = self.layout.session_dir(session_id) / "console.log"
        lines = (
            console.read_text(encoding="utf-8", errors="replace").splitlines()[-8000:]
            if console.exists()
            else []
        )
        return scan_lines(lines).as_dict()

    def _write_session_report(self, session_id: str, report: dict[str, Any]) -> None:
        path = self.layout.session_dir(session_id) / "report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def record_environment_failure(
        self, session: RuntimeSession, summary: str, details: dict[str, Any]
    ) -> None:
        self.incidents.create(
            incident_type=IncidentType.ENVIRONMENT_FAILURE,
            summary=summary,
            project_id=session.project_id,
            job_id=session.job_id,
            session_id=session.session_id,
            details=details,
        )
