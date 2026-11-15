"""Job housekeeping: orphan recovery and stale heartbeat reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .heartbeat import JobHeartbeat


def stale_heartbeats(log_root: Path, *, max_age_seconds: float = 300.0) -> list[dict[str, Any]]:
    """List job heartbeats that have not been refreshed recently.

    This is diagnostic information only: recovering orphans is driven by the
    database state, not by heartbeat files.
    """
    results: list[dict[str, Any]] = []
    if not log_root.exists():
        return results
    for path in sorted(log_root.glob("*.heartbeat.json")):
        age = JobHeartbeat.age_seconds(path)
        if age is None:
            continue
        if age > max_age_seconds:
            results.append(
                {
                    "job_id": path.stem.replace(".heartbeat", ""),
                    "heartbeat_age_seconds": round(age, 1),
                    "stale": True,
                }
            )
    return results


def recover(job_manager: Any) -> dict[str, Any]:
    recovered = job_manager.recover_orphans()
    return {
        "recovered_jobs": recovered,
        "count": len(recovered),
        "note": "Jobs left non-terminal by a previous BAT process are marked CRASHED (BAT-JOB-002).",
    }
