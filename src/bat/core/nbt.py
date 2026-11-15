"""Minimal little-endian NBT codec plus Bedrock ``level.dat`` read/write.

Facts this module encodes (per the Minecraft Wiki "Bedrock Edition level format"
and the Bedrock Wiki NBT notes):

* ``level.dat`` is **uncompressed little-endian NBT** preceded by an 8-byte
  header: a little-endian int32 storage version (modern saves use 10) and a
  little-endian int32 payload length that excludes the header.
* Strings carry a 2-byte little-endian length prefix.
* Numbers are fixed width little-endian; Bedrock does *not* use varints inside
  ``level.dat`` (varints appear in LevelDB/protocol payloads, not this file).

BAT only writes fields it can set honestly. Chunk terrain, entities and any
field the game owns are produced by Minecraft when the world is first loaded;
BAT does not fabricate them.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

LEVEL_DAT_STORAGE_VERSION = 10


class NbtError(ValueError):
    """Raised when NBT bytes cannot be decoded."""


# --------------------------------------------------------------------------- #
# Typed values
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Byte:
    value: int
    tag = TAG_BYTE


@dataclass(frozen=True)
class Short:
    value: int
    tag = TAG_SHORT


@dataclass(frozen=True)
class Int:
    value: int
    tag = TAG_INT


@dataclass(frozen=True)
class Long:
    value: int
    tag = TAG_LONG


@dataclass(frozen=True)
class Float:
    value: float
    tag = TAG_FLOAT


@dataclass(frozen=True)
class Double:
    value: float
    tag = TAG_DOUBLE


@dataclass(frozen=True)
class ByteArray:
    value: bytes
    tag = TAG_BYTE_ARRAY


@dataclass(frozen=True)
class String:
    value: str
    tag = TAG_STRING


@dataclass(frozen=True)
class IntArray:
    value: tuple[int, ...]
    tag = TAG_INT_ARRAY


@dataclass(frozen=True)
class LongArray:
    value: tuple[int, ...]
    tag = TAG_LONG_ARRAY


@dataclass(frozen=True)
class ListTag:
    value: tuple[Any, ...]
    element_tag: int
    tag = TAG_LIST


TYPED_TAGS = (Byte, Short, Int, Long, Float, Double, ByteArray, String, IntArray, LongArray)


# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #
def _string_bytes(text: str) -> bytes:
    data = text.encode("utf-8")
    if len(data) > 0x7FFF:
        raise NbtError("NBT string exceeds 32767 bytes")
    return struct.pack("<H", len(data)) + data


def _encode_payload(value: Any, out: bytearray) -> None:
    if isinstance(value, Byte):
        out += struct.pack("<b", _clamp(value.value, -128, 127))
    elif isinstance(value, Short):
        out += struct.pack("<h", _clamp(value.value, -32768, 32767))
    elif isinstance(value, Int):
        out += struct.pack("<i", _clamp(value.value, -(2**31), 2**31 - 1))
    elif isinstance(value, Long):
        out += struct.pack("<q", _clamp(value.value, -(2**63), 2**63 - 1))
    elif isinstance(value, Float):
        out += struct.pack("<f", float(value.value))
    elif isinstance(value, Double):
        out += struct.pack("<d", float(value.value))
    elif isinstance(value, ByteArray):
        out += struct.pack("<i", len(value.value)) + value.value
    elif isinstance(value, String):
        out += _string_bytes(value.value)
    elif isinstance(value, IntArray):
        out += struct.pack("<i", len(value.value))
        for item in value.value:
            out += struct.pack("<i", _clamp(int(item), -(2**31), 2**31 - 1))
    elif isinstance(value, LongArray):
        out += struct.pack("<i", len(value.value))
        for item in value.value:
            out += struct.pack("<q", _clamp(int(item), -(2**63), 2**63 - 1))
    elif isinstance(value, ListTag):
        out += struct.pack("<b", value.element_tag)
        if value.element_tag == TAG_END:
            out += struct.pack("<i", 0)
            return
        out += struct.pack("<i", len(value.value))
        for item in value.value:
            _encode_payload(item, out)
    elif isinstance(value, dict):
        for name, child in value.items():
            tag = _tag_of(child)
            out += struct.pack("<b", tag)
            out += _string_bytes(name)
            _encode_payload(child, out)
        out += struct.pack("<b", TAG_END)
    elif isinstance(value, list):
        element_tag = TAG_END
        if value:
            element_tag = _tag_of(value[0])
            for item in value[1:]:
                if _tag_of(item) != element_tag:
                    raise NbtError("NBT lists must be homogeneous")
        _encode_payload(ListTag(tuple(value), element_tag), out)
    else:
        raise NbtError(f"Cannot encode {type(value).__name__} as NBT (use a typed value)")


def _clamp(value: int, low: int, high: int) -> int:
    if not low <= value <= high:
        raise NbtError(f"Value {value} outside NBT range [{low}, {high}]")
    return value


def _tag_of(value: Any) -> int:
    tag = getattr(value, "tag", None)
    if isinstance(tag, int):
        return tag
    if isinstance(value, dict):
        return TAG_COMPOUND
    if isinstance(value, list):
        return TAG_LIST
    raise NbtError(f"Cannot determine NBT tag for {type(value).__name__}")


def encode_compound(root: dict[str, Any], root_name: str = "") -> bytes:
    """Encode a root compound (with its root name) to NBT bytes."""
    out = bytearray()
    out += struct.pack("<b", TAG_COMPOUND)
    out += _string_bytes(root_name)
    _encode_payload(root, out)
    return bytes(out)


# --------------------------------------------------------------------------- #
# Decoding
# --------------------------------------------------------------------------- #
class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def read(self, size: int) -> bytes:
        end = self.pos + size
        if end > len(self.data):
            raise NbtError("Unexpected end of NBT data")
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def unpack(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read(size))[0]

    def string(self) -> str:
        length = self.unpack("<H")
        return self.read(length).decode("utf-8", errors="replace")


def _decode_payload(reader: _Reader, tag: int) -> Any:
    if tag == TAG_BYTE:
        return Byte(reader.unpack("<b"))
    if tag == TAG_SHORT:
        return Short(reader.unpack("<h"))
    if tag == TAG_INT:
        return Int(reader.unpack("<i"))
    if tag == TAG_LONG:
        return Long(reader.unpack("<q"))
    if tag == TAG_FLOAT:
        return Float(reader.unpack("<f"))
    if tag == TAG_DOUBLE:
        return Double(reader.unpack("<d"))
    if tag == TAG_BYTE_ARRAY:
        length = reader.unpack("<i")
        return ByteArray(reader.read(length))
    if tag == TAG_STRING:
        return String(reader.string())
    if tag == TAG_LIST:
        element_tag = reader.unpack("<b")
        length = reader.unpack("<i")
        if element_tag == TAG_END:
            return ListTag((), TAG_END)
        items = tuple(_decode_payload(reader, element_tag) for _ in range(length))
        return ListTag(items, element_tag)
    if tag == TAG_COMPOUND:
        result: dict[str, Any] = {}
        while True:
            child_tag = reader.unpack("<b")
            if child_tag == TAG_END:
                return result
            name = reader.string()
            result[name] = _decode_payload(reader, child_tag)
    if tag == TAG_INT_ARRAY:
        length = reader.unpack("<i")
        return IntArray(tuple(reader.unpack("<i") for _ in range(length)))
    if tag == TAG_LONG_ARRAY:
        length = reader.unpack("<i")
        return LongArray(tuple(reader.unpack("<q") for _ in range(length)))
    raise NbtError(f"Unknown NBT tag id {tag}")


def decode_root(data: bytes) -> tuple[str, dict[str, Any]]:
    """Decode raw NBT bytes into ``(root_name, compound)``."""
    reader = _Reader(data)
    tag = reader.unpack("<b")
    if tag != TAG_COMPOUND:
        raise NbtError(f"Root tag must be TAG_Compound, got {tag}")
    name = reader.string()
    payload = _decode_payload(reader, TAG_COMPOUND)
    return name, payload


def decode_compound(data: bytes) -> dict[str, Any]:
    return decode_root(data)[1]


# --------------------------------------------------------------------------- #
# level.dat
# --------------------------------------------------------------------------- #
@dataclass
class WorldMetadata:
    level_name: str
    game_type: int = 1
    difficulty: int = 1
    seed: int = 0
    spawn_x: int = 0
    spawn_y: int = 64
    spawn_z: int = 0
    target_version: str = "1.21.80"
    generated_by: str = "BAT"
    commands_enabled: bool = True
    time: int = 0

    def as_compound(self) -> dict[str, Any]:
        parts = [int(p) for p in self.target_version.split(".") if p.isdigit()]
        while len(parts) < 4:
            parts.append(0)
        return {
            "LevelName": String(self.level_name),
            "GameType": Int(self.game_type),
            "Difficulty": Int(self.difficulty),
            "RandomSeed": Long(self.seed),
            "SpawnX": Int(self.spawn_x),
            "SpawnY": Int(self.spawn_y),
            "SpawnZ": Int(self.spawn_z),
            "Time": Long(self.time),
            "StorageVersion": Int(LEVEL_DAT_STORAGE_VERSION),
            "WorldVersion": Int(1),
            "Generator": Int(1),
            "commandsEnabled": Byte(1 if self.commands_enabled else 0),
            "isCreated": Byte(1),
            "experiments": {},
            "MinimumCompatibleClientVersion": ListTag(
                tuple(Int(p) for p in parts[:4]), TAG_INT
            ),
            "lastOpenedWithVersion": ListTag(tuple(Int(p) for p in parts[:4]), TAG_INT),
            "InventoryVersion": String(self.target_version),
            "CreatedBy": String(self.generated_by),
        }


def write_level_dat(path: Path, metadata: WorldMetadata) -> None:
    """Write an uncompressed little-endian ``level.dat`` with an 8-byte header."""
    payload = encode_compound(metadata.as_compound())
    header = struct.pack("<ii", LEVEL_DAT_STORAGE_VERSION, len(payload))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".dat.tmp")
    tmp.write_bytes(header + payload)
    tmp.replace(path)


def read_level_dat(path: Path) -> dict[str, Any]:
    """Read and decode a Bedrock ``level.dat``.

    Handles the 8-byte header, older zlib-compressed payloads (detected by the
    zlib magic byte rather than assumed) and version mismatches, which are
    reported instead of silently ignored.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    raw = path.read_bytes()
    if len(raw) < 8:
        raise NbtError(f"level.dat is too small ({len(raw)} bytes)")
    version, length = struct.unpack("<ii", raw[:8])
    payload = raw[8:]
    if payload[:1] == b"\x78":
        try:
            payload = zlib.decompress(payload)
        except zlib.error as exc:  # pragma: no cover - defensive
            raise NbtError(f"level.dat payload looks zlib-compressed but failed: {exc}") from exc
    if length and length != len(payload):
        raise NbtError(
            f"level.dat header length {length} does not match payload size {len(payload)}"
        )
    _, compound = decode_root(payload)
    compound["__storage_version"] = Int(version)
    return compound


def unwrap(value: Any) -> Any:
    """Convert NBT typed values into plain Python values."""
    tag = getattr(value, "tag", None)
    if tag in (TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG, TAG_FLOAT, TAG_DOUBLE):
        return value.value
    if tag == TAG_STRING:
        return value.value
    if tag == TAG_BYTE_ARRAY:
        return value.value
    if tag in (TAG_INT_ARRAY, TAG_LONG_ARRAY):
        return list(value.value)
    if tag == TAG_LIST:
        return [unwrap(item) for item in value.value]
    if isinstance(value, dict):
        return {key: unwrap(child) for key, child in value.items()}
    return value
