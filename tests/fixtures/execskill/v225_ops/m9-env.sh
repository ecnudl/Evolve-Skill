#!/usr/bin/env bash
# Operator template only. Fill reviewed paths; sourcing this file makes no calls.
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export M9_PY="${M9_PY:-/reviewed/python}"
export M9_SOURCE="${M9_SOURCE:-/reviewed/execskill-v29}"
export M9_HEAD="${M9_HEAD:-REPLACE_WITH_REVIEWED_HEAD}"
export M9_SNAPSHOT="${M9_SNAPSHOT:-/reviewed/snapshots/main-v9}"
export M9_PARENT_S0="${M9_PARENT_S0:-/reviewed/main-v4-s0/v211-s0.json}"
export M9_V3_MANIFEST="${M9_V3_MANIFEST:-/reviewed/frozen-v3-manifest.json}"
export M9_ZEBRA_POOL="${M9_ZEBRA_POOL:-/reviewed/zebralogic/pool.json}"
export M9_ZEBRA_SPLIT="${M9_ZEBRA_SPLIT:-/reviewed/zebralogic/split-manifest.json}"
export M9_PRACTICE_SUPPLY="${M9_PRACTICE_SUPPLY:-}"
export M9_ROLES="${M9_ROLES:-/reviewed/role-credentials-directory}"
export M9_ROUTE="${M9_ROUTE:-/reviewed/northgate-credential-file}"
export M9_ALFWORLD_DATA="${M9_ALFWORLD_DATA:-/reviewed/frozen-alfworld-data-root}"
export M9_ROOT="${M9_ROOT:-/data/execskill-20261104-main-v9}"
export M9_PRE="${M9_PRE:-/reviewed/main-v9-preparation}"
export M9_Q23="${M9_Q23:-/reviewed/main-v9-q23}"
export M9_SHEET="${M9_SHEET:-/reviewed/main-v9-sheet-runtime.json}"
export M9_CONSENT="${M9_CONSENT:-/reviewed/main-v9-owner-consent.json}"
export M9_SMOKE_G="${M9_SMOKE_G:-/reviewed/main-v9-smoke-G}"
export M9_SMOKE_D="${M9_SMOKE_D:-/reviewed/main-v9-smoke-D}"
export M9_LOGS="${M9_LOGS:-/reviewed/main-v9-logs}"
export M9_MANIFEST="${M9_MANIFEST:-$M9_ROOT-manifest.json}"
export TMPDIR=/tmp/v225-pre
export PYTHONDONTWRITEBYTECODE=1 OPENPYXL_LXML=False
export GRADIO_ANALYTICS_ENABLED=False SKILLOPT_TEST_REAL_OPENCODE=0 SKILLOPT_TEST_REAL_OPENCODE_SOURCE=0

m9_prepare_scratch() {
  "$M9_PY" -B - "$TMPDIR" <<'PY_SCRATCH'
import os
from pathlib import Path
import stat
import sys
path = Path(sys.argv[1])
closed = ('test', 'holdout', 'held_out', 'final', 'sealed', 'reserve', 'testaccess', 'test_panel', 'block_c', 'block_d')
assert not any(token in part.lower() for part in path.parts for token in closed), 'Scratch path must have plain names'
assert path.resolve().is_relative_to(Path('/tmp').resolve()), 'Scratch must be below /tmp'
assert not path.is_symlink(), 'Scratch itself cannot be a symlink'
path.mkdir(parents=True, exist_ok=True)
os.chmod(path, 0o1777)
assert path.is_dir() and stat.S_IMODE(path.stat().st_mode) == 0o1777, 'Scratch requires sticky mode 1777'
assert os.access(path, os.W_OK | os.X_OK), 'Scratch must be writable and traversable'
assert all(parent.stat().st_mode & stat.S_IXOTH for parent in path.parents), 'Scratch ancestors must allow uid 65534 traversal'
# World write/execute plus traversable ancestors admits uid 65534 without a root-only uid-switch probe.
PY_SCRATCH
}

m9_require_paths() {
  local name value
  for name in M9_PY M9_SOURCE M9_HEAD M9_SNAPSHOT M9_PARENT_S0 M9_V3_MANIFEST M9_ZEBRA_POOL M9_ZEBRA_SPLIT M9_ROLES M9_ROUTE M9_ALFWORLD_DATA M9_PRE M9_Q23 M9_SHEET M9_CONSENT M9_SMOKE_G M9_SMOKE_D M9_LOGS M9_MANIFEST; do
    value="${!name}"
    case "$value" in /reviewed/*|REPLACE_*|'') printf '%s\n' "Unfilled reviewed path: $name" >&2; return 2;; esac
  done
  "$M9_PY" -B -c "import os,pathlib; source=pathlib.Path(os.environ['M9_SOURCE']).resolve(); names=('M9_SNAPSHOT','M9_PRE','M9_Q23','M9_SHEET','M9_ROOT','M9_LOGS','M9_SMOKE_G','M9_SMOKE_D'); paths=[pathlib.Path(os.environ[n]).resolve() for n in names]; assert all(p != source and not p.is_relative_to(source) for p in paths), 'Runtime outputs must be outside the source checkout'; assert os.environ['M9_ROOT'] == '/data/execskill-20261104-main-v9', 'The registered run root is fixed'"
  m9_prepare_scratch
  mkdir -p -- "$M9_LOGS"
  export ALFWORLD_DATA="$M9_ALFWORLD_DATA"
}

m9_cli() {
  # Final compact status is deliberately the LAST line, after all CLI logging.
  "$M9_PY" -B -c "import json,sys; from scripts import run_execskill as cli; status=cli.main(); print(json.dumps({'passed': status == 0, 'exit_code': status, 'command': sys.argv[1]}, sort_keys=True)); sys.exit(status)" "$@"
}

m9_check_last_line() {
  "$M9_PY" -B -c "import json,pathlib,sys; rows=pathlib.Path(sys.argv[1]).read_text().splitlines(); value=json.loads(rows[-1]) if rows else {}; assert value.get('passed') is True and value.get('exit_code', 0) == 0, 'The last log line did not pass'" "$1"
}

m9_step() {
  local label="$1" log status=0
  shift
  log="$M9_LOGS/$label.log"
  "$@" >"$log" 2>&1 || status=$?
  # An earlier successful receipt cannot hide a later failed or truncated run.
  m9_check_last_line "$log" || return 3
  test "$status" -eq 0
}
