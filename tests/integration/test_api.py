from __future__ import annotations

import io
import json
import zipfile


def test_health_and_version(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] in {"OK", "DEGRADED"}
    assert body["version"]
    assert "runtime" in body["checks"]

    version = client.get("/api/v1/version").json()
    assert version["supported_minecraft"] == {"edition": "Bedrock", "min": "1.19.0", "max": "1.21.80"}
    assert set(version["interfaces"]) == {"MCP", "REST"}


def test_openapi_documents_endpoints(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for expected in (
        "/api/v1/projects",
        "/api/v1/projects/{project_id}/validate",
        "/api/v1/projects/{project_id}/build",
        "/api/v1/artifacts/{artifact_id}/download",
        "/api/v1/jobs",
        "/api/v1/incidents",
        "/api/v1/runtime/health",
    ):
        assert expected in paths


def test_project_lifecycle_over_rest(client):
    created = client.post(
        "/api/v1/projects",
        json={"name": "API Addon", "project_type": "ADDON", "target_version": "1.21.80"},
    )
    assert created.status_code == 201
    project_id = created.json()["project"]["project_id"]

    listing = client.get("/api/v1/projects").json()
    assert listing["total"] == 1
    assert listing["items"][0]["project_id"] == project_id

    fetched = client.get(f"/api/v1/projects/{project_id}").json()
    assert fetched["project"]["name"] == "API Addon"
    assert len(fetched["packs"]) == 2

    write = client.put(
        f"/api/v1/projects/{project_id}/files/behavior_packs/x/notes.json",
        json={"content": '{"hello": "world"}'},
    )
    assert write.status_code == 200
    assert write.json()["created"] is True

    read = client.get(f"/api/v1/projects/{project_id}/files/behavior_packs/x/notes.json")
    assert read.json()["content"] == '{"hello": "world"}'

    tree = client.get(f"/api/v1/projects/{project_id}/tree").json()
    assert tree["type"] == "dir"

    validation = client.post(f"/api/v1/projects/{project_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["status"] in {"PASS", "WARN", "FAIL"}

    report = client.get(f"/api/v1/projects/{project_id}/validation-report")
    assert report.status_code == 200

    deleted = client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_build_and_download_artifact(client):
    project_id = client.post(
        "/api/v1/projects", json={"name": "Build Me", "project_type": "ADDON"}
    ).json()["project"]["project_id"]
    built = client.post(f"/api/v1/projects/{project_id}/build", json={})
    assert built.status_code == 200
    artifacts = built.json()["artifacts"]
    assert artifacts[0]["artifact_type"] == "MCADDON"
    artifact_id = artifacts[0]["artifact_id"]

    inspection = client.get(f"/api/v1/artifacts/{artifact_id}").json()
    assert inspection["integrity_ok"] is True
    assert inspection["checksum_matches"] is True

    download = client.get(f"/api/v1/artifacts/{artifact_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert any(name.endswith("manifest.json") for name in archive.namelist())

    report = client.get(f"/api/v1/artifacts/{artifact_id}/report")
    assert report.status_code == 200


def test_world_endpoints(client):
    project_id = client.post(
        "/api/v1/projects",
        json={"name": "API World", "project_type": "WORLD", "target_version": "1.20.0"},
    ).json()["project"]["project_id"]

    inspection = client.get(f"/api/v1/runtime/worlds/{project_id}").json()
    assert inspection["level_dat_status"] == "OK"

    metadata = client.patch(
        f"/api/v1/runtime/worlds/{project_id}/metadata",
        json={"level_name": "Renamed via API", "game_mode": "survival"},
    )
    assert metadata.status_code == 200
    assert metadata.json()["verified"] is True
    assert metadata.json()["metadata"]["LevelName"] == "Renamed via API"

    structure = client.post(
        f"/api/v1/runtime/worlds/{project_id}/structures",
        json={"name": "tower", "size": [2, 2, 2]},
    )
    assert structure.status_code == 201
    assert structure.json()["path"].endswith("tower.mcstructure")

    listed = client.get(f"/api/v1/runtime/worlds/{project_id}/structures").json()
    assert listed["total"] == 1

    chunks = client.get(f"/api/v1/runtime/worlds/{project_id}/chunks").json()
    assert chunks["chunk_data_present"] is False
    assert "LevelDB" in chunks["notes"]


def test_content_generation_endpoint(client):
    project_id = client.post(
        "/api/v1/projects", json={"name": "Gen API", "project_type": "ADDON"}
    ).json()["project"]["project_id"]
    response = client.post(
        f"/api/v1/projects/{project_id}/content/entity", json={"spec": {"name": "api_mob"}}
    )
    assert response.status_code == 201
    assert response.json()["generated"]["path"].endswith("entities/api_mob.json")

    generators = client.get(f"/api/v1/projects/{project_id}/content").json()
    assert "entity" in generators["generators"]

    # A malformed spec is caller error, not a 500 with an internal traceback.
    bad = client.post(f"/api/v1/projects/{project_id}/content/item", json={"spec": {}})
    assert bad.status_code == 400
    error = bad.json()["error"]
    assert error["error_code"] == "BAT-INPUT-001"
    assert error["details"]["generator"] == "item"
    assert error["details"]["received"] == []


def test_job_flow_over_rest(client):
    project_id = client.post(
        "/api/v1/projects", json={"name": "Job API", "project_type": "ADDON"}
    ).json()["project"]["project_id"]
    created = client.post(
        "/api/v1/jobs", json={"job_type": "VALIDATE", "project_id": project_id}
    )
    assert created.status_code == 202
    job_id = created.json()["job"]["job_id"]

    waited = client.post(f"/api/v1/jobs/{job_id}/wait", json={"timeout": 15})
    assert waited.status_code == 200
    assert waited.json()["completed"] is True
    assert waited.json()["job"]["status"] == "COMPLETED"

    logs = client.get(f"/api/v1/jobs/{job_id}/logs").json()
    assert logs["total_lines"] >= 1
    report = client.get(f"/api/v1/jobs/{job_id}/report").json()
    assert report["job_id"] == job_id


def test_runtime_test_without_server_is_not_tested(client):
    project_id = client.post(
        "/api/v1/projects", json={"name": "No Runtime", "project_type": "ADDON"}
    ).json()["project"]["project_id"]
    created = client.post(
        "/api/v1/jobs",
        json={"job_type": "RUNTIME_TEST", "project_id": project_id},
    )
    job_id = created.json()["job"]["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/wait", json={"timeout": 20})
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "FAILED"
    assert job["error_code"] == "BAT-RUNTIME-003"
    assert job["result"]["test_status"] == "NOT_TESTED"


def test_error_responses_use_bat_codes(client):
    missing = client.get("/api/v1/projects/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["error_code"] == "BAT-NOTFOUND-001"

    invalid = client.post("/api/v1/projects", json={"project_type": "ADDON"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["error_code"] == "BAT-INPUT-001"

    bad_version = client.post(
        "/api/v1/projects", json={"name": "Old", "target_version": "1.8.0"}
    )
    assert bad_version.status_code == 400
    assert bad_version.json()["error"]["error_code"] == "BAT-COMPAT-001"

    duplicate = client.post("/api/v1/projects", json={"name": "Dup"})
    client.post("/api/v1/projects", json={"name": "Dup"})
    assert duplicate.status_code in {201, 400, 409}


def test_compatibility_and_error_code_endpoints(client):
    matrix = client.get("/api/v1/compatibility?version=1.19.0").json()
    assert matrix["target_version"] == "1.19.0"
    assert sum(matrix["counts"].values()) == len(matrix["features"])

    codes = client.get("/api/v1/error-codes").json()["codes"]
    assert any(c["code"] == "BAT-RUNTIME-001" for c in codes)
    profiles = client.get("/api/v1/compatibility/profiles").json()["profiles"]
    assert profiles[0]["target_version"] == "1.19.0"


def test_api_key_enforced(api_key_client):
    assert api_key_client.get("/api/v1/projects").status_code == 401
    assert (
        api_key_client.get(
            "/api/v1/projects", headers={"X-API-Key": "secret-key-for-tests"}
        ).status_code
        == 200
    )
    assert (
        api_key_client.get(
            "/api/v1/projects", headers={"Authorization": "Bearer secret-key-for-tests"}
        ).status_code
        == 200
    )
    assert api_key_client.get("/api/v1/health").status_code == 200  # health stays open


def test_incident_endpoints(client, services, addon_project):
    from bat.core.models import IncidentType

    incident = services.incidents.create(
        incident_type=IncidentType.PROCESS_CRASH,
        summary="crashed in test",
        project_id=addon_project,
    )
    listing = client.get("/api/v1/incidents", params={"project_id": addon_project}).json()
    assert listing["total"] == 1
    details = client.get(f"/api/v1/incidents/{incident.incident_id}").json()
    assert details["incident"]["incident_id"] == incident.incident_id
    links = client.get(f"/api/v1/incidents/{incident.incident_id}/links").json()
    assert links["project"]["project_id"] == addon_project
    diagnosed = client.post(f"/api/v1/incidents/{incident.incident_id}/diagnose")
    assert diagnosed.status_code == 200
    assert client.get("/api/v1/incidents/nope").status_code == 404


def test_missing_file_and_path_rejection(client, addon_project):
    missing = client.get(f"/api/v1/projects/{addon_project}/files/nope.json")
    assert missing.status_code == 404
    assert missing.json()["error"]["error_code"] == "BAT-NOTFOUND-002"

    absolute = client.put(
        f"/api/v1/projects/{addon_project}/files//etc/passwd", json={"content": "x"}
    )
    assert absolute.status_code in {400, 404, 405}
