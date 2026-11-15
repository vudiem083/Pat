"""Minecraft Bedrock version parsing and comparison.

BAT only claims awareness of versions between ``SUPPORTED_VERSION_MIN`` and
``SUPPORTED_VERSION_MAX`` (1.19.0 – 1.21.80). Anything else is rejected rather
than silently clamped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

from ..core.errors import make_error
from ..version import SUPPORTED_VERSION_MAX, SUPPORTED_VERSION_MIN

_VERSION_RE = re.compile(r"^\d{1,2}(\.\d{1,3}){1,3}$")


@total_ordering
@dataclass(frozen=True)
class BedrockVersion:
    """A parsed Bedrock version such as ``1.21.80`` or ``1.19.80.2``."""

    parts: tuple[int, int, int, int]

    def __str__(self) -> str:
        return ".".join(str(p) for p in self.parts)

    @property
    def short(self) -> str:
        """``major.minor.patch`` without the revision component."""
        return ".".join(str(p) for p in self.parts[:3])

    @property
    def numeric(self) -> int:
        major, minor, patch, rev = self.parts
        return major * 100_000_000 + minor * 100_000 + patch * 100 + rev

    def _key(self, other: "BedrockVersion | str") -> tuple[int, int, int, int]:
        other_version = parse_version(other) if isinstance(other, str) else other
        return other_version.parts

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (BedrockVersion, str)):
            return NotImplemented
        return self.parts == self._key(other)

    def __lt__(self, other: "BedrockVersion | str") -> bool:
        return self.parts < self._key(other)

    def __hash__(self) -> int:
        return hash(self.parts)


def parse_version(value: str | BedrockVersion) -> BedrockVersion:
    if isinstance(value, BedrockVersion):
        return value
    if not isinstance(value, str):
        raise make_error("BAT-INPUT-001", f"Version must be a string, got {type(value).__name__}.")
    raw = value.strip()
    if not raw:
        raise make_error("BAT-INPUT-001", "A Minecraft Bedrock version string is required.")
    # Tolerate a leading "v" and a trailing build suffix such as "1.21.80.3-beta".
    raw = raw.lstrip("vV")
    raw = raw.split("-")[0]
    if not _VERSION_RE.match(raw):
        raise make_error(
            "BAT-INPUT-001",
            f"Unrecognised Bedrock version string: {value!r}. Expected e.g. 1.21.80",
            details={"value": value},
        )
    numbers = [int(p) for p in raw.split(".")]
    while len(numbers) < 4:
        numbers.append(0)
    return BedrockVersion(tuple(numbers[:4]))  # type: ignore[arg-type]


MIN_VERSION = parse_version(SUPPORTED_VERSION_MIN)
MAX_VERSION = parse_version(SUPPORTED_VERSION_MAX)


def is_supported(value: str | BedrockVersion) -> bool:
    version = parse_version(value)
    return MIN_VERSION <= version <= MAX_VERSION


def require_supported(value: str | BedrockVersion) -> BedrockVersion:
    version = parse_version(value)
    if not (MIN_VERSION <= version <= MAX_VERSION):
        raise make_error(
            "BAT-COMPAT-001",
            (
                f"Minecraft Bedrock {version} is outside BAT's supported range "
                f"{MIN_VERSION.short}–{MAX_VERSION.short}."
            ),
            details={
                "requested": str(version),
                "min": MIN_VERSION.short,
                "max": MAX_VERSION.short,
            },
        )
    return version


def format_version(value: str | BedrockVersion) -> str:
    """Return the canonical ``format_version`` used in generated content files.

    Bedrock accepts the ``major.minor.patch`` form. We emit the minor series the
    target version belongs to, so 1.19 projects do not silently receive 1.21
    content definitions they cannot parse.
    """
    version = parse_version(value)
    major, minor, patch, _ = version.parts
    if (major, minor) >= (1, 21):
        return "1.21.0"
    if (major, minor) >= (1, 20):
        return "1.20.0"
    return f"{major}.{minor}.{patch}"


def format_version_for(value: str | BedrockVersion, minimum: str) -> str:
    """Return ``format_version`` for a feature that requires ``minimum``.

    If the target version is older than the feature's minimum the returned value
    is clamped to the target's own series — callers must check support first and
    report UNSUPPORTED rather than shipping content the target cannot load.
    """
    target = parse_version(value)
    required = parse_version(minimum)
    if target < required:
        return format_version(target)
    return format_version(target)
