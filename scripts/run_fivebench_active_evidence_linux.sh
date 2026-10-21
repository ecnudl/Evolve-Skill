#!/usr/bin/env bash
# Paid learning-v11 (active_evidence) stage: one stage on one API-only domain from a chosen parent Skill, no
# canonical validation split (a fresh panel from the reserved development challenge pool + replay decide, rule v2),
# then -- only if an update was kept and G_SKIP_TEST is not 1 -- one test cell
# paired with the recorded No-Skill test cell. The stage must already be prepared:
#   python scripts/run_fivebench_g_stage.py prepare --method active_evidence --learning-version v11 \
#     --study <F study> --split <split manifest> --repo <credential repo> --benchmark bigcodebench --parent none \
#     [--arm-feedback diagnosis_research] [--arm-post-update challenge_replay] --output <new stage dir>
# Usage: run_fivebench_active_evidence_linux.sh <prepared stage dir>
# Environment: G_SOURCE_ROOT (required; a fresh source snapshot that contains skillopt/active_evidence),
#              G_TEST_EVAL (default /root/fivebench-test-eval-20261005-h), G_SKIP_TEST=1 to stop after learn.
set -euo pipefail
umask 077
source_root=${G_SOURCE_ROOT:?set G_SOURCE_ROOT to the source snapshot of this run}
test_eval=${G_TEST_EVAL:-/root/fivebench-test-eval-20261005-h}
python_bin=/root/continual-alf-prep-20260928/env/bin/python
stage=${1:?prepared stage directory}

test -f "$stage/stage.json"
test -d "$source_root/skillopt/active_evidence"
cd "$source_root"
export PYTHONPATH="$source_root"
date -Iseconds
# Activate the Linux proxy in the same shell that launches the actual client (model calls and documentation fetch).
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
  "$python_bin" scripts/run_fivebench_g_stage.py learn --output "$stage" >>"$stage/run.log" 2>&1
date -Iseconds
"$python_bin" scripts/run_fivebench_g_stage.py status --output "$stage" >>"$stage/run.log" 2>&1 || true
if [ "${G_SKIP_TEST:-0}" = "1" ]; then
  echo "G_SKIP_TEST=1: stopping after learn"
  exit 0
fi
if "$python_bin" - "$stage" <<'EOF'
import json, sys
learned = json.load(open(sys.argv[1] + "/learned.json"))
accepted = learned["action"] == "selected_update"
print("kept update" if accepted else "no kept update (" + str(learned.get("decisions")) + "): the parent is already measured on test")
sys.exit(0 if accepted else 1)
EOF
then
  bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
    "$python_bin" scripts/run_fivebench_g_stage.py test --output "$stage" --test-eval "$test_eval" >>"$stage/run.log" 2>&1
fi
date -Iseconds
