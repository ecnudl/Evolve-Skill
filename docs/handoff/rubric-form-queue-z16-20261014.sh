#!/usr/bin/env bash
# 10/14 night, queue z16: the rubric-form study (fivebench-rubric-form-study-v1) on SearchQA -- six matched blocks,
# template stage searchqa-v10gen-b06 (parent = zero-shot instruction, selection = its 168 generated tasks). Design and
# pre-registered reading rules: docs/handoff/rubric-form-study-design-20261014.md. Snapshot 20261014-z2 (= z + per-benchmark budgets and the tightened SearchQA checks; the OfficeQA study keeps snapshot z).
# Order: after queue z15 (the OfficeQA study) exits. Before running it sets the LiveMath queue's yield file (z9c waits BETWEEN its
# blocks; nothing begun is interrupted) and removes it afterwards, whatever the outcome. Waits for z16.go
# (operator, after the review). A study that stops is pending and never resumed.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261014-source-z2
P=/root/fivebench-g-20261014
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
T=/root/fivebench-g-20261013-searchqa-v10gen-b06
OUT=$P-searchqa-rubric-form-a
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
halt() { rm -f $D/z9c.yield; echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z16-EXIT"; exit 1; }
while ! test -f $D/z16.go; do sleep 20; done
while ! grep -q "Z15-EXIT" /root/fivebench-g-20261014-active-z15.log 2>/dev/null; do sleep 30; done
touch $D/z9c.yield  # the LiveMath queue pauses between blocks from now on
test -e $OUT && halt "$(basename $OUT) exists already: the study is prepared and run once"
offline scripts/run_rubric_form_study.py prepare --template $T --output $OUT --blocks 6 > $OUT.prepare.log 2>&1 || halt "not prepared: see $OUT.prepare.log"
quiet 12 || halt "no fresh quiet connectivity probe; prepared, not begun"
echo "$(date -Iseconds) rubric-form study start"
online scripts/run_rubric_form_study.py run --template $T --output $OUT >> $OUT.run.log 2>&1; rc=$?
echo "$(date -Iseconds) rubric-form study end (exit $rc)"
offline scripts/run_rubric_form_study.py report --output $OUT > $OUT.report.txt 2>&1 || echo "$(date -Iseconds) REPORT FAILED: read the sealed records by hand"
rm -f $D/z9c.yield  # the LiveMath queue may take its next block
echo "$(date -Iseconds) Z16-EXIT (study exit $rc)"
exit $rc
