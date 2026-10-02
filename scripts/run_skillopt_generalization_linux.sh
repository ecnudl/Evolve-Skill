#!/usr/bin/env bash
# One new full five-domain SkillOpt study. No GEPA run and no historical writes.
# Launch only after this entire source tree and config have been frozen.
set -euo pipefail
umask 077
source_root=/root/continual-skillopt-generalization-20261002-d-source
study=/root/continual-skillopt-generalization-20261002-d-study
qualification=/root/continual-skillopt-generalization-20261002-d-q23
operations=/root/continual-skillopt-generalization-20261002-d-ops
python_bin=/root/continual-alf-prep-20260928/env/bin/python
credential_repo=/root/continual-noskill-bcb-20260928-a
native_lock=/root/continual-baselines-long-20261001-study/native.lock
config=configs/continual_learning/fivebench_sequence_v2.pjlab.json

cd "$source_root"
export PYTHONPATH="$source_root"
test -f "$config"
test -f "$native_lock"
test ! -e "$study"
test ! -e "$qualification"
mkdir -p "$operations"
date -Iseconds
echo 'Qualifying new source-bound numeric read-view scorer (23 controls; no model calls).'
"$python_bin" -m scripts.replay_sheet_v6 qualify \
  --output "$qualification" \
  --image sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790 \
  --legacy-qualification /root/continual-spreadsheet-long-20261001-study/q17/qualification.json \
  --comparison-fixture-qualification /root/continual-unknown-sheet-v6-20261001-q/qualification.json \
  --native-lock "$native_lock" --engine-version v7 \
  >"$operations/qualification.log" 2>&1

# Preparation validates the full qualification/receipts and each domain's
# actual runtime before paid work. Qualification applies only to learning;
# all-domain evaluation keeps its original matched No-Skill scorer/settings.
"$python_bin" -m scripts.continue_fivebench_baselines prepare \
  --config "$config" --output "$study" \
  >"$operations/prepare.log" 2>&1
"$python_bin" -m scripts.continue_fivebench_baselines check --output "$study" \
  >"$operations/check.log" 2>&1
mkdir "$study/launch"
echo 'Starting full-size five-domain SkillOpt sequence; inspect final.json for completed versus pending stages.'
# Activate the Linux proxy in the same shell that launches the actual client.
# The frozen BigModel client also binds its reviewed explicit PJLAB gateway.
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
  "$python_bin" -m scripts.continue_fivebench_baselines run --output "$study" \
  --method skillopt --repo "$credential_repo" \
  >"$study/launch/skillopt.log" 2>&1
echo 'SkillOpt sequence terminal: read the recorded status; terminal does not imply five successful learning stages.'
date -Iseconds
