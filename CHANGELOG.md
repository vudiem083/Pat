# Changelog

All notable changes to BAT — Bedrock Agent Toolkit.

## [0.1.0] — 2026-11-15

Initial MVP: a working vertical slice for Minecraft Bedrock add-ons and worlds, with MCP and REST
transports over one shared service layer.

### Added

- **Core**: typed shared models (Project, Job, Artifact, ValidationReport, RuntimeSession,
  Incident, DiagnosticReport), documented error-code namespace (48 codes), safe filesystem layer,
  SQLite persistence, runtime directory layout.
- **Projects**: ADDON / WORLD / COMBINED types, creation with seeded packs and world, tree,
  atomic file read/write with backups, deletion that retains diagnostics.
- **Add-on generation**: entity, block, item (1.20.50+ component format), shaped/shapeless recipe,
  loot table, spawn rules, animation, animation controller, particle, attachable, script module
  with manifest wiring.
- **World toolkit**: little-endian NBT codec for real `level.dat` read/write, inspection,
  snapshot-backed metadata editing with write verification, pack bindings, `.mcstructure`
  creation/import/export, chunk reporting that does not pretend to parse LevelDB.
- **Compatibility**: version-aware feature registry, component and script registries, feature
  matrix with SUPPORTED/UNSUPPORTED/UNKNOWN/NOT_TESTED.
- **Validation**: JSON, manifest, pack, content document, texture, animation and world validators
  plus an aggregating engine with persistent reports.
- **Builds**: `.mcpack`, `.mcaddon`, `.mcworld` with checksums, archive inspection and build
  reports.
- **Runtime**: adapter abstraction, BDS adapter for operator-supplied binaries, isolated
  environments, server supervision with incremental logs, heartbeats, console commands,
  readiness detection, crash/unresponsive classification and incidents.
- **Jobs**: SQLite-backed queue and workers, explicit state machine, timeouts, cancellation,
  logs, reports, orphan recovery.
- **Diagnostics**: evidence collection into incident directories, signature classification,
  confidence-scored analysis, diagnostic reports, project→job→session→incident correlation.
- **Interfaces**: 65 MCP tools, 7 documentation resources + 2 project resources, 5 prompt
  templates; REST API with 51 documented paths, OpenAPI, optional API key, structured errors.
- **Documentation**: English and Vietnamese READMEs, architecture/compatibility/error-code/runtime
  docs, security policy, contribution guide, MIT license.
- **Tests**: 142 tests across unit, compatibility, integration and runtime (simulated server
  process supervision).

### Known limitations at 0.1.0

No real Minecraft runtime verification is included (needs an operator-supplied Bedrock Dedicated
Server); client-side features are structurally validated only; no LevelDB reader; no Docker runtime
adapter; single-node only; static API key authentication. See README §13.
