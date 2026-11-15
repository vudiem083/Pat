"""Background job system: persistence, workers, cancellation, reports."""

from .manager import JobManager
from .state import JobAborted

__all__ = ["JobManager", "JobAborted"]
