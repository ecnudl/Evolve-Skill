#!/usr/bin/env bash
# Paid three-domain learning-v8 sequence on study F's frozen references (user request 10/6):
# BigCodeBench -> SearchQA -> KOR-Bench (F's order over the API-only domains; F's Sheet/ALF stages
# changed nothing), one method per invocation. Stage 1 is an already prepared or completed stage
# directory of that method; each later stage is prepared here from the previous stage's deployed
# Skill (`--parent g:<dir>`, a COMPLETED stage only), learned, and every stage whose learning
# accepted an update is tested once on each of the three test panels (a stage without an update
# deploys its parent, whose cells already exist). Every paid step takes F's native lock inside the
# tool. Any failure, pending outcome or inconsistent existing directory ends the chain (exit 1).
# Usage: run_fivebench_g_chain_linux.sh <method skillopt|gepa|rubric_research> <stage-1 dir> <chain tag>
# rubric_research (the main method: Rubric -> probe -> Research verifier feedback, learning v10) requires
# G_LEARNING_VERSION=v10 and vice versa.
set -uo pipefail
umask 077
method=${1:?method}; first=${2:?prepared or completed stage-1 directory}; tag=${3:?chain tag}
case "$method" in skillopt|gepa|rubric_research) ;; *) echo "unknown method $method" >&2; exit 2;; esac
source_root=${G_SOURCE_ROOT:?G_SOURCE_ROOT (tool snapshot) required}
python_bin=/root/continual-alf-prep-20260928/env/bin/python
test_eval=/root/fivebench-test-eval-20261005-h
study=/root/continual-fivebench-20261003-f-study
split=/root/fivebench-split-20261005-v2/split_manifest.json
repo=/root/continual-noskill-bcb-20260928-a
gepa_source=/root/continual-learning-env-20260928/gepa-source
log=/root/fivebench-g-20261006-chain-$method-$tag.log
declare -A val_source=(
  [searchqa]=/root/fivebench-split-20261005-source/data/searchqa_split/val/items.json
  [korbench]=/root/continual-kor-prep-20260928/prepared/panels/skill_confirmation.json
  [bigcodebench]=/root/continual-noskill-bcb-20260928-a/data/skill_confirmation.json
)
cd "$source_root"
export PYTHONPATH="$source_root"
[ "$method" = gepa ] && export PYTHONPATH="$source_root:$gepa_source/src"
# Learning protocol of the stages this chain prepares (stage 1 is prepared by the caller): v8, or v9
# (two-pass paired sign-test gate, 8192-token reflection cap) when G_LEARNING_VERSION=v9.
learning_version=${G_LEARNING_VERSION:-v8}
case "$learning_version" in v8|v9|v10) ;; *) echo "unknown learning version $learning_version" >&2; exit 2;; esac
if { [ "$method" = rubric_research ] && [ "$learning_version" != v10 ]; } \
   || { [ "$method" != rubric_research ] && [ "$learning_version" = v10 ]; }; then
  echo "rubric_research is learning v10 and vice versa (got $method / $learning_version)" >&2; exit 2
fi
extra=(--learning-version "$learning_version")
[ "$method" = gepa ] && extra+=(--method gepa --gepa-source "$gepa_source")
[ "$method" = rubric_research ] && extra+=(--method rubric_research)

run() {  # tool invocation with the Linux proxy active in the same shell
  bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- "$python_bin" scripts/run_fivebench_g_stage.py "$@"
}
stop() { echo "$(date -Iseconds) STOP ($method/$tag): $*" >> "$log"; exit 1; }
# check_stage <dir> <benchmark> <parent or -> <learning version or ->: the directory's record must be this
# method/domain/parent and, for stages this chain would prepare itself, the requested learning protocol
# (stage 1 may deliberately be an older stage, so its version is not constrained).
check_stage() {
  "$python_bin" - "$1" "$2" "$3" "$method" "$4" <<'EOF'
import json, sys
d, benchmark, parent, method, version = sys.argv[1:6]
r = json.load(open(d + "/stage.json"))
want = {"v8": "continual-learning-v8", "v9": "continual-learning-v9", "v10": "continual-learning-v10"}.get(version)
ok = (r.get("method", "skillopt") == method and r["benchmark"] == benchmark and (parent == "-" or r["parent"] == parent)
      and (version == "-" or r["learning_version"] == want))
print("stage record matches" if ok else
      f"stage record mismatch: {r.get('method')}/{r['benchmark']}/{r['parent']}/{r.get('learning_version')}")
sys.exit(0 if ok else 1)
EOF
}
# outcome <dir>: the tool's verified `status` (learned.json bound to its sealed result): 0 = completed with an
# accepted update, 10 = completed without update; every other exit code (20 = other recorded state, 1 =
# exception, anything else) is a failure that stops the chain.
outcome() {
  "$python_bin" scripts/run_fivebench_g_stage.py status --output "$1" >> "$log" 2>&1
  local code=$?
  case "$code" in 0) return 0;; 10) return 10;; *) return 2;; esac
}

learn_and_test() {  # learn_and_test <stage dir>
  local stage=$1
  if [ ! -f "$stage/learned.json" ]; then
    echo "$(date -Iseconds) learn $stage" >> "$log"
    run learn --output "$stage" >> "$stage/run.log" 2>&1 || stop "$stage learning failed or pending (operator review)"
  fi
  outcome "$stage"; local state=$?
  [ "$state" = 0 ] || [ "$state" = 10 ] || stop "$stage is not a verified completed stage (pending, unreadable or inconsistent); operator review"
  if [ "$state" = 0 ]; then
    local own; own=$("$python_bin" -c 'import json,sys; print(json.load(open(sys.argv[1]+"/stage.json"))["benchmark"])' "$stage")
    for b in searchqa bigcodebench korbench; do
      local suffix=""; [ "$b" != "$own" ] && suffix="-$b"
      [ -f "$stage/summary$suffix.json" ] && continue
      echo "$(date -Iseconds) test $stage on $b" >> "$log"
      run test --output "$stage" --test-eval "$test_eval" --test-benchmark "$b" >> "$stage/run.log" 2>&1 \
        || stop "$stage test on $b failed"
    done
  else
    echo "$(date -Iseconds) $stage deployed its parent (no accepted update); no new test cells" >> "$log"
  fi
}

echo "$(date -Iseconds) chain $method/$tag ($learning_version) start from $first" >> "$log"
[ -f "$first/stage.json" ] || stop "$first is not prepared"
check_stage "$first" bigcodebench - - >> "$log" 2>&1 || stop "$first is not a $method BigCodeBench stage"
learn_and_test "$first"
if [ "${G_FIRST_STAGE_ONLY:-0}" = 1 ]; then
  # A protocol change that only concerns the first domain (e.g. a BigCodeBench probe kind) is run as that
  # stage alone; rerunning this script without the flag continues the same chain from the completed stage.
  echo "$(date -Iseconds) chain $method/$tag: first stage only (G_FIRST_STAGE_ONLY=1); later stages not prepared" >> "$log"
  exit 0
fi
prev=$first
for b in searchqa korbench; do
  stage=/root/fivebench-g-20261006-$b-chain-$method-$tag
  if [ -f "$stage/stage.json" ]; then
    check_stage "$stage" "$b" "g:$prev" "$learning_version" >> "$log" 2>&1 \
      || stop "$stage exists but is not this chain's $b stage under $learning_version"
  else
    echo "$(date -Iseconds) prepare $stage (parent g:$prev)" >> "$log"
    run prepare --study "$study" --split "$split" --repo "$repo" --benchmark "$b" --parent "g:$prev" \
      --val-source "${val_source[$b]}" --output "$stage" "${extra[@]}" >> "$log" 2>&1 || stop "prepare $stage failed"
  fi
  learn_and_test "$stage"
  prev=$stage
done
echo "$(date -Iseconds) chain $method/$tag complete" >> "$log"
