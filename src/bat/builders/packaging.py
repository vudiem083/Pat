"""Deterministic ZIP packaging helpers shared by all artifact builders."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ..core.errors import make_error
from ..core.filesystem import walk_files


def zip_directory(
    source: Path,
    destination: Path,
    *,
    arc_prefix: str = "",
    include_hidden: bool = False,
) -> list[str]:
    """Zip ``source`` into ``destination`` and return the archived entry names.

    Skips symlinks, editor backup files created by BAT (``*.bak``) and empty
    directories. Entries are written in sorted order so identical projects
    produce stable archives.
    """
    if not source.exists() or not source.is_dir():
        raise make_error(
            "BAT-BUILD-001",
            f"Cannot package {source.name!r}: directory does not exist.",
            details={"source": str(source)},
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    tmp = destination.with_suffix(destination.suffix + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in walk_files(source):
                name = path.name
                if name.endswith(".bak") or name.startswith(".bat-"):
                    continue
                if name.startswith(".") and not include_hidden:
                    continue
                relative = path.relative_to(source).as_posix()
                arcname = f"{arc_prefix.rstrip('/')}/{relative}" if arc_prefix else relative
                archive.write(path, arcname)
                entries.append(arcname)
        tmp.replace(destination)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if not entries:
        destination.unlink(missing_ok=True)
        raise make_error(
            "BAT-BUILD-002",
            f"Nothing to package in {source.name!r}; the directory is empty.",
            details={"source": str(source)},
        )
    return entries


def zip_paths(
    paths: list[tuple[Path, str]], destination: Path
) -> list[str]:
    """Zip an explicit ``(directory, arc_prefix)`` list (used for .mcaddon)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    tmp = destination.with_suffix(destination.suffix + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for directory, prefix in paths:
                for path in walk_files(directory):
                    if path.name.endswith(".bak"):
                        continue
                    relative = path.relative_to(directory).as_posix()
                    arcname = f"{prefix}/{relative}" if prefix else relative
                    archive.write(path, arcname)
                    entries.append(arcname)
        tmp.replace(destination)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if not entries:
        destination.unlink(missing_ok=True)
        raise make_error("BAT-BUILD-002", "Nothing to package: all sources were empty.")
    return entries
