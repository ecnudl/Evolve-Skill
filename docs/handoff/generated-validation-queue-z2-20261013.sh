#!/usr/bin/env bash
# 10/13 queue z2 (03:15): replication of E2 -- generated test tasks as the selection set of the frozen
# learning-v10 rubric_research learner -- on seeds 20261007 and 20261008. Design contract:
# docs/handoff/generated-validation-design-20261013.md, section 5. Snapshot 20261013-o, the same tools, commands
# and evaluation function as queue v1 (steps 1 to 3). Runs beside master queue z1 on the shared native lock (one
# run at a time). A run starts after twelve consecutive successful TLS-level probes (about two minutes). Every
# outcome is kept and reported. A STOP is left for operator review; nothing is resumed. NO test cell, no canonical
# validation data. The queue waits for the release file z2.go (written by the operator after the review).
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z2-EXIT"; exit 1; }
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
while ! test -f $D/z2.go; do sleep 20; done
for n in 07 08; do
  G=$P-searchqa-gen$n; E=$P-searchqa-v10gen-s$n
  if ! offline scripts/generate_searchqa_tasks.py prepare $COMMON --seed 202610$n --output $G > $G.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED (generation gen$n): see $G.prepare.log"; continue; fi
  if ! quiet 12; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before generation gen$n; prepared, not begun)"; continue; fi
  echo "$(date -Iseconds) generation gen$n start"
  online scripts/generate_searchqa_tasks.py run --output $G >> $G.run.log 2>&1
  if ! offline scripts/generate_searchqa_tasks.py check --output $G >> $G.run.log 2>&1; then echo "$(date -Iseconds) STOP (generation gen$n did not complete): see $G.run.log"; continue; fi
  echo "$(date -Iseconds) generation gen$n end ($(tail -n 1 $G.run.log | cut -c1-160))"
  if ! offline scripts/run_fivebench_g_stage.py prepare --method rubric_research --learning-version v10 $COMMON --benchmark searchqa --parent none --seed 202610$n --generated-val $G --output $E > $E.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED (stage searchqa-v10gen-s$n): see $E.prepare.log"; continue; fi
  if ! quiet 12; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before stage searchqa-v10gen-s$n; prepared, not begun)"; continue; fi
  echo "$(date -Iseconds) stage searchqa-v10gen-s$n start"
  online scripts/run_fivebench_g_stage.py learn --output $E >> $E.run.log 2>&1 || echo "$(date -Iseconds) STOP (stage searchqa-v10gen-s$n): see $E.run.log"
  offline scripts/run_fivebench_g_stage.py status --output $E >> $E.run.log 2>&1
  echo "$(date -Iseconds) stage searchqa-v10gen-s$n end"
done
SKILLS="--skill empty=none --skill bzero=f:$Z/skill.md $OLD --skill v10gen=g:$P-searchqa-v10gen-a"
k=0
for n in 07 08; do
  E=$P-searchqa-v10gen-s$n
  if test -f $E/learned.json && grep -q '"status": "completed"' $E/learned.json; then SKILLS="$SKILLS --skill v10gen$n=g:$E"; k=$((k+1)); else echo "$(date -Iseconds) LOST HISTORY v10gen$n (not completed)"; fi
done
echo "$(date -Iseconds) frozen arms: 4 + $k new generated-gate histories"
if [ $k -lt 1 ]; then halt "no new completed history: no evaluation"; fi
missing=0
for b in 01 02 03 04 05 06 07 08 09 10; do
  panel e2b-r$b /root/searchqa-fresh-20261012/block_r$b/items.json $SKILLS || missing=$((missing+1))
done
echo "$(date -Iseconds) Z2-EXIT (blocks without a completed run: $missing of 10)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
