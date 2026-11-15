"""Supervise Minecraft server processes: lifecycle, logs, heartbeats, exits.

Design decisions that matter for correctness:

* stdout/stderr are streamed to disk line by line, so logs survive an abrupt
  process or BAT termination (no buffered data is lost at exit).
* A process that dies is classified as ``CRASHED`` / ``EXITED`` and recorded in
  an incident; it is never downgraded to a timeout.
* ``EXITED`` with code 0 when no stop was requested is still *unexpected*: BAT
  reports it as such rather than assuming success.
* Killing the MCP request must not kill the server; the server is owned by the
  session, and stopping is an explicit operation.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..core.errors import make_error
from ..core.models import (
    Incident,
    IncidentType,
    ProcessStatus,
    RuntimeSession,
    Severity,
    utcnow,
)
from ..storage.workspace import RuntimeLayout
from .adapter import RuntimeAdapter, ServerSpec
from .log_parser import classify, is_ready_line, scan_lines

IncidentRecorder = Callable[..., Incident]


@dataclass
class RunningServer:
    session: RuntimeSession
    process: subprocess.Popen[str]
    session_dir: Path
    server_dir: Path
    adapter: RuntimeAdapter
    port: int | None = None
    ready: bool = False
    ready_event: threading.Event = field(default_factory=threading.Event)
    expected_stop: bool = False
    last_output_at: float = field(default_factory=time.monotonic)
    started_monotonic: float = field(default_factory=time.monotonic)
    line_count: int = 0
    unresponsive_reported: bool = False
    exit_recorded: bool = False
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=4000))
    lock: threading.RLock = field(default_factory=threading.RLock)
    reader: threading.Thread | None = None
    monitor: threading.Thread | None = None
    waiter: threading.Thread | None = None


class ServerManager:
    def __init__(
        self,
        layout: RuntimeLayout,
        settings: Settings,
        db: Any,
        adapter: RuntimeAdapter,
        incident_recorder: IncidentRecorder | None = None,
    ) -> None:
        self.layout = layout
        self.settings = settings
        self.db = db
        self.adapter = adapter
        self.incident_recorder = incident_recorder
        self._servers: dict[str, RunningServer] = {}
        self._lock = threading.RLock()

    # -- helpers -----------------------------------------------------------
    def _session_dir(self, session: RuntimeSession) -> Path:
        directory = self.layout.session_dir(session.session_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _write_session_files(self, session: RuntimeSession, session_dir: Path) -> None:
        """Persist a session record before a process exists (start phase)."""
        (session_dir / "session.json").write_text(
            session.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        self.db.save_session(session)

    def _persist(self, running: RunningServer) -> None:
        session = running.session
        with running.lock:
            session.heartbeat = {
                "pid": running.process.pid,
                "alive": running.process.poll() is None,
                "ready": running.ready,
                "lines_captured": running.line_count,
                "last_output_at": _iso(running.last_output_at),
                "uptime_seconds": round(time.monotonic() - running.started_monotonic, 1),
                "port": running.port,
            }
            directory = running.session_dir
            (directory / "session.json").write_text(
                session.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            (directory / "heartbeat.json").write_text(
                json.dumps(
                    {
                        "session_id": session.session_id,
                        "environment_id": session.environment_id,
                        "job_id": session.job_id,
                        "project_id": session.project_id,
                        "process_status": session.process_status,
                        "heartbeat_at": utcnow(),
                        **session.heartbeat,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        self.db.save_session(session)

    # -- start -------------------------------------------------------------
    def start(
        self,
        session: RuntimeSession,
        *,
        environment_dir: Path,
        world_name: str | None = None,
        extra_args: list[str] | None = None,
        start_timeout: float | None = None,
    ) -> RuntimeSession:
        if not self.adapter.available():
            session.process_status = ProcessStatus.FAILED
            session.notes.append(self.adapter.unavailable_reason())
            self.db.save_session(session)
            raise make_error("BAT-RUNTIME-003", self.adapter.unavailable_reason())

        server_dir = environment_dir / "server"
        server_dir.mkdir(parents=True, exist_ok=True)
        worlds_dir = environment_dir / "worlds"
        world_name = world_name or session.heartbeat.get("world_name") or _first_world(worlds_dir)
        if world_name and not (worlds_dir / world_name).exists():
            raise make_error(
                "BAT-RUNTIME-006",
                f"World {world_name!r} is not installed in environment {session.environment_id}.",
            )
        port = _pick_udp_port(19132)
        _prepare_server_dir(server_dir, world_name, port)

        spec = ServerSpec(
            server_dir=server_dir,
            world_dir=(worlds_dir / world_name) if world_name else worlds_dir,
            world_name=world_name or "Bedrock level",
            extra_args=list(extra_args or []),
        )
        command = self.adapter.build_command(spec)
        session_dir = self._session_dir(session)
        for name in ("console.log", "runtime.log", "errors.log"):
            (session_dir / name).touch(exist_ok=True)
        session.logs = {
            "console": str(session_dir / "console.log"),
            "runtime": str(session_dir / "runtime.log"),
            "errors": str(session_dir / "errors.log"),
        }
        session.runtime_type = self.adapter.runtime_type
        session.process_status = ProcessStatus.STARTING
        session.heartbeat = {"world_name": world_name, "command": command, "port": port}
        self._write_session_files(session, session_dir)

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(server_dir),
            "LANG": "C.UTF-8",
            "BAT_ENVIRONMENT_ID": session.environment_id,
        }
        try:
            process = subprocess.Popen(  # noqa: S603 - explicit operator-supplied executable
                command,
                cwd=str(server_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=(os.name != "nt"),
            )
        except OSError as exc:
            session.process_status = ProcessStatus.FAILED
            session.notes.append(f"Process could not be started: {exc}")
            self._write_session_files(session, session_dir)
            raise make_error(
                "BAT-RUNTIME-006",
                f"Runtime process could not be started: {exc}",
                details={"command": command[0], "error": str(exc)},
            ) from exc

        running = RunningServer(
            session=session,
            process=process,
            session_dir=session_dir,
            server_dir=server_dir,
            adapter=self.adapter,
            port=port,
        )
        with self._lock:
            self._servers[session.session_id] = running

        running.reader = threading.Thread(
            target=self._read_output, args=(running,), name=f"bat-log-{session.session_id}", daemon=True
        )
        running.monitor = threading.Thread(
            target=self._monitor, args=(running,), name=f"bat-mon-{session.session_id}", daemon=True
        )
        running.waiter = threading.Thread(
            target=self._wait_exit, args=(running,), name=f"bat-wait-{session.session_id}", daemon=True
        )
        running.reader.start()
        running.monitor.start()
        running.waiter.start()

        timeout = start_timeout if start_timeout is not None else self.settings.server_start_timeout
        if not running.ready_event.wait(timeout=timeout):
            # Not ready in time: report a start timeout, not a crash.
            if process.poll() is None:
                session.notes.append(
                    f"Server did not report readiness within {timeout:g}s; stopping it."
                )
                self.stop(session.session_id, timeout=10, reason="start_timeout")
                raise make_error(
                    "BAT-RUNTIME-002",
                    f"Server did not become ready within {timeout:g}s.",
                    details={"session_id": session.session_id},
                )
            raise make_error(
                "BAT-RUNTIME-001",
                "Process exited before the server reported readiness.",
                details={
                    "session_id": session.session_id,
                    "exit_code": process.poll(),
                },
            )
        session.process_status = ProcessStatus.RUNNING
        self._persist(running)
        return session

    # -- background workers ------------------------------------------------
    def _read_output(self, running: RunningServer) -> None:
        console_path = running.session_dir / "console.log"
        runtime_path = running.session_dir / "runtime.log"
        errors_path = running.session_dir / "errors.log"
        try:
            with console_path.open("a", encoding="utf-8") as console, runtime_path.open(
                "a", encoding="utf-8"
            ) as runtime, errors_path.open("a", encoding="utf-8") as errors:
                assert running.process.stdout is not None
                for raw in running.process.stdout:
                    line = raw.rstrip("\n")
                    if not line:
                        continue
                    with running.lock:
                        running.last_output_at = time.monotonic()
                        running.line_count += 1
                        running.lines.append(line)
                    console.write(line + "\n")
                    console.flush()
                    runtime.write(
                        json.dumps(
                            {
                                "timestamp": utcnow(),
                                "level": classify(line),
                                "source": "minecraft_runtime",
                                "event": "console_line",
                                "session_id": running.session.session_id,
                                "message": line,
                            }
                        )
                        + "\n"
                    )
                    runtime.flush()
                    if classify(line) == "ERROR":
                        errors.write(line + "\n")
                        errors.flush()
                    if is_ready_line(line) and not running.ready:
                        running.ready = True
                        running.session.ready = True
                        running.session.process_status = ProcessStatus.RUNNING
                        running.ready_event.set()
                        self._persist(running)
        except Exception as exc:  # noqa: BLE001 - log capture must never crash the supervisor
            with running.lock:
                running.session.notes.append(f"Log reader stopped: {exc}")
        finally:
            if not running.ready_event.is_set():
                running.ready_event.set()

    def _monitor(self, running: RunningServer) -> None:
        interval = max(0.2, float(self.settings.heartbeat_interval))
        idle_threshold = max(1.0, float(self.settings.unresponsive_seconds))
        while True:
            time.sleep(interval)
            if running.process.poll() is not None:
                return
            try:
                self._persist(running)
            except Exception:  # noqa: BLE001 - heartbeat failures must not kill supervision
                continue
            with running.lock:
                idle = time.monotonic() - running.last_output_at
                already = running.unresponsive_reported
            if running.ready and idle > idle_threshold and not already:
                running.unresponsive_reported = True
                running.session.notes.append(
                    f"No console output for {idle:.0f}s while the process is alive: the server may "
                    "be unresponsive (this is not treated as a crash)."
                )
                self._record_incident(
                    running,
                    IncidentType.UNRESPONSIVE,
                    f"Runtime produced no output for {idle:.0f}s while the process was alive.",
                    {"idle_seconds": round(idle, 1)},
                    severity=Severity.WARNING,
                )

    def _wait_exit(self, running: RunningServer) -> None:
        exit_code = running.process.wait()
        self._finalize_exit(running, exit_code)

    def _finalize_exit(self, running: RunningServer, exit_code: int | None) -> None:
        with running.lock:
            if running.exit_recorded:
                return
            running.exit_recorded = True
            session = running.session
            session.exit_code = exit_code
            session.ended_at = utcnow()
            expected = running.expected_stop
            if expected:
                session.process_status = ProcessStatus.STOPPED
            elif exit_code is None:
                session.process_status = ProcessStatus.EXITED
            elif exit_code != 0:
                session.process_status = ProcessStatus.CRASHED
            else:
                session.process_status = ProcessStatus.EXITED

        scan = self._scan_session(running)
        session.notes.append(
            f"Process finished with exit code {exit_code} "
            f"({'requested stop' if expected else 'not requested by BAT'})."
        )
        self._persist(running)

        if not expected:
            incident_type = (
                IncidentType.PROCESS_CRASH if (exit_code or 0) != 0 else IncidentType.UNEXPECTED_EXIT
            )
            self._record_incident(
                running,
                incident_type,
                f"Runtime process exited unexpectedly with code {exit_code}.",
                {
                    "exit_code": exit_code,
                    "lines_captured": scan.total_lines,
                    "error_lines": scan.error_lines[:10],
                    "script_errors": scan.script_errors[:10],
                    "pack_errors": scan.pack_errors[:10],
                    "oom_detected": bool(scan.oom_lines),
                },
                severity=Severity.CRITICAL,
            )
        self._write_report(running, scan.as_dict())

    def _record_incident(
        self,
        running: RunningServer,
        incident_type: IncidentType,
        summary: str,
        details: dict[str, Any],
        *,
        severity: Severity,
    ) -> None:
        if self.incident_recorder is None:
            running.session.notes.append(f"Incident not recorded (no recorder): {summary}")
            return
        try:
            self.incident_recorder(
                running.session, incident_type, summary, details, severity=severity
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics must not break supervision
            running.session.notes.append(f"Incident recording failed: {exc}")

    def _scan_session(self, running: RunningServer):
        console = running.session_dir / "console.log"
        lines: list[str] = []
        if console.exists():
            lines = console.read_text(encoding="utf-8", errors="replace").splitlines()[-8000:]
        return scan_lines(lines)

    def _write_report(self, running: RunningServer, scan: dict[str, Any]) -> None:
        report = {
            "session_id": running.session.session_id,
            "environment_id": running.session.environment_id,
            "project_id": running.session.project_id,
            "job_id": running.session.job_id,
            "runtime_type": str(running.session.runtime_type),
            "started_at": running.session.started_at,
            "ended_at": running.session.ended_at,
            "process_status": str(running.session.process_status),
            "exit_code": running.session.exit_code,
            "ready": running.ready,
            "log_scan": scan,
            "notes": running.session.notes,
        }
        (running.session_dir / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

    # -- operations --------------------------------------------------------
    def wait_ready(self, session_id: str, timeout: float) -> bool:
        running = self._running(session_id)
        return running.ready_event.wait(timeout=timeout) and running.ready

    def send_command(self, session_id: str, command: str) -> dict[str, Any]:
        running = self._running(session_id)
        if running.process.poll() is not None:
            raise make_error(
                "BAT-RUNTIME-006",
                "The runtime process is no longer running; commands cannot be sent.",
                http_status=409,
            )
        if not self.adapter.capabilities.console_commands:
            raise make_error(
                "BAT-RUNTIME-007",
                "The active runtime adapter does not support console commands.",
            )
        assert running.process.stdin is not None
        try:
            running.process.stdin.write(command.rstrip("\n") + "\n")
            running.process.stdin.flush()
        except OSError as exc:
            raise make_error(
                "BAT-RUNTIME-006", f"Console command could not be delivered: {exc}"
            ) from exc
        running.session.command_log.append(command.rstrip("\n"))
        self._persist(running)
        return {"session_id": session_id, "command": command.rstrip("\n"), "delivered": True}

    def stop(
        self, session_id: str, *, timeout: float = 30.0, reason: str = "requested"
    ) -> RuntimeSession:
        running = self._running(session_id)
        session = running.session
        if running.process.poll() is None:
            # Only a live process can be "stopping"; an already-crashed session keeps
            # its recorded status so a late stop cannot disguise a crash as a clean stop.
            running.expected_stop = True
            session.process_status = ProcessStatus.STOPPING
        session.notes.append(f"Stop requested ({reason}).")
        self._persist(running)
        if running.process.poll() is None:
            try:
                assert running.process.stdin is not None
                running.process.stdin.write("stop\n")
                running.process.stdin.flush()
            except OSError:
                pass
        try:
            running.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            running.process.terminate()
            try:
                running.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                running.process.kill()
                running.process.wait(timeout=10)
            session.notes.append("Process did not stop gracefully and was terminated.")
        if running.waiter is not None:
            running.waiter.join(timeout=5)
        if not running.exit_recorded:
            self._finalize_exit(running, running.process.poll())
        return session

    def status(self, session_id: str) -> dict[str, Any]:
        running = self._servers.get(session_id)
        if running is not None:
            alive = running.process.poll() is None
            return {
                "session_id": session_id,
                "process_status": str(running.session.process_status),
                "alive": alive,
                "pid": running.process.pid,
                "ready": running.ready,
                "exit_code": running.process.poll(),
                "uptime_seconds": round(time.monotonic() - running.started_monotonic, 1),
                "lines_captured": running.line_count,
                "last_output_seconds_ago": round(time.monotonic() - running.last_output_at, 1),
                "port": running.port,
                "environment_id": running.session.environment_id,
                "job_id": running.session.job_id,
                "project_id": running.session.project_id,
            }
        session = self.db.get_session(session_id)
        if session is None:
            raise make_error(
                "BAT-NOTFOUND-005", f"Session {session_id} not found.", http_status=404
            )
        return {
            "session_id": session_id,
            "process_status": str(session.process_status),
            "alive": False,
            "pid": session.heartbeat.get("pid"),
            "ready": session.ready,
            "exit_code": session.exit_code,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "environment_id": session.environment_id,
            "job_id": session.job_id,
            "project_id": session.project_id,
            "notes": session.notes,
        }

    def logs(self, session_id: str, *, kind: str = "console", tail: int = 200) -> dict[str, Any]:
        if kind not in {"console", "runtime", "errors"}:
            raise make_error("BAT-INPUT-001", "log kind must be console, runtime or errors.")
        directory = self.layout.session_dir(session_id)
        path = directory / f"{kind}.log"
        if not path.exists():
            session = self.db.get_session(session_id)
            if session is None:
                raise make_error(
                    "BAT-NOTFOUND-005", f"Session {session_id} not found.", http_status=404
                )
            return {"session_id": session_id, "kind": kind, "lines": [], "path": str(path)}
        tail = max(1, min(int(tail), 5000))
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {
            "session_id": session_id,
            "kind": kind,
            "path": str(path),
            "total_lines": len(lines),
            "lines": lines[-tail:],
        }

    def heartbeat(self, session_id: str) -> dict[str, Any]:
        running = self._servers.get(session_id)
        if running is not None:
            with running.lock:
                return {
                    "session_id": session_id,
                    "status": running.session.process_status,
                    "alive": running.process.poll() is None,
                    "ready": running.ready,
                    "pid": running.process.pid,
                    "uptime_seconds": round(time.monotonic() - running.started_monotonic, 1),
                    "lines_captured": running.line_count,
                    "last_output_seconds_ago": round(
                        time.monotonic() - running.last_output_at, 1
                    ),
                }
        path = self.layout.session_dir(session_id) / "heartbeat.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        session = self.db.get_session(session_id)
        if session is None:
            raise make_error(
                "BAT-NOTFOUND-005", f"Session {session_id} not found.", http_status=404
            )
        return {"session_id": session_id, "status": str(session.process_status), "alive": False}

    def session_report(self, session_id: str) -> dict[str, Any]:
        path = self.layout.session_dir(session_id) / "report.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if self.db.get_session(session_id) is None:
            raise make_error(
                "BAT-NOTFOUND-005", f"Session {session_id} not found.", http_status=404
            )
        running = self._servers.get(session_id)
        scan = self._scan_session(running) if running else scan_lines([])
        return {
            "session_id": session_id,
            "process_status": self.status(session_id)["process_status"],
            "log_scan": scan.as_dict(),
            "notes": ["Report generated on demand; the session is still active."],
        }

    def get_session(self, session_id: str) -> RuntimeSession:
        session = self.db.get_session(session_id)
        if session is None:
            raise make_error(
                "BAT-NOTFOUND-005", f"Session {session_id} not found.", http_status=404
            )
        return session

    def list_sessions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self.db.list_sessions(project_id)]

    def running_sessions(self) -> list[str]:
        return [sid for sid, run in self._servers.items() if run.process.poll() is None]

    def shutdown(self) -> None:
        for session_id in self.running_sessions():
            try:
                self.stop(session_id, timeout=10, reason="bat_shutdown")
            except Exception:  # noqa: BLE001 - best effort during shutdown
                continue

    # -- internals ---------------------------------------------------------
    def _running(self, session_id: str) -> RunningServer:
        running = self._servers.get(session_id)
        if running is None:
            session = self.db.get_session(session_id)
            if session is None:
                raise make_error(
                    "BAT-NOTFOUND-005", f"Session {session_id} not found.", http_status=404
                )
            raise make_error(
                "BAT-RUNTIME-006",
                f"Session {session_id} is not owned by this BAT process; it cannot be controlled.",
                http_status=409,
            )
        return running


def _prepare_server_dir(server_dir: Path, world_name: str | None, port: int) -> None:
    properties = server_dir / "server.properties"
    if properties.exists():
        return
    lines = [
        "server-name=BAT Runtime",
        "gamemode=creative",
        "difficulty=easy",
        "allow-cheats=true",
        "online-mode=false",
        "allow-list=false",
        "enable-lan-visibility=false",
        "player-idle-timeout=0",
        "max-players=5",
        "view-distance=8",
        "tick-distance=4",
        "texturepack-required=false",
        "server-portv6=0",
        f"server-port={port}",
        f"level-name={world_name or 'Bedrock level'}",
    ]
    properties.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_world(worlds_dir: Path) -> str | None:
    if not worlds_dir.exists():
        return None
    worlds = sorted(p for p in worlds_dir.iterdir() if p.is_dir())
    return worlds[0].name if worlds else None


def _pick_udp_port(start: int) -> int:
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind(("0.0.0.0", port))
            except OSError:
                continue
            return port
    raise make_error("BAT-RUNTIME-006", "No free UDP port available for the runtime server.")


def _iso(monotonic_value: float) -> str:
    return utcnow()
