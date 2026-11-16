#!/usr/bin/env bash
# Operator template: reviewed smoke + exact consent + first real reply precede concurrency.
# Stage reads are launched by chain.run into <chain>/test/{anchor,s1..s5,i,c_end}.
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M9_OPS/m9-env.sh"
m9_require_paths
test "${M9_OWNER_LAUNCH:-}" = main-v9-reviewed-launch || { printf '%s\n' 'Reviewed owner launch decision required' >&2; exit 2; }
cd -- "$M9_SNAPSHOT"
export PYTHONPATH="$M9_SNAPSHOT"
m9_consent() {
  "$M9_PY" -B -c "import json,os,pathlib; from skillopt.execskill import evaluation,profiles as p; root=pathlib.Path(os.environ['M9_ROOT']); value=evaluation.consent(root/'shared',p.MAIN_V9); assert value == json.loads(pathlib.Path(os.environ['M9_CONSENT']).read_text()), 'Consent differs from the S0-pinned owner copy'; assert all(not (root/c/'chain.json').exists() for c in ('G','D')), 'Existing chain requires a separately reviewed recovery, never launch'; print(json.dumps({'passed': True, 'exit_code': 0, 'arms': list(p.read_arms_of(p.MAIN_V9))},sort_keys=True))"
}
m9_step consent m9_consent
m9_step manifest m9_cli v214-manifest --configuration main-v9 --out "$M9_MANIFEST" --root "$M9_ROOT" \
  --s0 "$M9_PRE/s0/v214-s0.json" --provenance "$M9_SNAPSHOT/snapshot-provenance.json" \
  --roles-repo "$M9_ROLES" --route-b-env "$M9_ROUTE" --sheet-runtime "$M9_SHEET" \
  --measured-smoke "$M9_SMOKE_G/G/v214-smoke/v214-smoke-result.json" \
  --measured-smoke "$M9_SMOKE_D/D/v214-smoke/v214-smoke-result.json"
"$M9_PY" -B -c "import json,os,pathlib; m=json.loads(pathlib.Path(os.environ['M9_MANIFEST']).read_text()); assert m['configuration'] == 'main-v9' and m['root'] == os.environ['M9_ROOT'], 'Manifest root/configuration differs from reviewed launch'"
nohup bash "$M9_OPS/m9-run.sh" G >"$M9_LOGS/driver-G.log" 2>&1 </dev/null &
M9_G_PID=$!
printf '%s\n' "$M9_G_PID" >"$M9_LOGS/driver-G.pid"
export M9_G_PID
m9_first_reply() {
  "$M9_PY" -B - <<'PY_REPLY'
import json
import os
import pathlib
import time
from skillopt.execskill import chain, profiles as p
m = json.loads(pathlib.Path(os.environ['M9_MANIFEST']).read_text())
root = pathlib.Path(os.environ['M9_ROOT'])
deadline = time.monotonic() + 1800
while not (root / 'G' / 'confirm.json').is_file():
    os.kill(int(os.environ['M9_G_PID']), 0)
    if time.monotonic() >= deadline:
        raise RuntimeError('First reply unconfirmed; retain G and do not release D')
    time.sleep(5)
record = chain.confirmation(root, m[p.RECORD_HASH], 'G', configuration=p.MAIN_V9)
assert record['checks']['reply'] is True and record['reply_sha256']
print(json.dumps({'passed': True, 'exit_code': 0, 'first_reply_confirmed': 'G'}, sort_keys=True))
PY_REPLY
}
m9_step first-reply m9_first_reply
nohup bash "$M9_OPS/m9-run.sh" D >"$M9_LOGS/driver-D.log" 2>&1 </dev/null &
printf '%s\n' "$!" >"$M9_LOGS/driver-D.pid"
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"drivers_started","experiment_complete":false}'
