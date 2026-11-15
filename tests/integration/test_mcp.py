from __future__ import annotations

import json

import pytest

REQUIRED_TOOLS = {
    # project
    "create_project", "get_project", "list_projects", "delete_project", "get_project_tree",
    "read_project_file", "write_project_file", "get_compatibility",
    # add-on
    "create_addon", "create_entity", "create_block", "create_item", "create_recipe",
    "create_loot_table", "create_spawn_rule", "create_animation",
    "create_animation_controller", "create_particle", "create_attachable",
    "create_script_module",
    # world
    "create_world_project", "inspect_world", "get_world_chunks", "create_structure",
    "import_structure", "export_structure", "modify_world_metadata", "export_mcworld",
    # validation
    "validate_project", "validate_manifest", "validate_entity", "validate_block",
    "validate_texture", "validate_animation", "validate_world", "get_validation_report",
    # build
    "build_project", "build_mcaddon", "build_mcpack", "build_mcworld", "inspect_artifact",
    "download_artifact", "get_build_report",
    # runtime
    "create_test_environment", "install_test_packs", "install_test_world",
    "start_bedrock_server", "stop_bedrock_server", "run_game_test", "execute_test_command",
    "get_runtime_logs", "get_runtime_status", "get_runtime_report",
    "destroy_test_environment",
    # jobs and diagnostics
    "start_runtime_job", "get_job_status", "wait_for_job", "cancel_job", "get_job_logs",
    "get_job_report", "get_runtime_health", "get_runtime_heartbeat", "get_incidents",
    "get_incident_details",
}


async def _call(mcp, name: str, arguments: dict | None = None) -> dict:
    result = await mcp.call_tool(name, arguments or {})
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


async def test_all_documented_tools_are_registered(mcp_server):
    tools = await mcp_server.list_tools()
    names = {tool.name for tool in tools}
    missing = REQUIRED_TOOLS - names
    assert not missing, f"Missing MCP tools: {sorted(missing)}"
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
        assert tool.inputSchema is not None


async def test_create_project_tool_returns_structured_result(mcp_server):
    payload = await _call(
        mcp_server,
        "create_project",
        {"name": "MCP Addon", "project_type": "ADDON", "target_version": "1.21.80"},
    )
    assert payload["ok"] is True
    project = payload["result"]["project"]
    assert project["name"] == "MCP Addon"
    assert len(payload["result"]["packs"]) == 2


async def test_tool_errors_are_structured(mcp_server):
    payload = await _call(
        mcp_server,
        "create_project",
        {"name": "Too Old", "project_type": "ADDON", "target_version": "1.16.0"},
    )
    assert payload["ok"] is False
    assert payload["error"]["error_code"] == "BAT-COMPAT-001"

    missing = await _call(mcp_server, "get_project", {"project_id": "nope"})
    assert missing["ok"] is False
    assert missing["error"]["error_code"] == "BAT-NOTFOUND-001"


async def test_tools_share_business_logic_with_rest(mcp_server, client):
    created = await _call(
        mcp_server, "create_project", {"name": "Parity", "project_type": "ADDON"}
    )
    project_id = created["result"]["project"]["project_id"]

    rest = client.get(f"/api/v1/projects/{project_id}")
    assert rest.status_code == 200
    assert rest.json()["project"]["project_id"] == project_id

    rest_validation = client.post(f"/api/v1/projects/{project_id}/validate").json()
    mcp_validation = await _call(mcp_server, "validate_project", {"project_id": project_id})
    assert mcp_validation["ok"] is True
    assert mcp_validation["result"]["status"] == rest_validation["status"]
    assert mcp_validation["result"]["report_id"] != rest_validation["report_id"]  # separate runs, same contract
    assert set(mcp_validation["result"]) == set(rest_validation)


async def test_generation_and_build_via_mcp(mcp_server):
    project_id = (
        await _call(mcp_server, "create_project", {"name": "Mcp Build", "project_type": "ADDON"})
    )["result"]["project"]["project_id"]

    generated = await _call(
        mcp_server, "create_entity", {"project_id": project_id, "name": "mcp_mob"}
    )
    assert generated["ok"] is True
    assert generated["result"]["generated"]["path"].endswith("entities/mcp_mob.json")

    built = await _call(mcp_server, "build_project", {"project_id": project_id})
    assert built["ok"] is True
    artifact = built["result"]["artifacts"][0]
    assert artifact["integrity_ok"] is True

    inspected = await _call(
        mcp_server, "inspect_artifact", {"artifact_id": artifact["artifact_id"]}
    )
    assert inspected["ok"] is True
    assert inspected["result"]["entry_count"] >= 3


async def test_world_tools_via_mcp(mcp_server):
    project_id = (
        await _call(
            mcp_server,
            "create_world_project",
            {"name": "Mcp World", "target_version": "1.20.0"},
        )
    )["result"]["project"]["project_id"]

    inspection = await _call(mcp_server, "inspect_world", {"project_id": project_id})
    assert inspection["result"]["level_dat_status"] == "OK"

    structure = await _call(
        mcp_server,
        "create_structure",
        {"project_id": project_id, "name": "hut", "size_x": 2, "size_y": 2, "size_z": 2},
    )
    assert structure["ok"] is True
    exported = await _call(
        mcp_server, "export_structure", {"project_id": project_id, "name": "hut"}
    )
    assert exported["result"]["block_count"] == 8

    chunks = await _call(mcp_server, "get_world_chunks", {"project_id": project_id})
    assert chunks["result"]["chunk_data_present"] is False

    built = await _call(mcp_server, "export_mcworld", {"project_id": project_id})
    assert built["result"]["artifacts"][0]["artifact_type"] == "MCWORLD"


async def test_job_tools_via_mcp(mcp_server):
    project_id = (
        await _call(mcp_server, "create_project", {"name": "Mcp Jobs", "project_type": "ADDON"})
    )["result"]["project"]["project_id"]

    started = await _call(
        mcp_server, "start_runtime_job", {"project_id": project_id, "job_type": "VALIDATE"}
    )
    job_id = started["result"]["job"]["job_id"]
    waited = await _call(
        mcp_server, "wait_for_job", {"job_id": job_id, "timeout_seconds": 15}
    )
    assert waited["result"]["completed"] is True

    status = await _call(mcp_server, "get_job_status", {"job_id": job_id})
    assert status["result"]["status"] == "COMPLETED"

    logs = await _call(mcp_server, "get_job_logs", {"job_id": job_id})
    assert logs["result"]["total_lines"] >= 1

    health = await _call(mcp_server, "get_runtime_health")
    assert health["result"]["adapter"]["available"] is False
    assert "jobs" in health["result"]


async def test_resources_and_prompts(mcp_server):
    resources = await mcp_server.list_resources()
    uris = {str(r.uri) for r in resources}
    for expected in (
        "bat://docs/bedrock/versions",
        "bat://docs/bedrock/manifest",
        "bat://docs/bedrock/entities",
        "bat://docs/bedrock/blocks",
        "bat://docs/bedrock/items",
        "bat://docs/bedrock/scripts",
        "bat://docs/bedrock/worlds",
    ):
        assert expected in uris

    versions = await mcp_server.read_resource("bat://docs/bedrock/versions")
    text = versions[0].content if isinstance(versions, list) else str(versions)
    data = json.loads(text)
    assert data["supported_range"]["max"] == "1.21.80"
    assert data["matrix"]["features"]

    templates = await mcp_server.list_resource_templates()
    template_uris = {t.uriTemplate for t in templates}
    assert "bat://projects/{project_id}/tree" in template_uris

    prompts = await mcp_server.list_prompts()
    names = {p.name for p in prompts}
    assert {
        "create_addon_prompt",
        "create_world_prompt",
        "debug_addon_prompt",
        "fix_validation_errors_prompt",
        "analyze_runtime_logs_prompt",
    } <= names


async def test_project_resources_return_live_data(mcp_server, addon_project):
    tree = await mcp_server.read_resource(f"bat://projects/{addon_project}/tree")
    text = tree[0].content if isinstance(tree, list) else str(tree)
    data = json.loads(text)
    assert data["path"] == "."

    report = await mcp_server.read_resource(f"bat://projects/{addon_project}/report")
    text = report[0].content if isinstance(report, list) else str(report)
    data = json.loads(text)
    assert data["project"]["project_id"] == addon_project
    assert data["validation_report"] is None  # nothing validated yet, reported honestly
