#!/usr/bin/env bash
# 10/13 queue z5 (11:30): confirmation run of the analyst prompt profile generalize_v1 (ordered by the owner).
# Design contract: docs/handoff/prompt-chain-design-20261013.md, section 5. Snapshot 20261013-p, the stage
# commands and the evaluation loop of the reviewed queue y1.
#   stages      le28..le35 (native analyst prompt) and lp28..lp35 (--analyst-profile generalize_v1): SearchQA,
#               arms scalar / none, parent empty, seeds 20261028-35; the order of the two alternates by seed
#   evaluation  empty, bzero and every COMPLETE new pair (member order alternating by seed) on 750 unused fresh
#               tasks (block B positions 251-1000, blocks S01..S30); the first study's histories are not evaluated
# A run starts after twelve consecutive successful TLS-level probes; a block that ends with a sealed pending
# result is repeated once. Every outcome is kept and reported; a stage that stops is lost; nothing is resumed.
# NO test cell. The queue waits for the release file z5.go (written by the operator after the review).
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z5-EXIT"; exit 1; }
D=/root/fivebench-g-20261013-queue-z1
while ! test -f $D/z5.go; do sleep 20; done
stage() {  # stage <name> <seed and profile arguments...>: one prepared-and-run learning stage, never resumed
  s=$1; shift
  if ! offline scripts/run_fivebench_g_stage.py prepare --method active_evidence --learning-version v11 $COMMON --benchmark searchqa --arm-feedback scalar --arm-post-update none --parent none "$@" --output $P-$s > $P-$s.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED (stage $s): see $P-$s.prepare.log"; return 1; fi
  if ! quiet 12; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before stage $s; prepared, not begun)"; return 1; fi
  echo "$(date -Iseconds) stage $s start"
  G_SOURCE_ROOT=$Q G_SKIP_TEST=1 bash $Q/scripts/run_fivebench_active_evidence_linux.sh $P-$s || echo "$(date -Iseconds) STOP (stage $s)"
  echo "$(date -Iseconds) stage $s end"
}
completed() { test -f $1/learned.json && grep -q '"status": "completed"' $1/learned.json; }
for n in 28 29 30 31 32 33 34 35; do
  if [ $((n % 2)) -eq 0 ]; then
    stage searchqa-active-le$n --seed 202610$n; stage searchqa-active-lp$n --seed 202610$n --analyst-profile generalize_v1
  else
    stage searchqa-active-lp$n --seed 202610$n --analyst-profile generalize_v1; stage searchqa-active-le$n --seed 202610$n
  fi
done
SKILLS="--skill empty=none --skill bzero=f:$Z/skill.md"
k=0
for n in 28 29 30 31 32 33 34 35; do
  a=$P-searchqa-active-le$n; b=$P-searchqa-active-lp$n
  if completed $a && completed $b; then
    if [ $((n % 2)) -eq 0 ]; then SKILLS="$SKILLS --skill le$n=g:$a --skill lp$n=g:$b"; else SKILLS="$SKILLS --skill lp$n=g:$b --skill le$n=g:$a"; fi
    k=$((k+1))
  else echo "$(date -Iseconds) LOST PAIR seed 202610$n (a stage did not complete)"; fi
done
echo "$(date -Iseconds) frozen arms: empty, bzero, $k complete new pairs of 8 (primary conclusions need at least six)"
if [ $k -lt 4 ]; then halt "fewer than four complete new pairs: no evaluation"; fi
missing=0
for b in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  done_block=0
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-c1-s$b$attempt
    quiet 12 || halt "no fresh quiet connectivity probe before eval c1-s$b$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --benchmark searchqa --items /root/searchqa-fresh-20261012/block_s$b/items.json --revision $REV $SKILLS --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval c1-s$b$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval c1-s$b$attempt end"
      if [ $rc -eq 0 ]; then done_block=1; break; fi
      if [ $rc -ne 3 ]; then halt "eval c1-s$b$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval c1-s$b$attempt): sealed pending result"
    else
      halt "eval c1-s$b$attempt could not be prepared: see $e.prepare.log"
    fi
  done
  if [ $done_block -eq 0 ]; then missing=$((missing+1)); fi
done
echo "$(date -Iseconds) Z5-EXIT (blocks without a completed run: $missing of 30)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
