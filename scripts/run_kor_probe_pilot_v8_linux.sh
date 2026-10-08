#!/usr/bin/env bash
# Paid KOR probe-stage pilot v8 (step 3b): No-Skill and F's SkillOpt S1 on 184 fresh
# probes (v7's 112 operation/puzzle probes plus 72 cipher probes), two one-call rewrites
# (with / without label-free evidence), the rewrites on the 92 held-out probes; about
# 1,106 calls. The user approved only the probe stage at about 900 calls (v7: 674), so
# v8 also needs the user's explicit approval, recorded as $pilot/user-approved-v8,
# and like v7 starts only after F has finished both methods. Scored only by the
# label-free verifier.
set -euo pipefail
umask 077
source_root=/root/kor-probe-pilot-20261004-v8-source
pilot=/root/kor-probe-pilot-20261004-h
f_study=/root/continual-fivebench-20261003-f-study
python_bin=/root/continual-alf-prep-20260928/env/bin/python
credential_repo=/root/continual-noskill-bcb-20260928-a
gepa_source=/root/continual-learning-env-20260928/gepa-source

test -f "$f_study/skillopt/final.json" && test -f "$f_study/gepa/final.json" \
  || { echo "F has not finished both methods; refusing to start the paid probe stage." >&2; exit 3; }
test -f "$pilot/protocol.json"
test -f "$pilot/user-approved-v8" \
  || { echo "v8 exceeds the approved probe-stage scale; it needs the user's explicit approval." >&2; exit 4; }
cd "$source_root"
export PYTHONPATH="$source_root:$gepa_source/src"
date -Iseconds
# Activate the Linux proxy in the same shell that launches the actual client.
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
  "$python_bin" -m scripts.run_kor_probe_pilot run --output "$pilot" --repo "$credential_repo" \
  >>"$pilot/run.log" 2>&1
date -Iseconds
