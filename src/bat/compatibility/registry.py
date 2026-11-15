"""Version-aware feature registry.

Each record states which Bedrock versions a feature is believed to work on,
*why* (evidence) and whether BAT has actually exercised it. Entries that BAT has
not verified against a real Minecraft runtime are marked ``verified=False`` and
are surfaced as ``NOT_TESTED`` rather than being advertised as supported.

Statuses follow the product contract:
SUPPORTED / UNSUPPORTED / UNKNOWN / NOT_TESTED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core.models import CompatibilityStatus, FeatureSupport
from .versions import BedrockVersion, MAX_VERSION, MIN_VERSION, parse_version


@dataclass(frozen=True)
class FeatureRecord:
    key: str
    label: str
    category: str
    min_version: str | None
    max_version: str | None = None
    evidence: str = ""
    notes: str = ""
    verified: bool = False


def _f(
    key: str,
    label: str,
    category: str,
    min_version: str | None,
    evidence: str,
    *,
    max_version: str | None = None,
    notes: str = "",
    verified: bool = False,
) -> FeatureRecord:
    return FeatureRecord(
        key=key,
        label=label,
        category=category,
        min_version=min_version,
        max_version=max_version,
        evidence=evidence,
        notes=notes,
        verified=verified,
    )


# Evidence strings name the documentation BAT relies on. "verified" is reserved
# for behaviour BAT has exercised itself; documentation alone is not evidence of
# runtime behaviour, so most entries stay verified=False.
_DOC_MANIFEST = "Minecraft Bedrock pack manifest documentation (format_version 2 header/modules)"
_DOC_BLOCK = "Bedrock block documentation (minecraft:block with components)"
_DOC_ITEM = "Bedrock 1.20.50 item component documentation"
_DOC_RECIPE = "Bedrock recipe documentation (minecraft:recipe_shaped / recipe_shapeless)"
_DOC_SCRIPT = "Bedrock Script API documentation (@minecraft/server module)"
_DOC_ANIM = "Bedrock animation / animation controller documentation"
_DOC_PARTICLE = "Bedrock particle effect documentation"
_DOC_ATTACHABLE = "Bedrock attachable documentation"
_DOC_WORLD = "Minecraft Wiki: Bedrock Edition level format (level.dat little-endian NBT)"
_DOC_STRUCTURE = "Bedrock .mcstructure documentation (NBT structure with palette + block_indices)"
_DOC_LOOT = "Bedrock loot table documentation"
_DOC_SPAWN = "Bedrock spawn rules documentation"

FEATURES: tuple[FeatureRecord, ...] = (
    # -- manifests ---------------------------------------------------------
    _f(
        "manifest.format_version_2",
        "Pack manifest format_version 2",
        "manifest",
        "1.19.0",
        _DOC_MANIFEST,
        verified=True,
        notes="BAT writes format_version 2 manifests; exercised by BAT's own validators.",
    ),
    _f(
        "manifest.min_engine_version",
        "manifest header.min_engine_version",
        "manifest",
        "1.19.0",
        _DOC_MANIFEST,
        verified=True,
    ),
    _f(
        "manifest.script_module",
        "manifest script module entry",
        "manifest",
        "1.19.0",
        _DOC_SCRIPT,
        notes="Requires the script module type and an entry script file.",
    ),
    _f(
        "manifest.dependency",
        "manifest dependencies between packs",
        "manifest",
        "1.19.0",
        _DOC_MANIFEST,
        verified=True,
    ),
    # -- entities ----------------------------------------------------------
    _f(
        "entity.server_definition",
        "Server entity definition (minecraft:entity)",
        "entity",
        "1.19.0",
        "Bedrock entity documentation (minecraft:entity with components/groups)",
        verified=True,
        notes="BAT generates and structurally validates these documents.",
    ),
    _f(
        "entity.behavior.trade_table",
        "Villager trade tables",
        "entity",
        "1.19.0",
        "Bedrock entity documentation (minecraft:trade_table)",
    ),
    # -- blocks ------------------------------------------------------------
    _f(
        "block.components",
        "Block definition with components",
        "block",
        "1.19.0",
        _DOC_BLOCK,
        verified=True,
        notes="Structural generation and validation verified; in-game loading NOT_TESTED.",
    ),
    _f(
        "block.geometry",
        "Block geometry with material instances",
        "block",
        "1.19.0",
        _DOC_BLOCK,
    ),
    _f(
        "block.custom_components",
        "Block custom components (1.21 series API)",
        "block",
        "1.21.0",
        _DOC_BLOCK,
        notes="BAT does not generate custom-component blocks; support of arbitrary API "
        "versions is UNKNOWN and must be checked per project.",
    ),
    # -- items -------------------------------------------------------------
    _f(
        "item.components",
        "Item definition with components",
        "item",
        "1.20.50",
        _DOC_ITEM,
        notes="Component-based item format. Older 1.19/1.20.0-1.20.40 projects use the "
        "legacy 'minecraft:item' format which BAT reports as UNSUPPORTED for generation.",
    ),
    _f(
        "item.icon_component",
        "minecraft:icon item component",
        "item",
        "1.20.50",
        _DOC_ITEM,
    ),
    # -- recipes -----------------------------------------------------------
    _f(
        "recipe.shaped",
        "Shaped crafting recipe",
        "recipe",
        "1.19.0",
        _DOC_RECIPE,
        verified=True,
    ),
    _f(
        "recipe.shapeless",
        "Shapeless crafting recipe",
        "recipe",
        "1.19.0",
        _DOC_RECIPE,
        verified=True,
    ),
    _f(
        "recipe.furnace",
        "Furnace recipe",
        "recipe",
        "1.19.0",
        _DOC_RECIPE,
    ),
    # -- loot / spawning ---------------------------------------------------
    _f(
        "loot_table.entity",
        "Entity loot table",
        "loot_table",
        "1.19.0",
        _DOC_LOOT,
        verified=True,
    ),
    _f(
        "spawn_rules.entity",
        "Entity spawn rules",
        "spawn_rules",
        "1.19.0",
        _DOC_SPAWN,
        verified=True,
    ),
    # -- animations / particles / attachables ------------------------------
    _f(
        "animation.bone_animation",
        "Bone animation",
        "animation",
        "1.19.0",
        _DOC_ANIM,
        verified=True,
    ),
    _f(
        "animation.controller",
        "Animation controller",
        "animation",
        "1.19.0",
        _DOC_ANIM,
        verified=True,
    ),
    _f(
        "particle.effect",
        "Particle effect definition",
        "particle",
        "1.19.0",
        _DOC_PARTICLE,
        verified=True,
        notes="Structural validation only; rendering is client-side and NOT_TESTED.",
    ),
    _f(
        "attachable.item",
        "Item attachable",
        "attachable",
        "1.19.60",
        _DOC_ATTACHABLE,
        notes="Client-side rendering feature; BAT can generate the definition but cannot "
        "verify it without a client adapter.",
    ),
    # -- scripts -----------------------------------------------------------
    _f(
        "script.module",
        "Script module in a behavior pack",
        "script",
        "1.19.0",
        _DOC_SCRIPT,
        notes="Requires experimental/stable script APIs enabled in the world; BAT generates "
        "the module but script runtime behaviour is NOT_TESTED without a real server.",
    ),
    _f(
        "script.gametest",
        "GameTest registration via scripts",
        "script",
        "1.21.0",
        _DOC_SCRIPT,
        notes="GameTest availability differs by version and server build. UNKNOWN unless "
        "the target server is verified by the operator.",
    ),
    # -- worlds ------------------------------------------------------------
    _f(
        "world.level_dat",
        "level.dat metadata (little-endian NBT, 8-byte header)",
        "world",
        "1.19.0",
        _DOC_WORLD,
        verified=True,
        notes="BAT writes and re-reads level.dat with its own codec; round-trip verified.",
    ),
    _f(
        "world.pack_binding",
        "world_behavior_packs.json / world_resource_packs.json binding",
        "world",
        "1.19.0",
        "Minecraft Wiki: Bedrock Edition level format (world pack binding files)",
        verified=True,
    ),
    _f(
        "world.terrain_generation",
        "Terrain/chunk generation",
        "world",
        None,
        "Terrain is generated by Minecraft, not by BAT",
        notes="BAT creates world skeletons; chunk data is produced by Minecraft on first load. "
        "NOT_SUPPORTED by BAT itself.",
    ),
    _f(
        "world.structure",
        ".mcstructure import/export",
        "world",
        "1.19.0",
        _DOC_STRUCTURE,
        verified=True,
        notes="BAT writes palette + block_indices structures and re-reads them.",
    ),
    # -- textures ----------------------------------------------------------
    _f(
        "texture.png",
        "PNG texture files",
        "texture",
        "1.19.0",
        "Bedrock resource pack documentation (textures/ tree)",
        verified=True,
        notes="BAT validates the PNG signature/IHDR of texture files.",
    ),
)


class CompatibilityRegistry:
    """Lookup registry with explicit UNKNOWN/NOT_TESTED handling."""

    def __init__(self, features: Iterable[FeatureRecord] = FEATURES) -> None:
        self._features: dict[str, FeatureRecord] = {f.key: f for f in features}

    @property
    def features(self) -> list[FeatureRecord]:
        return sorted(self._features.values(), key=lambda f: (f.category, f.key))

    def get(self, key: str) -> FeatureRecord | None:
        return self._features.get(key)

    def by_category(self, category: str) -> list[FeatureRecord]:
        return [f for f in self.features if f.category == category]

    def check(self, key: str, version: str) -> FeatureSupport:
        record = self._features.get(key)
        target = parse_version(version)
        if record is None:
            return FeatureSupport(
                feature=key,
                category="unknown",
                status=CompatibilityStatus.UNKNOWN.value,
                evidence="No registry entry for this feature; compatibility cannot be established.",
                notes="Report UNKNOWN rather than guessing.",
            )
        if record.min_version is None:
            return FeatureSupport(
                feature=record.key,
                category=record.category,
                status=CompatibilityStatus.UNSUPPORTED.value,
                evidence=record.evidence,
                notes=record.notes or "Not supported by BAT.",
            )
        min_v = parse_version(record.min_version)
        max_v = parse_version(record.max_version) if record.max_version else MAX_VERSION
        if target < MIN_VERSION or target > MAX_VERSION:
            return FeatureSupport(
                feature=record.key,
                category=record.category,
                status=CompatibilityStatus.UNSUPPORTED.value,
                min_version=record.min_version,
                max_version=record.max_version,
                evidence=record.evidence,
                notes=(
                    f"Target {target.short} is outside BAT's supported range "
                    f"{MIN_VERSION.short}–{MAX_VERSION.short}."
                ),
            )
        if target < min_v or target > max_v:
            return FeatureSupport(
                feature=record.key,
                category=record.category,
                status=CompatibilityStatus.UNSUPPORTED.value,
                min_version=record.min_version,
                max_version=record.max_version,
                evidence=record.evidence,
                notes=record.notes
                or f"Requires {record.min_version} or newer; target is {target.short}.",
            )
        if not record.verified:
            return FeatureSupport(
                feature=record.key,
                category=record.category,
                status=CompatibilityStatus.NOT_TESTED.value,
                min_version=record.min_version,
                max_version=record.max_version,
                evidence=record.evidence,
                notes=record.notes
                or "Documented for this range but not exercised against a real runtime.",
            )
        return FeatureSupport(
            feature=record.key,
            category=record.category,
            status=CompatibilityStatus.SUPPORTED.value,
            min_version=record.min_version,
            max_version=record.max_version,
            evidence=record.evidence,
            notes=record.notes,
        )

    def require(self, key: str, version: str) -> FeatureSupport:
        """Check a feature and raise BAT-COMPAT-002 when it is not SUPPORTED."""
        support = self.check(key, version)
        if support.status == CompatibilityStatus.UNSUPPORTED.value:
            from ..core.errors import make_error

            raise make_error(
                "BAT-COMPAT-002",
                f"Feature {key!r} is not supported for Bedrock {parse_version(version).short}: "
                f"{support.notes}",
                details={"feature": key, "target_version": version},
            )
        return support

    def matrix(self, version: str) -> list[FeatureSupport]:
        return [self.check(record.key, version) for record in self.features]

    @staticmethod
    def summary(supports: Iterable[FeatureSupport]) -> dict[str, int]:
        counts = {
            CompatibilityStatus.SUPPORTED.value: 0,
            CompatibilityStatus.UNSUPPORTED.value: 0,
            CompatibilityStatus.UNKNOWN.value: 0,
            CompatibilityStatus.NOT_TESTED.value: 0,
        }
        for support in supports:
            counts[support.status] = counts.get(support.status, 0) + 1
        return counts


def compare_versions(left: str, right: str) -> int:
    """Return -1/0/1 comparing two version strings."""
    a: BedrockVersion = parse_version(left)
    b: BedrockVersion = parse_version(right)
    return (a > b) - (a < b)


DEFAULT_REGISTRY = CompatibilityRegistry()
