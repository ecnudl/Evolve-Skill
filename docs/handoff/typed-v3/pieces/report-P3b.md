# Report of piece P3b (rules on J, screen unit, readout additions, presets), as returned by its builder 2026-11-15 ~05:1x

Worktree <repo-root> (branch research/typed-skills-v3-p3b at aaebef2). 7 files
changed (+723/-45) + tests/test_typed3_gate_rule.py (44 tests). Whole typed selection 1128 passed (1084 + 44); Python
3.10: new file 44 passed. No existing test edited.

(a) __init__: GATE_RULES ('whole','evolution'; default 'whole'), GATE_SCREENS (False, True; default False),
RESUME_REPLAYS ('off','on'; default 'off'). prepare: gate_rule_of, gate_screen_of, resume_replay_of (absent = default);
prepare(gate_rule=, gate_screen=, resume_replay=) checks all three before writing and seals them in EVERY manifest;
load_manifest checks them; TYPED_V3_PRESET, typed_v3_preset(smoke=), smoke_item_quotas(). chain: card rule on E =
card_decision_evolution(evolution_statistics(stats, E)) with E = R + A from the step's sealed items.json; screen unit
`<stem>-screen` (write-once screen.json) before every card round, program slot, repair version and archive package; a
candidate refused there gets a decision with 0 gate cells; verify_decision checks every card, program, repair and
archive decision, fresh or reloaded on resume; recompute_decision handles screen records and refusals; the state refuses
a resume under a different rule or screen; decisions.json gets a gate_rule block. gates.py re-exports P3a's names.
writers: round-2 summary for a card decided on E (counts on E + the harm clause on J) and for a round refused at the
screen (counts only); typed-v2 output unchanged. readout: per-step typed_v3 block + markdown (item block, the step's
rules, per candidate its numbers on E, screen record, gains by class, B's parity; programs' repair history; the archive
package's own decision apart from later candidates, with the T9 sentence and the B4 note). run_typed: prepare
--typed-v3 (+ --smoke for the smoke root), refuses any single-option flag beside it.

(b) Tests: E vs J hand-computed (E 14 items, gain 7.14, se 3.367, tau_E 6.734 accepted where the whole-list rule
refuses with tau 8.165); harm on guard items; gain only on K refused; programs keep the whole-list rule; a step without
made items gives typed-v2's record; screen passes at R*c = b (b=9, c=3), refuses at b-1 (b=10); a never-firing program
refused there; screen cells never in a gate arm; card round 2 still runs after a screen refusal; 7 in-process kill
points (inside the screen; after its cells before screen.json; between screen.json and the gate plan; at the first gate
cell; inside a program's screen; after a card refusal; after a program refusal) resume identical with no request sent
twice; 5 forged-E records and a changed screen.json pause (gate_decision_changed / gate_screen_changed); chains G and D
under the smoke preset complete 5 steps with a fresh read after each step (rows C, S1..S5, no C0); 7 SIGKILLs (two
mid-read, inside a card screen, inside the archive's screen, right after a screen record, at the first gate cell after a
screen) resume byte-identical; the preset seals exactly the brief's fields (run and smoke); consent C..S5 accepted, 7
arms refused; readout blocks; the shared-type case.

(d) Differently: screen refusal reasons are P3a's screen_below_baseline / screen_never_fired (not 'screen'); the screen
record is stored under `screen_run` (program rows already use `screen` for P1's static screen); the three fields are
written in every manifest, at defaults too; resume_replay only sealed and checked (no mechanism in this tree); added
guard: 'evolution' or a screen refused unless item_stage is 'planned'; no separate --gate-rule / --gate-screen flags
(the preset instead); smoke quota row judging 1/2/2, shown 1/4 so item stage, check, shown items and screen all run in
the smoke; the smoke's 2 learn items can never keep a weakness, so the replacement round never runs in the smoke; card
round 2 runs only if round 1 is refused (covered in memory); end-to-end tests use fake item makers; living docs not
updated; the readout does not re-check stored decisions (the chain does on every pass under the typed-v3 options).

(e) Risks: merge conflict with the resume_replay builder (same names; theirs seals resume_replay only when 'on', mine
always; conflicts in __init__, prepare signature and manifest fields, chain _open_state / run() / _Run.__init__,
run_typed _prepare / prepare / parser; with theirs two assertions of
test_prepare_seals_the_gate_options_and_a_default_manifest_stays_typed_v2s fail; after the merge add 'resume_replay' to
run_typed.PRESET_EXCLUSIVE and the CLI test's set); the screen is a coarse filter (B4), especially on ALFWorld's 28
screen items; cost one run per A+G item per candidate (SearchQA 105, ZebraLogic 140, ALFWorld 28, against 750, 900 and
240 runs for a full gate); verify_decision is strict (any stored decision that does not reproduce pauses with
gate_decision_changed) and untried on real records; real makers and selector with the screen on real pools and the dl
suite on 3.11 not run yet.

(f) Prepare: smoke `$CLI prepare --root /data/execskill-<DATE>-typed-v3-smoke --smoke --typed-v3`; real run
`$CLI prepare --root /data/execskill-<DATE>-typed-v3 --typed-v3`; check in the printed summary: gate_rule evolution,
gate_screen true, resume_replay on, read_anchors [C], arms C, S1..S5.

## Round 2 (answer to the one review, 2026-11-15 05:5x)
verify_decision now checks only decisions reloaded from disk, by REBUILDING them in a records-only mode from the cells and records the chain would use (gate cells of the candidate's unit and its incumbent, plan.json, the decision's own screen bound by unit and candidate_sha256, sealed items.json for E), and pauses gate_decision_changed / records_missing / records_invalid on any difference; under typed-v2 defaults it does nothing. 58 gate tests, 1142 typed tests. For the merge: the records-only branch must stay first in cells(), above the replay wrapper; combine the two _open_state signature extensions; resume_replay sealing: take the main tree's (sealed only when 'on').
