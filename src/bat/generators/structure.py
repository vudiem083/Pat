"""Bedrock ``.mcstructure`` generation, import and export.

A structure file is NBT with:

    format_version: Int(1)
    size: List[Int, Int, Int]
    structure: {
        block_indices: List[List[Int], List[Int]]   # layer 0 and layer 1
        entities: List
        palette: {default: {block_palette: List[Compound], block_position_data: Compound}}
    }
    structure_world_origin: List[Int, Int, Int]

BAT fills structures with a single block type so the palette/indices pairing is
unambiguous, and verifies its own output by decoding it again.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.models import GeneratedFile, PackKind, Project, ProjectType
from ..core.nbt import (
    Int,
    ListTag,
    NbtError,
    String,
    TAG_COMPOUND,
    TAG_INT,
    decode_root,
    encode_compound,
    unwrap,
)
from ..core.projects import ProjectManager


def build_structure_bytes(
    *,
    size: tuple[int, int, int],
    block: str = "minecraft:stone",
    block_states: dict[str, Any] | None = None,
    origin: tuple[int, int, int] = (0, 0, 0),
    air: str = "minecraft:air",
) -> bytes:
    sx, sy, sz = size
    if not (1 <= sx <= 64 and 1 <= sy <= 64 and 1 <= sz <= 64):
        raise make_error(
            "BAT-INPUT-001", "Structure dimensions must each be between 1 and 64 blocks."
        )
    if ":" not in block:
        raise make_error("BAT-INPUT-001", "Block must be a namespaced id such as minecraft:stone.")
    total = sx * sy * sz
    palette = [
        {"name": String(air), "states": {}},
        {"name": String(block), "states": _states_compound(block_states)},
    ]
    # Layer 0 holds the filled block, layer 1 is unused (-1 means "no block").
    layer0 = ListTag(tuple(Int(1) for _ in range(total)), TAG_INT)
    layer1 = ListTag(tuple(Int(-1) for _ in range(total)), TAG_INT)
    document: dict[str, Any] = {
        "format_version": Int(1),
        "size": ListTag(tuple(Int(v) for v in size), TAG_INT),
        "structure": {
            "block_indices": ListTag((layer0, layer1), 9),
            "entities": ListTag((), 0),
            "palette": {
                "default": {
                    "block_palette": ListTag(
                        tuple(_block_entry(item) for item in palette), TAG_COMPOUND
                    ),
                    "block_position_data": {},
                }
            },
        },
        "structure_world_origin": ListTag(tuple(Int(v) for v in origin), TAG_INT),
    }
    return encode_compound(document)


def _states_compound(states: dict[str, Any] | None) -> dict[str, Any]:
    from ..core.nbt import Byte, String as NbtString

    result: dict[str, Any] = {}
    for key, value in (states or {}).items():
        if isinstance(value, bool):
            result[str(key)] = Byte(1 if value else 0)
        elif isinstance(value, int):
            result[str(key)] = Int(value)
        else:
            result[str(key)] = NbtString(str(value))
    return result


def _block_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {"name": entry["name"], "states": entry.get("states", {})}


def parse_structure_bytes(data: bytes) -> dict[str, Any]:
    try:
        _, compound = decode_root(data)
    except NbtError as exc:
        raise make_error("BAT-WORLD-001", f"File is not a valid .mcstructure (NBT): {exc}") from exc
    plain = unwrap(compound)
    if "size" not in plain or "structure" not in plain:
        raise make_error(
            "BAT-WORLD-001",
            "NBT file is missing 'size' or 'structure' — not a Bedrock structure.",
        )
    size = plain.get("size")
    if not isinstance(size, list) or len(size) != 3:
        raise make_error("BAT-WORLD-001", "Structure 'size' must be a list of three integers.")
    palette = (
        plain.get("structure", {}).get("palette", {}).get("default", {}).get("block_palette", [])
    )
    indices = plain.get("structure", {}).get("block_indices", [])
    expected = size[0] * size[1] * size[2]
    layer0 = indices[0] if indices else []
    return {
        "size": size,
        "block_count": expected,
        "palette_size": len(palette),
        "palette": [entry.get("name") for entry in palette if isinstance(entry, dict)],
        "indices_match_size": len(layer0) == expected,
        "entities": len(plain.get("structure", {}).get("entities", []) or []),
        "format_version": plain.get("format_version"),
        "world_origin": plain.get("structure_world_origin"),
        "checksum_sha256": hashlib.sha256(data).hexdigest(),
    }


class StructureGenerator:
    def __init__(self, projects: ProjectManager) -> None:
        self.projects = projects

    def _structures_dir(self, project: Project) -> Path:
        if ProjectType(project.project_type) not in (ProjectType.WORLD, ProjectType.COMBINED):
            raise make_error(
                "BAT-PROJECT-003",
                "Structures require a WORLD or COMBINED project.",
                http_status=409,
            )
        world = self.projects.ensure_world_dir(project.project_id)
        structures = world / "structures"
        structures.mkdir(parents=True, exist_ok=True)
        return structures

    def create(
        self,
        project_id: str,
        *,
        name: str,
        size: tuple[int, int, int] | list[int] = (4, 4, 4),
        block: str = "minecraft:stone",
        origin: tuple[int, int, int] | list[int] = (0, 0, 0),
    ) -> GeneratedFile:
        project = self.projects.require_active(self.projects.get(project_id))
        if len(size) != 3 or len(origin) != 3:
            raise make_error("BAT-INPUT-001", "size and origin must each have three integers.")
        safe = "".join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c in "_-")
        if not safe:
            raise make_error("BAT-INPUT-001", "Structure name must contain alphanumerics.")
        data = build_structure_bytes(
            size=(int(size[0]), int(size[1]), int(size[2])),
            block=block,
            origin=(int(origin[0]), int(origin[1]), int(origin[2])),
        )
        target = self._structures_dir(project) / f"{safe}.mcstructure"
        target.write_bytes(data)
        self.projects.touch(project)
        info = parse_structure_bytes(data)
        return GeneratedFile(
            path=target.relative_to(self.projects.files_root(project_id)).as_posix(),
            kind="world.structure",
            description=(
                f"Structure {safe} ({info['size'][0]}x{info['size'][1]}x{info['size'][2]}, "
                f"{info['block_count']} blocks of {block})"
            ),
        )

    def import_structure(self, project_id: str, *, name: str, data: bytes) -> dict[str, Any]:
        project = self.projects.require_active(self.projects.get(project_id))
        info = parse_structure_bytes(data)
        safe = "".join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c in "_-")
        if not safe:
            raise make_error("BAT-INPUT-001", "Structure name must contain alphanumerics.")
        target = self._structures_dir(project) / f"{safe}.mcstructure"
        target.write_bytes(data)
        self.projects.touch(project)
        return {
            "path": target.relative_to(self.projects.files_root(project_id)).as_posix(),
            "name": safe,
            **info,
        }

    def export_structure(
        self, project_id: str, *, name: str, destination: Path
    ) -> dict[str, Any]:
        project = self.projects.get(project_id)
        source = self._structures_dir(project) / f"{name}.mcstructure"
        if not source.exists():
            raise make_error(
                "BAT-NOTFOUND-007",
                f"Structure {name!r} was not found in this project.",
                http_status=404,
            )
        data = source.read_bytes()
        info = parse_structure_bytes(data)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return {"exported_to": str(destination), "name": name, **info}

    def list_structures(self, project_id: str) -> list[dict[str, Any]]:
        project = self.projects.get(project_id)
        if ProjectType(project.project_type) not in (ProjectType.WORLD, ProjectType.COMBINED):
            return []
        directory = self.projects.ensure_world_dir(project_id) / "structures"
        if not directory.exists():
            return []
        result = []
        for path in sorted(directory.glob("*.mcstructure")):
            try:
                info = parse_structure_bytes(path.read_bytes())
                result.append({"name": path.stem, "valid": True, **info})
            except Exception as exc:  # noqa: BLE001 - report corruption, do not hide it
                result.append({"name": path.stem, "valid": False, "error": str(exc)})
        return result
