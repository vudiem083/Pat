"""Loot table templates."""

from __future__ import annotations

from typing import Any

from ..core.errors import make_error
from ..core.models import GeneratedFile, PackKind
from .common import GenerationContext
from .recipe import _validate_item_ref


def loot_document(
    entries: list[dict[str, Any]], *, rolls: int = 1, pool_name: str = "default"
) -> dict[str, Any]:
    return {
        "pools": [
            {
                "rolls": rolls,
                "entries": entries,
            }
        ]
    }


def create_loot_table(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    items: list[dict[str, Any]] | None = None,
    target: str = "entities",
) -> GeneratedFile:
    """Create a loot table.

    ``target`` selects the folder: ``entities``, ``blocks`` or ``gameplay``.
    Each entry is ``{"item": "namespace:name", "weight": 1, "min": 1, "max": 1}``.
    """
    context.feature("loot_table.entity")
    if target not in {"entities", "blocks", "gameplay"}:
        raise make_error("BAT-INPUT-001", "loot table target must be entities, blocks or gameplay.")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    raw_items = items or [{"item": "minecraft:stick", "weight": 1, "min": 1, "max": 1}]
    entries: list[dict[str, Any]] = []
    for entry in raw_items:
        item = _validate_item_ref(str(entry.get("item", "")))
        entries.append(
            {
                "type": "item",
                "name": item,
                "weight": int(entry.get("weight", 1)),
                "functions": [
                    {
                        "function": "set_count",
                        "count": {
                            "min": int(entry.get("min", 1)),
                            "max": int(entry.get("max", 1)),
                        },
                    }
                ],
            }
        )
    document = loot_document(entries)
    document["pools"][0]["rolls"] = int(document["pools"][0]["rolls"])
    return context.write_json(
        PackKind.BEHAVIOR,
        f"loot_tables/{target}/{slug}.json",
        document,
        description=f"Loot table {identifier} for {target}",
        feature="loot_table.entity",
    )
