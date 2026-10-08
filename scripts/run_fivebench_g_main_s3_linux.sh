#!/usr/bin/env bash
# Paid main-method S3 replacement (10/8; Codex design round v7-1, CONSENSUS). Chain e's KOR-Bench stage (verifier v3,
# /root/fivebench-g-20261006-korbench-chain-rubric_research-e) went pending at step 0 with `verifier_call_failed`:
# two closed length truncations of the 4096-token verifier cap -- a delivery-budget/protocol-handling failure before
# any S3 candidate comparison or gate decision. It stays an interrupted record and is never resumed. This queue
# prepares a NEW KOR-Bench stage (chain tag G_CHAIN_TAG) from the same parent -- chain e's completed SearchQA stage,
# whose accepted Skill is the main method's S2 -- with the default KOR rubric (the parent hands on no KOR record),
# under snapshot G_SOURCE_ROOT (verifier v7: one length recovery, terminal unit delivery results), learns it and,
# if an update is accepted, tests it once on each of the three test panels (run_fivebench_g_chain_linux.sh's rule).
# Frozen before launch: this stage supplies S3 whatever its outcome (accepted update; completed without update =
# the S2 Skill's existing cells; pending = S3 missing) -- no further replacement. Every paid step takes F's native
# lock inside the tool. Success is written only after a verified completed stage with all required test cells.
set -uo pipefail
umask 077
export G_SOURCE_ROOT=${G_SOURCE_ROOT:?G_SOURCE_ROOT (tool snapshot) required}
tag=${G_CHAIN_TAG:?G_CHAIN_TAG required}
python_bin=/root/continual-alf-prep-20260928/env/bin/python
test_eval=/root/fivebench-test-eval-20261005-h
study=/root/continual-fivebench-20261003-f-study
split=/root/fivebench-split-20261005-v2/split_manifest.json
repo=/root/continual-noskill-bcb-20260928-a
parent=/root/fivebench-g-20261006-searchqa-chain-rubric_research-e
superseded=/root/fivebench-g-20261006-korbench-chain-rubric_research-e
val=/root/continual-kor-prep-20260928/prepared/panels/skill_confirmation.json
stage=/root/fivebench-g-20261006-korbench-chain-rubric_research-$tag
log=/root/fivebench-g-20261008-main-s3-$tag.log
cd "$G_SOURCE_ROOT"
export PYTHONPATH="$G_SOURCE_ROOT"
run() { bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_g_stage.py "$@"; }
stop() { echo "$(date -Iseconds) STOP (main S3 $tag): $*" >> "$log"; echo "$(date -Iseconds) MAIN-EXIT=1" >> "$log"; exit 1; }
# verified <dir>: zero-call, read-only check that the stage's three test cells exist and bind (sealed request = the
# tool's request for the deployed Skill, result/checkpoint bound to it, summary = its recomputation; Codex round 17)
verified() { "$python_bin" scripts/verify_fivebench_g_cells.py --stage "$1" --test-eval "$test_eval" >> "$log" 2>&1; }

case "$tag" in a|b|c|d|e|f|g) echo "chain tag $tag is used or reserved" >&2; exit 2;; esac
echo "$(date -Iseconds) main S3 ($tag) start from snapshot $G_SOURCE_ROOT; parent $parent; supersedes $superseded" \
  "(learned $("$python_bin" -c 'import json,sys; r=json.load(open(sys.argv[1]+"/learned.json")); print(r["status"], r["reason"], r["record_hash"])' "$superseded"))" >> "$log"
if [ -f "$stage/stage.json" ]; then
  "$python_bin" - "$stage" "$parent" >> "$log" 2>&1 <<'EOF' || stop "$stage exists but is not this S3 replacement"
import json, sys
r = json.load(open(sys.argv[1] + "/stage.json"))
ok = (r.get("method") == "rubric_research" and r["benchmark"] == "korbench" and r["parent"] == "g:" + sys.argv[2]
      and r.get("learning_version") == "continual-learning-v10")
print("stage record matches" if ok else "stage record mismatch")
sys.exit(0 if ok else 1)
EOF
else
  echo "$(date -Iseconds) prepare $stage (parent g:$parent)" >> "$log"
  run prepare --study "$study" --split "$split" --repo "$repo" --benchmark korbench --parent "g:$parent" \
    --val-source "$val" --method rubric_research --learning-version v10 --output "$stage" >> "$log" 2>&1 \
    || stop "prepare $stage failed"
fi
if [ ! -f "$stage/learned.json" ]; then
  echo "$(date -Iseconds) learn $stage" >> "$log"
  run learn --output "$stage" >> "$stage/run.log" 2>&1 || stop "$stage learning failed or pending (operator review)"
fi
"$python_bin" scripts/run_fivebench_g_stage.py status --output "$stage" >> "$log" 2>&1
state=$?
case "$state" in
  0)
    for b in searchqa bigcodebench korbench; do
      suffix=""; [ "$b" != korbench ] && suffix="-$b"
      [ -f "$stage/summary$suffix.json" ] && continue  # verified below with every other cell
      # a begun cell (request written, no summary) is never resubmitted by this queue: operator review
      [ -e "$stage/test-request$suffix.json" ] && stop "$stage has a begun, unfinished $b test cell (operator review)"
      echo "$(date -Iseconds) test $stage on $b" >> "$log"
      run test --output "$stage" --test-eval "$test_eval" --test-benchmark "$b" >> "$stage/run.log" 2>&1 \
        || stop "$stage test on $b failed"
    done
    verified "$stage" || stop "$stage test cells do not verify against their sealed evidence"
    echo "$(date -Iseconds) $stage accepted an update; its three test cells verify" >> "$log" ;;
  10)
    verified "$parent" || stop "the inherited S2 cells of $parent do not verify"
    echo "$(date -Iseconds) $stage deployed its parent (no accepted update); S3 = the S2 Skill's verified cells in $parent" >> "$log" ;;
  *) stop "$stage is not a verified completed stage (pending, unreadable or inconsistent); operator review" ;;
esac
echo "$(date -Iseconds) main S3 ($tag) complete" >> "$log"
echo "$(date -Iseconds) MAIN-EXIT=0" >> "$log"
