#!/usr/bin/env bash
# Future operator template, not an authorization to launch or stop any live run.
set -euo pipefail
M8_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M8_OPS/m8-env.sh"
m8_require_paths
test "${M8_OWNER_LAUNCH:-}" = main-v8-reviewed-launch || { printf '%s\n' 'Reviewed owner launch decision required' >&2; exit 2; }
cd -- "$M8_SNAPSHOT"
export PYTHONPATH="$M8_SNAPSHOT"
m8_step manifest m8_cli v214-manifest --configuration main-v8 --out "$M8_MANIFEST" --root "$M8_ROOT" \
  --s0 "$M8_PRE/s0/v214-s0.json" --provenance "$M8_SNAPSHOT/snapshot-provenance.json" \
  --roles-repo "$M8_ROLES" --route-b-env "$M8_ROUTE" --sheet-runtime "$M8_SHEET" \
  --measured-smoke "$M8_SMOKE_G/G/v214-smoke/v214-smoke-result.json" \
  --measured-smoke "$M8_SMOKE_D/D/v214-smoke/v214-smoke-result.json"
for chain in G D; do
  nohup bash "$M8_OPS/m8-run.sh" "$chain" >"$M8_LOGS/driver-$chain.log" 2>&1 </dev/null &
  printf '%s\n' "$!" >"$M8_LOGS/driver-$chain.pid"
done
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"drivers_started","experiment_complete":false}'
