#!/usr/bin/env bash
# 10/15 early morning, queue z18: the verification-note binding study (fivebench-rubric-binding-study-v1; design
# docs/handoff/rubric-binding-study-design-20261015.md) as ONE-BLOCK studies run in series and pooled by block
# afterwards (docs/handoff/rubric-form-series-reader-20261014.py, which reads both protocols) -- the same shape as
# queue z17, for the same reason (the frozen recovery policy's cap of 64 unknown-cost attempts per ledger). Order:
# OfficeQA (template oq-v10-z41-gv, wanted 6 blocks, at most 8 attempts), then SearchQA (template
# searchqa-v10gen-b06, wanted 6, at most 9). Waits for z18.go and for queue z17 to exit (Z17-EXIT). Holds the
# LiveMath queue z9d at its between-block yield point while running (z9d.yield is created at launch so that z9d,
# which also waits for Z17-EXIT, begins nothing; it is removed at the end). Snapshot 20261015-z4.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261015-source-z4
P=/root/fivebench-g-20261015
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
finish() { rm -f $D/z9d.yield; echo "$(date -Iseconds) Z18-EXIT ($1)"; exit ${2:-0}; }
series() {  # series <benchmark> <template stage> <wanted completed blocks> <max attempts> <labels...>
  bench=$1; template=$2; wanted=$3; attempts=$4; shift 4
  done_blocks=0; tried=0
  for label in "$@"; do
    [ $done_blocks -ge $wanted ] && break
    [ $tried -ge $attempts ] && break
    tried=$((tried+1))
    out=$P-$bench-rubric-binding-$label
    if test -e $out; then echo "$(date -Iseconds) $(basename $out) exists: skipped"; continue; fi
    offline scripts/run_rubric_binding_study.py prepare --template $template --output $out --blocks 1 --series $label > $out.prepare.log 2>&1 || { echo "$(date -Iseconds) $(basename $out) not prepared: see $out.prepare.log"; continue; }
    quiet 12 || finish "no fresh quiet connectivity probe before $(basename $out); prepared, not begun" 1
    echo "$(date -Iseconds) study $(basename $out) start"
    online scripts/run_rubric_binding_study.py run --template $template --output $out >> $out.run.log 2>&1; rc=$?
    echo "$(date -Iseconds) study $(basename $out) end (exit $rc)"
    offline scripts/run_rubric_binding_study.py report --output $out > $out.report.txt 2>&1 || echo "$(date -Iseconds) REPORT FAILED ($(basename $out))"
    if [ $rc -eq 0 ]; then done_blocks=$((done_blocks+1)); else echo "$(date -Iseconds) $(basename $out) pending (kept, never resumed): $(grep -o '"reason": "[^"]*"' $out/study/result.json | head -n 1)"; fi
  done
  echo "$(date -Iseconds) series $bench: $done_blocks completed one-block studies in $tried attempts"
}
touch $D/z9d.yield
while ! test -f $D/z18.go; do sleep 20; done
while ! grep -q "Z17-EXIT" /root/fivebench-g-20261014-active-z17.log 2>/dev/null; do sleep 30; done
series officeqa /root/fivebench-g-20261014-officeqa-oq-v10-z41-gv 6 8 a b c d e f g h
series searchqa /root/fivebench-g-20261013-searchqa-v10gen-b06 6 9 a b c d e f g h i
finish "series done"
