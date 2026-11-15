"""In-process counters for BAT operations.

Deliberately minimal: no external metrics backend is required for a single-node
MVP, but the surface allows a Prometheus exporter to be added later.
"""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any


class Metrics:
    _instance: "Metrics | None" = None

    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._gauges: dict[str, float] = {}
        self._lock = threading.RLock()

    @classmethod
    def instance(cls) -> "Metrics":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"counters": dict(self._counters), "gauges": dict(self._gauges)}
