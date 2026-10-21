#!/usr/bin/env bash
# Part of master queue z1 (10/13 03:00): repetitions of the cross-benchmark runs (design memo, execution note of
# 03:00). A direction is repeated after a sealed pending result, each time in a new directory, up to -r<N> where N is
# the first argument (1 in the first pass, 3 in the last pass of z1); a completed run ends its direction; a
# directory that was begun and has no result is left for operator review. cross-qa-bcb-r1 was prepared by queue
# w2 (never begun) and is run as prepared. A run starts after thirty consecutive successful probes (five minutes).
# Revised 03:10 after the Codex review of queue z1, before this part started: a directory's state is read from its
# SEALED records (result bound to cross.json by cross_hash, exact version and status), never from a text match; any
# other state halts the direction for operator review; the script's exit status aggregates both directions; the
# part waits for the release file w3.go (written by the operator after the confirmation review).
# Same design, snapshot and inputs as w1:
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
MAX=${1:-1}
D=/root/fivebench-g-20261013-queue-z1
REF="--reference same_qa=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"
while ! test -f $D/w3.go; do sleep 20; done
state() {  # state <dir>: absent | prepared | begun | pending | completed | invalid
  offline - "$1" <<'EOF'
import sys
from pathlib import Path
from skillopt.continual_eval.core import read_json
d = Path(sys.argv[1])
try:
    if not d.exists():
        print("absent")
    else:
        record = read_json(d / "cross.json", sealed=True)
        names = sorted(p.name for p in d.iterdir())
        if (d / "result.json").exists():
            result = read_json(d / "result.json", sealed=True)
            bound = (record.get("version") == "cross-bench-selection-v1" and result.get("version") == record["version"]
                     and result.get("cross_hash") == record["record_hash"])
            print(result["status"] if bound and result.get("status") in ("completed", "pending") else "invalid")
        elif (d / "started.json").exists():
            print("begun")
        else:
            print("prepared" if names == ["cross.json", "references.json"] else "invalid")
except Exception:
    print("invalid")
EOF
}
direction() {  # direction <qa-bcb|bcb-qa>: 0 a completed run exists, 1 pending within this pass's limit, 2 operator review
  x=$1
  if [ $x = qa-bcb ]; then A=$P-searchqa-xstage-a; B=$P-bigcodebench-xstage-a; else A=$P-bigcodebench-xstage-a; B=$P-searchqa-xstage-a; fi
  n=0
  for r in "" -r1 -r2 -r3; do
    d=$P-cross-$x$r
    s=$(state $d)
    case "$s" in
      completed) echo "$(date -Iseconds) cross-$x$r is completed"; return 0;;
      pending) n=$((n+1)); continue;;
      absent|prepared) ;;
      *) echo "$(date -Iseconds) STOP (cross-$x$r is in state '$s': operator review)"; return 2;;
    esac
    if [ $n -eq 0 ] || [ $n -gt $MAX ]; then echo "$(date -Iseconds) cross-$x: no further repetition in this pass ($n pending runs, limit -r$MAX)"; return 1; fi
    if [ "$s" = absent ]; then
      if ! offline scripts/run_cross_bench_selection.py prepare --train-stage $A --selection-stage $B $REF --output $d > $d.prepare.log 2>&1; then echo "$(date -Iseconds) NOT PREPARED (cross-$x$r): see $d.prepare.log"; return 2; fi
      s=$(state $d)
      if [ "$s" != prepared ]; then echo "$(date -Iseconds) STOP (cross-$x$r is in state '$s' after its preparation: operator review)"; return 2; fi
    fi
    if ! quiet 30; then echo "$(date -Iseconds) STOP (no fresh quiet connectivity probe before cross-$x$r; prepared, not begun)"; return 2; fi
    echo "$(date -Iseconds) cross-$x$r start"
    online scripts/run_cross_bench_selection.py run --output $d >> $d.run.log 2>&1; rc=$?
    echo "$(date -Iseconds) cross-$x$r end (tool exit $rc)"
    s=$(state $d)
    case "$s" in
      completed) return 0;;
      pending) echo "$(date -Iseconds) STOP (cross-$x$r): sealed pending result, see $d.run.log"; n=$((n+1));;
      *) echo "$(date -Iseconds) STOP (cross-$x$r was left in state '$s': operator review)"; return 2;;
    esac
  done
  return 1
}
direction qa-bcb; a=$?
direction bcb-qa; b=$?
echo "$(date -Iseconds) W3-EXIT (pass with limit -r$MAX; qa-bcb=$a bcb-qa=$b; 0 completed, 1 pending within the limit, 2 operator review)"
if [ $a -eq 2 ] || [ $b -eq 2 ]; then exit 2; fi
if [ $a -eq 1 ] || [ $b -eq 1 ]; then exit 1; fi
exit 0
