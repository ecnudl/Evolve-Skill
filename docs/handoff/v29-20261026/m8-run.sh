#!/usr/bin/env bash
# Each chain performs its own first-call confirmation and records all failures.
set -euo pipefail
M8_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M8_OPS/m8-env.sh"
m8_require_paths
test "${M8_OWNER_LAUNCH:-}" = main-v8-reviewed-launch || exit 2
case "${1:-}" in G|D) chain="$1";; *) printf '%s\n' 'Use G or D' >&2; exit 2;; esac
cd -- "$M8_SNAPSHOT"
export PYTHONPATH="$M8_SNAPSHOT"
m8_step "run-$chain" m8_cli run --manifest "$M8_MANIFEST" --chain "$chain"
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"chain_complete"}'
