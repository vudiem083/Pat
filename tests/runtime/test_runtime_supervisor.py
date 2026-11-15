"""Runtime supervision tests.

These tests use a *simulated* server process (a small Python script), never real
Minecraft. They verify BAT's process supervision: readiness, incremental log
capture, heartbeats, console commands, graceful stop, crash classification,
incident creation and cleanup guarantees.

Real Minecraft runtime verification is NOT_TESTED in this repository: it needs
an operator-supplied Bedrock Dedicated Server.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from bat.config import load_settings
from bat.core.errors import BatError
from bat.core.models import (
    IncidentType,
    ProcessStatus,
    RuntimeSession,
    RuntimeType,
    TestStatus,
    short_id,
)
from bat.services import BatServices

pytestmark = pytest.mark.simulated


@pytest.fixture()
def supervised(runtime_services: BatServices):
    """Create an environment with a world and start a supervised server."""
    environment = runtime_services.environments.create(
        project_id=None, runtime_type=RuntimeType.BDS
    )
    environment_dir = runtime_services.environments.dir(environment.environment_id)
    world = environment_dir / "worlds" / "w"
    world.mkdir(parents=True)
    (world / "levelname.txt").write_text("Supervised\n")
    (world / "world_behavior_packs.json").write_text("[]\n")
    (world / "world_resource_packs.json").write_text("[]\n")

    session = RuntimeSession(
        session_id=short_id("session"),
        environment_id=environment.environment_id,
        project_id=None,
        runtime_type=RuntimeType.BDS,
    )
    runtime_services.servers.start(
        session, environment_dir=Path(environment.path), world_name="w", start_timeout=15
    )
    yield runtime_services, session
    if session.session_id in runtime_services.servers.running_sessions():
        runtime_services.servers.stop(session.session_id, timeout=5, reason="test_cleanup")


def _wait_for(predicate, timeout: float = 10.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_server_reaches_ready_and_writes_heartbeat(supervised):
    services, session = supervised
    status = services.servers.status(session.session_id)
    assert status["alive"] is True
    assert status["ready"] is True
    assert status["pid"] > 0

    heartbeat_path = services.layout.session_dir(session.session_id) / "heartbeat.json"
    assert _wait_for(lambda: heartbeat_path.exists(), timeout=5)
    assert heartbeat_path.exists()
    assert (services.layout.session_dir(session.session_id) / "session.json").exists()


def test_console_output_is_captured_incrementally(supervised):
    services, session = supervised
    console = services.layout.session_dir(session.session_id) / "console.log"
    assert _wait_for(lambda: "Server started" in console.read_text(), timeout=5)
    logs = services.runtime_logs(session.session_id)
    assert any("Server started" in line for line in logs["lines"])
    runtime_log = services.layout.session_dir(session.session_id) / "runtime.log"
    assert '"event": "console_line"' in runtime_log.read_text()


def test_console_command_roundtrip(supervised):
    services, session = supervised
    result = services.servers.send_command(session.session_id, "list")
    assert result["delivered"] is True
    assert _wait_for(
        lambda: "echo: list"
        in (services.layout.session_dir(session.session_id) / "console.log").read_text(),
        timeout=5,
    )


def test_graceful_stop_records_stopped_status(supervised):
    services, session = supervised
    stopped = services.servers.stop(session.session_id, timeout=10)
    assert stopped.process_status == ProcessStatus.STOPPED.value
    assert stopped.exit_code == 0
    report = services.runtime_report(session.session_id)
    assert report["session_id"] == session.session_id
    assert report["log_scan"]["server_ready"] is True
    # A requested stop is not an incident.
    assert services.incidents.list(session_id=session.session_id) == []


def test_crash_is_classified_and_creates_incident(supervised):
    services, session = supervised
    services.servers.send_command(session.session_id, "crash")
    assert _wait_for(
        lambda: services.servers.status(session.session_id)["alive"] is False, timeout=10
    )
    assert _wait_for(
        lambda: services.runtime_status(session.session_id)["process_status"] == "CRASHED",
        timeout=10,
    )
    status = services.runtime_status(session.session_id)
    assert status["process_status"] == ProcessStatus.CRASHED.value
    assert status["exit_code"] == 3

    incidents = services.incidents.list(session_id=session.session_id)
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.incident_type == IncidentType.PROCESS_CRASH.value
    assert incident.error_code in {"BAT-RUNTIME-001", "BAT-SCRIPT-001"}
    assert incident.session_id == session.session_id
    assert incident.evidence_files
    assert incident.possible_causes  # script signature matched
    assert incident.confidence > 0.3

    errors_log = services.layout.session_dir(session.session_id) / "errors.log"
    assert "ReferenceError" in errors_log.read_text()
    report = services.runtime_report(session.session_id)
    assert report["log_scan"]["script_error_count"] >= 1


def test_stop_after_crash_is_safe(supervised):
    services, session = supervised
    services.servers.send_command(session.session_id, "crash")
    assert _wait_for(
        lambda: services.servers.status(session.session_id)["alive"] is False, timeout=10
    )
    stopped = services.servers.stop(session.session_id, timeout=5)
    assert stopped.process_status == ProcessStatus.CRASHED.value


def test_missing_server_executable_reports_not_tested(settings):
    from bat.config import load_settings

    bad_settings = load_settings(
        env={
            "BAT_WORKSPACE": str(settings.workspace_root),
            "BAT_RUNTIME_ROOT": str(settings.runtime_root),
            "BAT_RUNTIME_ADAPTER": "bds",
            "BAT_BEDROCK_SERVER": "/nonexistent/bedrock_server",
        }
    )
    services = BatServices(bad_settings)
    try:
        assert services.adapter.available() is False
        project = services.create_project(
            name="No Server", project_type="ADDON", target_version="1.21.80"
        )
        project_id = project["project"]["project_id"]
        job = services.run_game_test(project_id)
        services.jobs.wait(job.job_id, timeout=20)
        finished = services.jobs.get(job.job_id)
        assert finished.status == "FAILED"
        assert finished.error_code == "BAT-RUNTIME-003"
        assert finished.result["test_status"] == TestStatus.NOT_TESTED.value
        assert finished.result["verified"] == []
    finally:
        services.shutdown()


def test_runtime_test_pass_is_scoped_and_honest(runtime_services: BatServices, addon_project: str):
    job = runtime_services.run_game_test(addon_project)
    runtime_services.jobs.wait(job.job_id, timeout=60)
    finished = runtime_services.jobs.get(job.job_id)
    assert finished.status == "COMPLETED", finished.message
    result = finished.result
    assert result["test_status"] == TestStatus.PASS.value
    assert result["scope"] == "SERVER_SIDE"
    assert result["ready"] is True
    assert result["verified"]
    assert any("Client-side" in note for note in result["not_verified"])
    assert any("GameTest" in note for note in result["not_verified"])

    session_id = result["session_id"]
    logs = runtime_services.runtime_logs(session_id)
    assert any("Server started" in line for line in logs["lines"])
    report = runtime_services.runtime_report(session_id)
    assert report["log_scan"]["server_ready"] is True


def test_runtime_test_crash_marks_job_crashed(runtime_services: BatServices, addon_project: str):
    job = runtime_services.run_game_test(addon_project, command="crash")
    runtime_services.jobs.wait(job.job_id, timeout=60)
    finished = runtime_services.jobs.get(job.job_id)
    assert finished.status == "CRASHED"
    assert finished.error_code == "BAT-RUNTIME-001"
    assert finished.result["test_status"] == TestStatus.FAIL.value
    incidents = runtime_services.incidents.list(project_id=addon_project)
    assert incidents
    assert incidents[0].incident_type in {
        IncidentType.PROCESS_CRASH.value,
        IncidentType.SCRIPT_ERROR.value,
    }


SILENT_SERVER_SCRIPT = '''#!/usr/bin/env python3
import sys, time

print("Server started.", flush=True)
for _line in sys.stdin:
    pass
while True:
    time.sleep(1)
'''


def test_unresponsive_server_is_not_treated_as_a_crash(tmp_path):
    executable = tmp_path / "silent_server"
    executable.write_text(SILENT_SERVER_SCRIPT, encoding="utf-8")
    executable.chmod(0o755)

    silent_settings = load_settings(
        env={
            "BAT_WORKSPACE": str(tmp_path / "data"),
            "BAT_RUNTIME_ROOT": str(tmp_path / "runtime"),
            "BAT_LOG_ROOT": str(tmp_path / "data" / "logs"),
            "BAT_RUNTIME_ADAPTER": "bds",
            "BAT_BEDROCK_SERVER": str(executable),
            "BAT_HEARTBEAT_INTERVAL": "0.2",
            "BAT_UNRESPONSIVE_SECONDS": "1.0",
            "BAT_SERVER_START_TIMEOUT": "10",
        }
    )
    services = BatServices(silent_settings)
    try:
        environment = services.environments.create(runtime_type=RuntimeType.BDS)
        environment_dir = services.environments.dir(environment.environment_id)
        world = environment_dir / "worlds" / "w"
        world.mkdir(parents=True)
        (world / "levelname.txt").write_text("Silent\n")
        session = RuntimeSession(
            environment_id=environment.environment_id,
            project_id=None,
            runtime_type=RuntimeType.BDS,
        )
        services.servers.start(
            session, environment_dir=Path(environment.path), world_name="w", start_timeout=15
        )
        assert _wait_for(
            lambda: bool(services.incidents.list(session_id=session.session_id)),
            timeout=10,
        )
        incident = services.incidents.list(session_id=session.session_id)[0]
        assert incident.incident_type == IncidentType.UNRESPONSIVE.value
        assert incident.severity == "WARNING"
        # The process is alive and was not recorded as a crash.
        status = services.servers.status(session.session_id)
        assert status["alive"] is True
        assert status["process_status"] != ProcessStatus.CRASHED.value
        services.servers.stop(session.session_id, timeout=5)
    finally:
        services.shutdown()


def test_environment_install_requires_matching_project_type(runtime_services, world_project):
    environment = runtime_services.environments.create(project_id=world_project)
    with pytest.raises(BatError) as exc:
        runtime_services.environments.install_packs(environment.environment_id, world_project)
    assert exc.value.code == "BAT-PROJECT-003"


def test_destroy_environment_retains_sessions_and_incidents(runtime_services, addon_project):
    environment = runtime_services.environments.create(project_id=addon_project)
    runtime_services.environments.install_packs(environment.environment_id, addon_project)
    session = RuntimeSession(
        environment_id=environment.environment_id,
        project_id=addon_project,
        runtime_type=RuntimeType.BDS,
    )
    runtime_services.db.save_session(session)
    incident = runtime_services.incidents.create(
        incident_type=IncidentType.ENVIRONMENT_FAILURE,
        summary="test incident",
        project_id=addon_project,
        session_id=session.session_id,
    )
    result = runtime_services.environments.destroy(environment.environment_id)
    assert result["removed"] is True
    assert not Path(environment.path).exists()
    assert runtime_services.db.get_session(session.session_id) is not None
    evidence_dir = runtime_services.layout.incident_dir(incident.incident_id) / "evidence"
    assert evidence_dir.exists()
    assert any("incident" in note for note in result["retained"])


def test_environment_paths_are_isolated(runtime_services):
    environment = runtime_services.environments.create()
    directory = runtime_services.environments.dir(environment.environment_id)
    assert directory.parent == runtime_services.layout.environments_root
    for sub in ("config", "server", "worlds", "behavior_packs", "resource_packs", "scripts"):
        assert (directory / sub).is_dir()
    with pytest.raises(BatError):
        runtime_services.environments.get("env_does_not_exist")
