#!/usr/bin/env bash
# Run the BAT test suite.
#
#   scripts/run_tests.sh                # everything
#   scripts/run_tests.sh tests/unit -q  # subset
#
# Requires the project virtualenv (see README installation).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python -m pytest "$@"
