"""Animation and animation controller templates (resource pack, client-side)."""

from __future__ import annotations

from typing import Any

from ..core.models import CompatibilityStatus, GeneratedFile, PackKind
from .common import GenerationContext


def animation_document(name: str, *, bone: str, axis: str, amplitude: float) -> dict[str, Any]:
    expr = f"math.sin(query.anim_time * 360) * {amplitude}"
    rotation: list[Any] = [0, 0, 0]
    rotation["xyz".index(axis)] = expr
    return {
        "format_version": "1.8.0",
        "animations": {
            f"animation.{name}": {
                "loop": True,
                "animation_length": 1.0,
                "bones": {bone: {"rotation": rotation}},
            }
        },
    }


def controller_document(name: str, *, animation_name: str) -> dict[str, Any]:
    return {
        "format_version": "1.10.0",
        "animation_controllers": {
            f"controller.animation.{name}": {
                "initial_state": "default",
                "states": {"default": {"animations": [animation_name]}},
            }
        },
    }


def create_animation(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    bone: str = "body",
    axis: str = "z",
    amplitude: float = 10.0,
) -> GeneratedFile:
    context.feature("animation.bone_animation")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    if axis not in {"x", "y", "z"}:
        from ..core.errors import make_error

        raise make_error("BAT-INPUT-001", "axis must be x, y or z.")
    document = animation_document(slug, bone=bone, axis=axis, amplitude=float(amplitude))
    generated = context.write_json(
        PackKind.RESOURCE,
        f"animations/{slug}.animation.json",
        document,
        description=f"Bone animation for {identifier}",
        feature="animation.bone_animation",
    )
    generated.warnings.append(
        "Client-side animation: BAT can only verify structure, not rendering."
    )
    generated.compatibility_status = CompatibilityStatus.NOT_TESTED
    return generated


def create_animation_controller(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    animation_name: str | None = None,
) -> GeneratedFile:
    context.feature("animation.controller")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    animation = animation_name or f"animation.{slug}"
    document = controller_document(slug, animation_name=animation)
    generated = context.write_json(
        PackKind.RESOURCE,
        f"animation_controllers/{slug}.animation_controllers.json",
        document,
        description=f"Animation controller for {identifier}",
        feature="animation.controller",
    )
    generated.warnings.append(
        "Client-side animation controller: structural validation only, not rendered by BAT."
    )
    generated.compatibility_status = CompatibilityStatus.NOT_TESTED
    return generated
