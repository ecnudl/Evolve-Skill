#!/usr/bin/env bash
# 10/14 queue z12: OfficeQA validation by GENERATED tasks (design and reading contract, written before any outcome:
# docs/handoff/officeqa-generated-validation-design-20261014.md). Snapshot 20261014-x = snapshot w + the OfficeQA
# generator, the benchmark hooks of the shared generator lifecycle and the stage tool's dispatch.
#   1. generation g41: questions written from the 48 training tasks a stage of seed 20261041 draws (public fields
#      only); reference answers computed in code from quoted figures; independent review call
#   2. only if the published tasks cover at least 30 families: three gated stages in new directories whose
#      selection set is the generated one -- the same seed, parents and arguments as the stages of queue z10
#      (oq-v9-z41, oq-v10-z41, oq-v9-e41) except for the validation source
# No evaluation and no test read. Every outcome is kept and reported; nothing that has begun is resumed; any stop
# (a generation or a stage that does not complete, a failed preparation, no quiet network) ends the queue.
# Waits for the release file z12.go (operator, after the review and the zero-call smoke).
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261014-source-x
P=/root/fivebench-g-20261014
X=/root/extension-20261013
D=/root/fivebench-g-20261013-queue-z1
PROBE=/root/net-probe-20261012d.log
WHERE="--study $X/study-officeqa --split $X/split-officeqa.json --repo /root/continual-noskill-bcb-20260928-a"
COMMON="$WHERE --benchmark officeqa"
BZERO=/root/fivebench-g-20261013-officeqa-bzero/skill.md
GEN=$P-officeqa-gen-g41
MIN_FAMILIES=30
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) Z12-EXIT"; exit 1; }
stage() {  # stage <name> <prepare arguments...>: one prepared-and-run learning stage, never resumed.
  # Anything but a completed stage (with or without an accepted update) halts the queue for operator review:
  # the stage tool's learn exits 3 for a pending result, its status 0 / 10 for the two completed outcomes.
  d=$P-officeqa-$1; shift
  offline scripts/run_fivebench_g_stage.py prepare $COMMON "$@" --output $d > $d.prepare.log 2>&1 || halt "stage $(basename $d) not prepared: see $d.prepare.log"
  quiet 12 || halt "no fresh quiet connectivity probe before $(basename $d); prepared, not begun"
  echo "$(date -Iseconds) stage $(basename $d) start"
  online scripts/run_fivebench_g_stage.py learn --output $d >> $d.run.log 2>&1; learned=$?
  offline scripts/run_fivebench_g_stage.py status --output $d >> $d.run.log 2>&1; state=$?
  echo "$(date -Iseconds) stage $(basename $d) end (learn exit $learned, status exit $state)"
  if [ "$learned" -ne 0 ] || { [ "$state" -ne 0 ] && [ "$state" -ne 10 ]; }; then
    halt "stage $(basename $d) did not complete (learn exit $learned, status exit $state): operator review, the queue does not advance; see $d.run.log"
  fi
}
while ! test -f $D/z12.go; do sleep 20; done
test -f $BZERO || halt "the zero-shot instruction of the headroom pilot does not exist"
test -e $GEN && halt "the generation directory exists already: a generation is made once"
offline scripts/generate_officeqa_tasks.py prepare $WHERE --seed 20261041 --output $GEN > $GEN.prepare.log 2>&1 || halt "generation not prepared: see $GEN.prepare.log"
quiet 12 || halt "no fresh quiet connectivity probe before the generation; prepared, not begun"
echo "$(date -Iseconds) generation $(basename $GEN) start"
online scripts/generate_officeqa_tasks.py run --output $GEN >> $GEN.run.log 2>&1; generated=$?
echo "$(date -Iseconds) generation $(basename $GEN) end (exit $generated)"
[ "$generated" -eq 0 ] || halt "the generation did not complete (exit $generated): see $GEN.run.log and $GEN/result.json; not repeated here"
offline scripts/generate_officeqa_tasks.py check --output $GEN >> $GEN.run.log 2>&1 || halt "the generation did not complete: see $GEN.run.log and $GEN/result.json; not repeated here"
FAMILIES=$(cd $V && PYTHONPATH=$V $PY -c "import sys; from scripts import generate_officeqa_tasks as g; print(len(set(g.family_map(sys.argv[1]).values())))" $GEN 2>> $GEN.run.log)
echo "$(date -Iseconds) generation published tasks in ${FAMILIES:-?} families"
case "$FAMILIES" in ''|*[!0-9]*) halt "the number of families could not be read";; esac
[ "$FAMILIES" -ge "$MIN_FAMILIES" ] || halt "fewer than $MIN_FAMILIES families: by the design's rule no stage is run"
stage oq-v9-z41-gv --method skillopt --learning-version v9 --parent f:$BZERO --generated-val $GEN --seed 20261041
stage oq-v10-z41-gv --method rubric_research --learning-version v10 --parent f:$BZERO --generated-val $GEN --seed 20261041
stage oq-v9-e41-gv --method skillopt --learning-version v9 --parent none --generated-val $GEN --seed 20261041
echo "$(date -Iseconds) Z12-EXIT"
