from __future__ import annotations

import pytest

from bat.compatibility.feature_matrix import matrix_report
from bat.compatibility.registry import DEFAULT_REGISTRY
from bat.core.models import CompatibilityStatus


def test_manifest_support_is_version_aware():
    old = DEFAULT_REGISTRY.check("manifest.format_version_2", "1.19.0")
    new = DEFAULT_REGISTRY.check("manifest.format_version_2", "1.21.80")
    assert old.status == CompatibilityStatus.SUPPORTED.value
    assert new.status == CompatibilityStatus.SUPPORTED.value


def test_item_components_unsupported_before_1_20_50():
    old = DEFAULT_REGISTRY.check("item.components", "1.19.0")
    new = DEFAULT_REGISTRY.check("item.components", "1.21.80")
    assert old.status == CompatibilityStatus.UNSUPPORTED.value
    assert old.min_version == "1.20.50"
    assert "legacy" in old.notes
    assert new.status == CompatibilityStatus.NOT_TESTED.value


def test_unverified_features_report_not_tested_not_supported():
    support = DEFAULT_REGISTRY.check("script.gametest", "1.21.80")
    assert support.status == CompatibilityStatus.NOT_TESTED.value


def test_unknown_feature_is_unknown_not_guessed():
    support = DEFAULT_REGISTRY.check("feature.that.does.not.exist", "1.21.80")
    assert support.status == CompatibilityStatus.UNKNOWN.value
    assert "No registry entry" in support.evidence


def test_out_of_range_version_is_unsupported():
    support = DEFAULT_REGISTRY.check("manifest.format_version_2", "1.22.0")
    assert support.status == CompatibilityStatus.UNSUPPORTED.value


def test_require_raises_for_unsupported():
    from bat.core.errors import BatError

    with pytest.raises(BatError) as exc:
        DEFAULT_REGISTRY.require("item.components", "1.19.0")
    assert exc.value.code == "BAT-COMPAT-002"


def test_matrix_report_counts_and_categories():
    report = matrix_report("1.19.0")
    counts = report["counts"]
    assert sum(counts.values()) == len(report["features"])
    assert report["supported_range"] == {"min": "1.19.0", "max": "1.21.80"}
    assert report["by_category"]
    for feature in report["features"]:
        assert feature["status"] in {
            "SUPPORTED",
            "UNSUPPORTED",
            "UNKNOWN",
            "NOT_TESTED",
        }


def test_terrain_generation_is_explicitly_unsupported():
    support = DEFAULT_REGISTRY.check("world.terrain_generation", "1.21.80")
    assert support.status == CompatibilityStatus.UNSUPPORTED.value
    assert "BAT" in support.notes
