#!/usr/bin/env bash
# 10/14 queue z9c (16:25): the LiveMath evaluations that were moved behind the OfficeQA work and the rubric
# exploration (owner's request of 15:40): (1) evaluation l1, blocks E02..E08 (block E01 was completed by queue z9b,
# which was then paused between blocks -- nothing begun was interrupted), exactly z9b's arms and commands;
# (2) evaluation l2 (queue z13b, stopped while it waited; nothing of it had been prepared), exactly z13b's arms and
# commands. Waits for queue z14 to exit and for the release file z9c.go. Same tool and snapshot (v) as before.
# 20:30: a yield file $D/z9c.yield makes the queue wait BETWEEN blocks (the rubric-form study of the night runs in
# those gaps); removing it lets the next block start. No begun block is ever interrupted by it.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261013-source-v
P=/root/fivebench-g-20261013
X=/root/extension-20261013
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
COMMON="--study $X/study-livemath --split $X/split-livemath.json --repo /root/continual-noskill-bcb-20260928-a --benchmark livemath"
BZERO=$P-livemath-bzero/skill.md
VAL=$X/livemath/val_panel.json
T=$P-livemath-texts
REV=6f53c5ff7227633ea954b2847cd590314d582047
online() { (cd $V && export PYTHONPATH=$V && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $V && PYTHONPATH=$V $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z9C-EXIT"; exit 1; }
completed() { test -f $1/learned.json && grep -q '"status": "completed"' $1/learned.json; }
stage() {  # stage <name> <prepare arguments...>: one prepared-and-run learning stage, never resumed
  d=$P-livemath-$1; shift
  if ! offline scripts/run_fivebench_g_stage.py prepare $COMMON "$@" --output $d > $d.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED ($(basename $d)): see $d.prepare.log"; return 1; fi
  if ! quiet 12; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before $(basename $d); prepared, not begun)"; return 1; fi
  echo "$(date -Iseconds) stage $(basename $d) start"
  online scripts/run_fivebench_g_stage.py learn --output $d >> $d.run.log 2>&1 || echo "$(date -Iseconds) STOP (stage $(basename $d)): see $d.run.log"
  offline scripts/run_fivebench_g_stage.py status --output $d >> $d.run.log 2>&1
  echo "$(date -Iseconds) stage $(basename $d) end"
}
while ! test -f $D/z9c.go; do sleep 20; done
while ! grep -q "Z14-EXIT" /root/fivebench-g-20261014-active-z14.log 2>/dev/null; do sleep 30; done
# 21:30: the two rubric-form studies (queues z15, z16) run first; the LiveMath evaluations follow them
while ! grep -q "Z16-EXIT" /root/fivebench-g-20261014-active-z16.log 2>/dev/null; do sleep 30; done
SKILLS="--skill empty=none --skill bzero=f:$BZERO --skill human=f:$T/human.md --skill paper=f:$T/paper.md"
k=0
for pair in lme41=lm-e41 lmz41=lm-z41 lme42=lm-e42 lmz42=lm-z42 lme43=lm-e43 lmz43=lm-z43 v9z41=lm-v9-z41 v10z41=lm-v10-z41 v9e41=lm-v9-e41; do
  d=$P-livemath-${pair#*=}
  if completed $d; then SKILLS="$SKILLS --skill ${pair%%=*}=g:$d"; k=$((k+1)); else echo "$(date -Iseconds) LOST STAGE ${pair#*=} (not completed)"; fi
done
echo "$(date -Iseconds) frozen arms: empty, bzero, human, paper and $k learned Skills of 9"
if [ $k -lt 1 ]; then halt "no completed stage: no evaluation"; fi
missing=0
for b in 02 03 04 05 06 07 08; do
  done_block=0
  for attempt in "" "-r1"; do
    e=$P-livemath-paneleval-l1-e$b$attempt
    while test -f $D/z9c.yield; do sleep 30; done  # operator's yield point between blocks (nothing begun is interrupted)
    quiet 12 || halt "no fresh quiet connectivity probe before eval l1-e$b$attempt"
    # block E02 was prepared by queue z9b seconds before that queue was paused (17:24:12-17:24:17): the directory
    # exists, nothing was begun (no started.json, no call); such a directory is reused, a begun one is never reused
    if test -e $e; then
      if test -e $e/result.json || test -e $e/learning/started.json; then echo "$(date -Iseconds) eval l1-e$b$attempt exists and was begun: not reused"; continue; fi
      echo "$(date -Iseconds) eval l1-e$b$attempt was prepared earlier and not begun: reused"
    elif ! offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --items $X/livemath/eval_blocks/block_e$b/items.json --revision $REV $SKILLS --chunk 10 --output $e > $e.prepare.log 2>&1; then
      halt "eval l1-e$b$attempt could not be prepared: see $e.prepare.log"
    fi
    if true; then
      echo "$(date -Iseconds) eval l1-e$b$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval l1-e$b$attempt end"
      if [ $rc -eq 0 ]; then done_block=1; break; fi
      if [ $rc -ne 3 ]; then halt "eval l1-e$b$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval l1-e$b$attempt): sealed pending result"
    else
      halt "eval l1-e$b$attempt could not be prepared: see $e.prepare.log"
    fi
  done
  if [ $done_block -eq 0 ]; then missing=$((missing+1)); fi
done
echo "$(date -Iseconds) L1-DONE (blocks E02..E08 without a completed run: $missing of 7)"

# ---- evaluation l2 (queue z13b's commands) ----
missing=0
P=/root/fivebench-g-20261014
X=/root/extension-20261013
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
COMMON="--study $X/study-livemath --split $X/split-livemath.json --repo /root/continual-noskill-bcb-20260928-a --benchmark livemath"
BZERO=/root/fivebench-g-20261013-livemath-bzero/skill.md
T=$P-livemath-candidates
REV=6f53c5ff7227633ea954b2847cd590314d582047
online() { (cd $V && export PYTHONPATH=$V && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $V && PYTHONPATH=$V $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z9C-EXIT"; exit 1; }
test -f $BZERO || halt "the zero-shot instruction does not exist"
test -e $T && halt "the candidate directory exists already: this evaluation is prepared once"
offline $D/lm_candidates.py --write $T > $T.write.log 2>&1 || halt "a candidate text does not match its stage record: see $T.write.log"
SKILLS="--skill empty=none --skill bzero=f:$BZERO --skill e41s0=f:$T/e41s0.md --skill e41s2=f:$T/e41s2.md --skill z41s0=f:$T/z41s0.md --skill z41s2=f:$T/z41s2.md"
echo "$(date -Iseconds) frozen arms: empty, bzero, e41s0, e41s2, z41s0, z41s2"
missing=0
for b in 01 02 03 04 05 06 07 08; do
  done_block=0
  for attempt in "" "-r1"; do
    e=$P-livemath-paneleval-l2-e$b$attempt
    while test -f $D/z9c.yield; do sleep 30; done  # operator's yield point between blocks
    quiet 12 || halt "no fresh quiet connectivity probe before eval l2-e$b$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --items $X/livemath/eval_blocks/block_e$b/items.json --revision $REV $SKILLS --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval l2-e$b$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval l2-e$b$attempt end"
      if [ $rc -eq 0 ]; then done_block=1; break; fi
      if [ $rc -ne 3 ]; then halt "eval l2-e$b$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval l2-e$b$attempt): sealed pending result"
    else
      halt "eval l2-e$b$attempt could not be prepared: see $e.prepare.log"
    fi
  done
  if [ $done_block -eq 0 ]; then missing=$((missing+1)); fi
done
echo "$(date -Iseconds) Z9C-EXIT (l2 blocks without a completed run: $missing of 8)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
