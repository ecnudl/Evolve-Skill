#!/usr/bin/env bash
# Operator-only measured smoke after review and approved external-call setup.
set -euo pipefail
M9_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M9_OPS/m9-env.sh"
m9_require_paths
cd -- "$M9_SNAPSHOT"
export PYTHONPATH="$M9_SNAPSHOT"
for chain in G D; do
  if test "$chain" = G; then root="$M9_SMOKE_G"; else root="$M9_SMOKE_D"; fi
  m9_step "manifest-smoke-$chain" m9_cli v214-manifest --configuration main-v9 \
    --out "$root-manifest.json" --root "$root" --s0 "$M9_PRE/s0/v214-s0.json" \
    --provenance "$M9_SNAPSHOT/snapshot-provenance.json" --roles-repo "$M9_ROLES" \
    --route-b-env "$M9_ROUTE" --sheet-runtime "$M9_SHEET" --smoke-chain "$chain"
  m9_step "structural-$chain" m9_cli v214-structural-smoke --configuration main-v9 \
    --manifest "$root-manifest.json" --out "$M9_PRE/structural-$chain.json"
  for stage in S0 S1 S2 S3 SE6 SX; do
    m9_step "smoke-$chain-$stage" m9_cli v214-smoke-run --configuration main-v9 \
      --manifest "$root-manifest.json" --chain "$chain" --stage "$stage"
  done
  m9_step "summary-$chain" m9_cli v214-smoke-summary --configuration main-v9 \
    --manifest "$root-manifest.json" --chain "$chain"
done
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"smoke"}'
