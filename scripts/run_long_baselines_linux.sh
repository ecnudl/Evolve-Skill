#!/usr/bin/env bash
# Explicit finite launcher. Root/operator owns tmux; this script never starts it.
set -euo pipefail
umask 077

if [[ $# -ne 5 || ( "$1" != "no_skill" && "$1" != "learning" ) ]]; then
  echo "Usage: bash run_long_baselines_linux.sh no_skill|learning STUDY PYTHON CREDENTIAL_REPO GEPA_SOURCE" >&2
  exit 2
fi
mode="$1"
study="$2"
python_bin="$3"
credential_repo="$4"
gepa_source="$5"
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ "$(uname -s)" == "Linux" ]] || { echo "Linux only" >&2; exit 2; }
[[ "$study" == /* && "$python_bin" == /* && "$credential_repo" == /* && "$gepa_source" == /* ]] || {
  echo "All launch paths must be absolute" >&2; exit 2;
}
command -v flock >/dev/null
cd "$source_root"
export PYTHONPATH="$source_root"
"$python_bin" -m scripts.prepare_long_baselines --check --output "$study"
# Never overwrite launch logs or silently resume an interrupted learning stage.
mkdir -p "$study/launches"
launch="$study/launches/$mode"
mkdir "$launch"

with_proxy() {
  # Load proxy_on on Linux, activate it in the same shell that execs the client.
  # The frozen model also names the approved gateway because trust_env=False.
  bash -ic 'proxy_on >/dev/null && exec "$@"' -- "$@"
}

if [[ "$mode" == "no_skill" ]]; then
  generate_status=0
  with_proxy "$python_bin" -m skillopt.continual_eval.cli generate --run "$study/no_skill" \
    --benchmark bigcodebench --method no_skill --history h0 --stage 0 --repo "$credential_repo" --workers 6 \
    >"$launch/generate.log" 2>&1 || generate_status=$?
  echo "No-Skill generation exit=$generate_status; scoring closed predictions under native.lock"
  score_status=0
  flock "$study/native.lock" "$python_bin" -m skillopt.continual_eval.cli score --run "$study/no_skill" \
    --benchmark bigcodebench --method no_skill --history h0 --stage 0 >"$launch/score.log" 2>&1 || score_status=$?
  report_status=0
  "$python_bin" -m skillopt.continual_eval.cli report --run "$study/no_skill" \
    >"$launch/report.json" 2>"$launch/report-error.log" || report_status=$?
  echo "No-Skill score exit=$score_status report exit=$report_status; private results=$launch"
  if [[ $generate_status -ne 0 ]]; then exit "$generate_status"; fi
  if [[ $score_status -ne 0 ]]; then exit "$score_status"; fi
  exit "$report_status"
fi

for method in skillopt gepa; do
  # Hold one common lock for the whole method: solver calls may overlap
  # No-Skill generation, but the two 8GB native scorers must never overlap.
  method_status=0
  flock "$study/native.lock" bash -ic 'proxy_on >/dev/null && exec "$@"' -- \
    "$python_bin" -m scripts.run_continual_learning --manifest "$study/manifests/$method.json" \
    --panel "$study/data/learning.json" --method "$method" --output "$study/learning/$method" \
    --repo "$credential_repo" --gepa-source "$gepa_source" --execute \
    >"$launch/$method.log" 2>&1 || method_status=$?
  echo "$method learning exit=$method_status; private results=$study/learning/$method"
  if [[ $method_status -ne 0 ]]; then
    echo "Learning queue stopped; no automatic next method, resume, checkpoint promotion, or S1 evaluation"
    exit "$method_status"
  fi
done
