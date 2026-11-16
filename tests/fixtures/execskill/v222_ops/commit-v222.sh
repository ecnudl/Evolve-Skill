#!/usr/bin/env bash
# TEMPLATE ONLY: the offline writer must never execute this script.
# Fill a reviewed expected HEAD and message, then execute only on owner approval.
set -euo pipefail
test "${V222_COMMIT_AUTHORIZATION:-}" = reviewed-owner-commit || exit 2
: "${V222_EXPECTED_HEAD:?Set the reviewed pre-commit HEAD}"
: "${V222_COMMIT_MESSAGE:?Set the reviewed commit message}"
test "$(git rev-parse HEAD)" = "$V222_EXPECTED_HEAD"
test -z "$(git diff --cached --name-only)" || { printf '%s\n' 'Existing staged changes; stop for review' >&2; exit 2; }
git diff --check
git add --pathspec-from-file=docs/handoff/v29-20261026/V222-CHANGED-FILES.txt
git diff --cached --check
git commit -m "$V222_COMMIT_MESSAGE"
