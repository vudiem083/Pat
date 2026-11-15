"""Script API module registry.

BAT deliberately does **not** guess exact ``@minecraft/server`` version numbers
per game release: those change frequently and a wrong pin produces packs that
fail to load. The registry records what is documented and marks the rest
UNKNOWN so callers can report uncertainty instead of inventing a mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.models import CompatibilityStatus
from .versions import parse_version

STABLE_API_MIN_GAME_VERSION = "1.19.70"
"""Game version from which stable (non-experimental) script APIs were available.

BAT treats anything older as requiring experimental script APIs, which is
reported as NOT_SUPPORTED for generated packs unless the operator opts in.
"""


@dataclass(frozen=True)
class ScriptModuleRecord:
    module: str
    api_version: str
    notes: str


# BAT writes the generic stable module name without pinning a minor API version,
# which Bedrock resolves to the stable API of the running game. This avoids
# emitting an invented version number while remaining loadable.
GENERATED_MODULES: tuple[ScriptModuleRecord, ...] = (
    ScriptModuleRecord(
        module="@minecraft/server",
        api_version="1.0.0",
        notes="Stable module floor written by BAT's script generator. Bedrock resolves the "
        "stable API family; BAT does not claim a specific minor version per game release.",
    ),
    ScriptModuleRecord(
        module="@minecraft/server-ui",
        api_version="1.0.0",
        notes="Stable UI module floor. Not required by generated scripts by default.",
    ),
)


def script_api_status(game_version: str) -> CompatibilityStatus:
    """Whether stable script APIs are expected to exist for a game version."""
    if parse_version(game_version) < parse_version(STABLE_API_MIN_GAME_VERSION):
        return CompatibilityStatus.UNSUPPORTED
    return CompatibilityStatus.SUPPORTED


def module_records() -> list[dict[str, str]]:
    return [
        {"module": record.module, "api_version": record.api_version, "notes": record.notes}
        for record in GENERATED_MODULES
    ]


def known_module(name: str) -> bool:
    return any(record.module == name for record in GENERATED_MODULES)
