"""Add-on generation MCP tools."""

from __future__ import annotations

from typing import Any

from ...services import BatServices
from ._wrap import tool


def register(mcp: Any, services: BatServices) -> None:
    @mcp.tool()
    @tool
    def create_addon(project_id: str) -> dict:
        """Ensure behavior and resource packs (with manifests) exist for a project."""
        return services.generate_content(project_id, "addon", {})

    @mcp.tool()
    @tool
    def create_entity(
        project_id: str,
        name: str,
        namespace: str = "bat",
        health: int = 20,
        movement: float = 0.25,
    ) -> dict:
        """Create a server entity definition plus its loot table reference."""
        return services.generate_content(
            project_id,
            "entity",
            {"name": name, "namespace": namespace, "health": health, "movement": movement},
        )

    @mcp.tool()
    @tool
    def create_block(
        project_id: str,
        name: str,
        namespace: str = "bat",
        texture: str | None = None,
        destroy_seconds: float = 1.5,
    ) -> dict:
        """Create a data-driven block definition (1.19+)."""
        return services.generate_content(
            project_id,
            "block",
            {
                "name": name,
                "namespace": namespace,
                "texture": texture,
                "destroy_seconds": destroy_seconds,
            },
        )

    @mcp.tool()
    @tool
    def create_item(
        project_id: str,
        name: str,
        namespace: str = "bat",
        texture: str | None = None,
        max_stack: int = 64,
        damage: int | None = None,
    ) -> dict:
        """Create a component-based item definition (requires Bedrock 1.20.50+)."""
        return services.generate_content(
            project_id,
            "item",
            {
                "name": name,
                "namespace": namespace,
                "texture": texture,
                "max_stack": max_stack,
                "damage": damage,
            },
        )

    @mcp.tool()
    @tool
    def create_recipe(
        project_id: str,
        name: str,
        result_item: str,
        template: str = "shaped",
        pattern: list[str] | None = None,
        keys: dict[str, str] | None = None,
        ingredients: list[str] | None = None,
        result_count: int = 1,
        namespace: str = "bat",
    ) -> dict:
        """Create a shaped or shapeless crafting recipe."""
        return services.generate_content(
            project_id,
            "recipe",
            {
                "name": name,
                "namespace": namespace,
                "template": template,
                "pattern": pattern,
                "keys": keys,
                "ingredients": ingredients,
                "result_item": result_item,
                "result_count": result_count,
            },
        )

    @mcp.tool()
    @tool
    def create_loot_table(
        project_id: str,
        name: str,
        items: list[dict] | None = None,
        target: str = "entities",
        namespace: str = "bat",
    ) -> dict:
        """Create a loot table for entities, blocks or gameplay."""
        return services.generate_content(
            project_id,
            "loot_table",
            {"name": name, "namespace": namespace, "items": items, "target": target},
        )

    @mcp.tool()
    @tool
    def create_spawn_rule(
        project_id: str,
        entity_identifier: str,
        weight: int = 10,
        herd_min: int = 1,
        herd_max: int = 3,
        biome_tag: str = "overworld",
    ) -> dict:
        """Create spawn rules for an entity identifier."""
        return services.generate_content(
            project_id,
            "spawn_rule",
            {
                "entity_identifier": entity_identifier,
                "weight": weight,
                "herd_min": herd_min,
                "herd_max": herd_max,
                "biome_tag": biome_tag,
            },
        )

    @mcp.tool()
    @tool
    def create_animation(
        project_id: str,
        name: str,
        namespace: str = "bat",
        bone: str = "body",
        axis: str = "z",
        amplitude: float = 10.0,
    ) -> dict:
        """Create a resource-pack bone animation (client-side; NOT_TESTED)."""
        return services.generate_content(
            project_id,
            "animation",
            {
                "name": name,
                "namespace": namespace,
                "bone": bone,
                "axis": axis,
                "amplitude": amplitude,
            },
        )

    @mcp.tool()
    @tool
    def create_animation_controller(
        project_id: str, name: str, namespace: str = "bat", animation_name: str | None = None
    ) -> dict:
        """Create an animation controller (client-side; NOT_TESTED)."""
        return services.generate_content(
            project_id,
            "animation_controller",
            {"name": name, "namespace": namespace, "animation_name": animation_name},
        )

    @mcp.tool()
    @tool
    def create_particle(
        project_id: str,
        name: str,
        namespace: str = "bat",
        texture: str = "textures/particle/particles",
        spawn_rate: int = 10,
        size: float = 0.1,
    ) -> dict:
        """Create a particle effect definition (structure validated, rendering NOT_TESTED)."""
        return services.generate_content(
            project_id,
            "particle",
            {
                "name": name,
                "namespace": namespace,
                "texture": texture,
                "spawn_rate": spawn_rate,
                "size": size,
            },
        )

    @mcp.tool()
    @tool
    def create_attachable(
        project_id: str,
        name: str,
        namespace: str = "bat",
        texture: str | None = None,
        geometry: str | None = None,
    ) -> dict:
        """Create an item attachable (client-side; NOT_TESTED)."""
        return services.generate_content(
            project_id,
            "attachable",
            {
                "name": name,
                "namespace": namespace,
                "texture": texture,
                "geometry": geometry,
            },
        )

    @mcp.tool()
    @tool
    def create_script_module(
        project_id: str, module_name: str = "main", include_ui: bool = False
    ) -> dict:
        """Add a script module to the behavior pack manifest and write its entry script.

        Script execution is NOT_TESTED without a running server.
        """
        return services.generate_content(
            project_id,
            "script_module",
            {"module_name": module_name, "include_ui": include_ui},
        )
