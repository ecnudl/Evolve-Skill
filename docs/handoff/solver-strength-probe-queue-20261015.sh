#!/usr/bin/env bash
# 10/15 solver-strength probe (evaluation only; scripts/weak_solver_probe.py; owner's request of 10/15: "weaker solver").
# Owner's choices were unavailable: the free router refuses non-agent requests (HTTP 456 session_id_required, not
# circumvented); glm-5.1 and glm-4.5-air have no resource package on the BigModel key (code 1113). Substitutes on the
# same BigModel key and endpoint: glm-5.3-flash (mildly weaker), glm-4.7-flash (thinking, free tier, slow),
# glm-4-flash-250414 (no thinking, weakest); glm-5.3 at the stages' setting (reasoning low) is the reference and runs
# under F's native lock. Same items and Skills for every model, two runs each:
#   OfficeQA: 124 generated items (oq-v10-z41-gv selection set) + 74 real train/val items (pilot-a), Skills empty,
#             zero-shot instruction, the gv stage's step-1 and step-2 candidates;
#   SearchQA: 168 generated items (v10gen-b06 selection set), Skills empty, zero-shot instruction, SkillOpt v9's
#             learned Skill, the b06 stage's step-1 candidate.
# Usage: bash queue.sh <model> <workers> [lock]   (one tmux session per model)
PY=/root/continual-alf-prep-20260928/env/bin/python
V=/root/fivebench-g-20261015-source-z4
T=/root/fivebench-g-20261015-probe-tools/scripts/weak_solver_probe.py
R=/root/continual-noskill-bcb-20260928-a
K=/root/fivebench-g-20261015-probe-skills
O=/root/fivebench-g-20261015-probe
LOCK=/root/continual-baselines-long-20261001-study/native.lock
model=$1; workers=$2; lockarg=""
[ "$3" = "lock" ] && lockarg="--lock $LOCK"
OQ="--items /root/fivebench-g-20261014-officeqa-oq-v10-z41-gv/panel.json:skill_confirmation --items /root/fivebench-g-20261013-officeqa-pilot-a/items.json --skill empty=none --skill bzero=f:$K/oq_bzero.md --skill oq_s1=f:$K/oq_s1.md --skill oq_s2=f:$K/oq_s2.md"
QA="--items /root/fivebench-g-20261013-searchqa-v10gen-b06/panel.json:skill_confirmation --skill empty=none --skill bzero=f:$K/qa_bzero.md --skill qa_v9=f:$K/qa_v9.md --skill qa_s1=f:$K/qa_s1.md"
for bench in officeqa searchqa; do
  args=$OQ; [ $bench = searchqa ] && args=$QA
  out=$O-$bench-$model
  if test -e $out; then echo "$(date -Iseconds) $out exists: skipped"; continue; fi
  echo "$(date -Iseconds) probe $model $bench start"
  (cd $V && PYTHONPATH=$V $PY $T run --model $model --benchmark $bench --repo $R $args --runs 2 --workers $workers $lockarg --output $out) >> $out.log 2>&1
  echo "$(date -Iseconds) probe $model $bench end (exit $?)"
done
echo "$(date -Iseconds) PROBE-EXIT $model"
