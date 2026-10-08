#!/usr/bin/env bash
# Paid re-measurement (user requests 10/4): one new five-domain evaluation of every F stage
# that reused earlier observations instead of sampling -- SkillOpt S2 (= the S1 Skill) and
# S5 (= the S4 Skill), GEPA S1 and S2 (empty Skill, i.e. the No-Skill policy), and any later
# GEPA stage that ends without an update. Waits until F's GEPA final.json exists; each run
# also waits on F's native lock, so it never overlaps the study. About 4,100 calls and
# 8-12M tokens per re-measured stage; any failure stops the queue for review.
set -euo pipefail
umask 077
source_root=/root/continual-fivebench-20261003-f-source
study=/root/continual-fivebench-20261003-f-study
tool=/root/fivebench-f-remeasure-20261004-tools-c/remeasure_fivebench_stage.py
out=/root/fivebench-f-remeasure-20261004-c
python_bin=/root/continual-alf-prep-20260928/env/bin/python
repo=/root/continual-noskill-bcb-20260928-a

until test -f "$study/gepa/final.json"; do sleep 600; done
cd "$source_root"
export PYTHONPATH="$source_root"
stages=$("$python_bin" "$tool" list --study "$study")
date -Iseconds
echo "re-measuring: $stages"
for spec in $stages; do  # zero calls; refuses anything but a fully reused stage
  dir="$out/${spec%%:*}-s${spec##*:}"
  test -f "$dir/remeasure.json" || "$python_bin" "$tool" prepare --study "$study" --method "${spec%%:*}" \
    --stage "${spec##*:}" --output "$dir" --repo "$repo"
done
for spec in $stages; do
  dir="$out/${spec%%:*}-s${spec##*:}"
  date -Iseconds
  echo "run $spec"
  # Activate the Linux proxy in the same shell that launches the actual client.
  bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
    "$python_bin" "$tool" run --output "$dir" >>"$dir/run.log" 2>&1
done
date -Iseconds
