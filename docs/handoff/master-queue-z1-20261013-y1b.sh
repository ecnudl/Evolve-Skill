#!/usr/bin/env bash
# Part of master queue z1 (10/13 03:00). The four queues u5, v1, w2 and y1 were stopped by the operator at 02:57 while
# each waited for ten quiet minutes (no run in progress). z1 runs their remaining work one part after another;
# an evaluation run starts after TWELVE consecutive successful TLS-level probes (about two minutes) instead of
# sixty; the tool's in-run gate and the retry rule (one repetition after a sealed pending result) are unchanged.
# Original header of queue y1 (the learning stages lp23..lp27 ran there; lp27 was lost):
# 10/13 queue y1: first prompt-chain experiment -- the analyst "generalization requirement" (profile generalize_v1).
# Design contract: docs/handoff/prompt-chain-design-20261013.md. Snapshot 20261013-p (= o + the optional analyst
# prompt profile in the v11 package and the stage tool; default behaviour unchanged).
#   lp23..lp27   SearchQA, arms scalar / none, parent empty, seeds 20261023-27 (the training rows of le23..le27),
#                --analyst-profile generalize_v1
#   evaluation   empty, bzero, le23..le27 (native prompt), the completed lp stages on 250 fresh tasks (R01..R10)
# Each paid step starts only after about ten quiet minutes of the TLS-level probe. Every outcome is kept and
# reported. A STOP is left for operator review; nothing is resumed. NO test cell.
PY=/root/continual-alf-prep-20260928/env/bin/python
Q=/root/fivebench-g-20261013-source-p
P=/root/fivebench-g-20261013
S=/root/fivebench-g-20261012-searchqa-active
Z=/root/fivebench-g-20261012-searchqa-bzero2
PROBE=/root/net-probe-20261012d.log
REV=c1a979068ba118d85467179b704031d113d689cc
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a"
online() { (cd $Q && export PYTHONPATH=$Q && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $Q && PYTHONPATH=$Q $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Y1B-EXIT"; exit 1; }
SKILLS="--skill empty=none --skill bzero=f:$Z/skill.md --skill le23=g:$S-le23 --skill le24=g:$S-le24 --skill le25=g:$S-le25 --skill le26=g:$S-le26 --skill le27=g:$S-le27"
k=0
for n in 23 24 25 26 27; do
  d=$P-searchqa-active-lp$n
  if test -f $d/learned.json && grep -q '"status": "completed"' $d/learned.json; then SKILLS="$SKILLS --skill lp$n=g:$d"; k=$((k+1)); else echo "$(date -Iseconds) LOST HISTORY lp$n (not completed)"; fi
done
echo "$(date -Iseconds) frozen arms: 7 + $k profile histories"
if [ $k -lt 3 ]; then halt "fewer than three completed profile histories: no evaluation"; fi
for b in 01 02 03 04 05 06 07 08 09 10; do
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-y1-r$b$attempt
    quiet 12 || halt "no fresh quiet connectivity probe before eval y1-r$b$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --benchmark searchqa --items /root/searchqa-fresh-20261012/block_r$b/items.json --revision $REV $SKILLS --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval y1-r$b$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval y1-r$b$attempt end"
      if [ $rc -eq 0 ]; then break; fi
      if [ $rc -ne 3 ]; then halt "eval y1-r$b$attempt left no valid result"; fi
      echo "$(date -Iseconds) STOP (eval y1-r$b$attempt): sealed pending result"
    else
      halt "eval y1-r$b$attempt could not be prepared: see $e.prepare.log"
    fi
  done
done
echo "$(date -Iseconds) Y1B-EXIT"
