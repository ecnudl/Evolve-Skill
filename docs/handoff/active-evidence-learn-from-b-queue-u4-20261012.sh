#!/usr/bin/env bash
# 10/12 queue u4: learn-from-B study, phase 1 -- the evaluation in forty runs of 25 tasks (design memo section 10).
# Block A (the same 1,000 fresh tasks) in file order: Q01..Q40, --chunk 25 (one batch per arm and run). Same
# evaluation tool (snapshot m) and the arm list frozen at 16:03, in A01's order. A run that leaves a sealed pending
# result is repeated ONCE in a new directory (-r1); a second pending run leaves that block missing; any other state
# halts the queue. The earlier runs a01, a01-r1 (pending) and a02c8 (cancelled) are records only and are not used.
# Every outcome is kept and reported. A STOP is left for operator review; nothing is resumed. NO test cell.
PY=/root/continual-alf-prep-20260928/env/bin/python
M=/root/fivebench-g-20261012-source-m
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261012
Z=$P-searchqa-bzero2
S=$P-searchqa-active
PROBE=/root/net-probe-20261012c.log
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a --benchmark searchqa"
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) U4-EXIT"; exit 1; }
for b in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40; do
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-q$b$attempt
    quiet 30 || halt "no fresh quiet connectivity probe before eval q$b$attempt; nothing was prepared or begun"
    if offline $M scripts/run_active_evidence_panel_eval.py prepare $COMMON --items /root/searchqa-fresh-20261012/block_q$b/items.json --revision c1a979068ba118d85467179b704031d113d689cc $SKILLS --chunk 25 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval q$b$attempt start"
      online $M scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline $M scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval q$b$attempt end"
      if [ $rc -eq 0 ]; then break; fi
      if [ $rc -ne 3 ]; then halt "eval q$b$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval q$b$attempt): sealed pending result, see $e.run.log"
    else
      halt "eval q$b$attempt could not be prepared: see $e.prepare.log"
    fi
  done
done
echo "$(date -Iseconds) U4-EXIT"
