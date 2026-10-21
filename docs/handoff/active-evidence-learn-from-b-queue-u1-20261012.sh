#!/usr/bin/env bash
# 10/12 queue u1: learn-from-B study, phase 1 (SearchQA, evaluated on FRESH tasks).
# Design contract: docs/handoff/active-evidence-learn-from-b-design-20261012.md (snapshot 20261012-l = k + three new
# scripts; stage tool and active_evidence package unchanged). Steps, one at a time on the shared lock:
#   1. bzero   ONE reflection call: the zero-shot initial Skill from the public task card (frozen before any solve).
#   2. 15 learning stages, arms scalar / none (one pass/fail step adopted without selection), seeds 20261021-25,
#      parents: empty (le), the hand-written generic text (lh), bzero (lz) -- same training rows per seed.
#   3. two evaluation runs (block A halves A1, A2; 500 fresh tasks each): empty, bhand, bzero, the completed learned
#      Skills and the two validation-gated methods' SearchQA Skills, interleaved. The list of surviving arms is
#      frozen once and used for both halves; a pending stage is a lost history (reported, never resumed or replaced).
# Every outcome is kept and reported. A STOP is left for operator review; nothing is resumed. NO test cell.
PY=/root/continual-alf-prep-20260928/env/bin/python
L=/root/fivebench-g-20261012-source-l
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261012
Z=$P-searchqa-bzero2
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a --benchmark searchqa"
STAGE="--method active_evidence --learning-version v11 $COMMON --arm-feedback scalar --arm-post-update none"
# the Linux proxy is activated in the same shell that launches the actual client
online() { (cd $L && export PYTHONPATH=$L && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $L && PYTHONPATH=$L $PY "$@"); }
stage() {
  s=$1; shift
  if offline scripts/run_fivebench_g_stage.py prepare $STAGE "$@" --output $P-$s > $P-$s.prepare.log 2>&1; then
    echo "$(date -Iseconds) stage $s start"
    G_SOURCE_ROOT=$L G_SKIP_TEST=1 bash $L/scripts/run_fivebench_active_evidence_linux.sh $P-$s || echo "$(date -Iseconds) STOP (stage $s)"
    echo "$(date -Iseconds) stage $s end"
  else
    echo "$(date -Iseconds) NOT PREPARED (stage $s): see $P-$s.prepare.log"
  fi
}
echo "$(date -Iseconds) bzero start"
online scripts/generate_zero_shot_skill.py run --output $Z >> $Z.run.log 2>&1
# the Skill is consumed only from a COMPLETED generation record whose hash matches the file
if offline scripts/generate_zero_shot_skill.py check --output $Z >> $Z.run.log 2>&1; then
  echo "$(date -Iseconds) bzero end ($(wc -c < $Z/skill.md) bytes, sha256 $(sha256sum $Z/skill.md | cut -c1-16))"
else
  echo "$(date -Iseconds) STOP (bzero): see $Z.run.log"; echo "$(date -Iseconds) U1-EXIT"; exit 1
fi
for n in 21 22 23 24 25; do
  stage searchqa-active-le$n --seed 202610$n --parent none
  stage searchqa-active-lh$n --seed 202610$n --parent f:$C/generic.md
  stage searchqa-active-lz$n --seed 202610$n --parent f:$Z/skill.md
done
SKILLS="--skill empty=none --skill bhand=f:$C/generic.md --skill bzero=f:$Z/skill.md"
for g in le lh lz; do for n in 21 22 23 24 25; do
  d=$P-searchqa-active-$g$n
  if test -f $d/learned.json && grep -q '"status": "completed"' $d/learned.json; then
    SKILLS="$SKILLS --skill $g$n=g:$d"
  else
    echo "$(date -Iseconds) LOST HISTORY $g$n (not completed): left out of the evaluation"
  fi
done; done
SKILLS="$SKILLS --skill old_v10=g:/root/fivebench-g-20261006-searchqa-chain-rubric_research-e --skill old_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"
for h in a1 a2; do
  e=$P-searchqa-paneleval-$h
  if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --items /root/searchqa-fresh-20261012/block_$h/items.json --revision c1a979068ba118d85467179b704031d113d689cc $SKILLS --chunk 25 --output $e > $e.prepare.log 2>&1; then
    echo "$(date -Iseconds) eval $h start"
    online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1 || echo "$(date -Iseconds) STOP (eval $h): see $e.run.log"
    echo "$(date -Iseconds) eval $h end"
  else
    echo "$(date -Iseconds) NOT PREPARED (eval $h): see $e.prepare.log"
  fi
done
echo "$(date -Iseconds) U1-EXIT"
