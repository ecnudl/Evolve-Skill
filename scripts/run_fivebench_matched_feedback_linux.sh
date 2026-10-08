#!/usr/bin/env bash
# Paid L3 matched one-step feedback study (fivebench-matched-feedback-study-v1; registered 10/8, Codex design round
# post-S3-2 and code review). Eight blocks from the main method's S2 Skill on KOR-Bench: one shared fresh train
# rollout per block, the frozen default and h2 rubrics' judgments and calibration, one native proposal per arm
# (scalar / default / h2), candidates frozen, then full validation passes. Zero-call prepare first (protocol frozen
# before any call), then the run under F's native lock (taken inside the tool). Never resumes; no test evaluation.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:?G_SOURCE_ROOT (tool snapshot) required}
python_bin=/root/continual-alf-prep-20260928/env/bin/python
source_stage=/root/fivebench-g-20261006-korbench-chain-rubric_research-h
out=${L3_OUTPUT:?L3_OUTPUT (new study directory) required}
log=/root/fivebench-g-20261008-l3-matched-feedback.log
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT"
tool() { "$python_bin" scripts/run_fivebench_matched_feedback_study.py "$@"; }
paid() { bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_matched_feedback_study.py "$@"; }
stop() { echo "$(date -Iseconds) STOP (L3 matched feedback): $*" >> "$log"; echo "$(date -Iseconds) L3-EXIT=1" >> "$log"; exit 1; }

echo "$(date -Iseconds) L3 start from snapshot $G_SOURCE_ROOT; source $source_stage; output $out" >> "$log"
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
echo "$(date -Iseconds) L3 complete" >> "$log"
echo "$(date -Iseconds) L3-EXIT=0" >> "$log"
