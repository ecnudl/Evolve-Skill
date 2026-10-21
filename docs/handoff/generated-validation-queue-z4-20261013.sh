#!/usr/bin/env bash
# 10/13 queue z4 (06:30): E3 -- the frozen learning-v10 rubric_research learner with generated validation, starting
# from the zero-shot initial instruction instead of the empty Skill. Design contract:
# docs/handoff/generated-validation-design-20261013.md, section 6. Snapshot 20261013-q (= p + a fixed-text parent
# for stages with a generated selection set). Reuses the generated sets gen06/07/08 of E2. Starts only after the
# fresh-task part u6 of master queue z1 has ended and the release file z4.go exists (operator, after the review);
# then runs beside the other queues on the shared native lock. A run starts after twelve consecutive successful
# TLS-level probes. Every outcome is kept and reported; nothing is resumed. NO test cell, no canonical validation.
PY=/root/continual-alf-prep-20260928/env/bin/python
O=/root/fivebench-g-20261013-source-q
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z4-EXIT"; exit 1; }
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
while ! test -f $D/z4.go; do sleep 20; done
while ! grep -q "part u6 end" $P-active-z1.log; do sleep 30; done
for n in 06 07 08; do
  G=$P-searchqa-gen$n; E=$P-searchqa-v10gen-b$n
  if ! offline scripts/run_fivebench_g_stage.py prepare --method rubric_research --learning-version v10 $COMMON --benchmark searchqa --parent f:$Z/skill.md --seed 202610$n --generated-val $G --output $E > $E.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED (stage searchqa-v10gen-b$n): see $E.prepare.log"; continue; fi
  if ! quiet 12; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before stage searchqa-v10gen-b$n; prepared, not begun)"; continue; fi
  echo "$(date -Iseconds) stage searchqa-v10gen-b$n start"
  online scripts/run_fivebench_g_stage.py learn --output $E >> $E.run.log 2>&1 || echo "$(date -Iseconds) STOP (stage searchqa-v10gen-b$n): see $E.run.log"
  offline scripts/run_fivebench_g_stage.py status --output $E >> $E.run.log 2>&1
  echo "$(date -Iseconds) stage searchqa-v10gen-b$n end"
done
SKILLS="--skill empty=none --skill bzero=f:$Z/skill.md --skill v10gen=g:$P-searchqa-v10gen-a --skill v10gen07=g:$P-searchqa-v10gen-s07 --skill v10gen08=g:$P-searchqa-v10gen-s08"
k=0
for n in 06 07 08; do
  E=$P-searchqa-v10gen-b$n
  if test -f $E/learned.json && grep -q '"status": "completed"' $E/learned.json; then SKILLS="$SKILLS --skill vb$n=g:$E"; k=$((k+1)); else echo "$(date -Iseconds) LOST HISTORY vb$n (not completed)"; fi
done
SKILLS="$SKILLS $OLD --skill old_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"
echo "$(date -Iseconds) frozen arms: 7 + $k from-bzero histories"
if [ $k -lt 1 ]; then halt "no completed from-bzero history: no evaluation"; fi
missing=0
for b in 01 02 03 04 05 06 07 08 09 10; do
  panel e3-r$b /root/searchqa-fresh-20261012/block_r$b/items.json $SKILLS || missing=$((missing+1))
done
echo "$(date -Iseconds) Z4-EXIT (blocks without a completed run: $missing of 10)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
