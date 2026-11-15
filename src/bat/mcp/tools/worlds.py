"""World MCP tools."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from ...core.errors import make_error
from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def create_world_project(
        name: str,
        target_version: str = "1.21.80",
        include_addon: bool = False,
        world_name: str | None = None,
    ) -> dict:
        """Create a WORLD project, or a COMBINED project when include_addon is true."""
        return services.create_project(
            name=name,
            project_type="COMBINED" if include_addon else "WORLD",
            target_version=target_version,
            world_name=world_name,
        )

    @mcp.tool()
    @tool
    def inspect_world(project_id: str) -> dict:
        """Inspect a project world: level.dat metadata, pack bindings and LevelDB presence."""
        return services.inspect_world(project_id)

    @mcp.tool()
    @tool
    def get_world_chunks(project_id: str) -> dict:
        """Report available chunk/LevelDB data.

        BAT does not implement a LevelDB chunk reader; this tool reports honestly
        whether chunk data exists instead of inventing a chunk list.
        """
        return services.world.chunks(project_id)

    @mcp.tool()
    @tool
    def create_structure(
        project_id: str,
        name: str,
        size_x: int = 4,
        size_y: int = 4,
        size_z: int = 4,
        block: str = "minecraft:stone",
        origin_x: int = 0,
        origin_y: int = 0,
        origin_z: int = 0,
    ) -> dict:
        """Create a .mcstructure file (little-endian NBT, verified by re-decoding)."""
        return services.create_structure(
            project_id,
            name=name,
            size=[size_x, size_y, size_z],
            block=block,
            origin=[origin_x, origin_y, origin_z],
        )

    @mcp.tool()
    @tool
    def import_structure(project_id: str, name: str, content_base64: str) -> dict:
        """Import a .mcstructure from base64 content, validating its NBT structure."""
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise make_error("BAT-INPUT-001", f"content_base64 is not valid base64: {exc}") from exc
        if len(data) > services.settings.max_upload_bytes:
            raise make_error("BAT-PATH-002", "Structure upload exceeds the configured size limit.")
        return services.import_structure(project_id, name, data)

    @mcp.tool()
    @tool
    def export_structure(project_id: str, name: str) -> dict:
        """Export a structure from the world into the artifact workspace."""
        return services.export_structure(project_id, name)

    @mcp.tool()
    @tool
    def modify_world_metadata(
        project_id: str,
        level_name: str | None = None,
        game_mode: str | None = None,
        difficulty: str | None = None,
        seed: int | None = None,
        spawn_x: int | None = None,
        spawn_y: int | None = None,
        spawn_z: int | None = None,
        commands_enabled: bool | None = None,
    ) -> dict:
        """Modify world metadata safely.

        A snapshot is written to runtime/snapshots before the edit and the new
        level.dat is re-read to verify the write.
        """
        spawn = None
        if None not in (spawn_x, spawn_y, spawn_z):
            spawn = [int(spawn_x), int(spawn_y), int(spawn_z)]
        elif any(v is not None for v in (spawn_x, spawn_y, spawn_z)):
            raise make_error("BAT-INPUT-001", "Provide spawn_x, spawn_y and spawn_z together.")
        return services.modify_world_metadata(
            project_id,
            level_name=level_name,
            game_mode=game_mode,
            difficulty=difficulty,
            seed=seed,
            spawn=spawn,
            commands_enabled=commands_enabled,
        )

    @mcp.tool()
    @tool
    def export_mcworld(project_id: str) -> dict:
        """Build a .mcworld artifact for a WORLD or COMBINED project."""
        return services.build_project(project_id, artifact_type="MCWORLD")
