# Version compatibility

BAT supports Minecraft Bedrock **1.19.0 – 1.21.80**. This document explains how compatibility is
modelled and what is currently claimed.

## Vocabulary

| Status | Meaning | Who should act |
|---|---|---|
| `SUPPORTED` | BAT exercises this feature itself (generation + structural validation) for the target version. | Nothing required. |
| `UNSUPPORTED` | Either the target version is outside the supported range, or the feature requires a different version, or BAT does not support it at all. | Choose another target or technique. |
| `NOT_TESTED` | Documented for this range, but BAT has not executed it against a real Minecraft runtime. | Verify with your own runtime before shipping. |
| `UNKNOWN` | BAT has no evidence (e.g. a feature or component missing from its registry). | Investigate manually; do not assume either way. |

`SUPPORTED` never means "verified in-game". It means BAT's own generation and validation path
handled it. Anything that requires Minecraft to load or render it is at best `NOT_TESTED`.

## Where the data lives

| Module | Contents |
|---|---|
| `compatibility/versions.py` | Parsing/comparison, supported range, `format_version` selection |
| `compatibility/registry.py` | Feature records with `min_version`, `evidence`, `verified` |
| `compatibility/component_registry.py` | Entity/block/item components with minimum versions |
| `compatibility/script_api_registry.py` | Script modules BAT writes and the stable-API floor |
| `compatibility/feature_matrix.py` | Matrix rendering and labels |
| `compatibility/compatibility_checker.py` | Scans a project for features actually used |

## Notable entries

| Feature | Range | Status today |
|---|---|---|
| Pack manifest `format_version: 2` | 1.19.0+ | SUPPORTED |
| Entity server definitions | 1.19.0+ | SUPPORTED (structure) |
| Blocks with components | 1.19.0+ | SUPPORTED (structure) |
| Item components (`minecraft:icon`, …) | 1.20.50+ | NOT_TESTED; `< 1.20.50` → UNSUPPORTED |
| Shaped/shapeless recipes | 1.19.0+ | SUPPORTED (structure) |
| Spawn rules / loot tables | 1.19.0+ | SUPPORTED (structure) |
| Bone animations / controllers | 1.19.0+ | SUPPORTED generation, rendering NOT_TESTED |
| Particles | 1.19.0+ | SUPPORTED structure, rendering NOT_TESTED |
| Attachables | 1.19.60+ | NOT_TESTED (client-side rendering) |
| Script modules | 1.19.0+ | NOT_TESTED (needs a running server) |
| GameTest via scripts | depends on server build | NOT_TESTED / UNKNOWN |
| `level.dat` metadata | 1.19.0+ | SUPPORTED (own codec, round-trip verified) |
| World pack bindings | 1.19.0+ | SUPPORTED |
| `.mcstructure` | 1.19.0+ | SUPPORTED (own codec, round-trip verified) |
| Terrain/chunk generation | — | UNSUPPORTED (Minecraft generates it, not BAT) |

## Checking a version

MCP: `get_compatibility({"version": "1.19.80"})`
REST: `GET /api/v1/compatibility?version=1.19.80`

Response includes `counts`, `by_category`, per-feature records and the component table. Current
matrix at the time of writing: 1.21.80 → 16 SUPPORTED, 1 UNSUPPORTED, 10 NOT_TESTED, 0 UNKNOWN;
1.19.0 → 16 SUPPORTED, 6 UNSUPPORTED, 5 NOT_TESTED, 0 UNKNOWN (numbers change as entries are added —
the endpoint is the source of truth).

## Rules

1. BAT never silently upgrades a project's `target_version`.
2. `format_version` in generated documents follows the target's minor series (`1.19.x → 1.19.x`,
   `1.20.x → 1.20.0`, `1.21.x → 1.21.0`).
3. A generator whose feature is `UNSUPPORTED` for the target raises `BAT-COMPAT-002` instead of
   writing a document that cannot load.
4. Script API minor versions are not pinned: BAT writes the stable module floor and tells you the
   runtime behaviour is untested.
5. Adding a feature means adding a registry record **with evidence**. If you cannot verify it, set
   `verified=False` so it reports `NOT_TESTED`.
