from __future__ import annotations

import os
from pathlib import Path

import pytest

from bat.core.errors import BatError
from bat.core.filesystem import read_text_file, resolve_within, write_text_file, walk_files


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    directory = tmp_path / "root"
    (directory / "nested").mkdir(parents=True)
    return directory


def test_resolves_relative_path(root: Path):
    assert resolve_within(root, "nested/file.json") == root / "nested" / "file.json"


@pytest.mark.parametrize(
    "attack",
    ["../escape.txt", "nested/../../escape.txt", "/etc/passwd", "nested/../../..", ".."],
)
def test_rejects_traversal_and_absolute_paths(root: Path, attack: str):
    with pytest.raises(BatError) as exc:
        resolve_within(root, attack)
    assert exc.value.code in {"BAT-PATH-001", "BAT-INPUT-001"}


def test_rejects_symlink_escape(root: Path, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "link.txt").symlink_to(outside)
    with pytest.raises(BatError) as exc:
        resolve_within(root, "link.txt")
    assert exc.value.code == "BAT-PATH-004"


def test_missing_file_reports_not_found(root: Path):
    with pytest.raises(BatError) as exc:
        resolve_within(root, "missing.json", must_exist=True)
    assert exc.value.code == "BAT-NOTFOUND-002"
    assert exc.value.http_status == 404


def test_write_is_atomic_and_reads_back(root: Path):
    target = root / "content" / "file.json"
    written = write_text_file(target, '{"a": 1}', max_bytes=1024)
    assert written == 8
    assert read_text_file(target, max_bytes=1024) == '{"a": 1}'
    assert not list(target.parent.glob(".bat-*"))


def test_size_limits_enforced(root: Path):
    with pytest.raises(BatError) as exc:
        write_text_file(root / "big.txt", "x" * 100, max_bytes=10)
    assert exc.value.code == "BAT-PATH-002"
    assert exc.value.http_status == 413


def test_binary_file_rejected(root: Path):
    binary = root / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
    with pytest.raises(BatError) as exc:
        read_text_file(binary, max_bytes=1024)
    assert exc.value.code == "BAT-PATH-003"


def test_walk_files_skips_hidden_and_symlinks(root: Path):
    (root / "a.json").write_text("{}")
    (root / ".hidden.json").write_text("{}")
    (root / "nested" / "b.json").write_text("{}")
    names = [p.name for p in walk_files(root)]
    assert names == ["a.json", "b.json"]


def test_symlink_inside_root_also_rejected(root: Path):
    # Even a symlink that stays inside the root is refused: deterministic behaviour.
    (root / "real.txt").write_text("x")
    (root / "alias.txt").symlink_to(root / "real.txt")
    with pytest.raises(BatError):
        resolve_within(root, "alias.txt")
