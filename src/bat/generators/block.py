"""Block definition template (data-driven blocks, 1.19+)."""

from __future__ import annotations

from typing import Any

from ..core.models import GeneratedFile, PackKind
from .common import GenerationContext


def block_document(identifier: str, fmt: str, *, texture: str, destroy_seconds: float) -> dict[str, Any]:
    return {
        "format_version": fmt,
        "minecraft:block": {
            "description": {
                "identifier": identifier,
                "menu_category": {"category": "construction"},
            },
            "components": {
                "minecraft:geometry": "minecraft:geometry.full_block",
                "minecraft:material_instances": {
                    "*": {"texture": texture, "render_method": "opaque"}
                },
                "minecraft:destructible_by_mining": {"seconds_to_destroy": destroy_seconds},
                "minecraft:destructible_by_explosion": {"explosion_resistance": 6.0},
                "minecraft:map_color": "#8a8a8a",
                "minecraft:light_emission": 0,
            },
        },
    }


def create_block(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    texture: str | None = None,
    destroy_seconds: float = 1.5,
) -> GeneratedFile:
    context.feature("block.components")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    texture_name = texture or f"{context.namespace(namespace)}_{slug}"
    document = block_document(
        identifier,
        context.fmt,
        texture=texture_name,
        destroy_seconds=float(destroy_seconds),
    )
    return context.write_json(
        PackKind.BEHAVIOR,
        f"blocks/{slug}.json",
        document,
        description=f"Block definition for {identifier} (texture {texture_name})",
        feature="block.components",
    )
