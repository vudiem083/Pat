"""Compatibility checker: derives the feature set a project actually uses.

Instead of validating an arbitrary feature list, this scans the project content
for constructs BAT recognizes (entity/block/item/recipe/animation/script files)
and returns a virtual feature list plus its compatibility info.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.models import CompatibilityInfo, Project
from ..compatibility.feature_matrix import compatibility_info
from ..compatibility.registry import DEFAULT_REGISTRY, CompatibilityRegistry

# (path fragment, feature key)
_CONTENT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("behavior_packs", "entities"), "entity.server_definition"),
    (("behavior_packs", "blocks"), "block.components"),
    (("behavior_packs", "items"), "item.components"),
    (("behavior_packs", "recipes"), "recipe.shaped"),
    (("behavior_packs", "loot_tables"), "loot_table.entity"),
    (("behavior_packs", "spawn_rules"), "spawn_rules.entity"),
    (("behavior_packs", "scripts"), "script.module"),
    (("resource_packs", "animations"), "animation.bone_animation"),
    (("resource_packs", "animation_controllers"), "animation.controller"),
    (("resource_packs", "particles"), "particle.effect"),
    (("resource_packs", "attachables"), "attachable.item"),
    (("resource_packs", "textures"), "texture.png"),
    (("world", "level.dat"), "world.level_dat"),
)


class CompatibilityChecker:
    def __init__(self, registry: CompatibilityRegistry | None = None) -> None:
        self.registry = registry or DEFAULT_REGISTRY

    def features_used(self, files_root: Path) -> list[str]:
        used: set[str] = {"manifest.format_version_2"}
        for path in files_root.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(files_root).parts
            for fragments, feature in _CONTENT_RULES:
                if all(fragment in parts for fragment in fragments):
                    used.add(feature)
        # Script API availability depends on the target version.
        return sorted(used)

    def check_project(self, project: Project, files_root: Path) -> CompatibilityInfo:
        features = self.features_used(files_root)
        info = compatibility_info(project.target_version, features=features, registry=self.registry)
        if (files_root / "world" / "world_behavior_packs.json").exists():
            bind = self.registry.check("world.pack_binding", project.target_version)
            info.checked_features.append(bind)
        return info

    def script_module_declared(self, files_root: Path) -> bool:
        for manifest in files_root.glob("behavior_packs/*/manifest.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for module in data.get("modules", []) or []:
                if isinstance(module, dict) and module.get("type") == "script":
                    return True
        return False
