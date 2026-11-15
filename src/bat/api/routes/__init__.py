"""API route modules."""

from . import artifacts, builds, health, incidents, jobs, projects, runtime, validation

ROUTERS = (
    health.router,
    projects.router,
    validation.router,
    builds.router,
    artifacts.router,
    runtime.router,
    jobs.router,
    incidents.router,
)

__all__ = ["ROUTERS"]
