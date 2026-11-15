"""Animation and animation controller validation."""

from __future__ import annotations

import json

from ..core.models import Finding, Severity
from .base import ValidationContext, finding

AUDIO_SAFE = {"loop", "animation_length", "bones", "particle_effects", "sound_effects"}


def validate_animations(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    root = context.files_root / "resource_packs"
    if not root.exists():
        return findings

    for path in sorted(root.glob("*/animations/*.json")):
        rel = context.rel(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                finding(
                    "BAT-ANIMATION-001",
                    Severity.ERROR,
                    f"{rel} is not valid JSON: {exc.msg}",
                    file_path=rel,
                    line_number=exc.lineno,
                )
            )
            continue
        animations = data.get("animations")
        if not isinstance(animations, dict) or not animations:
            findings.append(
                finding(
                    "BAT-ANIMATION-001",
                    Severity.ERROR,
                    f"{rel}: missing non-empty 'animations' object.",
                    file_path=rel,
                )
            )
            continue
        for name, body in animations.items():
            if not isinstance(body, dict):
                findings.append(
                    finding(
                        "BAT-ANIMATION-001",
                        Severity.ERROR,
                        f"{rel}: animation {name!r} must be an object.",
                        file_path=rel,
                    )
                )
                continue
            bones = body.get("bones")
            if not isinstance(bones, dict) or not bones:
                findings.append(
                    finding(
                        "BAT-ANIMATION-001",
                        Severity.WARNING,
                        f"{rel}: animation {name!r} has no bones; it will not animate anything.",
                        file_path=rel,
                    )
                )
            length = body.get("animation_length")
            if length is not None and not isinstance(length, (int, float)):
                findings.append(
                    finding(
                        "BAT-ANIMATION-001",
                        Severity.ERROR,
                        f"{rel}: animation {name!r} animation_length must be a number.",
                        file_path=rel,
                    )
                )
            unknown = set(body) - AUDIO_SAFE - {"bones", "anim_time_update"}
            for key in sorted(unknown):
                findings.append(
                    finding(
                        "BAT-ANIMATION-001",
                        Severity.INFO,
                        f"{rel}: animation {name!r} uses '{key}', which BAT does not validate.",
                        file_path=rel,
                    )
                )

    for path in sorted(root.glob("*/animation_controllers/*.json")):
        rel = context.rel(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                finding(
                    "BAT-ANIMATION-001",
                    Severity.ERROR,
                    f"{rel} is not valid JSON: {exc.msg}",
                    file_path=rel,
                    line_number=exc.lineno,
                )
            )
            continue
        controllers = data.get("animation_controllers")
        if not isinstance(controllers, dict) or not controllers:
            findings.append(
                finding(
                    "BAT-ANIMATION-001",
                    Severity.ERROR,
                    f"{rel}: missing non-empty 'animation_controllers' object.",
                    file_path=rel,
                )
            )
            continue
        for name, body in controllers.items():
            if not isinstance(body, dict):
                continue
            states = body.get("states")
            if not isinstance(states, dict) or not states:
                findings.append(
                    finding(
                        "BAT-ANIMATION-001",
                        Severity.ERROR,
                        f"{rel}: controller {name!r} needs a non-empty 'states' object.",
                        file_path=rel,
                    )
                )
                continue
            initial = body.get("initial_state")
            if initial is not None and initial not in states:
                findings.append(
                    finding(
                        "BAT-ANIMATION-001",
                        Severity.ERROR,
                        f"{rel}: controller {name!r} initial_state {initial!r} is not a declared state.",
                        file_path=rel,
                    )
                )
    return findings
