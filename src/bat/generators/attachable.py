"""Attachable template (item visuals, client-side)."""

from __future__ import annotations

from typing import Any

from ..core.models import CompatibilityStatus, GeneratedFile, PackKind
from .common import GenerationContext


def attachable_document(
    identifier: str, *, texture: str, geometry: str, material: str = "entity_alphatest"
) -> dict[str, Any]:
    return {
        "format_version": "1.10.0",
        "minecraft:attachable": {
            "description": {
                "identifier": identifier,
                "materials": {"default": material, "enchanted": "entity_alphatest_glint"},
                "textures": {
                    "default": texture,
                    "enchanted": "textures/misc/enchanted_item_glint",
                },
                "geometry": {"default": geometry},
                "render_controllers": ["controller.render.item_default"],
            }
        },
    }


def create_attachable(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    texture: str | None = None,
    geometry: str | None = None,
) -> GeneratedFile:
    context.feature("attachable.item")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    document = attachable_document(
        identifier,
        texture=texture or f"textures/items/{slug}",
        geometry=geometry or "geometry.bat_item",
    )
    generated = context.write_json(
        PackKind.RESOURCE,
        f"attachables/{slug}.attachable.json",
        document,
        description=f"Attachable for {identifier}",
        feature="attachable.item",
    )
    generated.warnings.append(
        "Attachables are rendered by the client; BAT validates structure only (NOT_TESTED "
        "unless a client adapter is available)."
    )
    generated.compatibility_status = CompatibilityStatus.NOT_TESTED
    return generated
