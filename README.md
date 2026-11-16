<div align="center">

# BAT — Bedrock Agent Toolkit

**Let AI agents work with *real* Minecraft Bedrock projects — not JSON that merely looks valid.**

MCP server · REST API · Python 3.12 · Minecraft Bedrock 1.19 – 1.21.80 · MIT

[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](#requirements)
[![Tests](https://img.shields.io/badge/tests-142%20passed-2ea44f)](#running-the-tests)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-65-6f42c1)](#mcp-server-for-ai-agents)
[![REST](https://img.shields.io/badge/REST%20endpoints-51-009688)](#rest-api)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

## The problem

An AI agent can produce a `manifest.json`, an entity and a recipe in seconds. What it usually cannot
tell you is:

- Will Minecraft actually **load** this pack?
- Is the manifest valid for the **target version** (1.20.50? 1.21.80?)?
- Why did the server **crash** right after the pack was installed — and where is the evidence?
- Does this feature even exist in that version, or is the model hallucinating it?

The result is a guessing loop: the agent writes files, you open Minecraft, something breaks, you
paste a log back, and the agent guesses at a cause.

**BAT closes that loop.** It is a working, tested toolkit that turns "write some files" into a
verified pipeline: create → validate → build → test → diagnose.

## What BAT is

One service layer, two interfaces:

| Interface | For |
|---|---|
| **MCP server** (FastMCP) | AI agents: 65 tools, 7 documentation resources, 2 project resource templates, 5 prompts |
| **REST API** (FastAPI, `/api/v1`) | Apps, CI and scripts: 51 documented, OpenAPI-described endpoints |

Both call the **same** business layer (`bat.services.BatServices`) and return the **same** Pydantic
models. REST and MCP cannot drift apart — an integration test enforces it.

## What makes it different from a JSON generator

> **Principle: BAT reports only what it actually observed.**

Enforced in code, not just in prose:

- **No version guessing.** Every feature has a version-aware registry entry with its evidence.
  Unverified → `NOT_TESTED`. No data → `UNKNOWN`. Never a default "supported".
- **No fake passes.** Test results are only `PASS`, `FAIL`, `NOT_SUPPORTED` or `NOT_TESTED`. No
  server? You get `NOT_TESTED` with an error code, not a green check mark.
- **A crash is a crash.** A dead process is recorded as `CRASHED` with an incident and copied
  evidence — never downgraded to "timeout" to make the report look tidy.
- **No invented error codes.** 48 documented `BAT-*` codes; `make_error` refuses an unregistered one.
- **No invented root causes.** When the evidence does not support a cause, the diagnosis says so.

## Requirements

| | |
|---|---|
| Python | **3.12** (3.11 is not tested) |
| OS | Linux or macOS for the API/MCP; runtime tests additionally need a platform supported by Bedrock Dedicated Server (Windows Server / Ubuntu) |
| Optional | Docker 24+ and Docker Compose v2, if you want the container path |
| Optional | A Bedrock Dedicated Server executable that **you** supply, for real runtime tests |

BAT never downloads, bundles or redistributes Minecraft server binaries, and has no runtime
dependency on Java.

## Installation

### Option A — from source (recommended)

```bash
git clone https://github.com/vudiem083/Pat.git
cd Pat

python3.12 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install -e .                # install BAT
pip install -e ".[dev]"         # install BAT + test/lint tooling
```

`pip install -e .` installs the `bat` command in editable mode, so code changes take effect without
reinstalling. Confirm the install:

```bash
bat --version                   # BAT 0.1.0
bat doctor                      # configuration + runtime readiness report
```

`bat doctor` prints the workspace paths, database location, job worker count, log settings and the
runtime adapter status. It exits non-zero when something essential is misconfigured.

### Option B — Docker

```bash
cp .env.example .env            # optional: set BAT_API_KEY before exposing a port
docker compose up -d --build
curl -s http://127.0.0.1:8000/api/v1/health
```

The Compose file mounts `./data` (projects, artifacts, SQLite, job logs) and `./runtime`
(environments, sessions, incidents, snapshots, cache) so state survives container restarts. The
image runs as an unprivileged user (UID 10001); if a bind mount is not writable, fix ownership on the
host:

```bash
sudo chown -R 10001:10001 data runtime
```

A plain Docker run works too:

```bash
docker build -t bat:0.1.0 .
docker run --rm -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" -v "$PWD/runtime:/app/runtime" bat:0.1.0
```

### Configuration

Settings come from environment variables (or a `.env` file, which is git-ignored). Copy the template
and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `BAT_WORKSPACE` | `./data` | projects, artifacts, `bat.db`, `logs/` |
| `BAT_RUNTIME_ROOT` | `./runtime` | environments, sessions, incidents, snapshots, cache |
| `BAT_DATABASE` | `$BAT_WORKSPACE/bat.db` | SQLite file |
| `BAT_HOST` / `BAT_PORT` | `127.0.0.1` / `8000` | REST bind address |
| `BAT_API_KEY` | *(empty)* | when set, every `/api/v1` request needs `X-API-Key` or a bearer token |
| `BAT_RUNTIME_ADAPTER` | `auto` | `auto` or `bds` |
| `BAT_BEDROCK_SERVER` | *(empty)* | absolute path to your `bedrock_server` executable |
| `BAT_SERVER_START_TIMEOUT` | `120` | seconds to wait for server readiness |
| `BAT_UNRESPONSIVE_SECONDS` | `90` | silence after which a live server is reported unresponsive |
| `BAT_JOB_WORKERS` | `4` | background job worker threads |
| `BAT_MAX_FILE_BYTES` | `10485760` | per-file write limit |
| `BAT_MAX_WAIT_SECONDS` | `300` | upper bound for a single `wait` call |
| `BAT_LOG_MAX_BYTES` / `BAT_LOG_BACKUP_COUNT` | `2097152` / `5` | BAT log rotation |

Never commit a real `.env`. There is no configuration that puts a secret into project files.

### Verify the installation

```bash
bat errors | head              # 48 documented error codes
bat compat 1.19.80             # feature matrix for a target version
python examples/example_workflow.py
```

The example runs a complete slice in a temporary workspace (nothing in `./data` is touched) and
finishes with real output:

```text
1. project created: dd050b66-1ca9-4517-8d1e-c4ccdb41efcf
   generated item: behavior_packs/example_gem_addon/items/example_gem.json
   ...
2. validation: WARN (3 findings)
3. artifacts:
   MCPACK example_gem_addon_behavior.mcpack (2731 bytes, integrity_ok=True)
4. compatibility for items on 1.19.80: UNSUPPORTED (min 1.20.50)
5. runtime test: job=FAILED error=BAT-RUNTIME-003 test_status=NOT_TESTED
```

That last line is the design working as intended: with no server installed, BAT refuses to call the
test a pass.

## Quick start with the CLI

```bash
# create a project (types: ADDON, WORLD, COMBINED; range 1.19.0–1.21.80)
bat project create "My Addon" --type ADDON --version 1.21.80
bat project list
export PID=<project_id from the listing>

# inspect and validate
bat project show "$PID"
bat validate "$PID"                       # persistent ValidationReport

# build packaged artifacts
bat build "$PID"                          # all artifact types for the project
bat build "$PID" --type MCADDON --strict  # refuse to build when validation fails

# version reality check
bat compat 1.20.0                         # which features exist on this target
```

Generated content goes through the same layer whether it comes from the CLI, REST or MCP; the CLI
exposes project/validate/build/compat/errors, while content generation, world editing and runtime
control are available over the two APIs.

## REST API

```bash
bat serve-api --host 127.0.0.1 --port 8000
# interactive docs: http://127.0.0.1:8000/docs
```

Representative calls:

```bash
BASE=http://127.0.0.1:8000/api/v1

curl -s $BASE/health
curl -s $BASE/version
curl -s $BASE/projects

# create a project
curl -s -X POST $BASE/projects -H 'Content-Type: application/json' -d '{
  "name": "My Addon", "project_type": "ADDON", "target_version": "1.21.80"
}'

# generate content (the generator spec goes under "spec"), validate, build
curl -s $BASE/projects/$PID/content                       # list generators
curl -s -X POST $BASE/projects/$PID/content/item \
  -H 'Content-Type: application/json' -d '{"spec": {"name": "example_gem", "max_stack": 16}}'
curl -s -X POST $BASE/projects/$PID/validate
curl -s -X POST $BASE/projects/$PID/build -H 'Content-Type: application/json' -d '{"artifact_type": "MCADDON"}'

# background job + evidence
curl -s -X POST $BASE/jobs -H 'Content-Type: application/json' \
  -d '{"job_type": "RUNTIME_TEST", "project_id": "'$PID'"}'
curl -s $BASE/jobs/$JOB_ID
curl -s "$BASE/jobs/$JOB_ID/logs?tail=50"
curl -s $BASE/jobs/$JOB_ID/report
```

When `BAT_API_KEY` is set, add the header to every call:

```bash
curl -s -H "X-API-Key: $BAT_API_KEY" $BASE/projects
```

Errors are structured and always carry a documented code:

```json
{"error": {"error_code": "BAT-NOTFOUND-001", "message": "Project not found",
           "severity": "ERROR", "retryable": false, "details": {}}}
```

## MCP server for AI agents

```bash
bat serve-mcp                       # stdio (default)
bat serve-mcp --transport streamable-http
```

Register it with any MCP client — for example:

```json
{
  "mcpServers": {
    "bat": {
      "command": "/absolute/path/to/Pat/.venv/bin/bat",
      "args": ["serve-mcp"],
      "env": {
        "BAT_WORKSPACE": "/absolute/path/to/Pat/data",
        "BAT_RUNTIME_ROOT": "/absolute/path/to/Pat/runtime",
        "BAT_BEDROCK_SERVER": "/absolute/path/to/bedrock_server"
      }
    }
  }
}
```

A copy of this file lives at [`examples/mcp-client.json`](examples/mcp-client.json). Tools are
grouped by ownership: projects, add-ons, worlds, validation, builds, runtime, jobs/health,
diagnostics. Long operations return a job id; a bounded `wait` never cancels the job, and
disconnecting never kills it.

## Running against a real Bedrock server

Runtime tests are the only part of BAT that needs Minecraft itself.

1. Obtain the **Bedrock Dedicated Server** package for your platform from Mojang's official download
   page and extract it somewhere outside this repository.
2. Make the executable runnable and point BAT at it:

   ```bash
   chmod +x /opt/bds/bedrock_server
   export BAT_RUNTIME_ADAPTER=bds
   export BAT_BEDROCK_SERVER=/opt/bds/bedrock_server
   bat doctor            # should now report the adapter as available
   ```

3. Run a test over the API or MCP (`POST /api/v1/jobs` with `{"job_type": "RUNTIME_TEST", ...}`, or
   the `run_game_test` MCP tool).

What BAT does: copies the world and packs into an isolated environment under
`runtime/environments/<env_id>/`, writes `server.properties`, starts the server with
`shell=False`, watches readiness, captures logs incrementally, records heartbeats, classifies the
exit, and copies evidence into an incident when something goes wrong.

Interpretation of results, honestly:

| Result | Meaning |
|---|---|
| `PASS` | server started with the packs installed and reported no pack/script error |
| `FAIL` | a concrete error was observed (log signature, crash, missing file) |
| `NOT_TESTED` | no usable server environment — **not** a pass |
| `NOT_SUPPORTED` | the active adapter cannot perform this check |

Client-side concerns (textures, models, animations, UI) are `NOT_TESTED` by definition: a dedicated
server cannot render them.

## Project layout

```text
<workspace>/projects/<project_id>/
  project.json                  canonical project record
  files/                        sandboxed content root (relative paths only)
    behavior_packs/<pack>/manifest.json + content
    resource_packs/<pack>/manifest.json + content
    world/level.dat, levelname.txt, world_*_packs.json, structures/, db/
<workspace>/artifacts/<project>/<artifact>/   packaged file + build_report.json
<workspace>/logs/jobs/<job>.log|.heartbeat.json|.report.json
<runtime>/environments|sessions|incidents|snapshots|cache
```

## Running the tests

```bash
pytest                          # 142 tests
pytest tests/unit               # fast, no processes
pytest tests/runtime            # process supervision (simulated server)
pytest -m simulated             # only simulated-runtime tests
```

Test outcomes use the same vocabulary as the product: `PASS`, `FAIL`, `NOT_SUPPORTED`,
`NOT_TESTED`. Runtime supervision tests launch a clearly marked **simulated** Python "server"; real
Bedrock execution remains `NOT_TESTED` unless you supply a server.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `runtime test: ... error=BAT-RUNTIME-003 test_status=NOT_TESTED` | No usable server. Set `BAT_BEDROCK_SERVER` and `BAT_RUNTIME_ADAPTER=bds`, or accept `NOT_TESTED`. |
| `BAT-RUNTIME-002` | Server started but never reported readiness inside `BAT_SERVER_START_TIMEOUT`. |
| `BAT-COMPAT-002` when generating an item on 1.19.x | Item components need 1.20.50+; use a newer target or a different technique. |
| `BAT-PATH-001` | A path escaped the project root (absolute path, `..`, or symlink). Use relative paths. |
| `BAT-PATH-002` | File exceeds `BAT_MAX_FILE_BYTES`. |
| HTTP 401 from `/api/v1` | `BAT_API_KEY` is set; send `X-API-Key` or a bearer token. |
| HTTP 403 with an `Origin` header | Cross-origin mutation rejected; call from the same origin or a client without `Origin`. |
| Job stuck in `QUEUED` | All `BAT_JOB_WORKERS` threads are busy; raise the limit or inspect `GET /api/v1/jobs`. |
| `Permission denied` on `data/` in Docker | `sudo chown -R 10001:10001 data runtime`. |
| Port already in use | `bat serve-api --port 8001`. |

## Known limitations

No LevelDB chunk reader (reported as unsupported rather than guessed); terrain/chunk generation is
Minecraft's job, not BAT's; world creation is metadata-level; client-side rendering is validated
structurally only; compatibility registry is curated and deliberately contains `UNKNOWN`/`NOT_TESTED`
entries; single-node SQLite storage; static API key rather than user accounts; cooperative
cancellation; no Docker runtime adapter yet.

## Documentation

- [Architecture](docs/architecture.md) — layers, request/job flows, timeout semantics
- [Version compatibility](docs/compatibility.md) — statuses, registry, evidence rules
- [Error codes](docs/error-codes.md) — all 48 codes with meaning and severity
- [Runtime design](docs/runtime.md) — layout, isolation, supervision, evidence retention
- [Security policy](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## License and trademarks

MIT — see [LICENSE](LICENSE). Minecraft is a trademark of Mojang Synergies AB. BAT is not affiliated
with, endorsed by or sponsored by Mojang or Microsoft, and does not redistribute any Minecraft
binaries or assets.
