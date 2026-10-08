#!/usr/bin/env bash
# Paid L1 fixed-rubric study (fivebench-fixed-rubric-study-v1; registered 10/8, Codex design round post-S3-2 and
# code review). One fresh train rollout of the main method's S2 Skill on the 90 KOR train tasks, judged by the
# frozen default / h0 / h1 / h2 KOR rubrics (one judgment per cell, randomized interleaved schedule). Zero-call
# prepare first (protocol frozen before any call), then the run under F's native lock (taken inside the tool).
# Never resumes: a started study without its result is interrupted and inconclusive (operator review).
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:?G_SOURCE_ROOT (tool snapshot) required}
python_bin=/root/continual-alf-prep-20260928/env/bin/python
source_stage=/root/fivebench-g-20261006-korbench-chain-rubric_research-h
out=${L1_OUTPUT:?L1_OUTPUT (new study directory) required}
log=/root/fivebench-g-20261008-l1-fixed-rubric.log
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT"
tool() { "$python_bin" scripts/run_fivebench_fixed_rubric_study.py "$@"; }
paid() { bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_fixed_rubric_study.py "$@"; }
stop() { echo "$(date -Iseconds) STOP (L1 fixed rubric): $*" >> "$log"; echo "$(date -Iseconds) L1-EXIT=1" >> "$log"; exit 1; }

echo "$(date -Iseconds) L1 start from snapshot $G_SOURCE_ROOT; source $source_stage; output $out" >> "$log"
if [ -f "$out/study/started.json" ] && [ ! -f "$out/study/result.json" ]; then
  stop "$out has an interrupted study (never resumed; inconclusive)"
fi
if [ ! -f "$out/study/protocol.json" ]; then
  tool prepare --source "$source_stage" --output "$out" >> "$log" 2>&1 || stop "zero-call prepare failed"
fi
if [ ! -f "$out/study/result.json" ]; then
  echo "$(date -Iseconds) run (holds F's native lock inside the tool)" >> "$log"
  paid run --source "$source_stage" --output "$out" >> "$log" 2>&1 || stop "the study did not complete (pending or failed; see result.json)"
fi
tool status --output "$out" >> "$log" 2>&1 || stop "the finished study does not verify"
echo "$(date -Iseconds) L1 complete" >> "$log"
echo "$(date -Iseconds) L1-EXIT=0" >> "$log"
