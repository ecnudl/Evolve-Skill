#!/usr/bin/env bash
# Paid queue (user request 10/6): the three API-only learning-v8 stage redos in order. Every stage
# takes F's native lock inside `learn`/`test` (one native workload and one holder of the key's
# concurrency ceiling at a time), so the queue starts paying only after the feedback pilot that
# holds it has finished. A stage that fails or stops for review ends the queue: nothing later starts.
set -uo pipefail
umask 077
runner=/root/fivebench-g-20261006-source/scripts/run_fivebench_g_stage_linux.sh
log=/root/fivebench-g-20261006-queue.log
for stage in /root/fivebench-g-20261006-qa-c /root/fivebench-g-20261006-kor-c /root/fivebench-g-20261006-bcb-b; do
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
