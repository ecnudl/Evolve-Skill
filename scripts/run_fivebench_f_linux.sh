#!/usr/bin/env bash
# New F: full five-domain SkillOpt then official GEPA, sequence v4 / learning v7.
# Raised 32000-byte Skill interface; new policies are evaluated in a derived copy
# of the frozen No-Skill source that differs only in that budget literal, with
# its source-bound Sheet scorer re-qualified. No historical writes.
# Launch only after this entire source tree and config have been frozen.
set -euo pipefail
umask 077
source_root=/root/continual-fivebench-20261003-f-source
study=/root/continual-fivebench-20261003-f-study
qualification=/root/continual-fivebench-20261003-f-q23
operations=/root/continual-fivebench-20261003-f-ops
python_bin=/root/continual-alf-prep-20260928/env/bin/python
credential_repo=/root/continual-noskill-bcb-20260928-a
native_lock=/root/continual-baselines-long-20261001-study/native.lock
gepa_source=/root/continual-learning-env-20260928/gepa-source
config=configs/continual_learning/fivebench_sequence_v4.pjlab.json

cd "$source_root"
export PYTHONPATH="$source_root:$gepa_source/src"
test -f "$config"
test -f "$native_lock"
test ! -e "$study"
test ! -e "$qualification"
mkdir -p "$operations"
date -Iseconds
echo 'Qualifying new source-bound numeric read-view learning scorer (23 controls; no model calls).'
"$python_bin" -m scripts.replay_sheet_v6 qualify \
  --output "$qualification" \
  --image sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790 \
  --legacy-qualification /root/continual-spreadsheet-long-20261001-study/q17/qualification.json \
  --comparison-fixture-qualification /root/continual-unknown-sheet-v6-20261001-q/qualification.json \
  --native-lock "$native_lock" --engine-version v7 \
  >"$operations/qualification.log" 2>&1

# Preparation verifies the derived evaluation sources byte-for-byte against the
# frozen No-Skill sources (only the budget literal may differ) before paid work.
"$python_bin" -m scripts.continue_fivebench_baselines prepare \
  --config "$config" --output "$study" \
  >"$operations/prepare.log" 2>&1
"$python_bin" -m scripts.continue_fivebench_baselines check --output "$study" \
  >"$operations/check.log" 2>&1
mkdir "$study/launch"
for method in skillopt gepa; do
  echo "Starting F five-domain method=$method (learning v7); inspect final.json for completed versus pending stages."
  # Activate the Linux proxy in the same shell that launches the actual client.
  # The frozen BigModel client also binds its reviewed explicit PJLAB gateway.
  bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
    "$python_bin" -m scripts.continue_fivebench_baselines run --output "$study" \
    --method "$method" --repo "$credential_repo" --gepa-source "$gepa_source" \
    >"$study/launch/$method.log" 2>&1
  echo "Finished method=$method; terminal does not imply five successful learning stages."
done
date -Iseconds
