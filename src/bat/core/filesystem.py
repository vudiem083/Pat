"""Filesystem helpers with strict containment and size checks.

Every path that originates outside BAT (MCP arguments, REST payloads) must be
resolved through :func:`resolve_within` before any read or write happens.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .errors import make_error


def resolve_within(root: Path, relative: str | Path, *, must_exist: bool = False) -> Path:
    """Resolve ``relative`` inside ``root``, rejecting escapes and symlinks.

    Rejected cases:
      * absolute paths,
      * any ``..`` component,
      * results that leave ``root`` after resolution,
      * existing symlinks (inside or outside the root).
    """
    if relative is None or str(relative).strip() == "":
        raise make_error("BAT-INPUT-001", "A relative path is required.")
    raw = str(relative).replace("\\", "/").strip()
    candidate = Path(raw)
    if candidate.is_absolute() or raw.startswith("/"):
        raise make_error(
            "BAT-PATH-001",
            f"Absolute paths are not allowed: {raw!r}",
            details={"path": raw},
        )
    parts = [p for p in candidate.parts if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise make_error(
            "BAT-PATH-001",
            f"Path traversal is not allowed: {raw!r}",
            details={"path": raw},
        )
    root_resolved = root.resolve()
    target = (root_resolved / Path(*parts)) if parts else root_resolved

    # Reject symlinked components so a project cannot link outside its root.
    probe = root_resolved
    for part in parts:
        probe = probe / part
        if probe.is_symlink():
            raise make_error(
                "BAT-PATH-004",
                f"Symlinks are not allowed in project paths: {raw!r}",
                details={"path": raw, "symlink": str(probe)},
            )
        if not probe.exists():
            break

    try:
        target.resolve().relative_to(root_resolved)
    except ValueError as exc:
        raise make_error(
            "BAT-PATH-001",
            f"Path escapes the allowed root: {raw!r}",
            details={"path": raw, "root": str(root_resolved)},
        ) from exc

    if must_exist and not target.exists():
        raise make_error(
            "BAT-NOTFOUND-002",
            f"File not found: {raw}",
            details={"path": raw},
            http_status=404,
        )
    return target


def relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_text_file(path: Path, *, max_bytes: int) -> str:
    if not path.exists() or not path.is_file():
        raise make_error("BAT-NOTFOUND-002", f"File not found: {path.name}", http_status=404)
    size = path.stat().st_size
    if size > max_bytes:
        raise make_error(
            "BAT-PATH-002",
            f"File is {size} bytes which exceeds the {max_bytes} byte limit.",
            details={"size_bytes": size, "max_bytes": max_bytes},
            http_status=413,
        )
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise make_error(
            "BAT-PATH-003",
            f"File {path.name!r} is not valid UTF-8 text.",
            details={"path": path.name},
        ) from exc


def write_text_file(path: Path, content: str, *, max_bytes: int) -> int:
    encoded = content.encode("utf-8")
    if len(encoded) > max_bytes:
        raise make_error(
            "BAT-PATH-002",
            f"Content is {len(encoded)} bytes which exceeds the {max_bytes} byte limit.",
            details={"size_bytes": len(encoded), "max_bytes": max_bytes},
            http_status=413,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace so a crash never leaves a half-written project file.
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".bat-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return len(encoded)


def walk_files(root: Path, *, suffix: str | None = None) -> list[Path]:
    """Return regular files under ``root`` (deterministic order, no symlinks)."""
    if not root.exists():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if suffix and not name.endswith(suffix):
                continue
            path = Path(dirpath) / name
            if path.is_symlink() or not path.is_file():
                continue
            found.append(path)
    return found


def human_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
