#!/usr/bin/env bash
# 10/14 night, queue z15: the rubric-form study (fivebench-rubric-form-study-v1) on OfficeQA -- six matched blocks,
# template stage oq-v10-z41-gv (parent = zero-shot instruction, selection = the 124 generated tasks). Design and
# pre-registered reading rules: docs/handoff/rubric-form-study-design-20261014.md. Snapshot 20261014-z.
# Order: after queue z14 exits. Before running it sets the LiveMath queue's yield file (z9c waits BETWEEN its
# blocks; nothing begun is interrupted) and removes it afterwards, whatever the outcome. Waits for z15.go
# (operator, after the review). A study that stops is pending and never resumed.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261014-source-z
P=/root/fivebench-g-20261014
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
T=$P-officeqa-oq-v10-z41-gv
OUT=$P-officeqa-rubric-form-a
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
halt() { rm -f $D/z9c.yield; echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z15-EXIT"; exit 1; }
while ! test -f $D/z15.go; do sleep 20; done
while ! grep -q "Z14-EXIT" /root/fivebench-g-20261014-active-z14.log 2>/dev/null; do sleep 30; done
touch $D/z9c.yield  # the LiveMath queue pauses between blocks from now on
test -e $OUT && halt "$(basename $OUT) exists already: the study is prepared and run once"
offline scripts/run_rubric_form_study.py prepare --template $T --output $OUT --blocks 6 > $OUT.prepare.log 2>&1 || halt "not prepared: see $OUT.prepare.log"
quiet 12 || halt "no fresh quiet connectivity probe; prepared, not begun"
echo "$(date -Iseconds) rubric-form study start"
online scripts/run_rubric_form_study.py run --template $T --output $OUT >> $OUT.run.log 2>&1; rc=$?
echo "$(date -Iseconds) rubric-form study end (exit $rc)"
offline scripts/run_rubric_form_study.py report --output $OUT > $OUT.report.txt 2>&1 || echo "$(date -Iseconds) REPORT FAILED: read the sealed records by hand"
rm -f $D/z9c.yield  # the LiveMath queue may take its next block
echo "$(date -Iseconds) Z15-EXIT (study exit $rc)"
exit $rc
