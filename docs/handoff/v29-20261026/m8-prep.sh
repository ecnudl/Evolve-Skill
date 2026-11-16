#!/usr/bin/env bash
# Reviewed operator preparation; never run by the offline writer.
set -euo pipefail
M8_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M8_OPS/m8-env.sh"
m8_require_paths
cd -- "$M8_SOURCE"
export PYTHONPATH="$M8_SOURCE"
m8_step pre bash "$M8_OPS/run-v222-pre.sh"
m8_step snapshot m8_cli v214-snapshot --configuration main-v8 --source "$M8_SOURCE" \
  --out "$M8_SNAPSHOT" --git-head "$M8_HEAD"
cd -- "$M8_SNAPSHOT"
export PYTHONPATH="$M8_SNAPSHOT"
m8_step verify m8_cli verify-snapshot --list "$M8_SNAPSHOT/sha256-list.txt" \
  --root "$M8_SNAPSHOT" --git-head "$M8_HEAD"
M8_PRACTICE_OPTIONS=()
if [[ -n "$M8_PRACTICE_SUPPLY" ]]; then
  M8_PRACTICE_OPTIONS=(--v222-practice-supply "$M8_PRACTICE_SUPPLY")
fi
# Exact 100/20 decomposition and 60/20 harm slices must exist before any native call.
m8_practice_preflight() {
  "$M8_PY" -B -c "import json,os; from skillopt.execskill import profiles as p,v214_preparation; value=v214_preparation.preparation(os.environ['M8_PARENT_S0'], zebra_pool=os.environ['M8_ZEBRA_POOL'], zebra_split_manifest=os.environ['M8_ZEBRA_SPLIT'], configuration=p.MAIN_V8, v222_practice_supply=os.environ['M8_PRACTICE_SUPPLY'] or None); print(json.dumps({'passed': True, 'exit_code': 0, 'practice': value['data']['v222_practice']['source']}, sort_keys=True))"
}
m8_step practice-preflight m8_practice_preflight

m8_q23() {
  "$M8_PY" -B - <<'PY_Q23'
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from skillopt.execskill import profiles as p, v218_lock
setting = SimpleNamespace(root=os.environ['M8_PRE'], extra={'configuration': p.MAIN_V8})
with v218_lock.environment(setting, 'spreadsheetbench', chain='G', unit='G/preparation/q23'):
    result = subprocess.run([sys.executable, '-B', '-m', 'scripts.replay_sheet_v6', 'qualify',
        '--output', os.environ['M8_Q23'],
        '--image', 'sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790',
        '--legacy-qualification', '/root/continual-spreadsheet-long-20261001-study/q17/qualification.json',
        '--comparison-fixture-qualification', '/root/continual-unknown-sheet-v6-20261001-q/qualification.json',
        '--native-lock', '/root/continual-baselines-long-20261001-study/native.lock',
        '--engine-version', 'v7'], check=False)
print(json.dumps({'passed': result.returncode == 0, 'exit_code': result.returncode}, sort_keys=True))
sys.exit(result.returncode)
PY_Q23
}
m8_step q23 m8_q23
m8_step sheet-runtime m8_cli sheet-runtime --manifest "$M8_V3_MANIFEST" \
  --engine-qualification "$M8_Q23/qualification.json" --out "$M8_SHEET"
# M8_CONSENT is supplied by the reviewed delegated owner writer, never invented here.
m8_step selftest m8_cli v214-selftest --configuration main-v8 --out "$M8_PRE/selftest" \
  --preparation "$M8_PARENT_S0" --zebra-pool "$M8_ZEBRA_POOL" --zebra-split-manifest "$M8_ZEBRA_SPLIT" "${M8_PRACTICE_OPTIONS[@]}"
m8_step s0 m8_cli v214-s0 --configuration main-v8 --out "$M8_PRE/s0" --root "$M8_ROOT" \
  --preparation "$M8_PARENT_S0" --zebra-pool "$M8_ZEBRA_POOL" --zebra-split-manifest "$M8_ZEBRA_SPLIT" \
  --consent "$M8_CONSENT" --selftest "$M8_PRE/selftest/sandbox-selftest.json" \
  --sheet-runtime "$M8_SHEET" --snapshot "$M8_SNAPSHOT" "${M8_PRACTICE_OPTIONS[@]}"
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"preparation"}'
