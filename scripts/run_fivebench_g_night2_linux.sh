#!/usr/bin/env bash
# Paid follow-up queue (user request 10/7 night: analyze, improve, launch). Runs from snapshot d and
# takes F's native lock per paid step, so it interleaves with the GEPA chain still running from c.
#  1. No-Skill replicate test cells (BigCodeBench, KOR-Bench, SearchQA): the completed BigCodeBench
#     stage from parent none deploys the empty Skill, so its replicate cells re-measure No-Skill on
#     the same test panels -- the run-to-run noise of the baseline every comparison shares
#     (already recorded by the first run, 10/7 03:07-06:53; existing cells are skipped).
#  2. A learning-v9 SkillOpt chain (family-level sign-test screen, fresh confirmation pass):
#     BigCodeBench (parent none) -> SearchQA -> KOR-Bench, every accepted Skill tested on the three
#     test panels. Snapshot and chain tag come from G_SOURCE_ROOT / G_CHAIN_TAG (a new tag per
#     reviewed protocol change; the v9a BigCodeBench stage stays as its pending record).
# Any failure ends the queue (exit 1); nothing later starts.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:-/root/fivebench-g-20261006-source-e}
export G_LEARNING_VERSION=v9
python_bin=/root/continual-alf-prep-20260928/env/bin/python
test_eval=/root/fivebench-test-eval-20261005-h
study=/root/continual-fivebench-20261003-f-study
split=/root/fivebench-split-20261005-v2/split_manifest.json
repo=/root/continual-noskill-bcb-20260928-a
tag=${G_CHAIN_TAG:-v9b}
log=/root/fivebench-g-20261007-night2-$tag.log
empty=/root/fivebench-g-20261006-bcb-b            # completed, no update, parent none: deploys the empty Skill
first=/root/fivebench-g-20261007-bigcodebench-chain-skillopt-$tag
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT"
run() { bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_g_stage.py "$@"; }
stop() { echo "$(date -Iseconds) STOP: $*" >> "$log"; echo "$(date -Iseconds) NIGHT2-EXIT=1" >> "$log"; exit 1; }

echo "$(date -Iseconds) night2 ($tag) start from snapshot $G_SOURCE_ROOT" >> "$log"
for b in searchqa korbench bigcodebench; do
  suffix="-r1"; [ "$b" != bigcodebench ] && suffix="-$b-r1"
  [ -f "$empty/summary$suffix.json" ] && continue
  echo "$(date -Iseconds) No-Skill replicate 1 on $b" >> "$log"
  run test --output "$empty" --test-eval "$test_eval" --test-benchmark "$b" --replicate 1 >> "$log" 2>&1 \
    || stop "No-Skill replicate on $b failed"
done
if [ ! -f "$first/stage.json" ]; then
  echo "$(date -Iseconds) prepare $first (v9, parent none)" >> "$log"
  run prepare --study "$study" --split "$split" --repo "$repo" --benchmark bigcodebench --parent none \
    --val-source /root/continual-noskill-bcb-20260928-a/data/skill_confirmation.json --learning-version v9 \
    --output "$first" >> "$log" 2>&1 || stop "prepare $first failed"
fi
bash "$G_SOURCE_ROOT/scripts/run_fivebench_g_chain_linux.sh" skillopt "$first" "$tag" >> "$log" 2>&1 \
  || stop "v9 SkillOpt chain failed or stopped for review"
echo "$(date -Iseconds) night2 complete" >> "$log"
echo "$(date -Iseconds) NIGHT2-EXIT=0" >> "$log"
