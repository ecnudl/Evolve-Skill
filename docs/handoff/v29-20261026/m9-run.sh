#!/usr/bin/env bash
# Each chain confirms its first call and runs fresh anchor, S1-S5, I and C_end units.
# Stage reads overlap the next step; learning pauses leave launched reads alive.
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M9_OPS/m9-env.sh"
m9_require_paths
test "${M9_OWNER_LAUNCH:-}" = main-v9-reviewed-launch || exit 2
case "${1:-}" in G|D) chain="$1";; *) printf '%s\n' 'Use G or D' >&2; exit 2;; esac
cd -- "$M9_SNAPSHOT"
export PYTHONPATH="$M9_SNAPSHOT"
if test -e "$M9_ROOT/$chain/chain.json"; then
  test "${M9_OWNER_RECOVERY:-}" = main-v9-reviewed-recovery || { printf '%s\n' 'Paused/existing chain requires reviewed recovery; no automatic relaunch' >&2; exit 2; }
  test -s "$M9_ROOT/$chain/recovery.json" || { printf '%s\n' 'Owner recovery record required' >&2; exit 2; }
fi
m9_step "run-$chain" m9_cli run --manifest "$M9_MANIFEST" --chain "$chain"
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"chain_complete"}'
