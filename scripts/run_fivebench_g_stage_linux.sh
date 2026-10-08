#!/usr/bin/env bash
# Paid learning-v8 stage redo (user request 10/6): one SkillOpt stage on one API-only domain from a
# chosen parent Skill of study F, selection on the canonical val split with the v8 margin gate, then
# (only if an update was accepted) one test cell paired with the recorded No-Skill test cell.
# Usage: run_fivebench_g_stage_linux.sh <prepared stage dir>   (prepare must already have run)
set -euo pipefail
umask 077
source_root=${G_SOURCE_ROOT:-/root/fivebench-g-20261006-source}
test_eval=/root/fivebench-test-eval-20261005-h
python_bin=/root/continual-alf-prep-20260928/env/bin/python
stage=${1:?prepared stage directory}

test -f "$stage/stage.json"
cd "$source_root"
export PYTHONPATH="$source_root"
# A GEPA stage needs the pinned official package on the path (the stage record names its source).
gepa_source=$("$python_bin" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("gepa_source") or "")' "$stage/stage.json")
if [ -n "$gepa_source" ]; then export PYTHONPATH="$source_root:$gepa_source/src"; fi
date -Iseconds
# Activate the Linux proxy in the same shell that launches the actual client.
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
  "$python_bin" scripts/run_fivebench_g_stage.py learn --output "$stage" >>"$stage/run.log" 2>&1
date -Iseconds
if "$python_bin" - "$stage" <<'EOF'
import json, sys
accepted = json.load(open(sys.argv[1] + "/learned.json"))["action"] == "selected_update"
print("accepted update" if accepted else "no accepted update: the parent is already measured on test")
sys.exit(0 if accepted else 1)
EOF
then
  bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
    "$python_bin" scripts/run_fivebench_g_stage.py test --output "$stage" --test-eval "$test_eval" >>"$stage/run.log" 2>&1
fi
date -Iseconds
