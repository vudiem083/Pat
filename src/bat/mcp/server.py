"""FastMCP server for BAT.

Uses the same :class:`~bat.services.BatServices` container as the REST API, so
tool and endpoint behaviour cannot drift.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..services import BatServices, build_services
from ..version import SUPPORTED_VERSION_MAX, SUPPORTED_VERSION_MIN, __version__
from .prompts import register as register_prompts
from .resources import register as register_resources
from .tools import MODULES

INSTRUCTIONS = f"""BAT — Bedrock Agent Toolkit {__version__}

Work with real Minecraft Bedrock Edition projects (supported: {SUPPORTED_VERSION_MIN} to
{SUPPORTED_VERSION_MAX}). Tools cover projects, add-on generation, worlds, validation,
builds (.mcpack/.mcaddon/.mcworld), background jobs and runtime diagnostics.

Conventions:
- Tools return {{"ok": true, "result": ...}} or {{"ok": false, "error": {{"error_code", "message", "details"}}}}.
- Long operations (runtime tests, builds) run as jobs: start them, then poll
  get_job_status / wait_for_job. A timed-out wait does not cancel the job.
- validate_project before build_project; inspect_artifact after building.
- Compatibility statuses are SUPPORTED / UNSUPPORTED / UNKNOWN / NOT_TESTED. Never report
  UNKNOWN or NOT_TESTED as if it were verified.
- Runtime testing requires an operator-supplied Bedrock Dedicated Server. Without one, runtime
  tools fail with BAT-RUNTIME-003 and the test is NOT_TESTED (never a false PASS).
- Client-side features (rendering, UI, attachables) cannot be verified by a server adapter.
"""


def build_mcp_server(services: BatServices | None = None) -> tuple[FastMCP, BatServices]:
    """Return ``(mcp_server, services)``.

    The services object is returned so a host (or tests) can inspect state and
    shut it down explicitly.
    """
    service_layer = services or build_services()
    mcp = FastMCP(name="BAT — Bedrock Agent Toolkit", instructions=INSTRUCTIONS)
    for module in MODULES:
        module.register(mcp, service_layer)
    register_resources(mcp, service_layer)
    register_prompts(mcp, service_layer)
    return mcp, service_layer


def run_stdio() -> None:  # pragma: no cover - exercised by manual runs
    mcp, services = build_mcp_server()
    try:
        mcp.run(transport="stdio")
    finally:
        services.shutdown()
