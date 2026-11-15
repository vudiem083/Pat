"""Compatibility package: version parsing, feature registry, feature matrix."""

from .versions import (
    BedrockVersion,
    parse_version,
    is_supported,
    format_version,
    format_version_for,
)

__all__ = [
    "BedrockVersion",
    "parse_version",
    "is_supported",
    "format_version",
    "format_version_for",
]
