#!/usr/bin/env bash
# Reviewed operator preparation; never run by the offline writer.
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M9_OPS/m9-env.sh"
m9_require_paths
# One host-wide owner covers standalone-suite scratch use and the complete S0.
exec 201>/tmp/execskill-s0.lock
flock -n 201 || { printf '%s\n' 'Another preparation owns the shared S0 host lock' >&2; exit 2; }
cd -- "$M9_SOURCE"
export PYTHONPATH="$M9_SOURCE"
m9_skip_linux_suite() {
  printf '%s\n' '{"passed":true,"exit_code":0,"standalone_linux_suite":"skipped","reason":"M9_SKIP_LINUX_SUITE=1","s0_admission":"still_required"}'
}
case "${M9_SKIP_LINUX_SUITE:-0}" in
  0) m9_step pre bash "$M9_OPS/run-v225-pre.sh";;
  1) m9_step pre m9_skip_linux_suite;;
  *) printf '%s\n' 'M9_SKIP_LINUX_SUITE must be 0 or 1' >&2; exit 2;;
esac
m9_step snapshot m9_cli v214-snapshot --configuration main-v9 --source "$M9_SOURCE" \
  --out "$M9_SNAPSHOT" --git-head "$M9_HEAD"
cd -- "$M9_SNAPSHOT"
export PYTHONPATH="$M9_SNAPSHOT"
m9_step verify m9_cli verify-snapshot --list "$M9_SNAPSHOT/sha256-list.txt" \
  --root "$M9_SNAPSHOT" --git-head "$M9_HEAD"
M9_PRACTICE_OPTIONS=()
if [[ -n "$M9_PRACTICE_SUPPLY" ]]; then
  M9_PRACTICE_OPTIONS=(--v222-practice-supply "$M9_PRACTICE_SUPPLY")
fi
# D1 harm slices use the registered available counts; no decomposition is run.
m9_practice_preflight() {
  "$M9_PY" -B -c "import json,os; from skillopt.execskill import profiles as p,v214_preparation; value=v214_preparation.preparation(os.environ['M9_PARENT_S0'], zebra_pool=os.environ['M9_ZEBRA_POOL'], zebra_split_manifest=os.environ['M9_ZEBRA_SPLIT'], configuration=p.MAIN_V9, v222_practice_supply=os.environ['M9_PRACTICE_SUPPLY'] or None); print(json.dumps({'passed': True, 'exit_code': 0, 'practice': value['data']['v222_practice']['source']}, sort_keys=True))"
}
m9_step practice-preflight m9_practice_preflight

m9_q23() {
  "$M9_PY" -B - <<'PY_Q23'
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from skillopt.execskill import profiles as p, v218_lock
setting = SimpleNamespace(root=os.environ['M9_PRE'], extra={'configuration': p.MAIN_V9})
with v218_lock.environment(setting, 'spreadsheetbench', chain='G', unit='G/preparation/q23'):
    result = subprocess.run([sys.executable, '-B', '-m', 'scripts.replay_sheet_v6', 'qualify',
        '--output', os.environ['M9_Q23'],
        '--image', 'sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790',
        '--legacy-qualification', '/root/continual-spreadsheet-long-20261001-study/q17/qualification.json',
        '--comparison-fixture-qualification', '/root/continual-unknown-sheet-v6-20261001-q/qualification.json',
        '--native-lock', '/root/continual-baselines-long-20261001-study/native.lock',
        '--engine-version', 'v7'], check=False)
print(json.dumps({'passed': result.returncode == 0, 'exit_code': result.returncode}, sort_keys=True))
sys.exit(result.returncode)
PY_Q23
}
m9_step q23 m9_q23
m9_step sheet-runtime m9_cli sheet-runtime --manifest "$M9_V3_MANIFEST" \
  --engine-qualification "$M9_Q23/qualification.json" --out "$M9_SHEET"
# M9_CONSENT is supplied by the reviewed delegated owner writer, never invented here.
m9_step selftest m9_cli v214-selftest --configuration main-v9 --out "$M9_PRE/selftest" \
  --preparation "$M9_PARENT_S0" --zebra-pool "$M9_ZEBRA_POOL" --zebra-split-manifest "$M9_ZEBRA_SPLIT" "${M9_PRACTICE_OPTIONS[@]}"
m9_s0_admission() {
  "$M9_PY" -B - <<'PY_S0_ADMISSION'
import json
import os
space = os.statvfs('/tmp')
assert space.f_favail >= 170000, 'S0 requires at least 170000 free /tmp inodes immediately before admission'
assert space.f_bavail > 0 and space.f_frsize > 0, 'S0 requires writable /tmp space'
print(json.dumps({'passed': True, 'exit_code': 0, 'tmp_free_inodes': space.f_favail,
    'minimum_free_inodes': 170000}, sort_keys=True))
PY_S0_ADMISSION
}
m9_s0_locked() (
  # Inherit fd 201: never release the host lock before S0 and its suite finish.
  cd -- "$M9_SNAPSHOT"
  export PYTHONPATH="$M9_SNAPSHOT"
  m9_step s0-admission m9_s0_admission
  m9_step s0 m9_cli v214-s0 --configuration main-v9 --out "$M9_PRE/s0" --root "$M9_ROOT" \
    --preparation "$M9_PARENT_S0" --zebra-pool "$M9_ZEBRA_POOL" --zebra-split-manifest "$M9_ZEBRA_SPLIT" \
    --consent "$M9_CONSENT" --selftest "$M9_PRE/selftest/sandbox-selftest.json" \
    --sheet-runtime "$M9_SHEET" --snapshot "$M9_SNAPSHOT" "${M9_PRACTICE_OPTIONS[@]}"
)
m9_s0_locked
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"preparation"}'
