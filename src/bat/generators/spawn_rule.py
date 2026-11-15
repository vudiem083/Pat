"""Spawn rules template."""

from __future__ import annotations

from typing import Any

from ..core.models import GeneratedFile, PackKind
from .common import GenerationContext


def spawn_rule_document(
    identifier: str,
    fmt: str,
    *,
    weight: int,
    herd_min: int,
    herd_max: int,
    biome_tag: str = "overworld",
    brightness_min: int = 7,
    brightness_max: int = 15,
) -> dict[str, Any]:
    return {
        "format_version": fmt,
        "minecraft:spawn_rules": {
            "description": {"identifier": identifier},
            "conditions": [
                {
                    "minecraft:spawns_on_surface": {},
                    "minecraft:brightness_filter": {
                        "min": brightness_min,
                        "max": brightness_max,
                        "adjust_for_weather": False,
                    },
                    "minecraft:weight": {"default": weight},
                    "minecraft:herd": {"min_size": herd_min, "max_size": herd_max},
                    "minecraft:biome_filter": {
                        "test": "has_biome_tag",
                        "operator": "==",
                        "value": biome_tag,
                    },
                }
            ],
        },
    }


def create_spawn_rule(
    context: GenerationContext,
    *,
    entity_identifier: str,
    weight: int = 10,
    herd_min: int = 1,
    herd_max: int = 3,
    biome_tag: str = "overworld",
) -> GeneratedFile:
    context.feature("spawn_rules.entity")
    if ":" not in entity_identifier:
        context.identifier(None, entity_identifier)
        entity_identifier = f"bat:{entity_identifier}"
    slug = context.slugify_suffix(entity_identifier)
    document = spawn_rule_document(
        entity_identifier,
        context.fmt,
        weight=int(weight),
        herd_min=int(herd_min),
        herd_max=int(herd_max),
        biome_tag=biome_tag,
    )
    return context.write_json(
        PackKind.BEHAVIOR,
        f"spawn_rules/{slug}.json",
        document,
        description=f"Spawn rules for {entity_identifier}",
        feature="spawn_rules.entity",
    )
