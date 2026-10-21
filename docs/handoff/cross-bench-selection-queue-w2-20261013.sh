#!/usr/bin/env bash
# 10/13 queue w2: repetitions of cross-benchmark runs that ended pending (each run is repeated ONCE, in a new
# directory, after a sealed pending result; a second pending result leaves that direction without a result).
# Waits for queue w1 to exit. Same design, snapshot and inputs as w1:
# 10/13 queue w1: SkillOpt with training tasks from one benchmark and the validation gate on another.
# Design contract: docs/handoff/cross-bench-selection-design-20261013.md. Snapshot 20261013-o. Both runs were
# prepared by hand (zero calls) from two prepared, never begun v9 skillopt stages of seed 20261006.
#   cross-qa-bcb   train SearchQA, gate on BigCodeBench validation
#   cross-bcb-qa   train BigCodeBench, gate on SearchQA validation
# Each run starts only after about ten quiet minutes of the TLS-level probe. Every outcome is kept and reported.
# A STOP is left for operator review; nothing is resumed. Development and validation partitions only; NO test data.
PY=/root/continual-alf-prep-20260928/env/bin/python
O=/root/fivebench-g-20261013-source-o
P=/root/fivebench-g-20261013
PROBE=/root/net-probe-20261012d.log
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
while ! grep -q "W1-EXIT" $P-active-w1.log; do sleep 30; done
for x in qa-bcb bcb-qa; do
  first=$P-cross-$x
  if ! (test -f $first/result.json && grep -q '"status": "pending"' $first/result.json); then continue; fi
  REF="--reference same_qa=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"
  if [ $x = qa-bcb ]; then A=$P-searchqa-xstage-a; B=$P-bigcodebench-xstage-a; else A=$P-bigcodebench-xstage-a; B=$P-searchqa-xstage-a; fi
  x=$x-r1
  if ! offline scripts/run_cross_bench_selection.py prepare --train-stage $A --selection-stage $B $REF --output $P-cross-$x > $P-cross-$x.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED (cross-$x)"; continue; fi
  if ! quiet 60; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before cross-$x)"; break; fi
  echo "$(date -Iseconds) cross-$x start"
  online scripts/run_cross_bench_selection.py run --output $P-cross-$x >> $P-cross-$x.run.log 2>&1 || echo "$(date -Iseconds) STOP (cross-$x): see $P-cross-$x.run.log"
  echo "$(date -Iseconds) cross-$x end"
done
echo "$(date -Iseconds) W2-EXIT"
