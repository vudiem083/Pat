# Architecture

## Design goals

1. **One business layer, two transports.** MCP and REST are thin adapters over
   `bat.services.BatServices`. A behaviour change happens once.
2. **Honest statuses.** Compatibility and test results use an explicit vocabulary; unverified is not
   "supported".
3. **Evidence survives.** Logs, sessions, incidents, snapshots and artifacts live on disk, outside
   any single process, so a crash (or BAT restart) does not erase why something failed.
4. **Bounded scope, clean seams.** SQLite + local filesystem for the MVP, behind interfaces
   (`RuntimeAdapter`, `Database`) that a later deployment can replace.

## Layers

```text
transport   api/ (FastAPI routes, schemas, auth dependency)
            mcp/ (FastMCP tools, resources, prompts)
              |
application services.py  — wires the object graph, registers job handlers
              |
domain      core/            models, errors, filesystem, projects, NBT
            compatibility/   versions, registries, matrix, checker
            generators/      content templates
            validators/      rules + aggregation
            builders/        packaging + inspection
            runtime/         adapter, environments, supervision, test runner
            jobs/            queue, workers, state machine
            diagnostics/     evidence, analysis, incidents
            observability/   logging, health, metrics
              |
infra       storage/database.py (SQLite), storage/workspace.py (runtime layout),
            filesystem (data/, runtime/), .env settings
```

Rules enforced by review:

- Transports never touch SQLite or the filesystem directly.
- Generators never bypass the compatibility registry for version-gated features.
- Validators never raise on invalid content; they return `Finding`s.
- Runtime code never classifies a dead process as a timeout, and never invents a cause.

## Request flow: validate

```text
POST /api/v1/projects/{id}/validate        MCP validate_project
                    \                     /
                     v                   v
              ValidatorEngine.validate_project
                     |
   json → manifest → pack → documents → texture → animation → world → compatibility
                     |
              ValidationReport  ──►  SQLite (validation_reports) + evidence list
```

## Job flow: runtime test

```text
run_game_test / POST /jobs  ──► JobManager.submit
                                    |
                          SQLite row (QUEUED) + log file
                                    |
                        worker thread: JobContext (log, cancel, checkpoints)
                                    |
                       RuntimeTester
          create environment → install world/packs → bind → start server
                                    |
              ServerManager (stdout/stderr threads, monitor thread, waiter thread)
                                    |
                    session.json / console.log / runtime.log / errors.log
                    heartbeat.json / report.json
                                    |
        exit classified → STOPPED | EXITED | CRASHED (incident)  |  unresponsive (incident)
                                    |
                 JobReport + session report → terminal job state
```

Timeout layering is explicit:

| Layer | Meaning | Recorded as |
|---|---|---|
| MCP/REST wait timeout | caller stopped waiting | job keeps running (`completed: false`) |
| Job timeout | handler exceeded its own budget | `TIMED_OUT` + `BAT-RUNTIME-005`, cancel signal set |
| Runtime start timeout | server never reported readiness | `BAT-RUNTIME-002`, process stopped |
| Process crash | non-zero exit / unexpected exit | `CRASHED` + incident |
| Unresponsive | process alive, no output past threshold | incident `UNRESPONSIVE`, not a crash |

## Storage

SQLite tables: `projects`, `jobs`, `artifacts`, `validation_reports`, `sessions`, `incidents`,
`environments`. Each row keeps indexed columns plus the canonical model JSON, so the contract and
the storage cannot drift.

Files:

- `<workspace>/projects/<id>/` — project record + sandboxed content root.
- `<workspace>/artifacts/<project>/<artifact>/` — artifact file + `build_report.json`.
- `<workspace>/logs/jobs/<job>.log|.heartbeat.json|.report.json` — job evidence.
- `<runtime>/environments|sessions|incidents|snapshots|cache` — approved runtime layout.

Incidents copy evidence into their own directory, so deleting an environment or project never
destroys diagnostic history.

## Failure handling principles

- Every terminal job state has a report with an error code.
- A worker that dies without finishing is detected and marked `CRASHED` (`BAT-JOB-002`), including
  jobs orphaned by a host restart (recovery runs at startup).
- `BatError` carries the HTTP status and the documented code; unexpected exceptions are still
  recorded, never swallowed.
- Cancellation is cooperative and explicit: the API marks the job and signals the worker.

## Extending

- **New runtime target** (Docker, client): implement `RuntimeAdapter` and select it in
  `runtime/adapter.select_adapter`. Job/diagnostic/API code needs no change.
- **New database**: implement the small surface used by services (`save_*`, `get_*`, `list_*`) and
  inject it in `BatServices`.
- **New transport**: call `BatServices`; reuse the models.
