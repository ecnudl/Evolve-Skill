#!/usr/bin/env bash
# Part of master queue z1 (10/13 03:00). The four queues u5, v1, w2 and y1 were stopped by the operator at 02:57 while
# each waited for ten quiet minutes (no run in progress). z1 runs their remaining work one part after another;
# an evaluation run starts after TWELVE consecutive successful TLS-level probes (about two minutes) instead of
# sixty; the tool's in-run gate and the retry rule (one repetition after a sealed pending result) are unchanged.
# Original header of queue v1 (steps 1 and 2 ran there):
# 10/13 queue v1: generated test tasks instead of a validation set for the Rubric+Research method (SearchQA).
# Design contract: docs/handoff/generated-validation-design-20261013.md. Snapshot 20261013-o.
#   1. gen06     generate test tasks from the 128 training tasks of seed 20261006 (public fields only);
#   2. v10gen-a  E2: the FROZEN learning-v10 rubric_research learner, seed 20261006, parent none, with the generated
#                tasks as its selection set (--generated-val); learn only, no test cell;
#   3. E2 read   empty / bzero / the original v10 Skill / the new Skill on 250 FRESH real tasks (block B, R01..R10);
#   4. E1        ten frozen Skills (empty, bhand, bzero, le23..le27, old_v10, old_v9) on the generated tasks.
# Each paid step starts only after about ten quiet minutes of the TLS-level probe. Every outcome is kept and
# reported. A STOP is left for operator review; nothing is resumed. NO test cell, no canonical validation data.
PY=/root/continual-alf-prep-20260928/env/bin/python
O=/root/fivebench-g-20261013-source-o
C=/root/fivebench-g-20261011-controls
P=/root/fivebench-g-20261013
S=/root/fivebench-g-20261012-searchqa-active
Z=/root/fivebench-g-20261012-searchqa-bzero2
G=$P-searchqa-gen06
E2=$P-searchqa-v10gen-a
PROBE=/root/net-probe-20261012d.log
REV=c1a979068ba118d85467179b704031d113d689cc
COMMON="--study /root/continual-fivebench-20261003-f-study --split /root/fivebench-split-20261005-v2/split_manifest.json --repo /root/continual-noskill-bcb-20260928-a"
OLD="--skill old_v10=g:/root/fivebench-g-20261006-searchqa-chain-rubric_research-e"
online() { (cd $O && export PYTHONPATH=$O && bash -ic 'proxy_on >/dev/null 2>&1 && exec "$@"' -- $PY "$@"); }
offline() { (cd $O && PYTHONPATH=$O $PY "$@"); }
quiet() {
  waited=0
  while ! offline scripts/connectivity_probe.py quiet --log $PROBE --count $1; do
    if [ "$waited" -ge "${2:-43200}" ]; then return 1; fi
    sleep 30; waited=$((waited+30))
  done
  return 0
}
halt() { echo "$(date -Iseconds) STOP ($1)"; echo "$(date -Iseconds) V1C-EXIT"; exit 1; }
panel() {  # panel <label> <items file> <skill args...>: one evaluation run, repeated once after a sealed pending result
  label=$1; items=$2; shift 2
  for attempt in "" "-r1"; do
    e=$P-searchqa-paneleval-$label$attempt
    quiet 12 || halt "no fresh quiet connectivity probe before eval $label$attempt"
    if offline scripts/run_active_evidence_panel_eval.py prepare $COMMON --benchmark searchqa --items $items --revision $REV "$@" --chunk 10 --output $e > $e.prepare.log 2>&1; then
      echo "$(date -Iseconds) eval $label$attempt start"
      online scripts/run_active_evidence_panel_eval.py run --output $e >> $e.run.log 2>&1
      offline scripts/run_active_evidence_panel_eval.py status --output $e >> $e.run.log 2>&1; rc=$?
      echo "$(date -Iseconds) eval $label$attempt end"
      if [ $rc -eq 0 ]; then return 0; fi
      if [ $rc -ne 3 ]; then halt "eval $label$attempt left no valid result: see $e.run.log"; fi
      echo "$(date -Iseconds) STOP (eval $label$attempt): sealed pending result"
    else
      halt "eval $label$attempt could not be prepared: see $e.prepare.log"
    fi
  done
  return 1
}
# 4. E1: frozen Skills on the generated tasks (six blocks of 25 in generation order; revised 03:10 after the Codex
# review of queue z1, before this part started: the blocks are written and verified as a whole or the part halts).
if ! offline scripts/generate_searchqa_tasks.py check --output $G > $G.check-e1.log 2>&1; then halt "the generation record does not verify: see $G.check-e1.log"; fi
if ! offline - >> $G.check-e1.log 2>&1 <<EOF
import json, pathlib
items = json.loads(pathlib.Path("$G/items.json").read_text(encoding="utf-8"))
assert len(items) == 168 and len({item["id"] for item in items}) == 168, "unexpected generated items"
root = pathlib.Path("$G/blocks")
assert not root.exists(), "the blocks directory already exists"
for k in range(6):
    d = root / ("block_%02d" % (k + 1)); d.mkdir(parents=True)
    (d / "items.json").write_text(json.dumps(items[k * 25:(k + 1) * 25], ensure_ascii=False, indent=2), encoding="utf-8")
seen = []
for k in range(6):
    block = json.loads((root / ("block_%02d" % (k + 1)) / "items.json").read_text(encoding="utf-8"))
    assert block == items[k * 25:(k + 1) * 25], "block content differs"
    seen += [item["id"] for item in block]
assert len(seen) == 150 == len(set(seen)) and sorted(p.name for p in root.iterdir()) == ["block_%02d" % (k + 1) for k in range(6)]
print("generated tasks:", len(items), "-> six verified blocks of 25")
EOF
then halt "the generated blocks could not be written and verified: see $G.check-e1.log"; fi
missing=0
for b in 01 02 03 04 05 06; do
  panel e1-g$b $G/blocks/block_$b/items.json --skill empty=none --skill bhand=f:$C/generic.md --skill bzero=f:$Z/skill.md --skill le23=g:$S-le23 --skill le24=g:$S-le24 --skill le25=g:$S-le25 --skill le26=g:$S-le26 --skill le27=g:$S-le27 $OLD --skill old_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c || missing=$((missing+1))
done
echo "$(date -Iseconds) V1C-EXIT (blocks without a completed run: $missing of 6)"
if [ $missing -gt 0 ]; then exit 1; fi
exit 0
