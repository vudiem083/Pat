"""Item definition template.

BAT generates the component-based item format (1.20.50+). For older targets the
generator reports BAT-COMPAT-002 instead of emitting a document the game cannot
parse; the legacy pre-1.20.50 item format is not generated.
"""

from __future__ import annotations

from typing import Any

from ..core.models import GeneratedFile, PackKind
from .common import GenerationContext


def item_document(
    identifier: str, fmt: str, *, texture: str, max_stack: int, damage: int | None
) -> dict[str, Any]:
    components: dict[str, Any] = {
        "minecraft:icon": {"texture": texture},
        "minecraft:max_stack_size": max_stack,
        "minecraft:display_name": {"value": identifier.split(":", 1)[1].replace("_", " ").title()},
    }
    if damage is not None:
        components["minecraft:damage"] = damage
        components["minecraft:hand_equipped"] = True
    return {
        "format_version": fmt,
        "minecraft:item": {
            "description": {
                "identifier": identifier,
                "menu_category": {"category": "items"},
            },
            "components": components,
        },
    }


def create_item(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    texture: str | None = None,
    max_stack: int = 64,
    damage: int | None = None,
) -> GeneratedFile:
    context.feature("item.components")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    texture_name = texture or f"{context.namespace(namespace)}_{slug}"
    if not 1 <= int(max_stack) <= 64:
        from ..core.errors import make_error

        raise make_error("BAT-INPUT-001", "max_stack must be between 1 and 64.")
    document = item_document(
        identifier,
        context.fmt,
        texture=texture_name,
        max_stack=int(max_stack),
        damage=int(damage) if damage is not None else None,
    )
    return context.write_json(
        PackKind.BEHAVIOR,
        f"items/{slug}.json",
        document,
        description=f"Item definition for {identifier}",
        feature="item.components",
    )
