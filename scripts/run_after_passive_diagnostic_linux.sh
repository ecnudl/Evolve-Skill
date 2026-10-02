#!/usr/bin/env bash
# Finite handoff: finish the zero-API repair first, then the two real baselines.
set -euo pipefail
umask 077
ops=/root/continual-sequential-20261002-ops
started=$SECONDS
while tmux has-session -t passive-links-20261002-b 2>/dev/null; do
  if (( SECONDS - started > 7200 )); then
    echo 'Diagnostic handoff exceeded two hours; no baseline launch'
    exit 4
  fi
  sleep 15
done
# Session absence is not completion: verify the actual frozen replay and cleanup.
cd /root/continual-unknown-passive-20261002-b-source
export PYTHONPATH=/root/continual-unknown-passive-20261002-b-source
/root/miniconda3/envs/skill_validation/bin/python -m scripts.replay_sheet_passive_links report \
  --output /root/continual-unknown-passive-20261002-b-replay > "$ops/passive-handoff.json"
/root/miniconda3/envs/skill_validation/bin/python - "$ops/passive-handoff.json" <<'PY'
import sys
from skillopt.continual_eval.core import read_json, require
value = read_json(sys.argv[1], sealed=True)
require(value['status'] == 'complete' and value['completed'] == value['positions'] == 160,
        'Repair evaluation incomplete; preserve it for review')
require(value['execution']['open_workbook_intents'] == 0
        and value['execution']['cleanup_unconfirmed'] == 0, 'Unsafe resource handoff')
require(value['known_preservation']['unchanged'] == value['known_preservation']['expected_positions'] == 134,
        'Existing known judgments changed; review before continuing')
print('Completed diagnostic with preserved known judgments; releasing baseline queue')
PY
exec bash /root/continual-sequential-20261002-c-source/scripts/run_fivebench_sequence_linux.sh
