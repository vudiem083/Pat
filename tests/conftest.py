"""Shared test fixtures.

Every test runs against a temporary workspace and runtime root so no test touches
the repository's real ``data/`` or ``runtime/`` directories.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from bat.config import Settings, load_settings
from bat.services import BatServices

#: A simulated Bedrock server used to test process supervision.
#:
#: This script is NOT Minecraft. It exists to exercise BAT's process management
#: (readiness detection, log capture, heartbeats, console commands, crash
#: classification). Tests that use it are marked ``simulated`` and the suite
#: never claims real Minecraft runtime verification.
FAKE_SERVER = r'''#!/usr/bin/env python3
import sys

print("INFO: Starting Server thread", flush=True)
print("INFO: IPv4 supported, port: 19132", flush=True)
print("Server started.", flush=True)

for line in sys.stdin:
    command = line.strip()
    if command == "stop":
        print("Quit correctly", flush=True)
        sys.exit(0)
    if command == "crash":
        print("ERROR: [Scripting][error] main.js:4 ReferenceError: boom", flush=True)
        sys.exit(3)
    print(f"echo: {command}", flush=True)
'''

SILENT_SERVER = r'''#!/usr/bin/env python3
import sys, time

print("Server started.", flush=True)
for _line in sys.stdin:
    pass
while True:
    time.sleep(1)
'''


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    env = {
        "BAT_WORKSPACE": str(tmp_path / "data"),
        "BAT_RUNTIME_ROOT": str(tmp_path / "runtime"),
        "BAT_LOG_ROOT": str(tmp_path / "data" / "logs"),
        "BAT_RUNTIME_ADAPTER": "none",
        "BAT_HEARTBEAT_INTERVAL": "0.2",
        "BAT_UNRESPONSIVE_SECONDS": "2",
        "BAT_SERVER_START_TIMEOUT": "10",
        "BAT_JOB_WORKERS": "2",
        "BAT_DEFAULT_WAIT_SECONDS": "5",
    }
    settings = load_settings(env=env)
    if overrides:
        settings = settings.with_overrides(**overrides)
    return settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return _settings(tmp_path)


@pytest.fixture()
def services(settings: Settings):
    service_layer = BatServices(settings)
    yield service_layer
    service_layer.shutdown()


@pytest.fixture()
def addon_project(services: BatServices) -> str:
    project = services.create_project(
        name="Test Addon", project_type="ADDON", target_version="1.21.80"
    )
    return project["project"]["project_id"]


@pytest.fixture()
def world_project(services: BatServices) -> str:
    project = services.create_project(
        name="Test World", project_type="WORLD", target_version="1.20.0", world_name="Test World"
    )
    return project["project"]["project_id"]


@pytest.fixture()
def combined_project(services: BatServices) -> str:
    project = services.create_project(
        name="Test Combined", project_type="COMBINED", target_version="1.21.80"
    )
    return project["project"]["project_id"]


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture()
def fake_server(tmp_path: Path) -> Path:
    executable = tmp_path / "fake_bedrock_server"
    return _write_executable(executable, FAKE_SERVER)


@pytest.fixture()
def silent_server(tmp_path: Path) -> Path:
    executable = tmp_path / "silent_bedrock_server"
    return _write_executable(executable, SILENT_SERVER)


@pytest.fixture()
def runtime_services(tmp_path: Path, fake_server: Path):
    """Services wired to a simulated BDS executable."""
    settings = _settings(
        tmp_path,
        runtime_adapter="bds",
        bedrock_server_path=fake_server,
        server_start_timeout=15.0,
        heartbeat_interval=0.2,
        unresponsive_seconds=2.0,
    )
    service_layer = BatServices(settings)
    yield service_layer
    service_layer.shutdown()


@pytest.fixture()
def client(services: BatServices):
    from fastapi.testclient import TestClient

    from bat.api.app import create_app

    with TestClient(create_app(services)) as test_client:
        yield test_client


@pytest.fixture()
def api_key_client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from bat.api.app import create_app

    settings = _settings(tmp_path, api_key="secret-key-for-tests")
    service_layer = BatServices(settings)
    with TestClient(create_app(service_layer)) as test_client:
        yield test_client
    service_layer.shutdown()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "simulated: uses a simulated server process instead of real Minecraft",
    )
    config.addinivalue_line("markers", "slow: test with real waiting")


@pytest.fixture()
def mcp_server(services: BatServices):
    from bat.mcp.server import build_mcp_server

    server, _ = build_mcp_server(services)
    return server


@pytest.fixture()
def env_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAT_RUNTIME_ADAPTER", "none")


def pytest_report_header(config: pytest.Config) -> str:
    return f"BAT test suite (python {sys.version.split()[0]}, cwd {os.getcwd()})"
