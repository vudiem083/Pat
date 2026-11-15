"""Content document validation: entities, blocks, items and recipes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..compatibility.component_registry import available_for
from ..core.models import Finding, Severity
from .base import ValidationContext, finding

IDENTIFIER_RE_PARTS = ("namespace", "name")


def _check_identifier(value: Any, kind: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(value, str) or value.count(":") != 1:
        findings.append(
            finding(
                f"BAT-{kind.upper()}-001",
                Severity.ERROR,
                f"{rel}: identifier must be 'namespace:name' (got {value!r}).",
                file_path=rel,
            )
        )
        return findings
    namespace, name = value.split(":", 1)
    if not namespace or not name:
        findings.append(
            finding(
                f"BAT-{kind.upper()}-001",
                Severity.ERROR,
                f"{rel}: identifier {value!r} has an empty namespace or name.",
                file_path=rel,
            )
        )
    if namespace == "minecraft":
        findings.append(
            finding(
                f"BAT-{kind.upper()}-001",
                Severity.WARNING,
                f"{rel}: overriding the 'minecraft' namespace can conflict with vanilla content.",
                file_path=rel,
            )
        )
    return findings


def _component_findings(
    kind: str,
    components: dict[str, Any],
    rel: str,
    version: str,
    code: str,
) -> list[Finding]:
    findings: list[Finding] = []
    for name in sorted(components):
        available = available_for(kind, name, version)
        if available is False:
            findings.append(
                finding(
                    code,
                    Severity.ERROR,
                    f"{rel}: component {name} is not available for Bedrock {version}.",
                    file_path=rel,
                    details={"component": name, "target_version": version},
                )
            )
        elif available is None:
            findings.append(
                finding(
                    code,
                    Severity.INFO,
                    f"{rel}: component {name} is not in BAT's compatibility registry; support "
                    "for this target is UNKNOWN.",
                    file_path=rel,
                    details={"component": name, "status": "UNKNOWN"},
                )
            )
    return findings


def validate_entity_document(
    data: dict[str, Any], rel: str, version: str
) -> list[Finding]:
    findings: list[Finding] = []
    entity = data.get("minecraft:entity")
    if not isinstance(entity, dict):
        return [
            finding("BAT-ENTITY-001", Severity.ERROR, f"{rel}: missing 'minecraft:entity' object.", file_path=rel)
        ]
    description = entity.get("description")
    if not isinstance(description, dict):
        findings.append(
            finding("BAT-ENTITY-001", Severity.ERROR, f"{rel}: missing description object.", file_path=rel)
        )
        return findings
    findings += _check_identifier(description.get("identifier"), "entity", rel)
    components = entity.get("components")
    if not isinstance(components, dict) or not components:
        findings.append(
            finding(
                "BAT-ENTITY-001",
                Severity.ERROR,
                f"{rel}: entities need a non-empty components object.",
                file_path=rel,
            )
        )
        return findings
    findings += _component_findings("entity", components, rel, version, "BAT-ENTITY-001")
    if "minecraft:health" not in components:
        findings.append(
            finding(
                "BAT-ENTITY-001",
                Severity.WARNING,
                f"{rel}: no minecraft:health component; the entity may be unkillable or invalid.",
                file_path=rel,
            )
        )
    return findings


def validate_block_document(data: dict[str, Any], rel: str, version: str) -> list[Finding]:
    findings: list[Finding] = []
    block = data.get("minecraft:block")
    if not isinstance(block, dict):
        return [
            finding("BAT-BLOCK-001", Severity.ERROR, f"{rel}: missing 'minecraft:block' object.", file_path=rel)
        ]
    description = block.get("description")
    if not isinstance(description, dict):
        findings.append(
            finding("BAT-BLOCK-001", Severity.ERROR, f"{rel}: missing description object.", file_path=rel)
        )
        return findings
    findings += _check_identifier(description.get("identifier"), "block", rel)
    components = block.get("components")
    if not isinstance(components, dict) or not components:
        findings.append(
            finding(
                "BAT-BLOCK-001",
                Severity.ERROR,
                f"{rel}: blocks need a non-empty components object.",
                file_path=rel,
            )
        )
        return findings
    findings += _component_findings("block", components, rel, version, "BAT-BLOCK-001")
    for required in ("minecraft:material_instances", "minecraft:destructible_by_mining"):
        if required not in components:
            findings.append(
                finding(
                    "BAT-BLOCK-001",
                    Severity.WARNING,
                    f"{rel}: missing {required}; the block will render or break unexpectedly.",
                    file_path=rel,
                )
            )
    return findings


def validate_item_document(data: dict[str, Any], rel: str, version: str) -> list[Finding]:
    findings: list[Finding] = []
    item = data.get("minecraft:item")
    if not isinstance(item, dict):
        return [
            finding("BAT-ITEM-001", Severity.ERROR, f"{rel}: missing 'minecraft:item' object.", file_path=rel)
        ]
    description = item.get("description")
    if not isinstance(description, dict):
        findings.append(
            finding("BAT-ITEM-001", Severity.ERROR, f"{rel}: missing description object.", file_path=rel)
        )
        return findings
    findings += _check_identifier(description.get("identifier"), "item", rel)
    components = item.get("components")
    if not isinstance(components, dict) or not components:
        findings.append(
            finding(
                "BAT-ITEM-001",
                Severity.ERROR,
                f"{rel}: items need a non-empty components object.",
                file_path=rel,
            )
        )
        return findings
    findings += _component_findings("item", components, rel, version, "BAT-ITEM-001")
    if "minecraft:icon" not in components:
        findings.append(
            finding(
                "BAT-ITEM-001",
                Severity.WARNING,
                f"{rel}: no minecraft:icon component; the item will render incorrectly.",
                file_path=rel,
            )
        )
    return findings


def validate_recipe_document(data: dict[str, Any], rel: str) -> list[Finding]:
    findings: list[Finding] = []
    keys = [k for k in data if k.startswith("minecraft:recipe_")]
    if len(keys) != 1:
        return [
            finding(
                "BAT-RECIPE-001",
                Severity.ERROR,
                f"{rel}: expected exactly one 'minecraft:recipe_*' object, found {len(keys)}.",
                file_path=rel,
            )
        ]
    recipe = data[keys[0]]
    if not isinstance(recipe, dict):
        return [finding("BAT-RECIPE-001", Severity.ERROR, f"{rel}: recipe must be an object.", file_path=rel)]
    description = recipe.get("description")
    if not isinstance(description, dict) or not description.get("identifier"):
        findings.append(
            finding(
                "BAT-RECIPE-001",
                Severity.ERROR,
                f"{rel}: recipe needs description.identifier.",
                file_path=rel,
            )
        )
    result = recipe.get("result")
    if isinstance(result, list):
        valid = all(isinstance(r, dict) and isinstance(r.get("item"), str) for r in result)
    else:
        valid = isinstance(result, dict) and isinstance(result.get("item"), str)
    if not valid:
        findings.append(
            finding(
                "BAT-RECIPE-001",
                Severity.ERROR,
                f"{rel}: recipe result must reference an item identifier.",
                file_path=rel,
            )
        )
    if keys[0] == "minecraft:recipe_shaped":
        pattern = recipe.get("pattern")
        key_map = recipe.get("key")
        if not isinstance(pattern, list) or not isinstance(key_map, dict):
            findings.append(
                finding(
                    "BAT-RECIPE-001",
                    Severity.ERROR,
                    f"{rel}: shaped recipes need 'pattern' and 'key'.",
                    file_path=rel,
                )
            )
        else:
            used = {c for row in pattern if isinstance(row, str) for c in row if c != " "}
            missing = used - set(key_map)
            if missing:
                findings.append(
                    finding(
                        "BAT-RECIPE-001",
                        Severity.ERROR,
                        f"{rel}: pattern symbols {sorted(missing)} have no key entry.",
                        file_path=rel,
                    )
                )
    if not recipe.get("tags"):
        findings.append(
            finding(
                "BAT-RECIPE-001",
                Severity.WARNING,
                f"{rel}: recipe has no tags; it will not appear in a crafting table.",
                file_path=rel,
            )
        )
    return findings


_DOCUMENT_VALIDATORS = {
    "entity": validate_entity_document,
    "block": validate_block_document,
    "item": validate_item_document,
    "recipe": validate_recipe_document,
}


def detect_kind(path: Path) -> str | None:
    parts = path.parts
    if "entities" in parts:
        return "entity"
    if "blocks" in parts:
        return "block"
    if "items" in parts:
        return "item"
    if "recipes" in parts:
        return "recipe"
    return None


def validate_document(
    context: ValidationContext, path: Path, kind: str | None = None
) -> list[Finding]:
    rel = context.rel(path)
    kind = kind or detect_kind(path)
    if kind is None or kind not in _DOCUMENT_VALIDATORS:
        return [
            finding(
                "BAT-INPUT-001",
                Severity.ERROR,
                f"{rel}: cannot determine document kind (entity/block/item/recipe).",
                file_path=rel,
            )
        ]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            finding(
                "BAT-JSON-001",
                Severity.ERROR,
                f"{rel}: is not valid JSON: {exc.msg}",
                file_path=rel,
                line_number=exc.lineno,
            )
        ]
    except OSError as exc:
        return [finding("BAT-NOTFOUND-002", Severity.ERROR, f"{rel}: {exc}", file_path=rel)]
    if not isinstance(data, dict):
        return [finding("BAT-JSON-001", Severity.ERROR, f"{rel}: must be a JSON object.", file_path=rel)]
    if kind == "recipe":
        return _DOCUMENT_VALIDATORS[kind](data, rel)  # type: ignore[call-arg]
    return _DOCUMENT_VALIDATORS[kind](data, rel, context.target_version)  # type: ignore[call-arg]


def validate_all_documents(context: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for directory in ("entities", "blocks", "items", "recipes"):
        for path in sorted(context.files_root.glob(f"behavior_packs/*/{directory}/*.json")):
            findings += validate_document(context, path)
    return findings
