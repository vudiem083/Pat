"""Validation MCP tools."""

from __future__ import annotations

from typing import Any

from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def validate_project(project_id: str) -> dict:
        """Run every validator over a project and return a structured report."""
        return services.validator.validate_project(project_id).model_dump()

    @mcp.tool()
    @tool
    def validate_manifest(project_id: str, path: str | None = None) -> dict:
        """Validate pack manifests (a single manifest when path is given)."""
        if path is None:
            return services.validator.validate_project(project_id).model_dump()
        return services.validator.validate_file(project_id, path, kind="manifest").model_dump()

    @mcp.tool()
    @tool
    def validate_entity(project_id: str, path: str) -> dict:
        """Validate one entity document (identifier, components, version availability)."""
        return services.validator.validate_file(project_id, path, kind="entity").model_dump()

    @mcp.tool()
    @tool
    def validate_block(project_id: str, path: str) -> dict:
        """Validate one block document."""
        return services.validator.validate_file(project_id, path, kind="block").model_dump()

    @mcp.tool()
    @tool
    def validate_texture(project_id: str, path: str) -> dict:
        """Validate one texture file (PNG signature and IHDR dimensions)."""
        return services.validator.validate_file(project_id, path, kind="texture").model_dump()

    @mcp.tool()
    @tool
    def validate_animation(project_id: str, path: str) -> dict:
        """Validate one animation or animation controller document."""
        return services.validator.validate_file(project_id, path, kind="animation").model_dump()

    @mcp.tool()
    @tool
    def validate_world(project_id: str) -> dict:
        """Validate world data: level.dat, pack bindings and world name."""
        return services.validator.validate_file(project_id, "world/level.dat", kind="world").model_dump()

    @mcp.tool()
    @tool
    def get_validation_report(project_id: str, report_id: str | None = None) -> dict:
        """Fetch the latest (or a specific) validation report for a project."""
        if report_id:
            return services.validator.get_report(report_id).model_dump()
        return services.validator.latest_report(project_id).model_dump()
