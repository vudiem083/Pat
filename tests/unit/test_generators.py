from __future__ import annotations

import json

import pytest

from bat.core.errors import BatError
from bat.services import BatServices


def _read(services: BatServices, project_id: str, relative: str) -> dict:
    root = services.projects.files_root(project_id)
    return json.loads((root / relative).read_text())


def test_entity_generation_writes_valid_document(services: BatServices, addon_project: str):
    result = services.generate_content(addon_project, "entity", {"name": "test_mob"})
    generated = result["generated"]
    assert generated["path"].endswith("entities/test_mob.json")
    document = _read(services, addon_project, generated["path"])
    entity = document["minecraft:entity"]
    assert entity["description"]["identifier"] == "bat:test_mob"
    assert entity["description"]["is_summonable"] is True
    assert "minecraft:health" in entity["components"]
    assert document["format_version"] == "1.21.0"


def test_block_generation_uses_full_block_geometry(services: BatServices, addon_project: str):
    result = services.generate_content(addon_project, "block", {"name": "test_block"})
    document = _read(services, addon_project, result["generated"]["path"])
    components = document["minecraft:block"]["components"]
    assert components["minecraft:geometry"] == "minecraft:geometry.full_block"
    assert components["minecraft:material_instances"]["*"]["texture"] == "bat_test_block"


def test_item_generation_requires_1_20_50(services: BatServices):
    project = services.create_project(
        name="Old Target", project_type="ADDON", target_version="1.19.80"
    )
    project_id = project["project"]["project_id"]
    with pytest.raises(BatError) as exc:
        services.generate_content(project_id, "item", {"name": "old_item"})
    assert exc.value.code == "BAT-COMPAT-002"


def test_item_generation_on_supported_target(services: BatServices, addon_project: str):
    result = services.generate_content(
        addon_project, "item", {"name": "gem", "max_stack": 16}
    )
    document = _read(services, addon_project, result["generated"]["path"])
    components = document["minecraft:item"]["components"]
    assert components["minecraft:max_stack_size"] == 16
    assert components["minecraft:icon"]["texture"] == "bat_gem"


def test_recipe_pattern_validation(services: BatServices, addon_project: str):
    with pytest.raises(BatError) as exc:
        services.generate_content(
            addon_project,
            "recipe",
            {"name": "bad", "pattern": ["XX", "Y"], "keys": {"X": "minecraft:stick"}},
        )
    assert exc.value.code == "BAT-INPUT-001"


def test_recipe_generation(services: BatServices, addon_project: str):
    result = services.generate_content(
        addon_project,
        "recipe",
        {
            "name": "gem_recipe",
            "pattern": ["XX"],
            "keys": {"X": "minecraft:stick"},
            "result_item": "bat:gem",
            "result_count": 2,
        },
    )
    document = _read(services, addon_project, result["generated"]["path"])
    recipe = document["minecraft:recipe_shaped"]
    assert recipe["result"] == {"item": "bat:gem", "count": 2}
    assert recipe["tags"] == ["crafting_table"]


def test_script_module_wires_manifest_dependency(services: BatServices, addon_project: str):
    result = services.generate_content(
        addon_project, "script_module", {"module_name": "main"}
    )
    manifest_path = services.projects.files_root(addon_project) / "behavior_packs"
    manifest = json.loads(next(manifest_path.glob("*/manifest.json")).read_text())
    types = [m["type"] for m in manifest["modules"]]
    assert "script" in types
    entry = next(m for m in manifest["modules"] if m["type"] == "script")["entry"]
    assert entry == "scripts/main.js"
    modules = [d["module_name"] for d in manifest["dependencies"]]
    assert "@minecraft/server" in modules
    assert result["generated"]["path"].endswith("scripts/main.js")
    # Generated script must be honest about being untested.
    assert result["generated"]["compatibility_status"] == "NOT_TESTED"


def test_generation_requires_addon_capable_project(services: BatServices, world_project: str):
    with pytest.raises(BatError) as exc:
        services.generate_content(world_project, "entity", {"name": "nope"})
    assert exc.value.code == "BAT-PROJECT-003"


def test_unknown_generator_is_rejected(services: BatServices, addon_project: str):
    with pytest.raises(BatError) as exc:
        services.generate_content(addon_project, "portal", {})
    assert exc.value.code == "BAT-INPUT-001"


def test_invalid_identifier_rejected(services: BatServices, addon_project: str):
    with pytest.raises(BatError):
        services.generate_content(addon_project, "entity", {"name": "Bad Name!"})
