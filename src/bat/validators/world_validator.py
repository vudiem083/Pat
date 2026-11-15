"""World validation: level.dat, world name, pack bindings."""

from __future__ import annotations

import json
import uuid

from ..core.models import Finding, Severity
from ..core.nbt import NbtError, read_level_dat, unwrap
from .base import ValidationContext, finding


def validate_world(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    world_dir = context.files_root / "world"
    if not world_dir.exists():
        findings.append(
            finding(
                "BAT-WORLD-001",
                Severity.ERROR,
                "World directory is missing from a WORLD/COMBINED project.",
                file_path="world",
            )
        )
        return findings

    level_dat = world_dir / "level.dat"
    if not level_dat.exists():
        findings.append(
            finding(
                "BAT-WORLD-001",
                Severity.ERROR,
                "world/level.dat is missing; Minecraft will not load this world.",
                file_path="world/level.dat",
            )
        )
    else:
        try:
            compound = unwrap(read_level_dat(level_dat))
            name = compound.get("LevelName")
            if not isinstance(name, str) or not name.strip():
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.ERROR,
                        "world/level.dat has no usable LevelName.",
                        file_path="world/level.dat",
                    )
                )
            storage_version = compound.get("__storage_version")
            if not isinstance(storage_version, int) or storage_version < 1:
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.WARNING,
                        f"world/level.dat has an unusual storage version {storage_version!r}.",
                        file_path="world/level.dat",
                    )
                )
            game_type = compound.get("GameType")
            if not isinstance(game_type, int) or game_type not in (0, 1, 2, 6):
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.WARNING,
                        f"world/level.dat GameType {game_type!r} is not a known game mode.",
                        file_path="world/level.dat",
                    )
                )
            difficulty = compound.get("Difficulty")
            if isinstance(difficulty, int) and not 0 <= difficulty <= 3:
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.ERROR,
                        f"world/level.dat Difficulty {difficulty} is out of range 0-3.",
                        file_path="world/level.dat",
                    )
                )
        except (NbtError, FileNotFoundError) as exc:
            findings.append(
                finding(
                    "BAT-WORLD-001",
                    Severity.ERROR,
                    f"world/level.dat cannot be decoded: {exc}",
                    file_path="world/level.dat",
                )
            )

    if (world_dir / "levelname.txt").exists():
        text = (world_dir / "levelname.txt").read_text(encoding="utf-8").strip()
        if not text:
            findings.append(
                finding(
                    "BAT-WORLD-001",
                    Severity.WARNING,
                    "world/levelname.txt is empty.",
                    file_path="world/levelname.txt",
                )
            )

    known_pack_uuids = _known_pack_uuids(context)
    for filename, kind in (
        ("world_behavior_packs.json", "behavior"),
        ("world_resource_packs.json", "resource"),
    ):
        path = world_dir / filename
        if not path.exists():
            findings.append(
                finding(
                    "BAT-WORLD-001",
                    Severity.WARNING,
                    f"world/{filename} is missing; the world will load without {kind} packs.",
                    file_path=f"world/{filename}",
                )
            )
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                finding(
                    "BAT-JSON-001",
                    Severity.ERROR,
                    f"world/{filename} is not valid JSON: {exc.msg}",
                    file_path=f"world/{filename}",
                    line_number=exc.lineno,
                )
            )
            continue
        if not isinstance(data, list):
            findings.append(
                finding(
                    "BAT-WORLD-001",
                    Severity.ERROR,
                    f"world/{filename} must be a list of pack references.",
                    file_path=f"world/{filename}",
                )
            )
            continue
        for index, entry in enumerate(data):
            if not isinstance(entry, dict) or not isinstance(entry.get("pack_id"), str):
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.ERROR,
                        f"world/{filename}[{index}] needs a 'pack_id' UUID.",
                        file_path=f"world/{filename}",
                    )
                )
                continue
            try:
                uuid.UUID(entry["pack_id"])
            except ValueError:
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.ERROR,
                        f"world/{filename}[{index}] pack_id is not a valid UUID.",
                        file_path=f"world/{filename}",
                    )
                )
                continue
            if known_pack_uuids and entry["pack_id"].lower() not in known_pack_uuids:
                findings.append(
                    finding(
                        "BAT-WORLD-001",
                        Severity.WARNING,
                        f"world/{filename}[{index}] references a pack that is not part of this "
                        "project. The world will show a missing-dependency prompt unless the pack "
                        "is installed separately.",
                        file_path=f"world/{filename}",
                    )
                )
    return findings


def _known_pack_uuids(context: ValidationContext) -> set[str]:
    uuids: set[str] = set()
    for path in list(context.files_root.glob("behavior_packs/*/manifest.json")) + list(
        context.files_root.glob("resource_packs/*/manifest.json")
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        header = data.get("header", {})
        if isinstance(header, dict) and isinstance(header.get("uuid"), str):
            uuids.add(header["uuid"].lower())
    return uuids
