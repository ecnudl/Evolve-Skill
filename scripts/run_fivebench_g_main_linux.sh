#!/usr/bin/env bash
# Paid main-method chain (user request 10/7): the Rubric -> probe -> Research verifier (learning v10,
# method rubric_research) on study F's frozen references, BigCodeBench (parent none) -> SearchQA ->
# KOR-Bench, every accepted Skill tested on the three test panels. Runs from the snapshot named by
# G_SOURCE_ROOT with chain tag G_CHAIN_TAG (a new tag per reviewed protocol change); every paid step
# takes F's native lock inside the tool, so it interleaves with the other chains. Any failure ends
# the queue (exit 1); nothing later starts and no begun cell is resumed automatically.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:?G_SOURCE_ROOT (tool snapshot) required}
export G_LEARNING_VERSION=v10
python_bin=/root/continual-alf-prep-20260928/env/bin/python
study=/root/continual-fivebench-20261003-f-study
split=/root/fivebench-split-20261005-v2/split_manifest.json
repo=/root/continual-noskill-bcb-20260928-a
tag=${G_CHAIN_TAG:?G_CHAIN_TAG required}
log=/root/fivebench-g-20261007-main-$tag.log
first=/root/fivebench-g-20261007-bigcodebench-chain-rubric_research-$tag
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT"
run() { bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_g_stage.py "$@"; }
stop() { echo "$(date -Iseconds) STOP: $*" >> "$log"; echo "$(date -Iseconds) MAIN-EXIT=1" >> "$log"; exit 1; }

echo "$(date -Iseconds) main ($tag) start from snapshot $G_SOURCE_ROOT" >> "$log"
if [ ! -f "$first/stage.json" ]; then
  echo "$(date -Iseconds) prepare $first (v10 rubric_research, parent none)" >> "$log"
  run prepare --study "$study" --split "$split" --repo "$repo" --benchmark bigcodebench --parent none \
    --val-source /root/continual-noskill-bcb-20260928-a/data/skill_confirmation.json \
    --method rubric_research --learning-version v10 --output "$first" >> "$log" 2>&1 || stop "prepare $first failed"
fi
bash "$G_SOURCE_ROOT/scripts/run_fivebench_g_chain_linux.sh" rubric_research "$first" "$tag" >> "$log" 2>&1 \
  || stop "main-method chain failed or stopped for review"
if [ "${G_FIRST_STAGE_ONLY:-0}" = 1 ]; then
  echo "$(date -Iseconds) main first stage only complete (G_FIRST_STAGE_ONLY=1)" >> "$log"
else
  echo "$(date -Iseconds) main complete" >> "$log"
fi
echo "$(date -Iseconds) MAIN-EXIT=0" >> "$log"
