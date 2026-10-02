#!/usr/bin/env bash
# Finite diagnostic after the baseline queue. Never alter the active C study.
set -euo pipefail
umask 077
baseline_source_root=/root/continual-sequential-20261002-c-source
baseline_study=/root/continual-sequential-20261002-c-study
baseline_python=/root/continual-alf-prep-20260928/env/bin/python
gepa_source=/root/continual-learning-env-20260928/gepa-source
credential_repo=/root/continual-noskill-bcb-20260928-a
source_root=/root/continual-unknown-passive-20261002-c-source
python_bin=/root/miniconda3/envs/skill_validation/bin/python
qualification=/root/continual-unknown-passive-20261002-c-q
replay_root=/root/continual-unknown-passive-20261002-c-replay

# Do not write an execution intent while another multi-domain method owns the
# resource. An errored/unfinished queue is not an authorized resource handoff.
deadline=$((SECONDS + 86400))
while tmux has-session -t fivebench-sequence-20261002-c 2>/dev/null ||
      [[ ! -f "$baseline_study/skillopt/final.json" || ! -f "$baseline_study/gepa/final.json" ]]; do
  if (( SECONDS >= deadline )); then
    echo 'No complete baseline handoff within 24h; diagnostic not launched.'
    exit 3
  fi
  sleep 30
done

# Require all ten stage terminals before using the existing replay validator.
# This prevents a missing stage from causing an accidental new paid launch.
"$python_bin" - "$baseline_study" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
domains = ['bigcodebench', 'spreadsheetbench', 'searchqa', 'korbench', 'alfworld']
for method in ['skillopt', 'gepa']:
    final = json.loads((root / method / 'final.json').read_text())
    assert final['attempted_stages'] == 5
    assert final['status'] in {'completed', 'attempts_finished_with_pending'}
    for stage, domain in enumerate(domains, 1):
        path = root / method / f's{stage}-{domain}'
        assert (path / 'stage.json').is_file()
        assert (path / 'learning/result.json').is_file()
PY
cd "$baseline_source_root"
for method in skillopt gepa; do
  PYTHONPATH="$baseline_source_root:$gepa_source/src" "$baseline_python" \
    -m scripts.continue_fivebench_baselines run --output "$baseline_study" \
    --method "$method" --repo "$credential_repo" --gepa-source "$gepa_source"
done

echo 'Completed baseline records revalidated; starting independent link C qualification.'
cd "$source_root"
export PYTHONPATH="$source_root"
test ! -e "$qualification"
test ! -e "$replay_root"
"$python_bin" -m scripts.replay_sheet_passive_links qualify \
  --original-qualification /root/continual-unknown-frozen-gold-c-20261002-q34/qualification.json \
  --prior-passive-qualification /root/continual-unknown-passive-20261002-b-q/qualification.json \
  --native-lock /root/continual-baselines-long-20261001-study/native.lock --output "$qualification"
"$python_bin" -c 'import json,sys; v=json.load(open(sys.argv[1])); assert v["status"] == "qualified"' \
  "$qualification/qualification.json"
"$python_bin" -m scripts.replay_sheet_passive_links prepare \
  --previous-replay /root/continual-unknown-frozen-gold-c-20261002-replay \
  --qualification "$qualification/qualification.json" \
  --native-lock /root/continual-baselines-long-20261001-study/native.lock --output "$replay_root"
"$python_bin" -m scripts.replay_sheet_passive_links run --output "$replay_root"
"$python_bin" -m scripts.replay_sheet_passive_links report --output "$replay_root"
