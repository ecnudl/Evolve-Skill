#!/usr/bin/env bash
# 10/14 queue z13: panel evaluation l2 on LiveMath -- the three candidates that reached a confirmation pass in the
# gated SkillOpt stages (lm-v9-e41 step 0; lm-v9-z41 steps 0 and 2), next to empty and bzero, on the 200
# evaluation items (blocks E01..E08). Design and reading contract, written before any outcome:
# docs/handoff/gate-pooled-replay-20261014.md, sections 3-4. Same tool and snapshot (v) as evaluation l1.
# Runs LAST: waits for queue z9b (evaluation l1) and queue z12 (OfficeQA generated validation) to exit, and for
# the release file z13.go (operator, after the review). The candidate texts are written from the stages' sealed
# records after their recorded hashes are checked. No learning, no test read; a block gets at most one repetition.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261013-source-v
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z13-EXIT"; exit 1; }
while ! test -f $D/z13.go; do sleep 20; done
while ! grep -q "Z9B-EXIT" /root/fivebench-g-20261013-active-z9b.log; do sleep 30; done
while ! grep -q "Z12-EXIT" /root/fivebench-g-20261014-active-z12.log 2>/dev/null; do sleep 30; done
test -f $BZERO || halt "the zero-shot instruction does not exist"
test -e $T && halt "the candidate directory exists already: this evaluation is prepared once"
offline $D/lm_candidates.py --write $T > $T.write.log 2>&1 || halt "a candidate text does not match its stage record: see $T.write.log"
SKILLS="--skill empty=none --skill bzero=f:$BZERO --skill e41s0=f:$T/e41s0.md --skill z41s0=f:$T/z41s0.md --skill z41s2=f:$T/z41s2.md"
echo "$(date -Iseconds) frozen arms: empty, bzero, e41s0, z41s0, z41s2"
missing=0
for b in 01 02 03 04 05 06 07 08; do
  done_block=0
  for attempt in "" "-r1"; do
    e=$P-livemath-paneleval-l2-e$b$attempt
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
echo "$(date -Iseconds) Z13-EXIT (blocks without a completed run: $missing of 8)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
