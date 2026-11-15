"""Uniform MCP tool responses.

Every tool returns an envelope so an agent can branch on ``ok`` without parsing
exception text:

    {"ok": true, "result": {...}}
    {"ok": false, "error": {"error_code": "BAT-...", "message": ..., "details": {...}}}
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from ...core.errors import BatError


def tool(fn: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"ok": True, "result": fn(*args, **kwargs)}
        except BatError as exc:
            return {"ok": False, "error": exc.to_dict()}
        except ValueError as exc:
            return {
                "ok": False,
                "error": {
                    "error_code": "BAT-INPUT-001",
                    "message": str(exc),
                    "severity": "ERROR",
                    "details": {},
                },
            }

    return wrapper


def text_result(payload: Any) -> str:
    import json

    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
