"""Project MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def create_project(
        name: str,
        project_type: Literal["ADDON", "WORLD", "COMBINED"] = "ADDON",
        target_version: str = "1.21.80",
        description: str | None = None,
        world_name: str | None = None,
    ) -> dict:
        """Create a Minecraft Bedrock project (ADDON, WORLD or COMBINED).

        Returns the project record, its packs and suggested next steps. Target
        version must be inside BAT's supported range (1.19.0–1.21.80).
        """
        return services.create_project(
            name=name,
            project_type=project_type,
            target_version=target_version,
            description=description,
            world_name=world_name,
        )

    @mcp.tool()
    @tool
    def get_project(project_id: str) -> dict:
        """Get a project record together with its behavior/resource packs."""
        project = services.projects.get(project_id)
        return {"project": project.model_dump(), "packs": services.projects.list_packs(project_id)}

    @mcp.tool()
    @tool
    def list_projects(limit: int = 50, offset: int = 0) -> dict:
        """List projects, newest first."""
        projects = services.projects.list(limit=limit, offset=offset)
        return {
            "items": [p.model_dump() for p in projects],
            "total": services.db.count_projects(),
            "limit": limit,
            "offset": offset,
        }

    @mcp.tool()
    @tool
    def delete_project(project_id: str, purge_artifacts: bool = False) -> dict:
        """Delete a project's files and record.

        Incidents, session logs and (by default) artifacts are retained so
        diagnostic evidence is never destroyed silently.
        """
        return services.projects.delete(project_id, purge_artifacts=purge_artifacts)

    @mcp.tool()
    @tool
    def get_project_tree(project_id: str) -> dict:
        """Return the project's file tree (directories and files with sizes)."""
        return services.project_tree(project_id)

    @mcp.tool()
    @tool
    def read_project_file(project_id: str, path: str) -> dict:
        """Read a UTF-8 project file. Paths are relative to the project files root."""
        return services.projects.read_file(project_id, path)

    @mcp.tool()
    @tool
    def write_project_file(
        project_id: str, path: str, content: str, create_backup: bool = True
    ) -> dict:
        """Write a UTF-8 project file atomically, backing up any previous version."""
        return services.projects.write_file(
            project_id, path, content, create_backup=create_backup
        )

    @mcp.tool()
    @tool
    def get_compatibility(version: str) -> dict:
        """Version-aware feature matrix for a Bedrock version (1.19.0–1.21.80).

        Statuses are SUPPORTED / UNSUPPORTED / UNKNOWN / NOT_TESTED. UNKNOWN means
        BAT has no evidence; it is not a guess in either direction.
        """
        return services.get_compatibility(version)
