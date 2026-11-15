from __future__ import annotations

import pytest

from bat.compatibility.versions import (
    format_version,
    is_supported,
    parse_version,
    require_supported,
)
from bat.core.errors import BatError


def test_parse_three_and_four_part_versions():
    assert parse_version("1.21.80").parts == (1, 21, 80, 0)
    assert parse_version("1.19.80.2").parts == (1, 19, 80, 2)
    assert parse_version("v1.20.1").short == "1.20.1"


def test_ordering_and_equality():
    assert parse_version("1.19.0") < parse_version("1.19.80")
    assert parse_version("1.21.80") > parse_version("1.20.50")
    assert parse_version("1.19.0") == "1.19.0.0"


def test_invalid_version_rejected():
    for bad in ("", "banana", "1", "1.x", "1.21.80.3.1"):
        with pytest.raises(BatError) as exc:
            parse_version(bad)
        assert exc.value.code == "BAT-INPUT-001"


def test_supported_range_bounds():
    assert is_supported("1.19.0")
    assert is_supported("1.21.80")
    assert not is_supported("1.18.30")
    assert not is_supported("1.22.0")
    with pytest.raises(BatError) as exc:
        require_supported("1.22.0")
    assert exc.value.code == "BAT-COMPAT-001"


def test_format_version_tracks_minor_series():
    assert format_version("1.19.80") == "1.19.80"
    assert format_version("1.20.10") == "1.20.0"
    assert format_version("1.21.80") == "1.21.0"
    assert format_version("1.21.0") == "1.21.0"
