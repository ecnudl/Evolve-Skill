#!/usr/bin/env bash
# Finite operator launch. No learner, continuation queue, or publication.
# Invoke from an interactive PJLAB Bash so proxy_on is available.
set -euo pipefail
umask 077

RECOVERY_ROOT=${1:?Pass the already prepared recovery snapshot directory}
RECOVERY_PYTHON=${2:-/root/miniconda3/envs/skill_validation/bin/python}
RECOVERY_WORKERS=${3:-10}
case "$RECOVERY_WORKERS" in
  [1-9]|10) ;;
  *) printf 'Workers must be 1..10\n' >&2; exit 2 ;;
esac
test -d "$RECOVERY_ROOT"
test -x "$RECOVERY_PYTHON"
cd "$RECOVERY_ROOT"
exec 9>launch.lock
flock -n 9 || exit 5
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
type proxy_on >/dev/null
proxy_on >/dev/null
# Interactive Bash is only needed to load proxy_on. Disable job control before
# launching Python; a stopped foreground job must not accidentally tear down
# its shell. Normal operator pauses use the runner's PAUSE marker, not SIGSTOP.
set +m

printf 'RECOVERY_STARTED %s\n' "$(date -Is)"
if "$RECOVERY_PYTHON" -m skillopt.continual_eval.truncation_recovery run \
    --output "$RECOVERY_ROOT/run" \
    --repo /root/continual-noskill-bcb-20260928-a --workers "$RECOVERY_WORKERS"; then
  printf 'RECOVERY_FINISHED %s\n' "$(date -Is)"
else
  RECOVERY_EXIT=$?
  printf 'RECOVERY_STOPPED exit=%s %s\n' "$RECOVERY_EXIT" "$(date -Is)"
  exit "$RECOVERY_EXIT"
fi
"$RECOVERY_PYTHON" -m skillopt.continual_eval.truncation_recovery report \
    --output "$RECOVERY_ROOT/run"
