# Security policy

## Reporting a vulnerability

Do not open a public issue for a security problem. Report it privately to the maintainers of this
repository (or, in a private fork, through your organisation's security channel) with:

- affected version/commit,
- a description of the impact,
- reproduction steps or a proof of concept,
- any suggested mitigation.

You will get an acknowledgement and an assessment. Please allow time for a fix before disclosure.

## Threat model

BAT is a local, single-tenant developer tool that manipulates files and launches a
user-supplied server binary. The relevant threats are:

| Threat | Mitigation in BAT |
|---|---|
| Path traversal via MCP/REST arguments | Every external path goes through `core.filesystem.resolve_within`, which rejects absolute paths, `..`, symlinks and anything resolving outside the root. Tests cover each case. |
| Arbitrary command execution | BAT never builds a shell string. It executes exactly one configured executable (`BAT_BEDROCK_SERVER`) with `shell=False`. Console commands are written to that process's stdin after validation. |
| Oversized uploads / disk exhaustion | `BAT_MAX_FILE_BYTES` and `BAT_MAX_UPLOAD_BYTES` are enforced on project writes and structure imports. |
| Malicious archive content | BAT writes ZIP artifacts, it does not extract untrusted archives. Downloaded artifacts are generated locally from project content. |
| Environment escape | Runtime environments are checked to live under `runtime/environments`; content is copied in, never symlinked; destroying an environment refuses paths outside the runtime root and keeps incidents/sessions. |
| Secret leakage in logs | Structured logs redact API keys/tokens/passwords and the values of `BAT_API_KEY`/`OPENAI_API_KEY` when present. |
| Unauthorised API access | Set `BAT_API_KEY`; comparison is constant-time. Without it, authentication is disabled, so bind to `127.0.0.1` (the default). |
| Data loss on destructive edits | Project writes are atomic with `.bak` backups; world metadata edits snapshot first and verify the write; project/environment deletion retains incidents, sessions and (unless explicitly purged) artifacts. |
| Artifact tampering | Every artifact stores a SHA-256 checksum; `inspect_artifact` reports a mismatch as an integrity failure. |

## What BAT deliberately does not do

- It does not download or redistribute Minecraft server binaries or assets.
- It does not accept licence/EULA terms on your behalf.
- It does not run as root by design; run it with the least privilege needed to read/write the
  workspace and runtime directories.
- It does not implement multi-tenant isolation, roles, or user accounts. Do not expose the REST API
  to untrusted networks without a reverse proxy that adds authentication and TLS.

## Secrets handling

Keep configuration in `.env` (git-ignored) or your secret manager. Never commit `.env`, API keys,
or server licence files. If a secret is ever committed, rotate it; removing it from the working tree
is not enough.

## Supported versions

The project is pre-1.0. Security fixes are applied to the `main` branch; pin a commit if you need
reproducible behaviour.
