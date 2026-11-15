"""Artifact inspection: internal structure, manifests and integrity."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.models import Artifact, ArtifactType


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_archive(path: Path, artifact_type: ArtifactType | str) -> dict[str, Any]:
    if not path.exists():
        raise make_error(
            "BAT-ARTIFACT-001", f"Artifact file is missing: {path.name}", http_status=404
        )
    expected = str(artifact_type)
    result: dict[str, Any] = {
        "artifact_type": expected,
        "file_name": path.name,
        "size_bytes": path.stat().st_size,
        "checksum_sha256": sha256_file(path),
        "valid_zip": False,
        "entries": [],
        "entry_count": 0,
        "manifests": [],
        "problems": [],
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result["valid_zip"] = True
            result["entries"] = sorted(names)
            result["entry_count"] = len(names)
            bad = archive.testzip()
            if bad is not None:
                result["problems"].append(f"Corrupt entry in archive: {bad}")
            for name in names:
                if not name.lower().endswith("manifest.json"):
                    continue
                try:
                    data = json.loads(archive.read(name).decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    result["problems"].append(f"{name} is not readable JSON: {exc}")
                    continue
                result["manifests"].append(
                    {
                        "path": name,
                        "header_name": data.get("header", {}).get("name"),
                        "header_uuid": data.get("header", {}).get("uuid"),
                        "module_types": [
                            m.get("type")
                            for m in data.get("modules", [])
                            if isinstance(m, dict)
                        ],
                    }
                )
    except zipfile.BadZipFile as exc:
        result["problems"].append(f"Not a valid ZIP archive: {exc}")
        return result

    if expected == ArtifactType.MCPACK.value:
        if len(result["manifests"]) != 1:
            result["problems"].append(
                "An .mcpack must contain exactly one pack manifest at its root."
            )
    elif expected == ArtifactType.MCADDON.value:
        if len(result["manifests"]) < 1:
            result["problems"].append("An .mcaddon must contain at least one pack manifest.")
    elif expected == ArtifactType.MCWORLD.value:
        if not any(name == "level.dat" for name in result["entries"]):
            result["problems"].append("An .mcworld must contain level.dat at its root.")
    result["integrity_ok"] = result["valid_zip"] and not result["problems"]
    return result


def verify_artifact(artifact: Artifact) -> dict[str, Any]:
    path = Path(artifact.storage_path)
    reported = inspect_archive(path, artifact.artifact_type)
    checksum_matches = reported["checksum_sha256"] == artifact.checksum
    if not checksum_matches:
        reported["problems"].append(
            "Checksum mismatch: the file on disk differs from the recorded checksum."
        )
        reported["integrity_ok"] = False
    return {
        "artifact_id": artifact.artifact_id,
        "project_id": artifact.project_id,
        "checksum_matches": checksum_matches,
        **reported,
    }
