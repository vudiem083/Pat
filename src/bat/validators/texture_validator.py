"""Texture validation: PNG integrity plus referenced-texture existence."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from ..core.models import Finding, Severity
from .base import ValidationContext, finding

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Return ``(width, height)`` from the IHDR chunk, or None if not a PNG."""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != PNG_SIGNATURE:
        return None
    if header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def validate_textures(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    textures_root = context.files_root / "resource_packs"
    png_files = (
        sorted(p for p in textures_root.rglob("*.png") if p.is_file())
        if textures_root.exists()
        else []
    )
    for path in png_files:
        rel = context.rel(path)
        dimensions = png_dimensions(path)
        if dimensions is None:
            findings.append(
                finding(
                    "BAT-TEXTURE-001",
                    Severity.ERROR,
                    f"{rel} is not a valid PNG (signature/IHDR check failed).",
                    file_path=rel,
                )
            )
            continue
        width, height = dimensions
        if width == 0 or height == 0:
            findings.append(
                finding(
                    "BAT-TEXTURE-001",
                    Severity.ERROR,
                    f"{rel} has zero dimensions.",
                    file_path=rel,
                )
            )
        elif width > 4096 or height > 4096:
            findings.append(
                finding(
                    "BAT-TEXTURE-001",
                    Severity.WARNING,
                    f"{rel} is {width}x{height}, larger than the 4096 px atlas limit BAT expects.",
                    file_path=rel,
                )
            )

    # Referenced textures inside generated content must exist in the resource pack.
    referenced = _referenced_textures(context.files_root)
    for reference, source_file in referenced.items():
        normalized = reference.strip().lstrip("/")
        if not normalized.startswith("textures/"):
            normalized = f"textures/{normalized}"
        if not normalized.lower().endswith(".png"):
            normalized = f"{normalized}.png"
        matches = list(textures_root.glob(f"*/{normalized}"))
        if not matches:
            findings.append(
                finding(
                    "BAT-TEXTURE-001",
                    Severity.WARNING,
                    f"{source_file} references texture {normalized!r} which is not present in the "
                    "resource pack.",
                    file_path=source_file,
                    details={"texture": normalized},
                )
            )
    return findings


def _referenced_textures(files_root: Path) -> dict[str, str]:
    references: dict[str, str] = {}
    for path in list(files_root.glob("behavior_packs/*/blocks/*.json")) + list(
        files_root.glob("resource_packs/*/attachables/*.json")
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rel = path.relative_to(files_root).as_posix()
        block = data.get("minecraft:block")
        if isinstance(block, dict):
            instances = block.get("components", {}).get("minecraft:material_instances", {})
            if isinstance(instances, dict):
                for instance in instances.values():
                    if isinstance(instance, dict) and isinstance(instance.get("texture"), str):
                        references[instance["texture"]] = rel
        attachable = data.get("minecraft:attachable")
        if isinstance(attachable, dict):
            textures = attachable.get("description", {}).get("textures", {})
            if isinstance(textures, dict):
                for value in textures.values():
                    if isinstance(value, str) and "textures/" in value:
                        references[value] = rel
    return references
