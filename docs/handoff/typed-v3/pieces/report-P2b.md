# Report of piece P2b (item stage wired into the chain), as returned by its builder 2026-11-15 ~04:0x

Worktree <repo-root> (branch research/typed-skills-v3-p2b, base bd421da).
28 new tests; whole typed selection 1047 passed (1019 + 28); no existing test edited.

(a) typed/__init__.py: ITEM_STAGES=('none','planned'), ITEM_STAGE_DEFAULT='none', ITEM_ZERO_REASONS (officeqa ->
'audit_bing_B36', spreadsheetbench -> 'maker_not_built'). prepare.py: item_stage_of, default_item_quotas (T5 table,
OfficeQA and SpreadsheetBench rows at zero), check_item_quotas, item_quotas_of; prepare(..., item_stage='none',
item_quotas=None) writes both fields into every manifest (item_quotas null under 'none'); bad input refused before
writing; load_manifest checks both. scripts/run_typed.py: prepare --item-stage {none,planned} (prepare only); summary
prints stage and judging/shown totals per bench. chain.py (hooks only): Services.plan_items / make_items (None = real
tools); _Run.own_items, gate_items (THE one place J is defined), shown_items, shown_examples; identities, gate_arm and
routed_gate_items read gate_items; the gate plan.json binds items_sha256 when the bench has sealed items; under
'planned' examples_of skips gate and judging ids; learn() clears step_items and calls itemstage.stage before noise;
outcomes() runs F on learn+shown; cards(): examples learn then shown, corpus and practice ids include shown, round-2
card-r<j>-learn runs on learn+shown; programs and programs_repair add shown examples, the repair probe and paid round
run on learn+shown; finalize calls itemstage.add_to_decisions; _open_state records item_stage and item_quotas_sha256
and refuses a mixed resume. NEW itemstage.py: records under s<k>/: diagnose/diagnose.json, items-plan[-2]/analyst.json,
items[-2]/made.json, items-check[-2]/check.json, items.json (sealed with record_sha256, verified on read); builds J in
memory; items block and by_class in decisions.json; the analyst's experience log; P2a's package imported lazily (an
eager import failed test_typed2_machinery's module count). NEW tests/test_typed3_item_stage.py (28).

(d) Decisions: stage in itemstage.py (chain.py hooks only); analyst record named analyst.json (plan.json is the gate's
sharing plan); a zero-quota bench / unbuilt maker runs no diagnose and no analyst, items.json records the reason, J = R;
round 2 replaces attack items only (B5), a side counts as replaced only if round 2 made at least one attack item there;
check 2 only when the judging side was replaced, fresh B cells only for round-2 items, check 1's calibration outcomes
reused; only the shown side replaced -> `judging_side_not_replaced` (shown attack from plan 2, judging from plan 1,
final_round 1); SearchQA round-2 shortfall fills join calibration on a replaced judging side, else 'unused'; shown
examples bounded per group (attack then guard) by outcomes_for_writer's caps; the rejected round-2 card also runs on
shown items; infrastructure unknown in diagnose/check pauses 'gate_cells_unknown'; analyst/selector retry once after
60 s then pause 'analyst_unavailable' / 'selector_unavailable'; by_class only in decisions.json rows (cards, programs,
typing.no_harm); prepare refuses non-zero OfficeQA/SpreadsheetBench rows; a custom quota table only through
prepare(item_quotas=...), no CLI flag; docs not updated.

(e) Risks: the card writer's 120k-character fit drops successes from the end first (on ZebraLogic learn successes can
be dropped before shown failures); machinery.frozen_uses scans only top-level typed modules: frozen names used inside
items/ and bank/ (supply.task_folder, zebralogic.normalize, coevo5.data.ranked) are not covered by REQUIRED: check on
the dl snapshot; routing of made items not tested with real embeddings (a made item too far from every type mounts the
base card alone and would hide card gains on attack items): the smoke must count J items routed to the home type; in
the smoke, practice panels can be picked as made items (the selector excludes only learn and gate items); a smoke with
2 learn items cannot keep a weakness; merge conflicts with P1's fixer likely on programs_repair example/practice lines;
any new outcomes unit (e.g. after an accepted archive) should go through self.outcomes() so shown items are included.

(f) For P3b: J = _Run.gate_items(bench) (real, then attack, guard, calibration); class map itemstage.gate_classes(run,
bench) (also run.step_items['classes']); full lists in s<k>/items.json (`lists`); shown items run.shown_items;
leakage-private ids itemstage.private_ids; the screen's items are A+G; apply the T7 rules on J; re-export the gatestats
functions in gates.py; a smoke needs smaller quotas through prepare's item_quotas parameter; --item-stage exists only
on prepare.
