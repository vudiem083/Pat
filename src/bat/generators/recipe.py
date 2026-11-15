"""Crafting recipe templates (shaped and shapeless)."""

from __future__ import annotations

import re
from typing import Any

from ..core.errors import make_error
from ..core.models import GeneratedFile, PackKind
from .common import GenerationContext

_IDENTIFIER_RE = re.compile(r"^[a-z0-9_]+:[a-z0-9_\.\-]+$")


def _validate_item_ref(value: str) -> str:
    if not _IDENTIFIER_RE.match(value or ""):
        raise make_error(
            "BAT-INPUT-001",
            f"Invalid item identifier {value!r}. Expected 'namespace:name'.",
        )
    return value


def shaped_document(
    identifier: str,
    fmt: str,
    *,
    pattern: list[str],
    keys: dict[str, str],
    result_item: str,
    result_count: int,
) -> dict[str, Any]:
    return {
        "format_version": fmt,
        "minecraft:recipe_shaped": {
            "description": {"identifier": identifier},
            "tags": ["crafting_table"],
            "pattern": pattern,
            "key": {symbol: {"item": _validate_item_ref(item)} for symbol, item in keys.items()},
            "result": {"item": _validate_item_ref(result_item), "count": result_count},
        },
    }


def shapeless_document(
    identifier: str,
    fmt: str,
    *,
    ingredients: list[str],
    result_item: str,
    result_count: int,
) -> dict[str, Any]:
    return {
        "format_version": fmt,
        "minecraft:recipe_shapeless": {
            "description": {"identifier": identifier},
            "tags": ["crafting_table"],
            "ingredients": [{"item": _validate_item_ref(i)} for i in ingredients],
            "result": {"item": _validate_item_ref(result_item), "count": result_count},
        },
    }


def validate_pattern(pattern: list[str], keys: dict[str, str]) -> None:
    if not pattern or len(pattern) > 3:
        raise make_error("BAT-INPUT-001", "A shaped recipe pattern must have 1–3 rows.")
    width = None
    used: set[str] = set()
    for row in pattern:
        if not isinstance(row, str) or not 1 <= len(row) <= 3:
            raise make_error("BAT-INPUT-001", "Each shaped recipe row must be 1–3 characters.")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise make_error("BAT-INPUT-001", "All shaped recipe rows must have equal length.")
        used |= {c for c in row if c != " "}
    missing = used - set(keys)
    if missing:
        raise make_error(
            "BAT-INPUT-001",
            f"Recipe pattern uses symbols without a key entry: {sorted(missing)}",
        )
    unused = set(keys) - used
    if unused:
        raise make_error(
            "BAT-INPUT-001",
            f"Recipe key defines symbols that are not in the pattern: {sorted(unused)}",
        )


def create_recipe(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    template: str = "shaped",
    pattern: list[str] | None = None,
    keys: dict[str, str] | None = None,
    ingredients: list[str] | None = None,
    result_item: str | None = None,
    result_count: int = 1,
) -> GeneratedFile:
    context.feature("recipe.shaped" if template == "shaped" else "recipe.shapeless")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    if not result_item:
        raise make_error("BAT-INPUT-001", "result_item is required (e.g. 'minecraft:stick').")
    if template == "shaped":
        pattern = pattern or ["XX", "XX"]
        keys = keys or {"X": "minecraft:stick"}
        validate_pattern(pattern, keys)
        document = shaped_document(
            identifier,
            context.fmt,
            pattern=pattern,
            keys=keys,
            result_item=result_item,
            result_count=int(result_count),
        )
        feature = "recipe.shaped"
    elif template == "shapeless":
        ingredients = ingredients or ["minecraft:stick"]
        document = shapeless_document(
            identifier,
            context.fmt,
            ingredients=ingredients,
            result_item=result_item,
            result_count=int(result_count),
        )
        feature = "recipe.shapeless"
    else:
        raise make_error(
            "BAT-INPUT-001",
            f"Unsupported recipe template {template!r}. Use 'shaped' or 'shapeless'.",
        )
    return context.write_json(
        PackKind.BEHAVIOR,
        f"recipes/{slug}.json",
        document,
        description=f"{template} recipe for {identifier}",
        feature=feature,
    )
