"""Particle effect template (client-side rendering)."""

from __future__ import annotations

from typing import Any

from ..core.models import CompatibilityStatus, GeneratedFile, PackKind
from .common import GenerationContext


def particle_document(
    identifier: str,
    *,
    texture: str = "textures/particle/particles",
    material: str = "particles_alpha",
    spawn_rate: int = 10,
    max_particles: int = 20,
    size: float = 0.1,
) -> dict[str, Any]:
    return {
        "format_version": "1.10.0",
        "particle_effect": {
            "description": {
                "identifier": identifier,
                "basic_render_parameters": {"material": material, "texture": texture},
            },
            "components": {
                "minecraft:emitter_local_space": {
                    "position": False,
                    "rotation": False,
                    "velocity": False,
                },
                "minecraft:emitter_rate_steady": {
                    "spawn_rate": spawn_rate,
                    "max_particles": max_particles,
                },
                "minecraft:emitter_lifetime_looping": {"active_time": 1.0},
                "minecraft:emitter_shape_point": {"offset": [0, 0, 0]},
                "minecraft:particle_lifetime_expression": {"max_lifetime": 1.0},
                "minecraft:particle_appearance_billboard": {
                    "size": [size, size],
                    "facing_camera_mode": "rotate_xyz",
                },
                "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, 2, 0]},
            },
        },
    }


def create_particle(
    context: GenerationContext,
    *,
    name: str,
    namespace: str | None = None,
    texture: str = "textures/particle/particles",
    spawn_rate: int = 10,
    size: float = 0.1,
) -> GeneratedFile:
    context.feature("particle.effect")
    identifier = context.identifier(namespace, name)
    slug = context.slugify_suffix(identifier)
    document = particle_document(
        identifier, texture=texture, spawn_rate=int(spawn_rate), size=float(size)
    )
    generated = context.write_json(
        PackKind.RESOURCE,
        f"particles/{slug}.particle.json",
        document,
        description=f"Particle effect {identifier}",
        feature="particle.effect",
    )
    generated.warnings.append(
        "Particle rendering is client-side; BAT validates structure only (NOT_TESTED)."
    )
    generated.compatibility_status = CompatibilityStatus.NOT_TESTED
    return generated
