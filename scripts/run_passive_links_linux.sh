#!/usr/bin/env bash
# Finite zero-model-call diagnostic. Every path is a new explicit run root.
set -euo pipefail
umask 077
source_root=/root/continual-sequential-20261002-a-source
python_bin=/root/miniconda3/envs/skill_validation/bin/python
qualification=/root/continual-unknown-passive-20261002-a-q
replay_root=/root/continual-unknown-passive-20261002-a-replay
cd "$source_root"
export PYTHONPATH="$source_root"
test ! -e "$qualification"
test ! -e "$replay_root"
"$python_bin" -m scripts.replay_sheet_passive_links qualify \
  --original-qualification /root/continual-unknown-frozen-gold-c-20261002-q34/qualification.json \
  --native-lock /root/continual-baselines-long-20261001-study/native.lock \
  --output "$qualification"
"$python_bin" -c 'import json,sys; v=json.load(open(sys.argv[1])); assert v["status"] == "qualified"' \
  "$qualification/qualification.json"
"$python_bin" -m scripts.replay_sheet_passive_links prepare \
  --previous-replay /root/continual-unknown-frozen-gold-c-20261002-replay \
  --qualification "$qualification/qualification.json" \
  --native-lock /root/continual-baselines-long-20261001-study/native.lock \
  --output "$replay_root"
"$python_bin" -m scripts.replay_sheet_passive_links run --output "$replay_root"
"$python_bin" -m scripts.replay_sheet_passive_links report --output "$replay_root"
