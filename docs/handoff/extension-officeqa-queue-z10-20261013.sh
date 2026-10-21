#!/usr/bin/env bash
# 10/13 queue z10: the first learning runs on OfficeQA (one-call form; the SkillOpt paper's split: 50 training
# items of which a stage draws 48, 24 validation items for the gate; the 172 test items are sealed, ids only).
# Design contract: docs/handoff/extension-study-design-20261013.md, section 7. Snapshot 20261013-w.
#   gated learners first: SkillOpt v9 and Rubric+Research v10 from the zero-shot instruction, SkillOpt v9 from
#   the empty Skill; then one-step learning v11 from the instruction and from the empty Skill (three seeds each)
# No evaluation: the only held-out data is the sealed test part, which needs the owner's go-ahead.
# Waits for the release file z10.go (operator, after the review) and for the OfficeQA headroom pilot (queue z8).
# Every outcome is kept and reported; a stage that stops is not resumed.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261013-source-w
P=/root/fivebench-g-20261013
X=/root/extension-20261013
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
COMMON="--study $X/study-officeqa --split $X/split-officeqa.json --repo /root/continual-noskill-bcb-20260928-a --benchmark officeqa"
BZERO=$P-officeqa-bzero/skill.md
VAL=$X/officeqa/val_panel.json
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z10-EXIT"; exit 1; }
completed() { test -f $1/learned.json && grep -q '"status": "completed"' $1/learned.json; }
stage() {  # stage <name> <prepare arguments...>: one prepared-and-run learning stage, never resumed
  d=$P-officeqa-$1; shift
  if ! offline scripts/run_fivebench_g_stage.py prepare $COMMON "$@" --output $d > $d.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED ($(basename $d)): see $d.prepare.log"; return 1; fi
  if ! quiet 12; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before $(basename $d); prepared, not begun)"; return 1; fi
  echo "$(date -Iseconds) stage $(basename $d) start"
  online scripts/run_fivebench_g_stage.py learn --output $d >> $d.run.log 2>&1 || echo "$(date -Iseconds) STOP (stage $(basename $d)): see $d.run.log"
  offline scripts/run_fivebench_g_stage.py status --output $d >> $d.run.log 2>&1
  echo "$(date -Iseconds) stage $(basename $d) end"
}
while ! test -f $D/z10.go; do sleep 20; done
while ! grep -q "Z8-EXIT" $P-active-z8.log; do sleep 30; done
test -f $BZERO || halt "the zero-shot instruction of the headroom pilot does not exist"
stage oq-v9-z41 --method skillopt --learning-version v9 --parent f:$BZERO --val-source $VAL --seed 20261041
stage oq-v10-z41 --method rubric_research --learning-version v10 --parent f:$BZERO --val-source $VAL --seed 20261041
stage oq-v9-e41 --method skillopt --learning-version v9 --parent none --val-source $VAL --seed 20261041
ONE="--method active_evidence --learning-version v11 --arm-feedback scalar --arm-post-update none"
for n in 41 42 43; do
  stage oq-z$n $ONE --parent f:$BZERO --seed 202610$n
  stage oq-e$n $ONE --parent none --seed 202610$n
done
echo "$(date -Iseconds) Z10-EXIT"
