#!/usr/bin/env bash
# Operator's full Linux pre-test. The writer only syntax-checks this template.
set -euo pipefail
M8_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M8_OPS/m8-env.sh"
m8_require_paths
cd -- "$M8_SOURCE"
export TMPDIR="${M8_PRE_TMP:-/tmp/v222-pre}"
mkdir -p -- "$TMPDIR"
log="$M8_LOGS/full-suite.log"
status=0
"$M8_PY" -B -m pytest -q -p no:cacheprovider --basetemp="$TMPDIR/cases" \
  tests/test_execskill_*.py tests/test_weak_solver_probe.py >"$log" 2>&1 || status=$?
"$M8_PY" -B -c "import json,pathlib,re,sys; rows=pathlib.Path(sys.argv[1]).read_text().splitlines(); last=rows[-1] if rows else ''; code=int(sys.argv[2]); passed=code == 0 and re.search(r'\b[0-9]+ passed\b', last) is not None and re.search(r'\b[0-9]+ (failed|errors?)\b', last) is None; print(json.dumps({'passed': passed, 'exit_code': code, 'result': last}, sort_keys=True)); sys.exit(0 if passed else 3)" "$log" "$status"
