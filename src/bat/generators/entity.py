"""Server entity definition template."""

from __future__ import annotations

from typing import Any

from ..core.models import GeneratedFile, PackKind
from .common import GenerationContext


def entity_document(identifier: str, fmt: str, *, health: int, movement: float, family: list[str]) -> dict[str, Any]:
    loot_path = f"loot_tables/entities/{identifier.split(':', 1)[1]}.json"
    return {
        "format_version": fmt,
        "minecraft:entity": {
            "description": {
                "identifier": identifier,
                "is_spawnable": True,
                "is_summonable": True,
                "is_experimental": False,
            },
            "components": {
                "minecraft:type_family": {"family": family},
                "minecraft:collision_box": {"width": 0.6, "height": 1.8},
                "minecraft:health": {"value": health, "max": health},
                "minecraft:physics": {},
                "minecraft:pushable": {"is_pushable": True, "is_pushable_by_piston": True},
                "minecraft:movement": {"value": movement},
                "minecraft:movement.basic": {},
                "minecraft:jump.static": {},
                "minecraft:navigation.walk": {
                    "can_path_over_water": True,
                    "avoid_water": True,
                    "avoid_damage_blocks": True,
                },
                "minecraft:behavior.random_stroll": {"priority": 6, "speed_multiplier": 0.8},
                "minecraft:behavior.look_at_player": {
                    "priority": 7,
                    "look_distance": 8.0,
                    "probability": 0.02,
                },
                "minecraft:loot": {"table": loot_path},
            },
        },
    }


def create_entity(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    health: int = 20,
    movement: float = 0.25,
) -> GeneratedFile:
    context.feature("entity.server_definition")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    document = entity_document(
        identifier,
        context.fmt,
        health=int(health),
        movement=float(movement),
        family=[slug],
    )
    return context.write_json(
        PackKind.BEHAVIOR,
        f"entities/{slug}.json",
        document,
        description=f"Server entity definition for {identifier}",
        feature="entity.server_definition",
    )
