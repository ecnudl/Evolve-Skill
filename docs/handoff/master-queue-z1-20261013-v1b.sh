#!/usr/bin/env bash
# Part of master queue z1 (10/13 03:00). The four queues u5, v1, w2 and y1 were stopped by the operator at 02:57 while
# each waited for ten quiet minutes (no run in progress). z1 runs their remaining work one part after another;
# an evaluation run starts after TWELVE consecutive successful TLS-level probes (about two minutes) instead of
# sixty; the tool's in-run gate and the retry rule (one repetition after a sealed pending result) are unchanged.
# Original header of queue v1 (steps 1 and 2 ran there):
# 10/13 queue v1: generated test tasks instead of a validation set for the Rubric+Research method (SearchQA).
# Design contract: docs/handoff/generated-validation-design-20261013.md. Snapshot 20261013-o.
#   1. gen06     generate test tasks from the 128 training tasks of seed 20261006 (public fields only);
#   2. v10gen-a  E2: the FROZEN learning-v10 rubric_research learner, seed 20261006, parent none, with the generated
#                tasks as its selection set (--generated-val); learn only, no test cell;
#   3. E2 read   empty / bzero / the original v10 Skill / the new Skill on 250 FRESH real tasks (block B, R01..R10);
#   4. E1        ten frozen Skills (empty, bhand, bzero, le23..le27, old_v10, old_v9) on the generated tasks.
# Each paid step starts only after about ten quiet minutes of the TLS-level probe. Every outcome is kept and
# reported. A STOP is left for operator review; nothing is resumed. NO test cell, no canonical validation data.
PY=/root/continual-alf-prep-20260928/env/bin/python
O=/root/fivebench-g-20261013-source-o
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261013
S=/root/fivebench-g-20261012-searchqa-active
Z=/root/fivebench-g-20261012-searchqa-bzero2
G=$P-searchqa-gen06
E2=$P-searchqa-v10gen-a
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) V1B-EXIT"; exit 1; }
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
# 3. E2 read on fresh real tasks (only if the stage completed)
if test -f $E2/learned.json && grep -q '"status": "completed"' $E2/learned.json; then
  for b in 01 02 03 04 05 06 07 08 09 10; do
    panel e2-r$b /root/searchqa-fresh-20261012/block_r$b/items.json --skill empty=none --skill bzero=f:$Z/skill.md $OLD --skill v10gen=g:$E2
  done
else
  echo "$(date -Iseconds) E2 read skipped: stage searchqa-v10gen-a is not completed"
fi
echo "$(date -Iseconds) V1B-EXIT"
