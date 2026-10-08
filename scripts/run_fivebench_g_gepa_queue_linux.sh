#!/usr/bin/env bash
# Paid queue (user request 10/6): the GEPA baseline under the same learning-v8 conditions as the SkillOpt
# stage redos (same parents, train families, canonical val selection, labeled failure feedback, margin
# gate). Runs from the second source snapshot; each stage waits for F's native lock inside learn/test, so
# it starts paying only after the SkillOpt queue has released it. A failed/pending stage ends the queue.
set -uo pipefail
umask 077
runner=/root/fivebench-g-20261006-source-b/scripts/run_fivebench_g_stage_linux.sh
export G_SOURCE_ROOT=/root/fivebench-g-20261006-source-b
log=/root/fivebench-g-20261006-gepa-queue.log
for stage in /root/fivebench-g-20261006-qa-gepa-a /root/fivebench-g-20261006-kor-gepa-a /root/fivebench-g-20261006-bcb-gepa-a; do
  if [ ! -f "$stage/stage.json" ]; then
    echo "$(date -Iseconds) stop: $stage is not prepared" >> "$log"; exit 2
  fi
  echo "$(date -Iseconds) start $stage" >> "$log"
  if ! bash "$runner" "$stage" >> "$log" 2>&1; then
    echo "$(date -Iseconds) STOP: $stage failed or needs operator review; later stages not started" >> "$log"
    exit 1
  fi
  echo "$(date -Iseconds) done $stage" >> "$log"
done
echo "$(date -Iseconds) queue complete" >> "$log"
