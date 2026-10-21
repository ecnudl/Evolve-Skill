#!/usr/bin/env bash
# 10/14 night, queue z17: the rubric-form study (fivebench-rubric-form-study-v1) as ONE-BLOCK studies run in
# series, pooled by block afterwards (docs/handoff/rubric-form-series-reader-20261014.py). Why: the frozen recovery
# policy caps unknown-cost attempts (retried HTTP attempts without usage) at 64 per ledger; at tonight's retry rate
# (2-5%) a six-block study exceeds it (the OfficeQA study stopped pending in its block 1; the SearchQA study stopped
# in block 0 on a judge call that failed its three attempts). Each one-block study is a complete sealed study with
# its own series label (a different block plan); a study that ends pending is kept and never resumed -- the series
# simply continues with the next label until the wanted number of completed blocks exists or the attempts are
# used up. Order: OfficeQA first (five more blocks beside block 0 of the six-block study), then SearchQA. Sets the
# LiveMath queue's yield file while running and removes it at the end. Waits for z17.go. Snapshot 20261014-z3.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261014-source-z3
P=/root/fivebench-g-20261014
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
online() { (cd $V && export PYTHONPATH=$V && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $V && PYTHONPATH=$V $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
finish() { rm -f $D/z9c.yield; echo "$(date -Iseconds) Z17-EXIT ($1)"; exit ${2:-0}; }
series() {  # series <benchmark> <template stage> <wanted completed blocks> <max attempts> <labels...>
  bench=$1; template=$2; wanted=$3; attempts=$4; shift 4
  done_blocks=0; tried=0
  for label in "$@"; do
    [ $done_blocks -ge $wanted ] && break
    [ $tried -ge $attempts ] && break
    tried=$((tried+1))
    out=$P-$bench-rubric-form-$label
    if test -e $out; then echo "$(date -Iseconds) $(basename $out) exists: skipped"; continue; fi
    offline scripts/run_rubric_form_study.py prepare --template $template --output $out --blocks 1 --series $label > $out.prepare.log 2>&1 || { echo "$(date -Iseconds) $(basename $out) not prepared: see $out.prepare.log"; continue; }
    quiet 12 || finish "no fresh quiet connectivity probe before $(basename $out); prepared, not begun" 1
    echo "$(date -Iseconds) study $(basename $out) start"
    online scripts/run_rubric_form_study.py run --template $template --output $out >> $out.run.log 2>&1; rc=$?
    echo "$(date -Iseconds) study $(basename $out) end (exit $rc)"
    offline scripts/run_rubric_form_study.py report --output $out > $out.report.txt 2>&1 || echo "$(date -Iseconds) REPORT FAILED ($(basename $out))"
    if [ $rc -eq 0 ]; then done_blocks=$((done_blocks+1)); else echo "$(date -Iseconds) $(basename $out) pending (kept, never resumed): $(grep -o '"reason": "[^"]*"' $out/study/result.json | head -n 1)"; fi
  done
  echo "$(date -Iseconds) series $bench: $done_blocks completed one-block studies in $tried attempts"
}
while ! test -f $D/z17.go; do sleep 20; done
touch $D/z9c.yield
series officeqa $P-officeqa-oq-v10-z41-gv 5 8 b c d e f g h i
series searchqa /root/fivebench-g-20261013-searchqa-v10gen-b06 6 9 b c d e f g h i j
finish "series done"
