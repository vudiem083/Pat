"""Job heartbeats.

A heartbeat file is written while a job runs so a later BAT process can tell a
job that died with BAT from one that is genuinely still working.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ..core.models import utcnow


class JobHeartbeat:
    def __init__(self, path: Path, *, interval: float = 5.0, metadata: dict | None = None) -> None:
        self.path = path
        self.interval = max(0.5, interval)
        self.metadata = metadata or {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.beats = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, state: str) -> None:
        payload = {
            "timestamp": utcnow(),
            "state": state,
            "beats": self.beats,
            "pid": threading.get_native_id(),
            **self.metadata,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def start(self) -> None:
        self._write("STARTED")

        def loop() -> None:
            while not self._stop.wait(self.interval):
                self.beats += 1
                self._write("RUNNING")

        self._thread = threading.Thread(target=loop, name=f"bat-heartbeat-{self.path.stem}", daemon=True)
        self._thread.start()

    def stop(self, final_state: str = "STOPPED") -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._write(final_state)

    @staticmethod
    def age_seconds(path: Path) -> float | None:
        if not path.exists():
            return None
        return max(0.0, time.time() - path.stat().st_mtime)
