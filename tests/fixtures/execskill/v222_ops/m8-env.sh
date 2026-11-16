#!/usr/bin/env bash
# Operator template only. Fill reviewed paths; sourcing this file makes no calls.
set -euo pipefail
M8_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export M8_PY="${M8_PY:-/reviewed/python}"
export M8_SOURCE="${M8_SOURCE:-/reviewed/execskill-v29}"
export M8_HEAD="${M8_HEAD:-REPLACE_WITH_REVIEWED_HEAD}"
export M8_SNAPSHOT="${M8_SNAPSHOT:-/reviewed/snapshots/main-v8}"
export M8_PARENT_S0="${M8_PARENT_S0:-/reviewed/main-v4-s0/v211-s0.json}"
export M8_V3_MANIFEST="${M8_V3_MANIFEST:-/reviewed/frozen-v3-manifest.json}"
export M8_ZEBRA_POOL="${M8_ZEBRA_POOL:-/reviewed/zebralogic/pool.json}"
export M8_ZEBRA_SPLIT="${M8_ZEBRA_SPLIT:-/reviewed/zebralogic/split-manifest.json}"
export M8_PRACTICE_SUPPLY="${M8_PRACTICE_SUPPLY:-}"
export M8_ROLES="${M8_ROLES:-/reviewed/role-credentials-directory}"
export M8_ROUTE="${M8_ROUTE:-/reviewed/northgate-credential-file}"
export M8_ALFWORLD_DATA="${M8_ALFWORLD_DATA:-/reviewed/frozen-alfworld-data-root}"
export M8_ROOT="${M8_ROOT:-/data/execskill-20261103-main-v8}"
export M8_PRE="${M8_PRE:-/reviewed/main-v8-preparation}"
export M8_Q23="${M8_Q23:-/reviewed/main-v8-q23}"
export M8_SHEET="${M8_SHEET:-/reviewed/main-v8-sheet-runtime.json}"
export M8_CONSENT="${M8_CONSENT:-/reviewed/main-v8-owner-consent.json}"
export M8_SMOKE_G="${M8_SMOKE_G:-/reviewed/main-v8-smoke-G}"
export M8_SMOKE_D="${M8_SMOKE_D:-/reviewed/main-v8-smoke-D}"
export M8_LOGS="${M8_LOGS:-/reviewed/main-v8-logs}"
export M8_MANIFEST="${M8_MANIFEST:-/reviewed/main-v8-manifest.json}"
export TMPDIR="${TMPDIR:-/tmp/v222-pre}"
export PYTHONDONTWRITEBYTECODE=1 OPENPYXL_LXML=False
export GRADIO_ANALYTICS_ENABLED=False SKILLOPT_TEST_REAL_OPENCODE=0 SKILLOPT_TEST_REAL_OPENCODE_SOURCE=0

m8_require_paths() {
  local name value
  for name in M8_PY M8_SOURCE M8_HEAD M8_SNAPSHOT M8_PARENT_S0 M8_V3_MANIFEST M8_ZEBRA_POOL M8_ZEBRA_SPLIT M8_ROLES M8_ROUTE M8_ALFWORLD_DATA M8_PRE M8_Q23 M8_SHEET M8_CONSENT M8_SMOKE_G M8_SMOKE_D M8_LOGS M8_MANIFEST; do
    value="${!name}"
    case "$value" in /reviewed/*|REPLACE_*|'') printf '%s\n' "Unfilled reviewed path: $name" >&2; return 2;; esac
  done
  "$M8_PY" -B -c "import os,pathlib; source=pathlib.Path(os.environ['M8_SOURCE']).resolve(); names=('M8_SNAPSHOT','M8_PRE','M8_Q23','M8_SHEET','M8_ROOT','M8_LOGS','M8_SMOKE_G','M8_SMOKE_D'); paths=[pathlib.Path(os.environ[n]).resolve() for n in names]; assert all(p != source and not p.is_relative_to(source) for p in paths), 'Runtime outputs must be outside the source checkout'; assert os.environ['M8_ROOT'] == '/data/execskill-20261103-main-v8', 'The registered run root is fixed'"
  mkdir -p -- "$TMPDIR" "$M8_LOGS"
  export ALFWORLD_DATA="$M8_ALFWORLD_DATA"
}

m8_cli() {
  # Final compact status is deliberately the LAST line, after all CLI logging.
  "$M8_PY" -B -c "import json,sys; from scripts import run_execskill as cli; status=cli.main(); print(json.dumps({'passed': status == 0, 'exit_code': status, 'command': sys.argv[1]}, sort_keys=True)); sys.exit(status)" "$@"
}

m8_check_last_line() {
  "$M8_PY" -B -c "import json,pathlib,sys; rows=pathlib.Path(sys.argv[1]).read_text().splitlines(); value=json.loads(rows[-1]) if rows else {}; assert value.get('passed') is True and value.get('exit_code', 0) == 0, 'The last log line did not pass'" "$1"
}

m8_step() {
  local label="$1" log status=0
  shift
  log="$M8_LOGS/$label.log"
  "$@" >"$log" 2>&1 || status=$?
  # An earlier successful receipt cannot hide a later failed or truncated run.
  m8_check_last_line "$log" || return 3
  test "$status" -eq 0
}
