#!/usr/bin/env bash
# 10/14 queue z14 (exploration, owner's request of 15:40): (1) the executable-rubric pilot on OfficeQA, (2) the
# cross-dataset evaluation of learned Skills on OfficeQA (74 train+val items) and on SearchQA (fresh blocks
# R01..R10). Design and reading contract, written before any outcome: docs/handoff/rubric-exploration-20261014.md,
# sections 4-5. Snapshot 20261014-y = snapshot x + scripts/pilot_officeqa_rubric_exec.py (+ its test).
# Order (operator, 16:20): after queue z12 (the OfficeQA generated-gate stages) and the release file z14.go
# (after the review); the LiveMath evaluations (l1 blocks e02..e08, l2) follow in queue z9c. Nothing
# that has begun is resumed; a pilot that does not complete ends the queue; a SearchQA block gets one repetition and
# a block that fails twice is counted missing while the other blocks continue; no test data (the OfficeQA test rows
# are neither written out nor supplied to the solver; the SearchQA blocks are development samples outside the
# canonical split).
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261014-source-y
P=/root/fivebench-g-20261014
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
OQ_BZERO=/root/fivebench-g-20261013-officeqa-bzero/skill.md
QA_BZERO=/root/fivebench-g-20261012-searchqa-bzero2/skill.md
QA_V9=/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c
T=$P-foreign-texts
UP=/root/officeqa-upstream-20261013
OQ_REV=763a8366abf2a3605c381d53586d844dc60fa756
QA_REV=c1a979068ba118d85467179b704031d113d689cc
F="--study /root/continual-fivebench-20261003-f-study --repo /root/continual-noskill-bcb-20260928-a"
QA="$F --split /root/fivebench-split-20261005-v2/split_manifest.json"
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z14-EXIT"; exit 1; }
pilot() {  # pilot <tool> <dir> <prepare arguments...>: prepare (zero calls), run once, report
  tool=$1; d=$2; shift 2
  test -e $d && halt "$(basename $d) exists already: a pilot is run once"
  offline scripts/$tool prepare $F --upstream $UP --id-split $UP/id_split --revision $OQ_REV "$@" --output $d > $d.prepare.log 2>&1 || halt "$(basename $d) not prepared: see $d.prepare.log"
  quiet 12 || halt "no fresh quiet connectivity probe before $(basename $d); prepared, not begun"
  echo "$(date -Iseconds) pilot $(basename $d) start"
  online scripts/$tool run --output $d >> $d.run.log 2>&1; rc=$?
  echo "$(date -Iseconds) pilot $(basename $d) end (exit $rc)"
  [ $rc -eq 0 ] || halt "pilot $(basename $d) did not complete: see $d.run.log and $d/result.json; not repeated"
}
panel() {  # panel <label> <items file> <skill args...>: one SearchQA evaluation run, repeated once after a sealed pending result
  label=$1; items=$2; shift 2
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-$label$attempt
    quiet 12 || halt "no fresh quiet connectivity probe before eval $label$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $QA --benchmark searchqa --items $items --revision $QA_REV "$@" --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval $label$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval $label$attempt end"
      if [ $rc -eq 0 ]; then return 0; fi
      if [ $rc -ne 3 ]; then halt "eval $label$attempt left no valid result: see $e.run.log"; fi
      if [ -z "$attempt" ]; then echo "$(date -Iseconds) PENDING (eval $label): sealed pending result, kept; one repetition in a new directory follows"; else echo "$(date -Iseconds) PENDING (eval $label$attempt): sealed pending result, kept; the block is counted missing"; fi
    else
      halt "eval $label$attempt could not be prepared: see $e.prepare.log"
    fi
  done
  return 1
}
while ! test -f $D/z14.go; do sleep 20; done
while ! grep -q "Z12-EXIT" /root/fivebench-g-20261014-active-z12.log 2>/dev/null; do sleep 30; done
test -f $OQ_BZERO && test -f $QA_BZERO || halt "a zero-shot instruction does not exist"
test -e $T && halt "the foreign-text directory exists already"
offline $D/foreign_texts.py $T > $T.log 2>&1 || halt "a learned text could not be written: see $T.log"
echo "$(date -Iseconds) foreign texts: $(tr '\n' ';' < $T.log | cut -c1-300)"
# (1) executable rubric at solve time: plain control, the structured contract, the contract without the instruction
pilot pilot_officeqa_rubric_exec.py $P-officeqa-rubric-exec-a --arm bzero=f:$OQ_BZERO --arm bzero_struct=f:$OQ_BZERO:struct --arm empty_struct=none:struct
offline scripts/pilot_officeqa_rubric_exec.py report --output $P-officeqa-rubric-exec-a --contrast bzero_struct_exec-bzero --contrast bzero_struct-bzero --contrast bzero_struct_exec-bzero_struct --contrast empty_struct_exec-bzero --contrast empty_struct-bzero --contrast empty_struct_exec-empty_struct > $P-officeqa-rubric-exec-a.report.json 2>&1 || echo "$(date -Iseconds) REPORT FAILED (rubric-exec-a): read the sealed records by hand"
# (2a) learned Skills of other datasets on OfficeQA (74 train+val items, plain contract)
pilot pilot_officeqa_headroom.py $P-officeqa-cross-a --skill empty=none --skill bzero=f:$OQ_BZERO --skill qa_v9=f:$T/qa_v9.md --skill lm_z41=f:$T/lm_z41.md --skill lm_e41=f:$T/lm_e41.md --skill e41s2=f:$T/e41s2.md
offline scripts/pilot_officeqa_headroom.py report --output $P-officeqa-cross-a --contrast qa_v9-bzero --contrast lm_z41-bzero --contrast lm_e41-bzero --contrast e41s2-bzero --contrast qa_v9-empty --contrast lm_z41-empty --contrast lm_e41-empty --contrast e41s2-empty > $P-officeqa-cross-a.report.json 2>&1 || echo "$(date -Iseconds) REPORT FAILED (cross-a): read the sealed records by hand"
# (2b) learned Skills of the two new datasets on SearchQA (fresh blocks R01..R10, 250 tasks), next to the controls
missing=0
for b in 01 02 03 04 05 06 07 08 09 10; do
  panel xd-r$b /root/searchqa-fresh-20261012/block_r$b/items.json --skill empty=none --skill bzero=f:$QA_BZERO --skill qa_v9=g:$QA_V9 --skill oq_z41=f:$T/oq_z41.md --skill oq_e41=f:$T/oq_e41.md --skill lm_z41=f:$T/lm_z41.md --skill lm_e41=f:$T/lm_e41.md --skill e41s2=f:$T/e41s2.md || missing=$((missing+1))
done
DIRS=""
for b in 01 02 03 04 05 06 07 08 09 10; do
  for attempt in "-r1" ""; do e=$P-searchqa-paneleval-xd-r$b$attempt; if test -f $e/result.json && grep -q '"status": "completed"' $e/result.json; then DIRS="$DIRS $e"; break; fi; done
done
# the pooled read over the completed block runs (planned 250 tasks): each foreign Skill against bzero and empty
offline scripts/run_active_evidence_panel_eval.py report --output $DIRS --planned-tasks 250 --contrast oq_z41-bzero --contrast oq_e41-bzero --contrast lm_z41-bzero --contrast lm_e41-bzero --contrast e41s2-bzero --contrast qa_v9-bzero --contrast oq_z41-empty --contrast oq_e41-empty --contrast lm_z41-empty --contrast lm_e41-empty --contrast e41s2-empty --contrast qa_v9-empty > $P-searchqa-paneleval-xd.report.json 2>&1 || echo "$(date -Iseconds) REPORT FAILED (searchqa xd): read the sealed records by hand"
echo "$(date -Iseconds) Z14-EXIT (SearchQA blocks without a completed run: $missing of 10)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
