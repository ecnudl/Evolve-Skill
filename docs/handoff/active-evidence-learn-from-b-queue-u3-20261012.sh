#!/usr/bin/env bash
# 10/12 queue u3: learn-from-B study, phase 1 -- evaluation blocks A02..A10 with --chunk 8 (design memo section 9,
# note of 16:10). Queue u2 ran block A01 with --chunk 10 at 53 evaluations per minute (a batch of 10 on 8 solver
# threads wastes most of a second wave); u2 was made to stop after A01 (placeholder directories for its A02..A10
# runs) BEFORE any evaluation outcome was read, and this queue runs the remaining nine blocks with batches of 8.
# Same evaluation tool (snapshot m), same frozen arm list in the same order as A01, same repetition rule: a run
# that leaves a sealed pending result is repeated ONCE in a new directory (-r1); any other state halts the queue.
# Every outcome is kept and reported. A STOP is left for operator review; nothing is resumed. NO test cell.
PY=/root/continual-alf-prep-20260928/env/bin/python
M=/root/fivebench-g-20261012-source-m
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261012
Z=$P-searchqa-bzero2
S=$P-searchqa-active
PROBE=/root/net-probe-20261012c.log
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a --benchmark searchqa"
# the arm list frozen by u2 at 16:03 (first five completed histories per parent in seed order), in A01's order
SKILLS="--skill empty=none --skill bhand=f:$C/generic.md --skill bzero=f:$Z/skill.md"
SKILLS="$SKILLS --skill le23=g:$S-le23 --skill le24=g:$S-le24 --skill le25=g:$S-le25 --skill le26=g:$S-le26 --skill le27=g:$S-le27"
SKILLS="$SKILLS --skill lh21=g:$S-lh21 --skill lh22=g:$S-lh22 --skill lh23=g:$S-lh23 --skill lh24=g:$S-lh24 --skill lh26=g:$S-lh26"
SKILLS="$SKILLS --skill lz21=g:$S-lz21 --skill lz22=g:$S-lz22 --skill lz23=g:$S-lz23 --skill lz24=g:$S-lz24 --skill lz25=g:$S-lz25"
SKILLS="$SKILLS --skill old_v10=g:/root/fivebench-g-20261006-searchqa-chain-rubric_research-e --skill old_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"
online() { src=$1; shift; (cd $src && export PYTHONPATH=$src && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { src=$1; shift; (cd $src && PYTHONPATH=$src $PY "$@"); }
quiet() {  # 0 once the probe log is quiet (scripts/connectivity_probe.py quiet); 1 after $2 seconds (default 4 h)
  waited=0
  while ! offline $M scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-14400}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) U3-EXIT"; exit 1; }
while ! grep -q "U2-EXIT" $P-active-u2.log; do sleep 30; done
echo "$(date -Iseconds) u2 has exited"
# block A01 must have a completed result with exactly this arm list before the remaining blocks are run
offline $M scripts/run_active_evidence_panel_eval.py status --output $P-searchqa-paneleval-a01 > /dev/null 2>&1; rc=$?
if [ $rc -ne 0 ] && [ $rc -ne 3 ]; then halt "block A01 left no valid result"; fi
for b in 02 03 04 05 06 07 08 09 10; do
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-a${b}c8$attempt
    quiet 30 || halt "no fresh quiet connectivity probe before eval a${b}c8$attempt; nothing was prepared or begun"
    if offline $M scripts/run_active_evidence_panel_eval.py prepare $COMMON --items /root/searchqa-fresh-20261012/block_a$b/items.json --revision c1a979068ba118d85467179b704031d113d689cc $SKILLS --chunk 8 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval a${b}c8$attempt start"
      online $M scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline $M scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval a${b}c8$attempt end"
      if [ $rc -eq 0 ]; then break; fi
      if [ $rc -ne 3 ]; then halt "eval a${b}c8$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval a${b}c8$attempt): sealed pending result, see $e.run.log"
    else
      halt "eval a${b}c8$attempt could not be prepared: see $e.prepare.log"
    fi
  done
done
echo "$(date -Iseconds) U3-EXIT"
