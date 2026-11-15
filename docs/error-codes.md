# Diagnostic error codes

Every code is registered in `src/bat/core/errors.py`. `make_error` / `BatError` refuse unregistered
codes, so this document is a complete list. Retrieve it at runtime:

- MCP: no dedicated tool; error responses carry `error_code`.
- REST: `GET /api/v1/error-codes`
- CLI: `bat errors`

Format: `BAT-<AREA>-<NNN>`.

## Input, lookup and filesystem

| Code | Severity | Meaning |
|---|---|---|
| `BAT-INPUT-001` | ERROR | A request argument is missing or malformed. |
| `BAT-NOTFOUND-001` | ERROR | Project not found (HTTP 404). |
| `BAT-NOTFOUND-002` | ERROR | File not found inside the project (404). |
| `BAT-NOTFOUND-003` | ERROR | Job not found (404). |
| `BAT-NOTFOUND-004` | ERROR | Artifact or build report not found (404). |
| `BAT-NOTFOUND-005` | ERROR | Runtime session, environment or report store not found (404/410). |
| `BAT-NOTFOUND-006` | ERROR | Incident not found (404). |
| `BAT-NOTFOUND-007` | ERROR | World file or structure not found (404). |
| `BAT-PATH-001` | ERROR | Path escapes its root (absolute path, `..`, or resolution outside). |
| `BAT-PATH-002` | ERROR | File exceeds the configured size limit (HTTP 413). |
| `BAT-PATH-003` | ERROR | Content is not valid UTF-8 text. |
| `BAT-PATH-004` | ERROR | Symlink or non-regular file rejected. |

## Projects

| Code | Meaning |
|---|---|
| `BAT-PROJECT-001` | Unsupported project type or target version. |
| `BAT-PROJECT-002` | A project with that name already exists (HTTP 409). |
| `BAT-PROJECT-003` | Operation not valid for this project type (e.g. packs on a WORLD project). |
| `BAT-PROJECT-004` | Project is archived and cannot be modified (409). |

## Validation

| Code | Meaning |
|---|---|
| `BAT-JSON-001` | A project JSON file is not valid JSON (finding includes line/column). |
| `BAT-MANIFEST-001` | Manifest missing required fields, bad UUID, bad module shape. |
| `BAT-MANIFEST-002` | Duplicate pack/module UUID across manifests. |
| `BAT-PACK-001` | Pack structure/module mismatch, missing script entry, unresolved dependency. |
| `BAT-ENTITY-001` | Entity document invalid (identifier, components, version availability). |
| `BAT-BLOCK-001` | Block document invalid. |
| `BAT-ITEM-001` | Item document invalid or components unavailable for the target. |
| `BAT-RECIPE-001` | Recipe invalid (pattern/key/result/tags). |
| `BAT-TEXTURE-001` | Texture missing, unreadable, not a PNG, or a referenced texture is absent. |
| `BAT-ANIMATION-001` | Animation/controller document invalid. |
| `BAT-WORLD-001` | World data missing or invalid (`level.dat`, bindings, name). |
| `BAT-VALIDATION-001` | Reserved for aggregate validation failures. |

## Compatibility

| Code | Meaning |
|---|---|
| `BAT-COMPAT-001` | Target version outside 1.19.0–1.21.80. |
| `BAT-COMPAT-002` | Feature unsupported for the target version (e.g. items before 1.20.50, `min_engine_version` newer than target). |
| `BAT-COMPAT-003` | Reserved: compatibility could not be established. |

## Build and artifacts

| Code | Meaning |
|---|---|
| `BAT-BUILD-001` | Build failed (including a strict build refused by validation). |
| `BAT-BUILD-002` | Nothing buildable for the requested artifact type. |
| `BAT-ARTIFACT-001` | Artifact file missing/corrupt or checksum mismatch. |
| `BAT-ARTIFACT-002` | Artifact internal structure unexpected (missing manifest/`level.dat`). |

## Runtime

| Code | Severity | Meaning |
|---|---|---|
| `BAT-RUNTIME-001` | CRITICAL | Runtime process exited unexpectedly (crash or premature exit). |
| `BAT-RUNTIME-002` | ERROR | Server did not report readiness before the start timeout. |
| `BAT-RUNTIME-003` | ERROR | No usable server executable / required file missing. Runtime test is `NOT_TESTED`. |
| `BAT-RUNTIME-004` | CRITICAL | Process alive but unresponsive (heartbeat/idle threshold exceeded). |
| `BAT-RUNTIME-005` | ERROR | Job exceeded its timeout; marked `TIMED_OUT`. |
| `BAT-RUNTIME-006` | ERROR | Environment failure (missing directory, path escape, process cannot start, command undeliverable). |
| `BAT-RUNTIME-007` | ERROR | Operation not supported by the active adapter. |
| `BAT-SCRIPT-001` | ERROR | Minecraft reported a script error. |

## Jobs

| Code | Meaning |
|---|---|
| `BAT-JOB-001` | Job cannot be cancelled / was cancelled (`CANCELLED`). |
| `BAT-JOB-002` | Worker ended without a terminal state (orphan recovery uses this). |
| `BAT-JOB-003` | Queue rejected the work (shut down / saturated). |
| `BAT-JOB-004` | Handler raised an unhandled error (recorded, not swallowed). |

## Sandbox

| Code | Meaning |
|---|---|
| `BAT-SANDBOX-001` | Operation would break runtime isolation (e.g. deleting a path outside the runtime root). |

## How codes reach the caller

MCP:

```json
{"ok": false, "error": {"error_code": "BAT-RUNTIME-003", "message": "...", "details": {}, "severity": "ERROR", "retryable": false}}
```

REST:

```json
{"error": {"error_code": "BAT-NOTFOUND-001", "message": "...", "severity": "ERROR", "retryable": false, "details": {}}}
```

Validation findings carry the same codes inside a report's `findings[]` and `error_codes[]`.
