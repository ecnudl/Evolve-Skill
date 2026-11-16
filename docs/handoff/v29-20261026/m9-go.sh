#!/usr/bin/env bash
# Operator driver; every phase uses its last status line and stops on failure.
# Example inspection: tmux capture-pane -pt =main-v9
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M9_OPS/m9-env.sh"
m9_require_paths
test "${M9_OWNER_LAUNCH:-}" = main-v9-reviewed-launch || exit 2
for phase in prep smoke launch; do
  m9_step "go-$phase" bash "$M9_OPS/m9-$phase.sh"
done
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"go_complete","experiment_complete":false}'
