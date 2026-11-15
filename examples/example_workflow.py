#!/usr/bin/env python3
"""The BAT vertical slice, end to end, without a network transport.

    create project → generate content → validate → build → inspect artifact

It uses an isolated temporary workspace, so running it never touches your real
`data/` or `runtime/` directories.

Run:

    python examples/example_workflow.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bat.config import load_settings
from bat.services import BatServices


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bat-example-") as tmp:
        settings = load_settings(
            env={
                "BAT_WORKSPACE": str(Path(tmp) / "data"),
                "BAT_RUNTIME_ROOT": str(Path(tmp) / "runtime"),
                "BAT_RUNTIME_ADAPTER": "none",
            }
        )
        services = BatServices(settings)
        try:
            startup = services.startup()
            print(f"BAT {startup['version']} | runtime adapter: {startup['runtime_adapter']}")

            # 1. Create an add-on project targeting Bedrock 1.21.80.
            created = services.create_project(
                name="Example Gem Addon",
                project_type="ADDON",
                target_version="1.21.80",
                description="Example project created by examples/example_workflow.py",
            )
            project_id = created["project"]["project_id"]
            print(f"\n1. project created: {project_id}")

            # 2. Generate content (behavior + resource pack documents).
            for generator, spec in (
                ("item", {"name": "example_gem", "max_stack": 16}),
                ("block", {"name": "example_ore"}),
                ("entity", {"name": "example_golem"}),
                (
                    "recipe",
                    {
                        "name": "example_gem_recipe",
                        "pattern": ["XX", "XX"],
                        "keys": {"X": "minecraft:stick"},
                        "result_item": "bat:example_gem",
                    },
                ),
                ("loot_table", {"name": "example_golem"}),
                ("spawn_rule", {"entity_identifier": "bat:example_golem"}),
            ):
                generated = services.generate_content(project_id, generator, spec)
                print(f"   generated {generator}: {generated['generated']['path']}")

            # 3. Validate.
            report = services.validator.validate_project(project_id)
            print(f"\n2. validation: {report.status} ({len(report.findings)} findings)")
            for finding in report.findings:
                location = f" [{finding.file_path}]" if finding.file_path else ""
                print(f"   {finding.severity:7} {finding.code}{location}: {finding.message[:90]}")

            # 4. Build both artifact types and 5. inspect them.
            built = services.build_project(project_id, artifact_type="MCPACK")
            print("\n3. artifacts:")
            for artifact in built["artifacts"]:
                inspection = services.builders.inspect_artifact(artifact["artifact_id"])
                print(
                    f"   {artifact['artifact_type']} {artifact['file_name']} "
                    f"({artifact['size_bytes']} bytes, integrity_ok={inspection['integrity_ok']})"
                )
                print(f"     checksum: {artifact['checksum'][:16]}…")
                print(f"     path: {artifact['storage_path']}")

            # 6. Show the compatibility decision for a version-gated feature.
            support = services.get_compatibility("1.19.80")
            item_support = next(
                f for f in support["features"] if f["feature"] == "item.components"
            )
            print(
                f"\n4. compatibility for items on 1.19.80: {item_support['status']} "
                f"(min {item_support['min_version']})"
            )

            # 7. A runtime test without a server must be NOT_TESTED, not PASS.
            job = services.run_game_test(project_id)
            services.jobs.wait(job.job_id, timeout=20)
            finished = services.jobs.get(job.job_id)
            print(
                f"\n5. runtime test: job={finished.status} error={finished.error_code} "
                f"test_status={(finished.result or {}).get('test_status')}"
            )

            print("\nExample complete. The temporary workspace is removed on exit.")
            print(json.dumps({"project_id": project_id, "validation": report.status}, indent=2))
            return 0
        finally:
            services.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
