"""MCP tool registration modules."""

from . import addons, builds, diagnostics, jobs, projects, runtime, validation, worlds

MODULES = (projects, addons, worlds, validation, builds, runtime, jobs, diagnostics)

__all__ = ["MODULES"]
