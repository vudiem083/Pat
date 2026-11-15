from __future__ import annotations

import json
from pathlib import Path

import pytest

from bat.core.errors import BatError
from bat.core.models import ProjectType
from bat.services import BatServices


def test_create_addon_seeds_two_packs(services: BatServices, addon_project: str):
    project = services.projects.get(addon_project)
    assert project.project_type == ProjectType.ADDON.value
    packs = services.projects.list_packs(addon_project)
    kinds = {p["kind"] for p in packs}
    assert kinds == {"BEHAVIOR", "RESOURCE"}
    for pack in packs:
        manifest = (
            services.projects.files_root(addon_project) / pack["path"] / "manifest.json"
        )
        data = json.loads(manifest.read_text())
        assert data["format_version"] == 2
        assert data["header"]["min_engine_version"] == [1, 21, 80]
        assert data["modules"][0]["type"] in {"data", "resources"}


def test_duplicate_name_rejected(services: BatServices, addon_project: str):
    with pytest.raises(BatError) as exc:
        services.create_project(
            name="Test Addon", project_type="ADDON", target_version="1.21.80"
        )
    assert exc.value.code == "BAT-PROJECT-002"
    assert exc.value.http_status == 409


def test_unsupported_target_version_rejected(services: BatServices):
    with pytest.raises(BatError) as exc:
        services.create_project(name="Old", project_type="ADDON", target_version="1.12.0")
    assert exc.value.code == "BAT-COMPAT-001"


def test_invalid_project_type_rejected(services: BatServices):
    with pytest.raises(BatError) as exc:
        services.create_project(name="Bad", project_type="JAVA", target_version="1.21.80")
    assert exc.value.code == "BAT-PROJECT-001"


def test_world_project_has_real_level_dat(services: BatServices, world_project: str):
    world_dir = services.projects.ensure_world_dir(world_project)
    level_dat = world_dir / "level.dat"
    assert level_dat.exists()
    raw = level_dat.read_bytes()
    assert raw[:4] == (10).to_bytes(4, "little")
    inspection = services.inspect_world(world_project)
    assert inspection["level_dat_status"] == "OK"
    assert inspection["level_name"] == "Test World"
    assert inspection["game_mode"] in {"creative", "survival", "adventure", "spectator"}


def test_addon_project_has_no_world(services: BatServices, addon_project: str):
    with pytest.raises(BatError) as exc:
        services.inspect_world(addon_project)
    assert exc.value.code == "BAT-PROJECT-003"


def test_read_write_file_with_backup(services: BatServices, addon_project: str):
    first = services.projects.write_file(
        addon_project, "behavior_packs/x/data.json", '{"a": 1}'
    )
    assert first["created"] is True and first["backup"] is None
    second = services.projects.write_file(
        addon_project, "behavior_packs/x/data.json", '{"a": 2}'
    )
    assert second["created"] is False
    assert second["backup"] == "behavior_packs/x/data.json.bak"
    read = services.projects.read_file(addon_project, "behavior_packs/x/data.json")
    assert json.loads(read["content"]) == {"a": 2}
    backup = services.projects.read_file(addon_project, second["backup"])
    assert json.loads(backup["content"]) == {"a": 1}


def test_file_paths_cannot_escape(services: BatServices, addon_project: str):
    for bad in ("../../etc/passwd", "/etc/passwd", ".."):
        with pytest.raises(BatError) as exc:
            services.projects.read_file(addon_project, bad)
        assert exc.value.code in {"BAT-PATH-001", "BAT-INPUT-001"}


def test_delete_file(services: BatServices, addon_project: str):
    services.projects.write_file(addon_project, "notes.txt", "hello")
    result = services.projects.delete_file(addon_project, "notes.txt")
    assert result["deleted"] is True
    with pytest.raises(BatError):
        services.projects.read_file(addon_project, "notes.txt")


def test_tree_lists_directories_and_files(services: BatServices, addon_project: str):
    services.projects.write_file(addon_project, "behavior_packs/p/entities/e.json", "{}")
    tree = services.project_tree(addon_project)
    assert tree["type"] == "dir"
    paths = _flatten(tree)
    assert "behavior_packs/p/entities/e.json" in paths
    assert "behavior_packs/test_addon/manifest.json" in paths


def _flatten(node: dict) -> set[str]:
    paths = {node["path"]}
    for child in node.get("children", []):
        paths |= _flatten(child)
    return paths


def test_delete_project_retains_evidence_by_default(services: BatServices, addon_project: str):
    result = services.projects.delete(addon_project)
    assert result["removed_files"] is True
    assert "incidents" in result["retained"]
    assert result["retained"]["artifacts"] == "kept"
    with pytest.raises(BatError):
        services.projects.get(addon_project)


def test_combined_project_has_world_and_packs(services: BatServices, combined_project: str):
    project = services.projects.get(combined_project)
    assert project.project_type == ProjectType.COMBINED.value
    assert len(services.projects.list_packs(combined_project)) == 2
    assert (services.projects.ensure_world_dir(combined_project) / "level.dat").exists()


def test_write_is_refused_for_archived_project(services: BatServices, addon_project: str):
    project = services.projects.get(addon_project)
    project.status = "ARCHIVED"
    services.db.save_project(project)
    with pytest.raises(BatError) as exc:
        services.projects.write_file(addon_project, "x.txt", "no")
    assert exc.value.code == "BAT-PROJECT-004"
