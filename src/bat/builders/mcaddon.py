"""``.mcaddon`` builder: behavior and resource packs in one archive."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.errors import make_error
from ..core.models import PackKind
from .mcpack import pack_content
from .packaging import zip_paths


def build_mcaddon(
    files_root: Path, destination: Path, *, packs: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    sources: list[tuple[Path, str]] = []
    included: list[dict[str, Any]] = []
    for kind, base in ((PackKind.BEHAVIOR, "behavior_packs"), (PackKind.RESOURCE, "resource_packs")):
        directory = files_root / base
        if not directory.exists():
            continue
        for pack in sorted(p for p in directory.iterdir() if p.is_dir()):
            if not (pack / "manifest.json").exists():
                continue
            info = pack_content(pack)
            sources.append((pack, f"{base}/{pack.name}"))
            included.append(
                {
                    "kind": kind.value,
                    "pack": pack.name,
                    "entries": info["content_files"] + 1,
                    "header_uuid": info["header"].get("uuid"),
                }
            )
    if not sources:
        raise make_error(
            "BAT-BUILD-002",
            "Project has no packs with manifests; an .mcaddon needs at least one pack.",
        )
    entries = zip_paths(sources, destination)
    if not any(name.endswith("manifest.json") for name in entries):
        raise make_error(
            "BAT-ARTIFACT-002", "Built .mcaddon does not contain any manifest.json."
        )
    return {
        "file": str(destination),
        "packs": included,
        "entries": entries,
        "entry_count": len(entries),
    }
