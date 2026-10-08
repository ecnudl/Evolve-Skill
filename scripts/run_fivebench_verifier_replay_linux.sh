#!/usr/bin/env bash
# Registered frozen-train verifier replay (10/8; Codex design rounds 1-2, review rounds 14-15; amended 10/8 by Codex
# design round v7-1): the current verifier (v7) on chain f's BigCodeBench step-0 train rollout, verifier-only
# (scripts/replay_fivebench_verifier.py, replay protocol v2; source rollout and launch criteria unchanged). It must not
# compete with the prespecified main table: it waits until every main-table queue has written its completion line --
# the main method's S3 is now the replacement queue run_fivebench_g_main_s3_linux.sh (chain e's KOR stage went pending
# and is superseded; its STOP logs are kept) -- exits without running if that queue stopped, and the tool re-checks the
# same markers after taking F's native lock, which it holds for the whole replay. Never resumed automatically; a
# pending/interrupted replay is inconclusive (operator review). New output directory and log for the v7 replay.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:?G_SOURCE_ROOT (v7 tool snapshot) required}
python_bin=/root/continual-alf-prep-20260928/env/bin/python
source_stage=/root/fivebench-g-20261007-bigcodebench-chain-rubric_research-f
s3_tag=${G_S3_TAG:?G_S3_TAG (chain tag of the main-method S3 replacement queue) required}
output=${G_REPLAY_OUTPUT:-/root/fivebench-g-20261008-verifier-replay-f0-v7}
log=/root/fivebench-g-20261008-verifier-replay-v7.log
s3_log=/root/fivebench-g-20261008-main-s3-$s3_tag.log
markers=(
  "/root/fivebench-g-20261006-chain-skillopt-v9c.log::chain skillopt/v9c complete"
  "/root/fivebench-g-20261006-chain-gepa-v9a.log::chain gepa/v9a complete"
  "/root/fivebench-g-20261007-main-f.log::MAIN-EXIT=0"
  "$s3_log::main S3 ($s3_tag) complete"
  "$s3_log::MAIN-EXIT=0"
)
# the S3 queue's own stop line (its log also carries tool JSON, e.g. a Skill text, so a bare "STOP" could misfire)
stops=("$s3_log::STOP (main S3 $s3_tag)")
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT"
echo "$(date -Iseconds) replay queued from snapshot $G_SOURCE_ROOT -> $output" >> "$log"
complete() { local m; for m in "${markers[@]}"; do grep -qF -- "${m#*::}" "${m%%::*}" 2>/dev/null || return 1; done; }
stopped() {  # checked BEFORE completion is accepted (a STOP after the markers must still prevent the replay)
  local s
  for s in "${stops[@]}"; do
    if grep -qF -- "${s#*::}" "${s%%::*}" 2>/dev/null; then
      echo "$(date -Iseconds) main table stopped (${s%%::*}); replay NOT started (operator review)" >> "$log"
      return 0
    fi
  done
  return 1
}
while true; do
  if stopped; then echo "$(date -Iseconds) REPLAY-EXIT=2" >> "$log"; exit 2; fi
  complete && break
  sleep 600
done
args=()
for m in "${markers[@]}"; do args+=(--require "$m"); done
for s in "${stops[@]}"; do args+=(--forbid "$s"); done  # re-checked by the tool after taking the lock
echo "$(date -Iseconds) main table complete; replay starts (waits for F's native lock)" >> "$log"
bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/replay_fivebench_verifier.py \
  --source "$source_stage" --step 0 --output "$output" "${args[@]}" >> "$log" 2>&1
code=$?
echo "$(date -Iseconds) REPLAY-EXIT=$code" >> "$log"
exit $code
