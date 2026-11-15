"""Component availability across Bedrock versions.

Used by the compatibility checker to reason about components found in a project's
entity/block/item documents. Entries only claim what BAT can substantiate; a
component that is absent from this table is reported as UNKNOWN rather than
assumed to work.
"""

from __future__ import annotations

from dataclasses import dataclass

from .versions import parse_version


@dataclass(frozen=True)
class ComponentRecord:
    name: str
    kind: str  # entity | block | item
    min_version: str
    max_version: str | None = None
    notes: str = ""


COMPONENTS: tuple[ComponentRecord, ...] = (
    # Entities
    ComponentRecord("minecraft:health", "entity", "1.19.0"),
    ComponentRecord("minecraft:physics", "entity", "1.19.0"),
    ComponentRecord("minecraft:movement", "entity", "1.19.0"),
    ComponentRecord("minecraft:movement.basic", "entity", "1.19.0"),
    ComponentRecord("minecraft:jump.static", "entity", "1.19.0"),
    ComponentRecord("minecraft:navigation.walk", "entity", "1.19.0"),
    ComponentRecord("minecraft:behavior.random_stroll", "entity", "1.19.0"),
    ComponentRecord("minecraft:behavior.look_at_player", "entity", "1.19.0"),
    ComponentRecord("minecraft:type_family", "entity", "1.19.0"),
    ComponentRecord("minecraft:collision_box", "entity", "1.19.0"),
    ComponentRecord("minecraft:loot", "entity", "1.19.0"),
    ComponentRecord("minecraft:despawn", "entity", "1.19.0"),
    ComponentRecord("minecraft:pushable", "entity", "1.19.0"),
    ComponentRecord("minecraft:damage_sensor", "entity", "1.19.0"),
    # Blocks
    ComponentRecord("minecraft:destructible_by_mining", "block", "1.19.0"),
    ComponentRecord("minecraft:destructible_by_explosion", "block", "1.19.0"),
    ComponentRecord("minecraft:material_instances", "block", "1.19.0"),
    ComponentRecord("minecraft:geometry", "block", "1.19.0"),
    ComponentRecord("minecraft:collision_box", "block", "1.19.0"),
    ComponentRecord("minecraft:selection_box", "block", "1.19.0"),
    ComponentRecord("minecraft:light_emission", "block", "1.19.0"),
    ComponentRecord("minecraft:map_color", "block", "1.19.0"),
    ComponentRecord("minecraft:friction", "block", "1.19.0"),
    ComponentRecord("minecraft:loot", "block", "1.19.0"),
    ComponentRecord("minecraft:placement_filter", "block", "1.19.0"),
    ComponentRecord("minecraft:flammable", "block", "1.19.0"),
    ComponentRecord("minecraft:redstone_conductivity", "block", "1.21.40"),
    # Items
    ComponentRecord("minecraft:icon", "item", "1.20.50"),
    ComponentRecord("minecraft:max_stack_size", "item", "1.20.50"),
    ComponentRecord("minecraft:hand_equipped", "item", "1.20.50"),
    ComponentRecord("minecraft:damage", "item", "1.20.50"),
    ComponentRecord("minecraft:display_name", "item", "1.20.50"),
    ComponentRecord("minecraft:durability", "item", "1.20.50"),
    ComponentRecord("minecraft:food", "item", "1.20.50"),
    ComponentRecord("minecraft:cooldown", "item", "1.20.50"),
    ComponentRecord("minecraft:use_modifiers", "item", "1.20.50"),
    ComponentRecord("minecraft:enchantable", "item", "1.20.50"),
    ComponentRecord("minecraft:wearable", "item", "1.20.50"),
)

COMPONENT_INDEX: dict[tuple[str, str], ComponentRecord] = {
    (record.kind, record.name): record for record in COMPONENTS
}


def lookup(kind: str, name: str) -> ComponentRecord | None:
    return COMPONENT_INDEX.get((kind, name))


def available_for(kind: str, name: str, version: str) -> bool | None:
    """Return True/False when known, ``None`` when the registry has no entry."""
    record = lookup(kind, name)
    if record is None:
        return None
    target = parse_version(version)
    if target < parse_version(record.min_version):
        return False
    if record.max_version and target > parse_version(record.max_version):
        return False
    return True
