"""``.mcpack`` builder: a single pack zipped with its manifest at the root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.filesystem import walk_files
from ..core.models import PackKind
from .packaging import zip_directory


def pack_content(pack_dir: Path) -> dict[str, Any]:
    if not pack_dir.exists():
        raise make_error("BAT-BUILD-002", f"Pack directory {pack_dir.name!r} does not exist.")
    manifest = pack_dir / "manifest.json"
    if not manifest.exists():
        raise make_error(
            "BAT-BUILD-002",
            f"Pack {pack_dir.name!r} has no manifest.json, so a valid .mcpack cannot be built.",
        )
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise make_error(
            "BAT-MANIFEST-001",
            f"Pack {pack_dir.name!r} manifest is not valid JSON: {exc.msg}",
        ) from exc
    content = [f for f in walk_files(pack_dir) if f.name != "manifest.json"]
    return {
        "pack_dir": pack_dir,
        "manifest": data,
        "content_files": len(content),
        "header": data.get("header", {}),
    }


def build_mcpack(pack_dir: Path, destination: Path, *, kind: PackKind) -> dict[str, Any]:
    info = pack_content(pack_dir)
    entries = zip_directory(pack_dir, destination, include_hidden=False)
    if "manifest.json" not in entries:
        raise make_error(
            "BAT-ARTIFACT-002", "Built .mcpack does not contain manifest.json at its root."
        )
    return {
        "file": str(destination),
        "kind": kind.value,
        "pack": pack_dir.name,
        "entries": entries,
        "entry_count": len(entries),
        "manifest_header": info["header"],
        "content_files": info["content_files"],
    }
