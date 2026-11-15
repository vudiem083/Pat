"""Compatibility profiles: packaged facts for a target Bedrock version."""

from __future__ import annotations

from dataclasses import dataclass

from .script_api_registry import script_api_status
from .versions import BedrockVersion, parse_version


@dataclass(frozen=True)
class VersionProfile:
    target: str
    format_version: str
    min_engine_version: list[int]
    stable_scripts: bool
    pack_manifest_format_version: int = 2

    def as_dict(self) -> dict[str, object]:
        return {
            "target_version": self.target,
            "format_version": self.format_version,
            "min_engine_version": self.min_engine_version,
            "stable_scripts": self.stable_scripts,
            "pack_manifest_format_version": self.pack_manifest_format_version,
        }


def profile_for(version: str) -> VersionProfile:
    parsed: BedrockVersion = parse_version(version)
    major, minor, patch, _ = parsed.parts
    if (major, minor) >= (1, 21):
        format_version = "1.21.0"
    elif (major, minor) >= (1, 20):
        format_version = "1.20.0"
    else:
        format_version = f"{major}.{minor}.{patch}"
    return VersionProfile(
        target=parsed.short,
        format_version=format_version,
        min_engine_version=[major, minor, patch],
        stable_scripts=script_api_status(version).value == "SUPPORTED",
    )


#: Profiles BAT is prepared to generate for. One per supported minor series.
KNOWN_PROFILES: tuple[str, ...] = ("1.19.0", "1.20.0", "1.21.0", "1.21.80")


def known_profiles() -> list[dict[str, object]]:
    return [profile_for(v).as_dict() for v in KNOWN_PROFILES]
