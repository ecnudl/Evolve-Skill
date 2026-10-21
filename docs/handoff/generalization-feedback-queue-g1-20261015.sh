#!/usr/bin/env bash
# 10/15 queue g1: the generalization feedback study on OfficeQA with GLM-5.3 (owner approved 10/15; design
# docs/handoff/generalization-architecture-20261015.md). Steps: L/H split (zero calls) -> generator v2 on L (with
# source questions) and on H (page-only) (~250 calls) -> pools (zero calls) -> calibration probes of the parent, 3 runs on each
# pool (glm-5.3 at the stages' setting, F's native lock) -> registered go/no-go -> one-block studies in series
# (wanted 6, at most 8 attempts; pending studies kept, never resumed) -> pooled report. Snapshot 20261015-z5.
# Waits for g1.go. Writes G1-EXIT.
PY=/root/continual-alf-prep-20260928/env/bin/python
V=$1
MODE=$2
test -d "$V" && { [ "$MODE" = prep ] || [ "$MODE" = series ]; } || { echo "usage: g1.sh <snapshot> prep|series"; exit 2; }
P=/root/fivebench-g-20261015-genfb
D=/root/fivebench-g-20261013-queue-z1
TPL=/root/fivebench-g-20261014-officeqa-oq-v10-z41-gv
X=/root/extension-20261013
R=/root/continual-noskill-bcb-20260928-a
PARENT=/root/fivebench-g-20261013-officeqa-bzero/skill.md
LOCK=/root/continual-baselines-long-20261001-study/native.lock
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
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) G1-EXIT"; exit 1; }
while ! test -f $D/g1.go; do sleep 20; done
echo "$(date -Iseconds) g1 $MODE start (snapshot $V)"
# 1 split
test -e $P-split.json || offline scripts/run_generalization_feedback_study.py split --template $TPL --held-out 16 --output $P-split.json > $P-split.log 2>&1 || halt "split failed: see $P-split.log"
# 2 generator v2 on each side of the split (the template's training draw: seed 20261041): L with source questions
#   (diagnostic items), H page-only (transfer items; no held-out question in any prompt)
for side in d:generate_officeqa_diagnostic_tasks t:generate_officeqa_transfer_tasks; do
  name=${side%%:*}; tool=scripts/${side#*:}.py; out=$P-gen-$name
  if ! test -e $out/result.json; then
    test -e $out || offline $tool prepare --study $X/study-officeqa --split $X/split-officeqa.json --repo $R --seed 20261041 --lh-split $P-split.json --output $out > $out.prepare.log 2>&1 || halt "generation $name not prepared: see $out.prepare.log"
    quiet 12 || halt "no quiet connectivity probe before generation $name"
    echo "$(date -Iseconds) generation $name start"
    online $tool run --output $out >> $out.run.log 2>&1
    echo "$(date -Iseconds) generation $name end"
  fi
  offline $tool check --output $out > /dev/null 2>&1 || halt "no completed generation $name: see $out.run.log"
done
# 3 pools
test -e $P-pools || offline scripts/run_generalization_feedback_study.py pools --template $TPL --split $P-split.json --generation-d $P-gen-d --generation-t $P-gen-t --output $P-pools > $P-pools.log 2>&1 || halt "pools failed: see $P-pools.log"
cat $P-pools.log
# 4 calibration: the parent, three runs on each pool, glm-5.3 low under the native lock
for pool in D:development T:skill_confirmation; do
  name=${pool%%:*}; part=${pool#*:}; out=$P-cal-$name
  if test -e $out/summary.json; then continue; fi
  test -e $out && halt "calibration $name exists without a summary: not reused"
  echo "$(date -Iseconds) calibration $name start"
  offline scripts/weak_solver_probe.py run --model glm-5.3 --benchmark officeqa --repo $R --items $P-pools/pool-$name.json:$part --skill parent=f:$PARENT --runs 3 --workers 8 --lock $LOCK --output $out > $out.log 2>&1 || halt "calibration $name failed: see $out.log"
  echo "$(date -Iseconds) calibration $name end"
done
if [ "$MODE" = prep ]; then echo "$(date -Iseconds) G1-PREP-EXIT (data steps done)"; exit 0; fi
# 5 series of one-block studies (every attempted study with a result is reported: completed blocks pooled, pending
#   ones with their reasons and costs)
done_blocks=0; tried=0; dirs=""
for label in a b c d e f g h; do
  [ $done_blocks -ge 6 ] && break
  [ $tried -ge 8 ] && break
  tried=$((tried+1))
  out=$P-study-$label
  if test -e $out; then echo "$(date -Iseconds) $(basename $out) exists: skipped"; continue; fi
  offline scripts/run_generalization_feedback_study.py prepare --template $TPL --pools $P-pools --calibration $P-cal-D $P-cal-T --output $out --blocks 1 --series $label > $out.prepare.log 2>&1; rc=$?
  if [ $rc -eq 2 ]; then cat $out.prepare.log; halt "registered go/no-go not met: the study is not run"; fi
  [ $rc -eq 0 ] || halt "$(basename $out) not prepared: see $out.prepare.log"
  quiet 12 || halt "no quiet connectivity probe before $(basename $out); prepared, not begun"
  echo "$(date -Iseconds) study $(basename $out) start"
  online scripts/run_generalization_feedback_study.py run --template $TPL --output $out >> $out.run.log 2>&1; rc=$?
  echo "$(date -Iseconds) study $(basename $out) end (exit $rc)"
  test -e $out/study/result.json && dirs="$dirs $out"
  if [ $rc -eq 0 ]; then done_blocks=$((done_blocks+1)); else echo "$(date -Iseconds) $(basename $out) pending (kept, never resumed): $(grep -o '"reason": "[^"]*"' $out/study/result.json 2>/dev/null | head -n 1)"; fi
done
echo "$(date -Iseconds) series: $done_blocks completed one-block studies in $tried attempts"
if [ -n "$dirs" ]; then
  offline scripts/run_generalization_feedback_study.py report --output $dirs > $P-series.report.txt 2>&1 || echo "$(date -Iseconds) REPORT FAILED: see $P-series.report.txt"
fi
echo "$(date -Iseconds) G1-EXIT (series done)"
