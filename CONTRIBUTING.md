# Contributing to BAT

Thanks for helping. BAT is opinionated about one thing: **never claim a result that was not
observed**. Contributions that violate honesty rules will be rejected even if the code is clean.

## Ground rules

1. **One service layer.** MCP tools and REST routes must call `bat.services.BatServices` (or the
   objects it wires). Do not add business logic to a transport.
2. **Register error codes before raising them.** Add an `ErrorDefinition` to
   `src/bat/core/errors.py`; `make_error` refuses unregistered codes by design.
3. **Compatibility needs evidence.** New generator/validator features need a registry entry with
   `evidence` and an honest `verified` flag. If you cannot verify it against a runtime, leave it
   `NOT_TESTED` and say so.
4. **Statuses are earned.** `PASS` only when the check actually ran. Missing environment →
   `NOT_TESTED`, missing capability → `NOT_SUPPORTED`.
5. **No silent failure.** Exceptions become structured errors with a code; nothing is swallowed.
6. **Tests for behaviour.** If you claim it works, test it. Do not weaken or skip existing tests to
   get a green run.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Useful commands:

```bash
pytest -q                                  # full suite
pytest tests/unit -q                        # fast feedback
pytest tests/runtime -m simulated -q        # process supervision (simulated server)
bat doctor                                  # configuration + runtime readiness
python examples/example_workflow.py          # end-to-end slice
```

## Adding a validation rule

1. Choose the file that owns the area (`validators/documents.py`, `validators/world_validator.py`, …).
2. Return `Finding` objects with a registered code, severity and `file_path`/`line_number` when known.
3. Register the validator in `validators/engine.py` so it runs in `validate_project`.
4. Add a unit test that fails before your change and passes after it — include the negative case.

## Adding an MCP tool

1. Implement the operation in `services.py` (or the object it owns).
2. Register the tool in the relevant `mcp/tools/*.py` module using the `@mcp.tool()` + `@tool`
   decorator pair so the `{ok, result}` / `{ok, error}` envelope is preserved.
3. Give it a docstring: agents rely on it for tool selection.
4. If it is long-running, make it a job (`services.jobs.submit(...)`) instead of blocking the call.
5. Add a REST route for the same operation if it is part of the public API surface.

## Adding a REST endpoint

- Put it under `/api/v1` with a router in `src/bat/api/routes/`.
- Add a request model to `src/bat/api/schemas.py`; return domain models/dicts from `core.models`.
- Raise `BatError` (or `make_error`) so the handler returns the documented error shape.
- Apply `require_api_key` to anything that mutates state.

## Pull requests

- Keep the change focused; describe the behaviour, the evidence, and what you could not verify.
- Include the test command you ran and its result.
- Update docs (`README.md`, `README.vi.md`, `docs/*`) when behaviour changes. Both READMEs must stay
  equivalent.
- Do not add dependencies casually; BAT's runtime dependency set is intentionally small
  (FastAPI, uvicorn, pydantic, mcp).

## Commit messages

Short imperative subject, then what changed and why. Reference the module. Example:

```
validators: reject min_engine_version newer than the project target

A pack whose min_engine_version exceeds the target will not load, so the
manifest validator now raises BAT-COMPAT-002 instead of silently accepting it.
```
