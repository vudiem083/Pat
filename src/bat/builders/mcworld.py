"""``.mcworld`` builder: the world directory zipped with level.dat at the root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.nbt import NbtError, read_level_dat, unwrap
from .packaging import zip_directory


def world_content(world_dir: Path) -> dict[str, Any]:
    if not world_dir.exists():
        raise make_error("BAT-BUILD-002", "Project has no world directory to export.")
    level_dat = world_dir / "level.dat"
    if not level_dat.exists():
        raise make_error(
            "BAT-WORLD-001",
            "World has no level.dat; Minecraft cannot open this world. Create the world files "
            "first (create_world_project or modify_world_metadata).",
        )
    try:
        metadata = unwrap(read_level_dat(level_dat))
        level_name = metadata.get("LevelName")
    except (NbtError, FileNotFoundError) as exc:
        raise make_error("BAT-WORLD-001", f"level.dat cannot be decoded: {exc}") from exc
    return {
        "world_dir": world_dir,
        "level_name": level_name,
        "has_leveldb": (world_dir / "db").is_dir(),
        "behavior_packs": _read_json_list(world_dir / "world_behavior_packs.json"),
        "resource_packs": _read_json_list(world_dir / "world_resource_packs.json"),
    }


def _read_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def build_mcworld(world_dir: Path, destination: Path) -> dict[str, Any]:
    info = world_content(world_dir)
    entries = zip_directory(world_dir, destination)
    if "level.dat" not in entries:
        raise make_error("BAT-ARTIFACT-002", "Built .mcworld does not contain level.dat.")
    return {
        "file": str(destination),
        "level_name": info["level_name"],
        "has_leveldb": info["has_leveldb"],
        "behavior_packs_bound": len(info["behavior_packs"]),
        "resource_packs_bound": len(info["resource_packs"]),
        "entries": entries,
        "entry_count": len(entries),
    }
