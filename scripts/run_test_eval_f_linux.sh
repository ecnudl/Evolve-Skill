#!/usr/bin/env bash
# Paid test-split evaluation (user request 10/5): study F's six distinct policies (No-Skill,
# SkillOpt S1/S3/S4, GEPA S3/S4) on the five test panels of fivebench-split-v2, one repeat each:
# 30 cells, about 23,000 model calls and 60-65M tokens. One cell generates at a time with the
# study's 10 workers (the key's concurrency limit); native scoring overlaps the next cell. The run
# waits on F's native lock, so it starts only after the dev-panel re-measurement holding it has
# finished; any failure stops it for review, and a begun cell is never resumed automatically.
set -euo pipefail
umask 077
source_root=/root/continual-fivebench-20261003-f-source
tool=/root/fivebench-test-eval-20261005-tools-h/evaluate_fivebench_test.py
out=/root/fivebench-test-eval-20261005-h
python_bin=/root/continual-alf-prep-20260928/env/bin/python

test -f "$out/test_eval.json"
cd "$source_root"
export PYTHONPATH="$source_root"
date -Iseconds
# Activate the Linux proxy in the same shell that launches the actual client.
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- \
  "$python_bin" "$tool" run --output "$out" >>"$out/run.log" 2>&1
date -Iseconds
