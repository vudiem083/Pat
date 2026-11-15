# Runtime design

> A `PASS` from BAT means "the server started with the installed packs and reported no pack/script
> errors". It does not mean the add-on is fun, balanced, or correct on a client.

## Directory layout

```text
runtime/
  environments/<env_id>/        one isolated test environment
    config/environment.json     purpose, project, runtime type, notes
    server/                     working directory for the server (server.properties, generated files)
    worlds/<world_name>/        copied world (level.dat, levelname.txt, db/, pack bindings)
    behavior_packs/<pack>/      copied packs
    resource_packs/<pack>/
    scripts/
  sessions/<session_id>/
    session.json                canonical RuntimeSession
    console.log                 raw stdout/stderr, appended line by line
    runtime.log                 structured JSONL of the same lines
    errors.log                  only lines classified as errors
    heartbeat.json              pid, alive, ready, uptime, last output, line count
    report.json                 log scan + exit info + notes
  incidents/<incident_id>/
    incident.json
    diagnosis.json
    evidence/                   copies of session/job logs + manifest.json
  snapshots/<snapshot_id>/      pre-edit copies of a world or environment
  cache/                        regenerable data only
```

Identifiers are unique (`env_<12 hex>`, `session_<12 hex>`, `incident_<12 hex>`, timestamped
snapshots), not fixed example ids.

## Isolation guarantees

- Environment content is **copied**, never symlinked, so a destructive test cannot touch project
  files.
- Environment paths are validated to live under `runtime/environments`; destroying an environment
  refuses paths outside the runtime root.
- Each server runs with `cwd = <env>/server`, a minimal environment, its own free UDP port and its
  own session directory.
- Destroying an environment removes only that environment: sessions, incidents and snapshots are
  retained.

## Process supervision

Three threads per server:

| Thread | Responsibility |
|---|---|
| reader | stream stdout/stderr to `console.log`, classify into `runtime.log`/`errors.log`, update last-output time, detect readiness |
| monitor | write `heartbeat.json` + session record every interval; raise `UNRESPONSIVE` once if a live process stops producing output |
| waiter | block on process exit, then finalize status, scan logs, create an incident when the exit was not requested, write `report.json` |

Classification:

| Situation | Status | Incident | Error code |
|---|---|---|---|
| Stop requested, exit 0 | `STOPPED` | none | — |
| Exit 0 without a stop request | `EXITED` | `UNEXPECTED_EXIT` | `BAT-RUNTIME-001` |
| Non-zero exit | `CRASHED` | `PROCESS_CRASH` (+ `SCRIPT_ERROR` signatures) | `BAT-RUNTIME-001` / `BAT-SCRIPT-001` |
| Alive but silent past threshold | `RUNNING` | `UNRESPONSIVE` (WARNING) | `BAT-RUNTIME-004` (in report) |
| Never ready before timeout | stopped | none | `BAT-RUNTIME-002` |
| No executable configured | refusal | none | `BAT-RUNTIME-003`, test `NOT_TESTED` |

A stop request never overwrites a crash status: if the process is already dead, `stop()` leaves the
recorded status intact.

## Producing your own server

BAT does not ship or download server binaries.

```bash
mkdir -p runtime/server
# place your Bedrock Dedicated Server files here (or anywhere) and:
export BAT_RUNTIME_ADAPTER=bds
export BAT_BEDROCK_SERVER=/absolute/path/to/bedrock_server
chmod +x "$BAT_BEDROCK_SERVER"
bat doctor
```

BAT writes `server.properties` in the environment's own `server/` directory on the first run, with
`level-name` pointing at the installed world and a free UDP port. You remain responsible for the
licence and terms of the server software.

## Server-side vs client-side

| Verifiable by BDS | Not verifiable by BDS |
|---|---|
| Manifest/pack load errors | Textures, models, animations, particles rendering |
| Script errors raised on the server | UI screens, attachables |
| World load failures and `level.dat` problems | Mobile/console import flows |
| Console command responses, player join messages | Gameplay feel, balance, behaviour in GUI |

Client-only results are reported as `NOT_TESTED`, never as `PASS`.

## Reading evidence

```bash
# REST
curl -s $BASE/runtime/sessions/<session_id>            # status
curl -s $BASE/runtime/sessions/<session_id>/logs?kind=errors&tail=100
curl -s $BASE/runtime/sessions/<session_id>/heartbeat
curl -s $BASE/runtime/sessions/<session_id>/report

# MCP
get_runtime_status, get_runtime_logs, get_runtime_heartbeat, get_runtime_report
get_incidents(session_id=...), get_incident_details, diagnose_incident
```

Incident evidence is copied into the incident directory, so it remains readable after the
environment or project is deleted.

## Retention

- BAT's own log (`<workspace>/logs/bat.jsonl`) rotates by size (`BAT_LOG_MAX_BYTES`,
  `BAT_LOG_BACKUP_COUNT`).
- Session logs and incidents are **not** pruned automatically; they are evidence. Remove them
  deliberately, or archive them, when you no longer need them.
- `runtime/cache/` holds regenerable data only and is safe to delete.
- Snapshots accumulate on each destructive world edit; prune `runtime/snapshots/` when you have
  confirmed the changes.
