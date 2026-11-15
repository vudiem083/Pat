from __future__ import annotations

import pytest

from bat.core.errors import ERROR_CODES, BatError, describe_codes, make_error


def test_unregistered_code_is_refused():
    with pytest.raises(ValueError):
        make_error("BAT-MADE-UP-999", "should not exist")


def test_error_payload_shape():
    error = make_error("BAT-RUNTIME-001", "process died", details={"exit_code": 3})
    payload = error.to_dict()
    assert payload["error_code"] == "BAT-RUNTIME-001"
    assert payload["severity"] == "CRITICAL"
    assert payload["details"]["exit_code"] == 3
    assert payload["retryable"] is False


def test_every_code_is_documented():
    codes = describe_codes()
    assert len(codes) == len(ERROR_CODES)
    for entry in codes:
        assert entry["code"].startswith("BAT-")
        assert entry["summary"].strip()
        assert entry["area"]


def test_error_carries_http_status():
    error = make_error("BAT-NOTFOUND-001", "gone", http_status=404)
    assert error.http_status == 404
    assert isinstance(error, BatError)
