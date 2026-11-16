#!/usr/bin/env bash
# Operator-only measured smoke after review and approved external-call setup.
set -euo pipefail
M8_OPS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$M8_OPS/m8-env.sh"
m8_require_paths
cd -- "$M8_SNAPSHOT"
export PYTHONPATH="$M8_SNAPSHOT"
for chain in G D; do
  if test "$chain" = G; then root="$M8_SMOKE_G"; else root="$M8_SMOKE_D"; fi
  m8_step "manifest-smoke-$chain" m8_cli v214-manifest --configuration main-v8 \
    --out "$root-manifest.json" --root "$root" --s0 "$M8_PRE/s0/v214-s0.json" \
    --provenance "$M8_SNAPSHOT/snapshot-provenance.json" --roles-repo "$M8_ROLES" \
    --route-b-env "$M8_ROUTE" --sheet-runtime "$M8_SHEET" --smoke-chain "$chain"
  m8_step "structural-$chain" m8_cli v214-structural-smoke --configuration main-v8 \
    --manifest "$root-manifest.json" --out "$M8_PRE/structural-$chain.json"
  for stage in S0 S1 S2 S3 SE6 SX; do
    m8_step "smoke-$chain-$stage" m8_cli v214-smoke-run --configuration main-v8 \
      --manifest "$root-manifest.json" --chain "$chain" --stage "$stage"
  done
  m8_step "summary-$chain" m8_cli v214-smoke-summary --configuration main-v8 \
    --manifest "$root-manifest.json" --chain "$chain"
done
printf '%s\n' '{"passed":true,"exit_code":0,"phase":"smoke"}'
