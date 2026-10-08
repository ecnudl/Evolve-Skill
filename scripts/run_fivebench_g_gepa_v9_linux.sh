#!/usr/bin/env bash
# Paid GEPA chain under the v9 gate (user-authorized follow-up 10/7): the v8 GEPA chain's KOR-Bench
# stage went Pending at the 4096-token reflection cap, so the baseline table gets a GEPA chain under the
# same protocol as the SkillOpt v9 chain and the v10 main chain -- BigCodeBench (parent none) ->
# SearchQA -> KOR-Bench, every accepted Skill tested on the three test panels. Snapshot from
# G_SOURCE_ROOT, chain tag from G_CHAIN_TAG; every paid step takes F's native lock inside the tool.
# Any failure ends the queue (exit 1); nothing is resumed automatically.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:?G_SOURCE_ROOT (tool snapshot) required}
export G_LEARNING_VERSION=v9
python_bin=/root/continual-alf-prep-20260928/env/bin/python
study=/root/continual-fivebench-20261003-f-study
split=/root/fivebench-split-20261005-v2/split_manifest.json
repo=/root/continual-noskill-bcb-20260928-a
gepa_source=/root/continual-learning-env-20260928/gepa-source
tag=${G_CHAIN_TAG:?G_CHAIN_TAG required}
log=/root/fivebench-g-20261007-gepa-v9-$tag.log
first=/root/fivebench-g-20261007-bigcodebench-chain-gepa-$tag
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT:$gepa_source/src"
run() { bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_g_stage.py "$@"; }
stop() { echo "$(date -Iseconds) STOP: $*" >> "$log"; echo "$(date -Iseconds) GEPA-V9-EXIT=1" >> "$log"; exit 1; }

echo "$(date -Iseconds) gepa-v9 ($tag) start from snapshot $G_SOURCE_ROOT" >> "$log"
if [ ! -f "$first/stage.json" ]; then
  echo "$(date -Iseconds) prepare $first (v9 gepa, parent none)" >> "$log"
  run prepare --study "$study" --split "$split" --repo "$repo" --benchmark bigcodebench --parent none \
    --val-source /root/continual-noskill-bcb-20260928-a/data/skill_confirmation.json \
    --method gepa --gepa-source "$gepa_source" --learning-version v9 --output "$first" >> "$log" 2>&1 \
    || stop "prepare $first failed"
fi
bash "$G_SOURCE_ROOT/scripts/run_fivebench_g_chain_linux.sh" gepa "$first" "$tag" >> "$log" 2>&1 \
  || stop "GEPA v9 chain failed or stopped for review"
echo "$(date -Iseconds) gepa-v9 complete" >> "$log"
echo "$(date -Iseconds) GEPA-V9-EXIT=0" >> "$log"
