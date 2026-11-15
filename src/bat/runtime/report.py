"""Runtime test report shape.

The report separates what BAT actually verified from what it could not verify,
so a caller can never mistake "server started" for "add-on works in game".
"""

from __future__ import annotations

from typing import Any

from ..core.models import ProcessStatus, RuntimeSession, TestStatus

SERVER_SIDE_VERIFIED = (
    "The Bedrock server process started and reported readiness.",
    "Installed packs were present in the world's pack binding files.",
    "Console output was captured and scanned for pack/script errors.",
)


def build_runtime_report(
    *,
    session: RuntimeSession,
    environment_id: str,
    log_scan: dict[str, Any],
    incidents: list[str],
    test_status: TestStatus,
    evidence: list[str],
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    not_verified = [
        "Client-side rendering, textures, UI and attachables are not exercised by a server.",
        "Gameplay behaviour, balance and player experience are not asserted.",
        "GameTest execution is NOT_TESTED unless the operator's server build supports it and a "
        "test harness was run explicitly.",
        "Mobile/console import flows are not tested.",
    ]
    notes = list(extra_notes or [])
    if session.process_status == ProcessStatus.CRASHED:
        notes.append("The runtime process crashed; the test is a failure, not a timeout.")
    return {
        "test_status": test_status.value,
        "scope": "SERVER_SIDE",
        "session_id": session.session_id,
        "environment_id": environment_id,
        "project_id": session.project_id,
        "job_id": session.job_id,
        "process_status": str(session.process_status),
        "exit_code": session.exit_code,
        "ready": session.ready,
        "log_scan": log_scan,
        "incidents": incidents,
        "verified": list(SERVER_SIDE_VERIFIED),
        "not_verified": not_verified,
        "evidence": evidence,
        "notes": notes,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
    }
