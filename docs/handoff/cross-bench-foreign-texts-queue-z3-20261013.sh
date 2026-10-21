#!/usr/bin/env bash
# 10/13 queue z3 (04:25): exploratory follow-up of the cross-benchmark experiment -- three BigCodeBench-trained
# Skill texts on the 250 fresh SearchQA tasks R01..R10, next to no Skill, two initial instructions and the
# same-benchmark SkillOpt Skill. Design contract: docs/handoff/cross-bench-selection-design-20261013.md, section 5.
# Snapshot 20261013-o, the reviewed panel() function of queue v1 with a two-minute quiet window. The three texts are
# written once by extract_foreign_texts.py (zero calls) from sealed records. Runs beside the other queues on the
# shared native lock. Every outcome is kept and reported; nothing is resumed; NO test data. The queue waits for the
# release file z3.go (written by the operator after the review).
PY=/root/continual-alf-prep-20260928/env/bin/python
O=/root/fivebench-g-20261013-source-o
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261013
S=/root/fivebench-g-20261012-searchqa-active
Z=/root/fivebench-g-20261012-searchqa-bzero2
PROBE=/root/net-probe-20261012d.log
REV=c1a979068ba118d85467179b704031d113d689cc
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a"
OLD="--skill old_v10=g:/root/fivebench-g-20261006-searchqa-chain-rubric_research-e"
online() { (cd $O && export PYTHONPATH=$O && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $O && PYTHONPATH=$O $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z3-EXIT"; exit 1; }
panel() {  # panel <label> <items file> <skill args...>: one evaluation run, repeated once after a sealed pending result
  label=$1; items=$2; shift 2
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-$label$attempt
    quiet 12 || halt "no fresh quiet connectivity probe before eval $label$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --benchmark searchqa --items $items --revision $REV "$@" --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval $label$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval $label$attempt end"
      if [ $rc -eq 0 ]; then return 0; fi
      if [ $rc -ne 3 ]; then halt "eval $label$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval $label$attempt): sealed pending result"
    else
      halt "eval $label$attempt could not be prepared: see $e.prepare.log"
    fi
  done
  return 1
}
D=/root/fivebench-g-20261013-queue-z1
X=$P-foreign-texts
while ! test -f $D/z3.go; do sleep 20; done
if ! offline $D/extract_foreign_texts.py $X > $X.log 2>&1; then halt "the foreign texts could not be written: see $X.log"; fi
echo "$(date -Iseconds) foreign texts: $(tail -n 1 $X.log | cut -c1-200)"
missing=0
for b in 01 02 03 04 05 06 07 08 09 10; do
  panel xt-r$b /root/searchqa-fresh-20261012/block_r$b/items.json --skill empty=none --skill bhand=f:$C/generic.md --skill bzero=f:$Z/skill.md --skill old_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c --skill xbcb0=f:$X/xbcb0.md --skill xbcb1=f:$X/xbcb1.md --skill xbcbp=f:$X/xbcbp.md || missing=$((missing+1))
done
echo "$(date -Iseconds) Z3-EXIT (blocks without a completed run: $missing of 10)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
