#!/usr/bin/env bash
# Explicit finite queue. Learner/result resume is checked by the Python driver.
set -euo pipefail
umask 077
source_root=/root/continual-sequential-20261002-c-source
study=/root/continual-sequential-20261002-c-study
python_bin=/root/continual-alf-prep-20260928/env/bin/python
gepa_source=/root/continual-learning-env-20260928/gepa-source
credential_repo=/root/continual-noskill-bcb-20260928-a
cd "$source_root"
export PYTHONPATH="$source_root:$gepa_source/src"
"$python_bin" -m scripts.continue_fivebench_baselines check --output "$study"
mkdir "$study/launch"
date -Iseconds
for method in skillopt gepa; do
  echo "Starting finite five-domain method=$method"
  # proxy_on and client execution share a Linux shell. The frozen client also
  # explicitly uses the reviewed PJLAB gateway (trust_env=False).
  bash -ic 'proxy_on >/dev/null && exec "$@"' -- \
    "$python_bin" -m scripts.continue_fivebench_baselines run --output "$study" \
    --method "$method" --repo "$credential_repo" --gepa-source "$gepa_source" \
    >"$study/launch/$method.log" 2>&1
  echo "Finished method=$method; inspect final.json for completed vs pending stages"
done
date -Iseconds
