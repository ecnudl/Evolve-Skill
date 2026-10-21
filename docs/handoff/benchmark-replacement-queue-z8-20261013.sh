#!/usr/bin/env bash
# 10/13 queue z8: the two headroom pilots with ROLLING submission (snapshot 20261013-t = s + the rolling loop in
# both pilot tools). Design contract: docs/handoff/benchmark-replacement-pilot-20261013.md (sections 1-6 and the
# amendment of 17:00). Replaces queues z6 and z7: the batch-synchronous LiveMath run (pilot-a) was stopped by the
# operator after 80 of 800 positions because single replies of half an hour held whole batches back; it is sealed
# pending and not used.
#   1. LiveMath pilot-b: the SAME 200 items, option orders, four Skill texts (the zero-shot instruction generated
#      at 15:55 is reused, not regenerated), model, caps, scorer and reading rules; all 800 positions solved anew
#   2. OfficeQA: the zero-shot instruction (one call), then the pilot on the 74 training and validation items
# Nothing is resumed. NO test item of either benchmark's sealed part is read out.
PY=/root/continual-alf-prep-20260928/env/bin/python
R=/root/fivebench-g-20261013-source-t
P=/root/fivebench-g-20261013
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
# ---- 1. LiveMath
T=$P-livemath-texts; Z=$P-livemath-bzero; A=$P-livemath-pilot-b
if offline scripts/pilot_livemath_headroom.py prepare $COMMON --upstream /root/livemath-upstream-20261013 --id-split /root/livemath-upstream-20261013/id_split --revision 6f53c5ff7227633ea954b2847cd590314d582047 --per-month 50 --seed 20261013 --skill empty=none --skill bzero=f:$Z/skill.md --skill human=f:$T/human.md --skill paper=f:$T/paper.md --output $A > $A.prepare.log 2>&1 && quiet 12; then
  echo "$(date -Iseconds) livemath pilot-b start"
  online scripts/pilot_livemath_headroom.py run --output $A >> $A.run.log 2>&1 || echo "$(date -Iseconds) STOP (livemath pilot-b did not complete: see $A.run.log)"
  echo "$(date -Iseconds) livemath pilot-b end"
else
  echo "$(date -Iseconds) STOP (livemath pilot-b not prepared or no quiet connectivity: see $A.prepare.log)"
fi
# ---- 2. OfficeQA
T=$P-officeqa-texts; Z=$P-officeqa-bzero; A=$P-officeqa-pilot-a
if quiet 12; then
  echo "$(date -Iseconds) officeqa zero-shot instruction start"
  online scripts/pilot_officeqa_headroom.py zeroshot $COMMON --output $Z > $Z.log 2>&1
  if test -f $Z/skill.md; then
    echo "$(date -Iseconds) officeqa zero-shot instruction end ($(wc -c < $Z/skill.md) bytes)"
    if offline scripts/pilot_officeqa_headroom.py prepare $COMMON --upstream /root/officeqa-upstream-20261013 --id-split /root/officeqa-upstream-20261013/id_split --revision 763a8366abf2a3605c381d53586d844dc60fa756 --skill empty=none --skill bzero=f:$Z/skill.md --skill human=f:$T/human.md --skill paper=f:$T/paper.md --output $A > $A.prepare.log 2>&1 && quiet 12; then
      echo "$(date -Iseconds) officeqa pilot start"
      online scripts/pilot_officeqa_headroom.py run --output $A >> $A.run.log 2>&1 || echo "$(date -Iseconds) STOP (officeqa pilot did not complete: see $A.run.log)"
      echo "$(date -Iseconds) officeqa pilot end"
    else
      echo "$(date -Iseconds) STOP (officeqa pilot not prepared or no quiet connectivity: see $A.prepare.log)"
    fi
  else
    echo "$(date -Iseconds) STOP (the officeqa zero-shot instruction was not generated: see $Z.log)"
  fi
else
  echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before the officeqa zero-shot generation)"
fi
echo "$(date -Iseconds) Z8-EXIT"
