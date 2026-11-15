"""Runtime environment and Minecraft server MCP tools."""

from __future__ import annotations

from typing import Any

from ...core.models import RuntimeType
from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def create_test_environment(project_id: str | None = None) -> dict:
        """Create an isolated runtime environment (unique id under runtime/environments)."""
        environment = services.environments.create(
            project_id=project_id, runtime_type=RuntimeType(services.adapter.runtime_type)
        )
        return environment.model_dump()

    @mcp.tool()
    @tool
    def install_test_packs(environment_id: str, project_id: str) -> dict:
        """Copy a project's behavior/resource packs into an environment."""
        return services.environments.install_packs(environment_id, project_id)

    @mcp.tool()
    @tool
    def install_test_world(environment_id: str, project_id: str, world_name: str | None = None) -> dict:
        """Copy a project's world into an environment."""
        return services.environments.install_world(
            environment_id, project_id, world_name=world_name
        )

    @mcp.tool()
    @tool
    def start_bedrock_server(
        project_id: str,
        keep_running: bool = True,
        world_name: str | None = None,
        command: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict:
        """Start a Bedrock server as a background job.

        Returns immediately with a job id. Poll get_job_status and read
        result.session_id once the job completes. If no server executable is
        configured the job fails with BAT-RUNTIME-003 and status NOT_TESTED.
        """
        job = services.jobs.submit(
            "RUNTIME_START",
            project_id=project_id,
            params={
                "project_id": project_id,
                "keep_running": keep_running,
                "world_name": world_name,
                "command": command,
            },
            timeout_seconds=timeout_seconds,
        )
        return {"job": job.model_dump(), "hint": "Poll get_job_status(job_id)."}

    @mcp.tool()
    @tool
    def stop_bedrock_server(session_id: str, timeout: float = 30.0) -> dict:
        """Stop a running server session gracefully (stop command, then terminate)."""
        session = services.servers.stop(session_id, timeout=timeout)
        return session.model_dump()

    @mcp.tool()
    @tool
    def run_game_test(
        project_id: str,
        command: str | None = None,
        keep_running: bool = False,
        timeout_seconds: float | None = None,
    ) -> dict:
        """Run a runtime test as a background job and return its job id.

        Scope is server-side loading. Client rendering, UI and gameplay are
        reported as NOT_TESTED, never as passed.
        """
        job = services.run_game_test(
            project_id,
            command=command,
            keep_running=keep_running,
            timeout_seconds=timeout_seconds,
        )
        return {"job": job.model_dump(), "hint": "Poll get_job_status or wait_for_job."}

    @mcp.tool()
    @tool
    def execute_test_command(session_id: str, command: str) -> dict:
        """Send a console command to a running server session."""
        return services.servers.send_command(session_id, command)

    @mcp.tool()
    @tool
    def get_runtime_logs(session_id: str, kind: str = "console", tail: int = 200) -> dict:
        """Read captured session logs (console, runtime or errors)."""
        return services.runtime_logs(session_id, kind=kind, tail=tail)

    @mcp.tool()
    @tool
    def get_runtime_status(session_id: str) -> dict:
        """Live status of a runtime session (alive, ready, exit code, uptime)."""
        return services.runtime_status(session_id)

    @mcp.tool()
    @tool
    def get_runtime_report(session_id: str) -> dict:
        """Read the runtime report for a session (log scan, exit info, notes)."""
        return services.runtime_report(session_id)

    @mcp.tool()
    @tool
    def destroy_test_environment(environment_id: str) -> dict:
        """Destroy an environment. Sessions, incidents and snapshots are retained."""
        return services.environments.destroy(environment_id)
