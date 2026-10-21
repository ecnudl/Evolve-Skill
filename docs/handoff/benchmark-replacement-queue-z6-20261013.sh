#!/usr/bin/env bash
# 10/13 queue z6: headroom pilot on LiveMathematicianBench before it replaces a benchmark of the toolchain.
# Design contract: docs/handoff/benchmark-replacement-pilot-20261013.md. Snapshot 20261013-r (= q + the pilot tool).
#   1. one call: the zero-shot instruction from the public task card (generated once, not selected)
#   2. prepare (zero calls): 50 items of each month 2026-03..06 (months of the paper's split are excluded as a
#      whole; five options per item), four arms: empty, bzero, human (the original codebase's starting Skill), paper (its GPT-5.5 Skill)
#   3. run: every arm solves every item once; margins are enforced before each batch; nothing is resumed
# Starts after queue z5 has exited (shared native lock). NO test item of the paper's split is read.
PY=/root/continual-alf-prep-20260928/env/bin/python
R=/root/fivebench-g-20261013-source-r
P=/root/fivebench-g-20261013
T=$P-livemath-texts
PROBE=/root/net-probe-20261012d.log
COMMON="--study /root/continual-fivebench-20261003-f-study --repo /root/continual-noskill-bcb-20260928-a"
online() { (cd $R && export PYTHONPATH=$R && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $R && PYTHONPATH=$R $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z6-EXIT"; exit 1; }
while ! grep -q "Z5-EXIT" $P-active-z5.log; do sleep 30; done
Z=$P-livemath-bzero; A=$P-livemath-pilot-a
quiet 12 || halt "no fresh quiet connectivity probe before the zero-shot generation"
echo "$(date -Iseconds) zero-shot instruction start"
online scripts/pilot_livemath_headroom.py zeroshot $COMMON --output $Z > $Z.log 2>&1
test -f $Z/skill.md || halt "the zero-shot instruction was not generated: see $Z.log"
echo "$(date -Iseconds) zero-shot instruction end ($(wc -c < $Z/skill.md) bytes)"
offline scripts/pilot_livemath_headroom.py prepare $COMMON --upstream /root/livemath-upstream-20261013 --id-split /root/livemath-upstream-20261013/id_split --revision 6f53c5ff7227633ea954b2847cd590314d582047 --per-month 50 --seed 20261013 --skill empty=none --skill bzero=f:$Z/skill.md --skill human=f:$T/human.md --skill paper=f:$T/paper.md --output $A > $A.prepare.log 2>&1 || halt "the pilot could not be prepared: see $A.prepare.log"
quiet 12 || halt "no fresh quiet connectivity probe before the pilot run; prepared, not begun"
echo "$(date -Iseconds) pilot start"
online scripts/pilot_livemath_headroom.py run --output $A >> $A.run.log 2>&1 || echo "$(date -Iseconds) STOP (pilot run did not complete: see $A.run.log)"
echo "$(date -Iseconds) pilot end"
echo "$(date -Iseconds) Z6-EXIT"
