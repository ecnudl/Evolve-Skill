#!/usr/bin/env bash
# 10/13 queue z7: headroom pilot on OfficeQA in a one-call form (the question plus the parsed pages its source
# hints point to). Design contract: docs/handoff/benchmark-replacement-pilot-20261013.md, section 6.
# Snapshot 20261013-s (= r + the OfficeQA pilot tool).
#   1. one call: the zero-shot instruction from the public task card (generated once, not selected)
#   2. prepare (zero calls): the 74 training and validation items of the paper's split (its 172 test items are
#      never selected), four arms: empty, bzero, human (the original codebase's starting Skill), paper (its GPT-5.5
#      Skill, which was learned and selected on these very items: an optimistic reference)
#   3. run: every arm solves every item once; margins are enforced before each batch; nothing is resumed
# Starts after queue z6 has exited (shared native lock).
PY=/root/continual-alf-prep-20260928/env/bin/python
R=/root/fivebench-g-20261013-source-s
P=/root/fivebench-g-20261013
T=$P-officeqa-texts
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z7-EXIT"; exit 1; }
while ! grep -q "Z6-EXIT" $P-active-z6.log; do sleep 30; done
Z=$P-officeqa-bzero; A=$P-officeqa-pilot-a
quiet 12 || halt "no fresh quiet connectivity probe before the zero-shot generation"
echo "$(date -Iseconds) zero-shot instruction start"
online scripts/pilot_officeqa_headroom.py zeroshot $COMMON --output $Z > $Z.log 2>&1
test -f $Z/skill.md || halt "the zero-shot instruction was not generated: see $Z.log"
echo "$(date -Iseconds) zero-shot instruction end ($(wc -c < $Z/skill.md) bytes)"
offline scripts/pilot_officeqa_headroom.py prepare $COMMON --upstream /root/officeqa-upstream-20261013 --id-split /root/officeqa-upstream-20261013/id_split --revision 763a8366abf2a3605c381d53586d844dc60fa756 --skill empty=none --skill bzero=f:$Z/skill.md --skill human=f:$T/human.md --skill paper=f:$T/paper.md --output $A > $A.prepare.log 2>&1 || halt "the pilot could not be prepared: see $A.prepare.log"
quiet 12 || halt "no fresh quiet connectivity probe before the pilot run; prepared, not begun"
echo "$(date -Iseconds) pilot start"
online scripts/pilot_officeqa_headroom.py run --output $A >> $A.run.log 2>&1 || echo "$(date -Iseconds) STOP (pilot run did not complete: see $A.run.log)"
echo "$(date -Iseconds) pilot end"
echo "$(date -Iseconds) Z7-EXIT"
