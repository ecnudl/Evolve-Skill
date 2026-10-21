#!/usr/bin/env bash
# 10/12 queue u2: learn-from-B study, phase 1, after the amendment of 14:30 (design memo section 9).
# Runs after queue u1 has exited (u1's evaluation phase was disabled before it began). Steps, one at a time:
#   1. more learning stages (arms scalar / none, seeds 26..36 in order) for every parent that has fewer than five
#      COMPLETED histories -- decided by the completed / pending status only;
#   2. the arm list is frozen once: empty, bhand, bzero, the first five completed histories of each parent in seed
#      order, old_v10, old_v9;
#   3. ten evaluation runs of 100 fresh tasks (block A01..A10), --chunk 10, with the evaluation tool of snapshot m
#      (= l + the connectivity gate). A run that ends pending is repeated ONCE in a new directory (-r1).
# Before each paid step the queue waits for a quiet stretch of the external connectivity probe.
# Every outcome is kept and reported. A STOP is left for operator review; nothing is resumed. NO test cell.
PY=/root/continual-alf-prep-20260928/env/bin/python
L=/root/fivebench-g-20261012-source-l
M=/root/fivebench-g-20261012-source-m
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261012
Z=$P-searchqa-bzero2
PROBE=/root/net-probe-20261012c.log  # written by: connectivity_probe.py log (snapshot m), epoch-stamped
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a --benchmark searchqa"
STAGE="--method active_evidence --learning-version v11 $COMMON --arm-feedback scalar --arm-post-update none"
online() { src=$1; shift; (cd $src && export PYTHONPATH=$src && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { src=$1; shift; (cd $src && PYTHONPATH=$src $PY "$@"); }
quiet() {  # 0 once the probe log is quiet: the last $1 probes (one every 10 s) all ok, strictly advancing and fresh
           # (scripts/connectivity_probe.py quiet); 1 when that has not happened within $2 seconds (default four hours)
  waited=0
  while ! offline $M scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-14400}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) U2-EXIT"; exit 1; }
completed() {  # number of completed histories of parent group $1
  c=0
  for d in $P-searchqa-active-$1??; do
    if test -f $d/learned.json && grep -q '"status": "completed"' $d/learned.json; then c=$((c+1)); fi
  done
  echo $c
}
stage() {
  s=$1; shift
  quiet 12 || halt "no fresh quiet connectivity probe before stage $s; nothing was prepared or begun"
  if offline $L scripts/run_fivebench_g_stage.py prepare $STAGE "$@" --output $P-$s > $P-$s.prepare.log 2>&1; then
    echo "$(date -Iseconds) stage $s start"
    G_SOURCE_ROOT=$L G_SKIP_TEST=1 bash $L/scripts/run_fivebench_active_evidence_linux.sh $P-$s || echo "$(date -Iseconds) STOP (stage $s)"
    echo "$(date -Iseconds) stage $s end"
  else
    echo "$(date -Iseconds) NOT PREPARED (stage $s): see $P-$s.prepare.log"
  fi
}
while ! grep -q "U1-EXIT" $P-active-u1.log; do sleep 30; done
echo "$(date -Iseconds) u1 has exited; completed histories: le $(completed le), lh $(completed lh), lz $(completed lz)"
if ! offline $L scripts/generate_zero_shot_skill.py check --output $Z > /dev/null 2>&1; then
  echo "$(date -Iseconds) STOP (bzero is not a completed generation)"; echo "$(date -Iseconds) U2-EXIT"; exit 1
fi
for n in 26 27 28 29 30 31 32 33 34 35 36; do
  if [ "$(completed le)" -lt 5 ]; then stage searchqa-active-le$n --seed 202610$n --parent none; fi
  if [ "$(completed lh)" -lt 5 ]; then stage searchqa-active-lh$n --seed 202610$n --parent f:$C/generic.md; fi
  if [ "$(completed lz)" -lt 5 ]; then stage searchqa-active-lz$n --seed 202610$n --parent f:$Z/skill.md; fi
done
SKILLS="--skill empty=none --skill bhand=f:$C/generic.md --skill bzero=f:$Z/skill.md"
for g in le lh lz; do
  k=0
  for d in $(ls -d $P-searchqa-active-$g?? | sort); do
    if [ $k -lt 5 ] && test -f $d/learned.json && grep -q '"status": "completed"' $d/learned.json; then
      SKILLS="$SKILLS --skill $g${d: -2}=g:$d"; k=$((k+1))
    fi
  done
  echo "$(date -Iseconds) frozen group $g: $k completed histories"
done
SKILLS="$SKILLS --skill old_v10=g:/root/fivebench-g-20261006-searchqa-chain-rubric_research-e --skill old_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"
echo "$(date -Iseconds) frozen arms: $(echo $SKILLS | tr ' ' '\n' | grep -c =)"
for b in 01 02 03 04 05 06 07 08 09 10; do
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-a$b$attempt
    quiet 30 || halt "no fresh quiet connectivity probe before eval a$b$attempt; nothing was prepared or begun"
    if offline $M scripts/run_active_evidence_panel_eval.py prepare $COMMON --items /root/searchqa-fresh-20261012/block_a$b/items.json --revision c1a979068ba118d85467179b704031d113d689cc $SKILLS --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval a$b$attempt start"
      online $M scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      # what the run left behind decides: 0 completed, 3 a sealed PENDING result bound to this directory (the only
      # state after which the block is repeated once, in a new directory), anything else stops the queue
      offline $M scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval a$b$attempt end"
      if [ $rc -eq 0 ]; then break; fi
      if [ $rc -ne 3 ]; then halt "eval a$b$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval a$b$attempt): sealed pending result, see $e.run.log"
    else
      halt "eval a$b$attempt could not be prepared: see $e.prepare.log"
    fi
  done
done
echo "$(date -Iseconds) U2-EXIT"
