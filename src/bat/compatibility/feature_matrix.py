"""Feature support matrix rendering for a target Bedrock version."""

from __future__ import annotations

from typing import Any, Iterable

from ..core.models import CompatibilityInfo, CompatibilityStatus, FeatureSupport
from .component_registry import COMPONENTS
from .registry import CompatibilityRegistry, DEFAULT_REGISTRY
from .script_api_registry import STABLE_API_MIN_GAME_VERSION, script_api_status
from .versions import MAX_VERSION, MIN_VERSION, parse_version


def build_matrix(version: str, registry: CompatibilityRegistry | None = None) -> list[FeatureSupport]:
    registry = registry or DEFAULT_REGISTRY
    return registry.matrix(version)


def compatibility_info(
    version: str,
    *,
    features: Iterable[str] | None = None,
    registry: CompatibilityRegistry | None = None,
) -> CompatibilityInfo:
    registry = registry or DEFAULT_REGISTRY
    if features is None:
        supports = build_matrix(version, registry)
    else:
        supports = [registry.check(key, version) for key in features]
    notes = [
        f"Target version {parse_version(version).short}.",
        f"BAT supports {MIN_VERSION.short}–{MAX_VERSION.short}.",
        "Statuses are version-aware: SUPPORTED means BAT exercises the feature, "
        "NOT_TESTED means documented but unverified, UNKNOWN means no evidence.",
    ]
    script_status = script_api_status(version)
    if script_status is CompatibilityStatus.UNSUPPORTED:
        notes.append(
            f"Stable script APIs are not available before {STABLE_API_MIN_GAME_VERSION}; "
            "script modules generated for this target need experimental APIs."
        )
    return CompatibilityInfo(target_version=parse_version(version).short, checked_features=supports, notes=notes)


def matrix_report(version: str, registry: CompatibilityRegistry | None = None) -> dict[str, Any]:
    registry = registry or DEFAULT_REGISTRY
    supports = build_matrix(version, registry)
    counts = registry.summary(supports)
    by_category: dict[str, dict[str, int]] = {}
    for support in supports:
        bucket = by_category.setdefault(support.category, {})
        bucket[support.status] = bucket.get(support.status, 0) + 1
    return {
        "target_version": parse_version(version).short,
        "supported_range": {"min": MIN_VERSION.short, "max": MAX_VERSION.short},
        "counts": counts,
        "by_category": by_category,
        "features": [support.model_dump() for support in supports],
        "components": [
            {"kind": c.kind, "component": c.name, "min_version": c.min_version}
            for c in COMPONENTS
        ],
        "script_api": {"stable_from": "1.19.70", "status": script_api_status(version).value},
        "notes": [
            "UNKNOWN and NOT_TESTED entries are intentional: BAT does not claim support "
            "without evidence.",
        ],
    }
