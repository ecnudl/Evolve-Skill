#!/usr/bin/env bash
# 10/13 queue z9: the first learning runs on LiveMathematicianBench (extension study).
# Design contract: docs/handoff/extension-study-design-20261013.md, section 6. Snapshot 20261013-v (= u + a fixed
# initial instruction as the parent of v9 / v10 stages in an extension study).
#   one-step learning v11 (pass/fail, no selection): lm-e41..43 from the empty Skill, lm-z41..43 from bzero
#   gated learners from bzero: SkillOpt v9 (labelled feedback of failed training rows), Rubric+Research v10
#   SkillOpt v9 from the empty Skill
#   then one panel evaluation of every completed Skill, next to empty / bzero / human / paper, on the 200
#   evaluation items (blocks E01..E08)
# Starts after queue z8 (the headroom pilots) has exited AND the release file z9.go exists (written by the operator
# after reading the LiveMath pilot: no launch if no arm is above chance). Every outcome is kept and reported; a
# stage that stops is not resumed. The sealed test part is never read (the tools refuse test cells here).
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z9-EXIT"; exit 1; }
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
while ! test -f $D/z9.go; do sleep 20; done
while ! grep -q "Z8-EXIT" $P-active-z8.log; do sleep 30; done
ONE="--method active_evidence --learning-version v11 --arm-feedback scalar --arm-post-update none"
for n in 41 42 43; do
  stage lm-e$n $ONE --parent none --seed 202610$n
  stage lm-z$n $ONE --parent f:$BZERO --seed 202610$n
done
stage lm-v9-z41 --method skillopt --learning-version v9 --parent f:$BZERO --val-source $VAL --seed 20261041
stage lm-v10-z41 --method rubric_research --learning-version v10 --parent f:$BZERO --val-source $VAL --seed 20261041
stage lm-v9-e41 --method skillopt --learning-version v9 --parent none --val-source $VAL --seed 20261041
SKILLS="--skill empty=none --skill bzero=f:$BZERO --skill human=f:$T/human.md --skill paper=f:$T/paper.md"
k=0
for pair in lme41=lm-e41 lmz41=lm-z41 lme42=lm-e42 lmz42=lm-z42 lme43=lm-e43 lmz43=lm-z43 v9z41=lm-v9-z41 v10z41=lm-v10-z41 v9e41=lm-v9-e41; do
  d=$P-livemath-${pair#*=}
  if completed $d; then SKILLS="$SKILLS --skill ${pair%%=*}=g:$d"; k=$((k+1)); else echo "$(date -Iseconds) LOST STAGE ${pair#*=} (not completed)"; fi
done
echo "$(date -Iseconds) frozen arms: empty, bzero, human, paper and $k learned Skills of 9"
if [ $k -lt 1 ]; then halt "no completed stage: no evaluation"; fi
missing=0
for b in 01 02 03 04 05 06 07 08; do
  done_block=0
  for attempt in "" "-r1"; do
    e=$P-livemath-paneleval-l1-e$b$attempt
    quiet 12 || halt "no fresh quiet connectivity probe before eval l1-e$b$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --items $X/livemath/eval_blocks/block_e$b/items.json --revision $REV $SKILLS --chunk 10 --output $e > $e.prepare.log 2>&1; then
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
echo "$(date -Iseconds) Z9-EXIT (blocks without a completed run: $missing of 8)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
