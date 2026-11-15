from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bat.core.nbt import (
    Int,
    ListTag,
    Long,
    NbtError,
    String,
    Byte,
    TAG_INT,
    decode_compound,
    decode_root,
    encode_compound,
    read_level_dat,
    unwrap,
    write_level_dat,
    WorldMetadata,
)


def test_encode_decode_roundtrip():
    document = {
        "name": String("hello"),
        "count": Int(42),
        "big": Long(2**40),
        "flag": Byte(1),
        "list": ListTag((Int(1), Int(2), Int(3)), TAG_INT),
        "nested": {"inner": String("value")},
    }
    root_name, decoded = decode_root(encode_compound(document, "root"))
    assert root_name == "root"
    plain = unwrap(decoded)
    assert plain["name"] == "hello"
    assert plain["count"] == 42
    assert plain["big"] == 2**40
    assert plain["list"] == [1, 2, 3]
    assert plain["nested"]["inner"] == "value"


def test_empty_list_and_empty_compound_roundtrip():
    payload = encode_compound({"empty": ListTag((), 0), "compound": {}})
    decoded = decode_compound(payload)
    assert unwrap(decoded["empty"]) == []
    assert unwrap(decoded["compound"]) == {}


def test_level_dat_has_eight_byte_header_and_le_length(tmp_path: Path):
    path = tmp_path / "level.dat"
    metadata = WorldMetadata(level_name="Header Check", game_type=1)
    write_level_dat(path, metadata)
    raw = path.read_bytes()
    version, length = struct.unpack("<ii", raw[:8])
    assert version == 10
    assert length == len(raw) - 8
    compound = read_level_dat(path)
    assert unwrap(compound)["LevelName"] == "Header Check"


def test_level_dat_roundtrip_matches_written_metadata(tmp_path: Path):
    path = tmp_path / "level.dat"
    metadata = WorldMetadata(
        level_name="Roundtrip", game_type=0, difficulty=3, seed=12345, spawn_y=70
    )
    write_level_dat(path, metadata)
    plain = unwrap(read_level_dat(path))
    assert plain["LevelName"] == "Roundtrip"
    assert plain["GameType"] == 0
    assert plain["Difficulty"] == 3
    assert plain["RandomSeed"] == 12345
    assert plain["SpawnY"] == 70
    assert plain["lastOpenedWithVersion"][0] == 1


def test_corrupt_header_length_detected(tmp_path: Path):
    path = tmp_path / "level.dat"
    write_level_dat(path, WorldMetadata(level_name="Corrupt"))
    raw = bytearray(path.read_bytes())
    raw[4:8] = struct.pack("<i", 999999)
    path.write_bytes(bytes(raw))
    with pytest.raises(NbtError):
        read_level_dat(path)


def test_truncated_file_is_rejected(tmp_path: Path):
    path = tmp_path / "level.dat"
    path.write_bytes(b"\x0a\x00\x00")
    with pytest.raises(NbtError):
        read_level_dat(path)


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_level_dat(tmp_path / "nope.dat")
