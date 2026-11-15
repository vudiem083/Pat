from __future__ import annotations

import json

from bat.core.models import Severity, ValidationOutcome
from bat.services import BatServices


def _manifest_path(services: BatServices, project_id: str, kind: str) -> str:
    root = services.projects.files_root(project_id) / f"{kind}_packs"
    manifest = next(root.glob("*/manifest.json"))
    return manifest.relative_to(services.projects.files_root(project_id)).as_posix()


def test_clean_project_passes_or_warns_only(services: BatServices, addon_project: str):
    services.generate_content(addon_project, "entity", {"name": "clean_mob"})
    report = services.validator.validate_project(addon_project)
    assert report.status in {ValidationOutcome.PASS.value, ValidationOutcome.WARN.value}
    assert report.error_codes == []
    assert "json" in report.validators_run
    assert report.checked_files > 0


def test_invalid_json_reports_line_number(services: BatServices, addon_project: str):
    services.projects.write_file(
        addon_project, "behavior_packs/x/broken.json", '{\n  "a": 1,\n  broken\n}'
    )
    report = services.validator.validate_project(addon_project)
    assert ValidationOutcome(report.status) is ValidationOutcome.FAIL
    json_findings = [f for f in report.findings if f.code == "BAT-JSON-001"]
    assert json_findings
    assert json_findings[0].file_path == "behavior_packs/x/broken.json"
    assert json_findings[0].line_number == 3


def test_manifest_missing_uuid_is_an_error(services: BatServices, addon_project: str):
    path = _manifest_path(services, addon_project, "behavior")
    root = services.projects.files_root(addon_project)
    data = json.loads((root / path).read_text())
    data["header"].pop("uuid")
    services.projects.write_file(addon_project, path, json.dumps(data))
    report = services.validator.validate_project(addon_project)
    assert "BAT-MANIFEST-001" in report.error_codes


def test_duplicate_uuid_across_packs_detected(services: BatServices, addon_project: str):
    root = services.projects.files_root(addon_project)
    bp = json.loads((root / _manifest_path(services, addon_project, "behavior")).read_text())
    rp_rel = _manifest_path(services, addon_project, "resource")
    rp = json.loads((root / rp_rel).read_text())
    rp["header"]["uuid"] = bp["header"]["uuid"]
    services.projects.write_file(addon_project, rp_rel, json.dumps(rp))
    report = services.validator.validate_project(addon_project)
    assert "BAT-MANIFEST-002" in report.error_codes


def test_min_engine_version_newer_than_target_is_error(services: BatServices, addon_project: str):
    rel = _manifest_path(services, addon_project, "behavior")
    root = services.projects.files_root(addon_project)
    data = json.loads((root / rel).read_text())
    data["header"]["min_engine_version"] = [9, 9, 9]
    services.projects.write_file(addon_project, rel, json.dumps(data))
    report = services.validator.validate_project(addon_project)
    assert "BAT-COMPAT-002" in report.error_codes


def test_script_module_without_entry_file_is_error(services: BatServices, addon_project: str):
    rel = _manifest_path(services, addon_project, "behavior")
    root = services.projects.files_root(addon_project)
    data = json.loads((root / rel).read_text())
    data["modules"].append(
        {
            "type": "script",
            "language": "javascript",
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "version": [1, 0, 0],
            "entry": "scripts/missing.js",
        }
    )
    services.projects.write_file(addon_project, rel, json.dumps(data))
    report = services.validator.validate_project(addon_project)
    assert "BAT-PACK-001" in report.error_codes


def test_item_on_old_target_flags_component_error(services: BatServices):
    project = services.create_project(
        name="Legacy", project_type="ADDON", target_version="1.19.0"
    )
    project_id = project["project"]["project_id"]
    # Write the document directly to bypass the generator's version gate.
    services.projects.write_file(
        project_id,
        "behavior_packs/legacy/items/legacy_item.json",
        json.dumps(
            {
                "format_version": "1.19.0",
                "minecraft:item": {
                    "description": {"identifier": "bat:legacy_item"},
                    "components": {"minecraft:icon": "x", "minecraft:max_stack_size": 64},
                },
            }
        ),
    )
    report = services.validator.validate_project(project_id)
    assert "BAT-ITEM-001" in report.error_codes
    assert any("1.19.0" in f.message for f in report.findings if f.code == "BAT-ITEM-001")


def test_broken_world_level_dat_is_reported(services: BatServices, world_project: str):
    world = services.projects.ensure_world_dir(world_project)
    (world / "level.dat").write_bytes(b"not-nbt-at-all")
    report = services.validator.validate_project(world_project)
    assert "BAT-WORLD-001" in report.error_codes


def test_broken_world_pack_binding_is_reported(services: BatServices, world_project: str):
    world = services.projects.ensure_world_dir(world_project)
    (world / "world_behavior_packs.json").write_text('{"not": "a list"}')
    report = services.validator.validate_project(world_project)
    assert "BAT-WORLD-001" in report.error_codes


def test_reports_are_persisted_and_retrievable(services: BatServices, addon_project: str):
    report = services.validator.validate_project(addon_project)
    latest = services.validator.latest_report(addon_project)
    assert latest.report_id == report.report_id
    fetched = services.validator.get_report(report.report_id)
    assert fetched.project_id == addon_project


def test_single_file_validation(services: BatServices, addon_project: str):
    generated = services.generate_content(addon_project, "entity", {"name": "single"})
    report = services.validator.validate_file(
        addon_project, generated["generated"]["path"], kind="entity"
    )
    assert report.validators_run == ["document:entity"]
    assert not [f for f in report.findings if f.severity == Severity.ERROR.value]
