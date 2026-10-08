#!/usr/bin/env bash
# Paid BCB feedback-content pilot (step 2): one SkillOpt learning stage with sanitized
# execution evidence (arm B) against F's scalar-feedback S1 (arm A, reused), then
# arm B's Skill on the same BCB panel. User decision (10/4): small pilot, and only
# after F has finished both methods. The pilot also takes F's native lock.
set -euo pipefail
umask 077
source_root=/root/feedback-pilot-20261004-source
pilot=/root/feedback-pilot-20261004-a
f_study=/root/continual-fivebench-20261003-f-study
python_bin=/root/continual-alf-prep-20260928/env/bin/python
credential_repo=/root/continual-noskill-bcb-20260928-a
gepa_source=/root/continual-learning-env-20260928/gepa-source

test -f "$f_study/skillopt/final.json" && test -f "$f_study/gepa/final.json" \
  || { echo "F has not finished both methods; refusing to start the paid pilot." >&2; exit 3; }
test -f "$pilot/protocol.json"
cd "$source_root"
export PYTHONPATH="$source_root:$gepa_source/src"
date -Iseconds
# Activate the Linux proxy in the same shell that launches the actual client.
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
  "$python_bin" -m scripts.run_feedback_ablation_pilot run --output "$pilot" --repo "$credential_repo" \
  >>"$pilot/run.log" 2>&1
date -Iseconds
