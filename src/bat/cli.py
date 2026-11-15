"""BAT command line interface.

    bat serve-api            # REST API (default 127.0.0.1:8000)
    bat serve-mcp            # MCP server on stdio
    bat doctor               # environment + runtime readiness
    bat project create ...   # project management
    bat validate <id>        # validation report
    bat build <id>           # build artifacts
    bat compat <version>     # feature matrix

Commands print JSON so they are easy to script.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .config import load_settings
from .core.errors import BatError
from .version import SUPPORTED_VERSION_MAX, __version__


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _services():
    from .services import build_services

    return build_services(load_settings())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bat", description="BAT — Bedrock Agent Toolkit")
    parser.add_argument("--version", action="version", version=f"BAT {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_api = sub.add_parser("serve-api", help="Run the REST API")
    serve_api.add_argument("--host", default=None)
    serve_api.add_argument("--port", type=int, default=None)

    serve_mcp = sub.add_parser("serve-mcp", help="Run the MCP server on stdio")
    serve_mcp.add_argument(
        "--transport", default="stdio", choices=["stdio", "sse", "streamable-http"]
    )

    sub.add_parser("doctor", help="Check configuration and runtime readiness")

    project = sub.add_parser("project", help="Project operations")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    create = project_sub.add_parser("create", help="Create a project")
    create.add_argument("name")
    create.add_argument(
        "--type", dest="project_type", default="ADDON", choices=["ADDON", "WORLD", "COMBINED"]
    )
    create.add_argument("--version", dest="target_version", default=SUPPORTED_VERSION_MAX)
    project_sub.add_parser("list", help="List projects")
    show = project_sub.add_parser("show", help="Show a project")
    show.add_argument("project_id")
    delete = project_sub.add_parser("delete", help="Delete a project")
    delete.add_argument("project_id")
    delete.add_argument("--purge-artifacts", action="store_true")

    validate = sub.add_parser("validate", help="Validate a project")
    validate.add_argument("project_id")

    build = sub.add_parser("build", help="Build project artifacts")
    build.add_argument("project_id")
    build.add_argument(
        "--type", dest="artifact_type", default=None, choices=["MCPACK", "MCADDON", "MCWORLD"]
    )
    build.add_argument("--strict", action="store_true")

    compat = sub.add_parser("compat", help="Feature matrix for a version")
    compat.add_argument("version", nargs="?", default=SUPPORTED_VERSION_MAX)

    sub.add_parser("errors", help="List documented BAT error codes")

    args = parser.parse_args(argv)

    try:
        if args.command == "serve-api":
            return _serve_api(args)
        if args.command == "serve-mcp":
            return _serve_mcp(args)
        return _run_offline_command(args)
    except BatError as exc:
        _print({"ok": False, "error": exc.to_dict()})
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


def _serve_api(args: argparse.Namespace) -> int:
    import uvicorn

    from .api.app import create_app

    settings = load_settings()
    host = args.host or settings.host
    port = args.port or settings.port
    print(f"BAT REST API on http://{host}:{port}  (docs: /docs)")
    uvicorn.run(create_app(), host=host, port=port)
    return 0


def _serve_mcp(args: argparse.Namespace) -> int:  # pragma: no cover - long-running
    from .mcp.server import build_mcp_server

    mcp, services = build_mcp_server()
    print("BAT MCP server starting (transport: %s)" % args.transport, file=sys.stderr)
    try:
        mcp.run(transport=args.transport)
    finally:
        services.shutdown()
    return 0


def _run_offline_command(args: argparse.Namespace) -> int:
    services = _services()
    try:
        if args.command == "doctor":
            _print(
                {
                    "startup": services.startup(),
                    "health": services.health.report().model_dump(),
                    "runtime": services.adapter.describe(),
                    "settings": {
                        "workspace": str(services.settings.workspace_root),
                        "runtime_root": str(services.settings.runtime_root),
                        "database": str(services.settings.database_path),
                        "api_auth": "enabled" if services.settings.api_key else "disabled",
                    },
                    "job_types": services.jobs.registered_types(),
                }
            )
            return 0
        if args.command == "project":
            if args.project_command == "create":
                _print(
                    services.create_project(
                        name=args.name,
                        project_type=args.project_type,
                        target_version=args.target_version,
                    )
                )
                return 0
            if args.project_command == "list":
                projects = services.projects.list()
                _print({"items": [p.model_dump() for p in projects], "total": len(projects)})
                return 0
            if args.project_command == "show":
                _print(
                    {
                        "project": services.projects.get(args.project_id).model_dump(),
                        "packs": services.projects.list_packs(args.project_id),
                    }
                )
                return 0
            if args.project_command == "delete":
                _print(
                    services.projects.delete(
                        args.project_id, purge_artifacts=args.purge_artifacts
                    )
                )
                return 0
        if args.command == "validate":
            report = services.validator.validate_project(args.project_id)
            _print(report.model_dump())
            return 0 if report.status != "FAIL" else 2
        if args.command == "build":
            result = services.build_project(
                args.project_id, artifact_type=args.artifact_type, strict=args.strict
            )
            _print(result)
            return 0
        if args.command == "compat":
            _print(services.get_compatibility(args.version))
            return 0
        if args.command == "errors":
            _print({"codes": services.list_error_codes()})
            return 0
        _print({"ok": False, "error": f"Unknown command {args.command!r}"})
        return 1
    finally:
        services.shutdown()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
