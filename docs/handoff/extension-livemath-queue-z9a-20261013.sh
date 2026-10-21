#!/usr/bin/env bash
# Split at 19:55 on the owner's request to try OfficeQA before LiveMath's long gated stages (queue z9 was stopped
# while it waited; nothing of it had begun): z9a = the six one-step stages (after the pilots), z9b = the three
# gated stages and the evaluation (after the OfficeQA learning queue z10). Stages, arguments, arms and reading
# are those of z9 / section 6 of the design memo.
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z9A-EXIT"; exit 1; }
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
while ! grep -q "Z8-EXIT" $P-active-z8.log; do sleep 30; done
ONE="--method active_evidence --learning-version v11 --arm-feedback scalar --arm-post-update none"
for n in 41 42 43; do
  stage lm-e$n $ONE --parent none --seed 202610$n
  stage lm-z$n $ONE --parent f:$BZERO --seed 202610$n
done
echo "$(date -Iseconds) Z9A-EXIT"
