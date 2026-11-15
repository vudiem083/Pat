from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from bat.core.errors import BatError
from bat.services import BatServices


def test_mcaddon_contains_pack_folders(services: BatServices, addon_project: str):
    services.generate_content(addon_project, "entity", {"name": "packed_mob"})
    result = services.build_project(addon_project)
    assert len(result["artifacts"]) == 1
    artifact = result["artifacts"][0]
    assert artifact["artifact_type"] == "MCADDON"
    assert artifact["integrity_ok"] is True
    with zipfile.ZipFile(artifact["storage_path"]) as archive:
        names = archive.namelist()
        manifests = [n for n in names if n.endswith("manifest.json")]
        assert len(manifests) == 2
        assert any(n.startswith("behavior_packs/") for n in names)
        assert any(n.startswith("resource_packs/") for n in names)


def test_mcpack_build_and_inspection(services: BatServices, addon_project: str):
    result = services.build_project(addon_project, artifact_type="MCPACK")
    assert len(result["artifacts"]) == 2
    kinds = set()
    for artifact in result["artifacts"]:
        inspection = services.builders.inspect_artifact(artifact["artifact_id"])
        assert inspection["integrity_ok"] is True
        assert inspection["checksum_matches"] is True
        assert inspection["valid_zip"] is True
        kinds.add(inspection["manifests"][0]["module_types"][0])
    assert kinds == {"data", "resources"}


def test_artifact_checksum_mismatch_detected(services: BatServices, addon_project: str):
    artifact = services.build_project(addon_project)["artifacts"][0]
    path = Path(artifact["storage_path"])
    path.write_bytes(path.read_bytes() + b"tampered")
    inspection = services.builders.inspect_artifact(artifact["artifact_id"])
    assert inspection["checksum_matches"] is False
    assert inspection["integrity_ok"] is False


def test_build_report_is_persisted(services: BatServices, addon_project: str):
    artifact = services.build_project(addon_project)["artifacts"][0]
    report = services.builders.get_build_report(artifact["artifact_id"])
    assert report["artifact_type"] == "MCADDON"
    assert report["inspection"]["integrity_ok"] is True
    assert report["validation"]["status"] in {"PASS", "WARN"}


def test_mcworld_requires_level_dat(services: BatServices, world_project: str):
    world = services.projects.ensure_world_dir(world_project)
    (world / "level.dat").unlink()
    with pytest.raises(BatError) as exc:
        services.build_project(world_project, artifact_type="MCWORLD")
    assert exc.value.code == "BAT-WORLD-001"


def test_mcworld_contains_level_dat_at_root(services: BatServices, world_project: str):
    result = services.build_project(world_project)
    artifact = result["artifacts"][0]
    assert artifact["artifact_type"] == "MCWORLD"
    with zipfile.ZipFile(artifact["storage_path"]) as archive:
        names = archive.namelist()
        assert "level.dat" in names
        assert "levelname.txt" in names


def test_wrong_artifact_type_for_project(services: BatServices, world_project: str):
    with pytest.raises(BatError) as exc:
        services.build_project(world_project, artifact_type="MCADDON")
    assert exc.value.code == "BAT-BUILD-002"


def test_combined_project_builds_both_artifacts(services: BatServices, combined_project: str):
    services.generate_content(combined_project, "entity", {"name": "combined_mob"})
    result = services.build_project(combined_project)
    types = {a["artifact_type"] for a in result["artifacts"]}
    assert types == {"MCADDON", "MCWORLD"}
    for artifact in result["artifacts"]:
        assert artifact["integrity_ok"] is True


def test_strict_build_refuses_invalid_project(services: BatServices, addon_project: str):
    services.projects.write_file(
        addon_project, "behavior_packs/x/broken.json", "{not json"
    )
    result = services.build_project(addon_project)
    assert result["validation"]["status"] == "FAIL"  # non-strict build still runs
    with pytest.raises(BatError) as exc:
        services.build_project(addon_project, strict=True)
    assert exc.value.code == "BAT-BUILD-001"


def test_structure_create_export_import(services: BatServices, world_project: str):
    created = services.create_structure(
        world_project, name="hut", size=[2, 3, 4], block="minecraft:stone"
    )
    assert created["path"].endswith("structures/hut.mcstructure")
    listed = services.structures.list_structures(world_project)
    assert listed[0]["name"] == "hut"
    assert listed[0]["indices_match_size"] is True
    assert listed[0]["block_count"] == 24

    exported = services.export_structure(world_project, "hut")
    assert Path(exported["exported_to"]).exists()

    data = Path(exported["exported_to"]).read_bytes()
    imported = services.import_structure(world_project, "hut_copy", data)
    assert imported["palette_size"] == 2
    assert imported["size"] == [2, 3, 4]


def test_import_rejects_non_structure_bytes(services: BatServices, world_project: str):
    with pytest.raises(BatError) as exc:
        services.import_structure(world_project, "bad", b"garbage")
    assert exc.value.code == "BAT-WORLD-001"


def test_world_metadata_edit_creates_snapshot(services: BatServices, world_project: str):
    result = services.modify_world_metadata(
        world_project, game_mode="survival", difficulty="hard", level_name="Renamed World"
    )
    assert result["verified"] is True
    assert result["game_mode"] == "survival"
    assert result["difficulty"] == "hard"
    assert result["metadata"]["LevelName"] == "Renamed World"
    snapshot = Path(result["snapshot"])
    assert (snapshot / "snapshot.json").exists()
    assert (snapshot / "world" / "level.dat").exists()


def test_world_pack_bindings_use_real_uuids(services: BatServices, combined_project: str):
    result = services.bind_world_packs(combined_project)
    assert len(result["behavior_packs"]) == 1
    assert len(result["resource_packs"]) == 1
    world = services.projects.ensure_world_dir(combined_project)
    bindings = json.loads((world / "world_behavior_packs.json").read_text())
    assert bindings[0]["pack_id"] == result["behavior_packs"][0]["pack_id"]
