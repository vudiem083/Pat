"""Build and artifact MCP tools."""

from __future__ import annotations

from typing import Any

from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def build_project(project_id: str, artifact_type: str | None = None, strict: bool = False) -> dict:
        """Build artifacts for a project.

        ADDON -> .mcaddon, WORLD -> .mcworld, COMBINED -> both. Pass
        artifact_type to build a specific type (MCPACK, MCADDON, MCWORLD).
        """
        return services.build_project(
            project_id, artifact_type=artifact_type, strict=strict
        )

    @mcp.tool()
    @tool
    def build_mcaddon(project_id: str) -> dict:
        """Build a .mcaddon containing the project's behavior and resource packs."""
        return services.build_project(project_id, artifact_type="MCADDON")

    @mcp.tool()
    @tool
    def build_mcpack(project_id: str) -> dict:
        """Build .mcpack artifacts (one per pack kind)."""
        return services.build_project(project_id, artifact_type="MCPACK")

    @mcp.tool()
    @tool
    def build_mcworld(project_id: str) -> dict:
        """Build a .mcworld from the project's world."""
        return services.build_project(project_id, artifact_type="MCWORLD")

    @mcp.tool()
    @tool
    def inspect_artifact(artifact_id: str) -> dict:
        """Inspect an artifact: entries, manifests, checksum match and problems."""
        return services.builders.inspect_artifact(artifact_id)

    @mcp.tool()
    @tool
    def download_artifact(artifact_id: str) -> dict:
        """Locate an artifact on disk for the caller to read/copy.

        MCP transports cannot stream binary files, so this returns the absolute
        path plus checksum and size. The file is inside BAT's artifact workspace.
        """
        artifact, path = services.builders.artifact_path(artifact_id)
        return {
            "artifact": artifact.model_dump(),
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "checksum_sha256": artifact.checksum,
        }

    @mcp.tool()
    @tool
    def get_build_report(artifact_id: str) -> dict:
        """Read the build report written alongside an artifact."""
        return services.builders.get_build_report(artifact_id)
