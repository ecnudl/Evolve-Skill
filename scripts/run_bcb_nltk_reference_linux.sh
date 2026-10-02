#!/usr/bin/env bash
# Bounded zero-model qualification of the separately prepared data-only image.
# Earlier job exit is a scheduling condition, not a claim that those jobs passed.
set -euo pipefail
test "$(uname -s)" = Linux
qualification_source=/root/continual-reference-qualification-20261001-source
qualification_run=/root/continual-reference-nltk-20261001-study/run
qualification_python=/root/continual-learning-env-20260928/bin/python
cd "$qualification_source"
"$qualification_python" -m skillopt.continual_eval.reference_qualification check --output "$qualification_run"
for predecessor in korbench-long-20261001 alfworld-long-20261001; do
  while tmux has-session -t "$predecessor" 2>/dev/null; do
    sleep 30
  done
done
# The reviewed module itself acquires the shared native lock; never wrap a second flock.
exec "$qualification_python" -m skillopt.continual_eval.reference_qualification run --output "$qualification_run"
