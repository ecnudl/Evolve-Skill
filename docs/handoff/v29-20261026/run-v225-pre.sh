#!/usr/bin/env bash
# Linux operator template. Run ALONE: no reads or other suites on the machine.
# Never run by the offline writer. A suite can consume about 161k scratch inodes.
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M9_OPS/m9-env.sh"
m9_require_paths
test "$(uname -s)" = Linux || exit 2
test "${M9_FULL_SUITE_ALONE:-}" = operator-confirmed-alone || { printf '%s\n' 'Confirm no reads or other suites run on this machine' >&2; exit 2; }
# A standalone suite shares the S0 host lock. The prep child reuses the same
# inherited open-file description so its parent's existing lock cannot self-block.
if ! "$M9_PY" -B - /tmp/execskill-s0.lock <<'PY_S0_DESCRIPTOR'
import os
import sys
try:
    inherited, fixed = os.fstat(201), os.stat(sys.argv[1])
    same = (inherited.st_dev, inherited.st_ino) == (fixed.st_dev, fixed.st_ino)
except OSError:
    same = False
sys.exit(0 if same else 1)
PY_S0_DESCRIPTOR
then
  exec 201>/tmp/execskill-s0.lock
fi
flock -n 201 || { printf '%s\n' 'Another preparation or suite owns the shared S0 host lock' >&2; exit 2; }
# Shared with cooperating suites/drivers; the scan also catches existing jobs
# which do not use it. Never replace the explicit operator ALONE confirmation.
M9_MACHINE_LOCK="${M9_MACHINE_LOCK:-/tmp/execskill-machine.lock}"
exec 200>"$M9_MACHINE_LOCK"
flock -n 200 || { printf '%s\n' 'Another suite/driver owns the shared machine lock' >&2; exit 2; }
"$M9_PY" -B "$M9_OPS/m9-alone.py"
cd -- "$M9_SOURCE"
mkdir -p -- "$TMPDIR"
M9_SUITE_SCRATCH="$(mktemp -d "$TMPDIR/suite-XXXXXX")"
export TMPDIR="$M9_SUITE_SCRATCH"
m9_prepare_scratch
log="$M9_LOGS/full-suite.log"
status=0
"$M9_PY" -B -m pytest -q -p no:cacheprovider --basetemp="$TMPDIR/cases" \
  tests/test_execskill_*.py tests/test_weak_solver_probe.py >"$log" 2>&1 || status=$?
"$M9_PY" -B - "$log" "$status" "$M9_SUITE_SCRATCH" <<'PY_SUITE_RESULT'
import json
from pathlib import Path
import re
import shutil
import sys
rows = Path(sys.argv[1]).read_text().splitlines()
last, code = rows[-1] if rows else '', int(sys.argv[2])
passed = code == 0 and re.search(r'\b[0-9]+ passed\b', last) is not None and re.search(r'\b[0-9]+ (failed|errors?)\b', last) is None
scratch = Path(sys.argv[3])
cases = scratch / 'cases'
removed = False
if passed:
    assert not scratch.is_symlink() and not cases.is_symlink(), 'Only this suite owns the cases directory'
    assert scratch.resolve().is_relative_to(Path('/tmp').resolve()) and scratch.name.startswith('suite-'), 'The suite scratch identity must be retained'
    if cases.exists():
        assert cases.is_dir(), 'The owned cases path must be a directory'
        shutil.rmtree(cases)
        removed = True
print(json.dumps({'passed': passed, 'exit_code': code, 'result': last,
    'scratch_preserved': str(scratch), 'cases_removed': removed}, sort_keys=True))
sys.exit(0 if passed else 3)
PY_SUITE_RESULT
