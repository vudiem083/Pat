# BAT — Bedrock Agent Toolkit

**BAT** is a toolkit that lets AI agents create, inspect, modify, validate, build, test and
diagnose **Minecraft Bedrock Edition** projects through two interfaces built on one shared
service layer:

- an **MCP server** (FastMCP) for AI agent integration, and
- a **REST API** (FastAPI, `/api/v1`) for applications, automation and other clients.

[Giới thiệu dự án (tiếng Việt)](README.md) · English reference (this file) · [Tài liệu tiếng Việt đầy đủ](README.vi.md)

---

## 1. Vision

Agents are good at producing JSON that *looks* like a Bedrock pack. They are bad at knowing
whether Minecraft will load it, whether the manifest is valid for the target release, or why a
server crashed after the pack was installed.

BAT closes that gap. Its core principle:

> BAT must help AI agents work with **actual** Minecraft Bedrock projects, not merely generate
> files that look valid.

That principle is enforced in code, not just documented:

- Every feature BAT claims to support has a version-aware registry entry with its evidence.
  Anything unverified is reported as **NOT_TESTED**; anything unknown is **UNKNOWN**.
- Runtime tests report `PASS`, `FAIL`, `NOT_SUPPORTED` or `NOT_TESTED` — never a pass that was
  not observed.
- A process crash is recorded as a crash with an incident, never downgraded to a timeout.
- Error codes are a fixed, documented namespace; BAT refuses to emit an unregistered code.
- Diagnostics state "root cause unknown" when the evidence does not support a cause.

## 2. Platform scope

| | |
|---|---|
| Edition | **Minecraft Bedrock Edition** (Minecraft PE is in scope) |
| Out of scope | Minecraft Java Edition |
| Supported target versions | **1.19.0 – 1.21.80** |
| Default target | 1.21.80 |

BAT does not silently expand the supported range and does not silently upgrade a project's
target version. Versions outside the range are rejected with `BAT-COMPAT-001`. Within the range,
individual features may still be `UNSUPPORTED`, `NOT_TESTED` or `UNKNOWN` — see §8.

## 3. Project types

| Type | What BAT manages |
|---|---|
| `ADDON` | Behavior Pack + Resource Pack: manifests, entities, blocks, items, recipes, loot tables, spawn rules, animations, animation controllers, particles, attachables, script modules. |
| `WORLD` | A standalone world: `level.dat` metadata, `levelname.txt`, pack bindings, structures, validation, snapshots and `.mcworld` export. |
| `COMBINED` | A world **plus its associated packs**, with real pack-to-world bindings, dependency tracking, combined validation, combined builds and combined runtime tests. |

`COMBINED` is not a folder of unrelated files: the world's
`world_behavior_packs.json` / `world_resource_packs.json` are generated from the project's actual
packs, and builds produce both a `.mcaddon` and a `.mcworld`.

On disk a project is:

```text
<workspace>/projects/<project_id>/
  project.json                  canonical project record
  files/                        sandboxed content root (relative paths only)
    behavior_packs/<pack>/manifest.json + content
    resource_packs/<pack>/manifest.json + content
    world/level.dat, levelname.txt, world_*_packs.json, structures/, db/
```

## 4. Capabilities

**Projects** — create, inspect, list, delete, file tree, read/write/delete files (atomic writes,
automatic `.bak` on overwrite, size limits, path-traversal and symlink rejection).

**Add-ons** — generate version-aware manifests and content documents; item generation uses the
component format and refuses targets below 1.20.50 instead of emitting content that cannot load.

**Worlds** — read and write real little-endian NBT `level.dat` (8-byte header), edit metadata with
a snapshot taken first and the write verified by re-reading, bind packs, create/import/export
`.mcstructure`, export `.mcworld`.

**Validation** — JSON syntax (with line numbers), manifests (fields, UUIDs, duplicates,
`min_engine_version` vs target, script entry files), pack structure, content documents
(entities/blocks/items/recipes), textures (PNG signature + IHDR, missing texture references),
animations and controllers, world data and pack bindings. Produces a persistent
`ValidationReport` with findings, error codes, compatibility info and evidence.

**Builds** — `.mcpack`, `.mcaddon`, `.mcworld` with deterministic ZIP entry order, SHA-256
checksums, structural inspection inside the archive and a build report.

**Runtime** — an adapter abstraction with a Bedrock Dedicated Server adapter (operator-supplied
binary), isolated environments, server lifecycle, incremental log capture, heartbeats, console
commands, readiness detection, and honest crash/unresponsive classification.

**Jobs** — SQLite-backed background jobs with states `QUEUED → STARTING → RUNNING → COMPLETED |
FAILED | CRASHED | TIMED_OUT | CANCELLED`, persisted logs, heartbeats, bounded waits that never
cancel, explicit cancellation and orphan recovery on startup.

**Diagnostics** — incidents with copied evidence, signature-based analysis, confidence scores and
structured diagnostic reports correlated across project → job → session → incident.

## 5. Architecture

```text
MCP tools / resources / prompts        REST /api/v1 routes
             \                        /
              v                      v
        services.BatServices (single container, one object graph)
             |
  +----------+-----------+-----------+-----------+----------+---------+
  |          |           |           |           |          |         |
projects  generators  validators   builders   runtime    jobs   diagnostics
  |          |           |           |           |          |         |
  +----------+-----------+-----------+-----------+----------+---------+
                              |
                SQLite (projects, jobs, artifacts, reports,
                        sessions, incidents, environments)
                Filesystem (workspace data/, runtime/ layout)
```

Both transports call the same functions and return the same models, so REST and MCP cannot drift
apart. That parity is covered by an integration test.

### Repository structure

```text
src/bat/
  config.py            settings from environment (immutable)
  services.py          service container + job registration (used by MCP and REST)
  cli.py               `bat` command line
  core/                models, error-code registry, safe filesystem, projects, NBT codec
  compatibility/       versions, registry, component/script registries, matrix, checker
  generators/          addon, entity, block, item, recipe, loot, spawn, animation,
                       particle, attachable, script, world, structure
  validators/          json, manifest, pack, documents, texture, animation, world, engine
  builders/            mcpack, mcaddon, mcworld, packaging, inspection, engine
  runtime/             adapter, environment manager, server manager, log parser, tester, report
  jobs/                state machine, manager, worker context, heartbeat, scheduler
  diagnostics/         evidence, classifier, analyzer, incidents, correlation, report
  observability/       structured JSON logging (redaction, rotation), health, metrics
  storage/             SQLite database, runtime layout
  api/                 FastAPI app, dependencies, schemas, routes
  mcp/                 FastMCP server, tools, resources, prompts
tests/
  unit/  integration/  compatibility/  runtime/
docs/                  architecture, compatibility, error codes, runtime
examples/              runnable vertical-slice script, MCP client config
runtime/               approved runtime layout (environments, sessions, incidents,
                       snapshots, cache) — see docs/runtime.md
```

## 6. Installation

Prerequisites: **Python 3.10+** (3.12 tested), `pip`, and a POSIX shell. For runtime tests you also
need your own Minecraft Bedrock Dedicated Server binary — BAT never downloads, bundles or
redistributes it.

```bash
git clone <your-private-repo-url> bedrock-agent-toolkit
cd bedrock-agent-toolkit
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then edit
bat doctor                    # verify configuration
```

`bat doctor` prints the resolved paths, database status, runtime adapter availability and the
registered job types. On a machine without a server binary it reports
`runtime_available: false` — that is expected and means runtime tests will be `NOT_TESTED`.

## 7. Configuration

All configuration is environment variables (see `.env.example`). Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `BAT_WORKSPACE` | `./data` | Project data, artifacts, SQLite DB, job logs |
| `BAT_RUNTIME_ROOT` | `./runtime` | Environments, sessions, incidents, snapshots, cache |
| `BAT_DATABASE` | `$BAT_WORKSPACE/bat.db` | SQLite database file |
| `BAT_API_KEY` | *(empty)* | When set, `/api/v1` requires `X-API-Key` or `Authorization: Bearer` |
| `BAT_RUNTIME_ADAPTER` | `auto` | `auto`, `bds` or `none` |
| `BAT_BEDROCK_SERVER` | *(empty)* | Path to **your** `bedrock_server` executable |
| `BAT_SERVER_START_TIMEOUT` | `120` | Seconds to wait for readiness |
| `BAT_HEARTBEAT_INTERVAL` | `5` | Heartbeat write interval |
| `BAT_UNRESPONSIVE_SECONDS` | `90` | No-output threshold before an `UNRESPONSIVE` incident |
| `BAT_MAX_FILE_BYTES` | `10485760` | Project file size limit |
| `BAT_LOG_MAX_BYTES` / `BAT_LOG_BACKUP_COUNT` | `2097152` / `5` | BAT log rotation |
| `BAT_JOB_WORKERS` | `4` | Background worker threads |
| `BAT_DEFAULT_WAIT_SECONDS` / `BAT_MAX_WAIT_SECONDS` | `30` / `300` | Bounded job waits |

## 8. Version compatibility

Compatibility is a first-class subsystem, not a footnote. `get_compatibility(<version>)` returns a
matrix where each entry carries:

```json
{
  "feature": "item.components",
  "category": "item",
  "status": "UNSUPPORTED",
  "min_version": "1.20.50",
  "evidence": "Bedrock 1.20.50 item component documentation",
  "notes": "Component-based item format. Older projects use the legacy format ..."
}
```

Statuses: `SUPPORTED` (BAT exercises it), `UNSUPPORTED` (target too old/new, or outside scope),
`NOT_TESTED` (documented but not exercised against a real runtime), `UNKNOWN` (no evidence —
BAT does not guess). Details and the current matrix: [docs/compatibility.md](docs/compatibility.md).

## 9. Running the REST API

```bash
export BAT_WORKSPACE=./data BAT_RUNTIME_ROOT=./runtime
bat serve-api --host 127.0.0.1 --port 8000
# or: python -m uvicorn "bat.api.app:create_app" --factory --port 8000
```

- OpenAPI UI: <http://127.0.0.1:8000/docs> (`/openapi.json` for the schema)
- Health: `GET /api/v1/health` → `{"status": "OK" | "DEGRADED", ...}`
- Capabilities: `GET /api/v1/version`

Example session (verified against this repository):

```bash
BASE=http://127.0.0.1:8000/api/v1

# 1. create an add-on project
PID=$(curl -s -X POST $BASE/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"My Addon","project_type":"ADDON","target_version":"1.21.80"}' \
  | python -c 'import json,sys;print(json.load(sys.stdin)["project"]["project_id"])')

# 2. write a file (relative path, inside the project)
curl -s -X PUT $BASE/projects/$PID/files/resource_packs/readme.txt \
  -H 'Content-Type: application/json' -d '{"content":"hello"}'

# 3. validate
curl -s -X POST $BASE/projects/$PID/validate | python -m json.tool | head -20

# 4. build and download
AID=$(curl -s -X POST $BASE/projects/$PID/build -H 'Content-Type: application/json' -d '{}' \
  | python -c 'import json,sys;print(json.load(sys.stdin)["artifacts"][0]["artifact_id"])')
curl -s -o myaddon.mcaddon $BASE/artifacts/$AID/download
```

Authentication: with `BAT_API_KEY` set, send it as `X-API-Key: <key>` or
`Authorization: Bearer <key>`. Health/version stay public. Without the key, authentication is
disabled — expose the API on localhost only.

Asynchronous work: `POST /api/v1/jobs` returns `202` with a job id; poll `GET /api/v1/jobs/{id}` or
call `POST /api/v1/jobs/{id}/wait` with a bounded timeout. **A timed-out wait does not cancel the
job.** Cancellation is `POST /api/v1/jobs/{id}/cancel`.

## 10. Running the MCP server

```bash
bat serve-mcp            # stdio transport (default)
bat serve-mcp --transport sse
bat serve-mcp --transport streamable-http
```

Example MCP client configuration (see `examples/mcp-client.json`):

```json
{
  "mcpServers": {
    "bat": {
      "command": "/absolute/path/to/.venv/bin/bat",
      "args": ["serve-mcp"],
      "env": {
        "BAT_WORKSPACE": "/absolute/path/to/data",
        "BAT_RUNTIME_ROOT": "/absolute/path/to/runtime"
      }
    }
  }
}
```

### Tool conventions

Every tool returns an envelope so an agent can branch on `ok`:

```json
{"ok": true, "result": { ... }}
{"ok": false, "error": {"error_code": "BAT-COMPAT-001", "message": "...", "details": {}, "severity": "ERROR", "retryable": false}}
```

65 tools are registered: project (8), add-on generation (12), world (8), validation (8), build (7),
runtime (11), jobs/health (8), diagnostics (3). Resources:
`bat://docs/bedrock/{versions,manifest,entities,blocks,items,scripts,worlds}`,
`bat://projects/{project_id}/tree`, `bat://projects/{project_id}/report`. Prompts:
`create_addon_prompt`, `create_world_prompt`, `debug_addon_prompt`,
`fix_validation_errors_prompt`, `analyze_runtime_logs_prompt`.

## 11. The first vertical slice

```text
AI agent → create_project → write_project_file / generators → validate_project
        → build_project → artifact (.mcaddon) → inspect_artifact
```

Runnable version (creates a real project, validates it, builds and inspects the artifact):

```bash
python examples/example_workflow.py
```

Extended slice (needs your server binary):

```text
run_game_test → job → isolated environment → server started → logs + heartbeat
              → runtime report / incident
```

## 12. Runtime tests and diagnostics

```bash
# without a server binary this fails with BAT-RUNTIME-003 and test_status NOT_TESTED
curl -s -X POST $BASE/jobs -H 'Content-Type: application/json' \
  -d "{\"job_type\":\"RUNTIME_TEST\",\"project_id\":\"$PID\"}"
```

With a server configured:

```bash
export BAT_RUNTIME_ADAPTER=bds
export BAT_BEDROCK_SERVER=/path/to/bedrock_server   # your own binary
```

BAT creates an isolated environment under `runtime/environments/<env_id>/`, copies the packs and
world in (never links them), writes `server.properties`, picks a free UDP port, starts the process,
detects readiness from the log, captures output incrementally, writes heartbeats, then stops it.

Results separate what was verified from what was not:

```json
{
  "test_status": "PASS",
  "scope": "SERVER_SIDE",
  "verified": ["The Bedrock server process started and reported readiness.", "..."],
  "not_verified": [
    "Client-side rendering, textures, UI and attachables are not exercised by a server.",
    "Gameplay behaviour, balance and player experience are not asserted.",
    "GameTest execution is NOT_TESTED unless the operator's server build supports it ...",
    "Mobile/console import flows are not tested."
  ]
}
```

Retrieving evidence:

| What | REST | MCP |
|---|---|---|
| Job status / logs / report | `/jobs/{id}`, `/jobs/{id}/logs`, `/jobs/{id}/report` | `get_job_status`, `get_job_logs`, `get_job_report` |
| Session status / logs / heartbeat / report | `/runtime/sessions/{id}/...` | `get_runtime_status`, `get_runtime_logs`, `get_runtime_heartbeat`, `get_runtime_report` |
| Incidents | `/incidents`, `/incidents/{id}`, `/incidents/{id}/diagnose` | `get_incidents`, `get_incident_details`, `diagnose_incident` |

An unexpected exit creates `runtime/incidents/<incident_id>/` containing `incident.json`,
`diagnosis.json`, and `evidence/` (session console/error/runtime logs, session report, job log).
Destroying an environment or deleting a project does **not** delete incidents, sessions or
snapshots.

## 13. Known limitations

These are real, current limits. They are also encoded in code so BAT reports them rather than
papering over them.

1. **No real Minecraft runtime in this repository's verification.** The runtime supervisor is
   verified with a *simulated* server process (readiness, logs, heartbeat, console commands,
   graceful stop, crash classification, unresponsive detection). Actual Bedrock Dedicated Server
   execution is **NOT_TESTED** here because no server binary is bundled. Real-runtime verification
   requires your binary.
2. **Client-side features cannot be verified by a server adapter.** Textures, rendering,
   attachables, particles, UI and mobile import flows are structurally validated only; their
   compatibility is reported `NOT_TESTED`.
3. **No LevelDB chunk reader.** `get_world_chunks` reports whether chunk data exists and says
   plainly that BAT does not enumerate chunks.
4. **World creation is metadata-level.** BAT writes a valid `level.dat` and world skeleton; terrain
   and chunks are generated by Minecraft on first load. A `.mcworld` exported before any load has
   no chunk data (reported in the build report).
5. **Compatibility registry is curated, not exhaustive.** Unknown features are `UNKNOWN`; script
   API minor versions are deliberately not pinned.
6. **Single node only.** SQLite + local filesystem; no distributed workers, Redis or PostgreSQL.
7. **Authentication is a static API key.** No user accounts, roles or multi-tenant isolation.
8. **Only an item format for 1.20.50+.** Legacy item documents are reported unsupported for
   generation rather than emitted unverifiably.
9. **Cancellation is cooperative.** A job is marked `CANCELLED`/`TIMED_OUT` and signalled; a handler
   blocked inside an OS call stops at its next checkpoint.
10. **No Docker-based runtime isolation adapter yet.** The adapter interface allows one, but only
    the BDS subprocess adapter ships today. `Dockerfile` packages BAT itself, not Minecraft.
11. **Runtime tests do not assert gameplay.** A `PASS` means "server loaded with the packs installed
    and reported no pack/script errors", nothing more.

## 14. Testing

```bash
pytest                                   # everything (142 tests)
pytest tests/unit tests/integration       # fast suites
pytest tests/runtime -m simulated         # simulated server-process supervision
pytest -m "not simulated"                 # exclude simulated-process tests
```

Test result vocabulary: `PASS`, `FAIL`, `NOT_SUPPORTED`, `NOT_TESTED`. Tests are never skipped or
weakened to obtain a green run, and no test claims real Minecraft verification. The simulated
server used by `tests/runtime` is a small Python script; it exercises BAT's process supervision
only.

Coverage by area: unit (versions, filesystem safety, NBT round-trip, projects, generators,
validators, builders, structures, job state machine/timeout/cancel/orphan recovery, diagnostics,
error codes), compatibility (statuses, matrix, unsupported features), integration (REST
project→file→validate→build→download, jobs, incidents, API key, MCP tool registry/errors/
resources/prompts/REST parity), runtime (readiness, incremental logs, commands, graceful stop,
crash → incident, unresponsive ≠ crash, missing binary → `NOT_TESTED`, environment isolation and
cleanup guarantees).

## 15. Security

See [SECURITY.md](SECURITY.md). Highlights: every external path goes through
`resolve_within` (absolute paths, `..`, and symlinks are rejected); project files are written
atomically with size limits; runtime environments are copied, not linked, and their paths are
checked to stay under the runtime root; server processes get a minimal environment and their own
session directory; logs redact obvious secrets; no secrets are needed in project files; the API key
is compared in constant time. BAT never executes a shell string: it runs one configured executable
with `shell=False`.

Deleting data: `delete_project` keeps incidents, sessions and artifacts unless you pass
`purge_artifacts=true`; `destroy_test_environment` keeps incidents, sessions and snapshots.

## 16. Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: keep the two transports on the shared
service layer, register any new error code before raising it, add tests for behaviour you claim,
and never report a status BAT did not observe.

## 17. License

MIT — see [LICENSE](LICENSE). Minecraft is a trademark of Mojang Synergies AB. BAT is not
affiliated with or endorsed by Mojang or Microsoft, and it does not redistribute Minecraft server
binaries or assets.
