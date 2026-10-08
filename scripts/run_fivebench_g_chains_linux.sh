#!/usr/bin/env bash
# Runs the two three-domain chains (SkillOpt, then GEPA) after both stage-redo queues have fully
# ended. Their tmux wrappers append `QUEUE-EXIT=<code>` to the queue logs when the queue process
# exits (the queue scripts themselves end with `queue complete` or a STOP line); this launcher also
# requires that no redo-queue or stage-runner process is alive, so a marker alone never releases it
# while a queue still runs. Stage 1 of each chain is a BigCodeBench stage (parent none) that must not be
# touched while a redo queue may still be learning or testing it. Exit code: 0 only if both chains
# completed; the per-chain exit codes are logged.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=/root/fivebench-g-20261006-source-c
log=/root/fivebench-g-20261006-chains.log
skillopt_first=${1:-/root/fivebench-g-20261006-bcb-b}
gepa_first=${2:-/root/fivebench-g-20261006-bcb-gepa-chain-a}
echo "$(date -Iseconds) chains launcher started; waiting for both redo queues" >> "$log"
ended() {  # ended <log>: the queue's QUEUE-EXIT marker is present and no redo queue process is alive
  # Anchored at "bash": the tmux server keeps the argv of the command that started it, so an
  # unanchored pattern would match the server itself forever.
  [ -f "$1" ] && grep -q "QUEUE-EXIT" "$1" \
    && ! pgrep -f "^bash /root/.*run_fivebench_g_(queue|gepa_queue|stage)_linux\.sh" >/dev/null
}
until ended /root/fivebench-g-20261006-queue.log && ended /root/fivebench-g-20261006-gepa-queue.log; do sleep 60; done
echo "$(date -Iseconds) both redo queues ended; starting chains" >> "$log"
status=0
bash "$G_SOURCE_ROOT/scripts/run_fivebench_g_chain_linux.sh" skillopt "$skillopt_first" a >> "$log" 2>&1; code=$?
echo "$(date -Iseconds) skillopt chain exit=$code" >> "$log"; [ "$code" = 0 ] || status=1
bash "$G_SOURCE_ROOT/scripts/run_fivebench_g_chain_linux.sh" gepa "$gepa_first" a >> "$log" 2>&1; code=$?
echo "$(date -Iseconds) gepa chain exit=$code" >> "$log"; [ "$code" = 0 ] || status=1
echo "$(date -Iseconds) CHAINS-EXIT=$status" >> "$log"
exit $status
