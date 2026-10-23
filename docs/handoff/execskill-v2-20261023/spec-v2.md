# Route B v2 ("train then accept") — change specification as implemented (2026-10-23)

## Owner decisions (chat, verbatim)
- 2026-10-23 ~13:3x: "好的，那就按照你的建议来修改，最好真正的跑通了一个示例再开始正式实验，修改过程做好code review，用codexdl"
  (approves v2 "train then accept", solver effort stays low; a real example must run through before the formal
  experiment; code review with codexdl).
- 2026-10-23 ~15:1x: "我觉得我们的实施可以参考一下skillopt那种多轮反馈的" → v2 also takes SkillOpt's minibatch
  reflection (analysts) and step buffer (history of every earlier proposal and its fate). Not taken: SkillOpt's
  validation-set gate (tenet: no validation set) and a free-text skill (route A, rejected 2026-10-21).

Basis: chain G v1 main (11:18–13:10) ended all five steps `not_run / no_surviving_change` (8 procedures, 0 survived:
C3 description > 600 chars, C4 leakage via the description, C7 self-proof tests). v1 has no training loop.

## Invariants (unchanged from v1)
- Five benches in v3 order, cumulative package, card, router, shell, format guards, solver settings (GLM-5.3,
  thinking on, effort low).
- Acceptance unchanged: fresh acceptance slice, four arms, J1–J7, blocks, redo rules, consumption registry.
- No validation set: training uses only the run slice (already consumed by the run unit) and the examiner's admitted
  G_self items; the acceptance slice is read once, by the acceptance unit.
- C4 leakage (code literals, header, description, notes), static bans, C5 import, C6 zero crash, C8 format guard and
  C9 output screen stay fatal. The engineer and its analysts never see acceptance or test cells.
- Test read once per chain at its end; F = C → not read.
- v1 configurations ("default", "recommended", "main"), their prompts (engineer sha256 c3e80057…), units, namespaces
  and every frozen record keep their exact behaviour.

## New configuration `main-v2`
order BENCHES; slices SLICES; evidence `main_v2_real_run`; root `/data/execskill-20261023-main-v2`; manifest
`/data/execskill-20261023-main-v2-manifest.json`; learning `train`; consumption namespaces `G-v2` / `D-v2` (the same
fixed-order cut reproduces v1's run slices, which are reused as training items; v1's never-dispatched acceptance
slices are fresh). Caps: selftest scope per step = v1 main selftest + training cells at the maximum schedule
(SQ 87.0M, OQ 83.6M, LM 76.7M, SB 69.2M, ALF 227.6M); role caps per step engineer 20M, examiner 10M, research 9.2M;
GLM chain cap 588M; solver cap 1,855M; test read 407M; redo 72M.

## The v2 step
run → diagnose → generate → engineer-r1, train-r1, … engineer-r6, train-r6 → selftest → accept → freeze.

- generate: v2 prompts (policy: use all 24 requests, at least 16 family_material; generator: one spec per material,
  up to 10 parameter sets); up to TOPUP_ROUNDS (2) top-up generator calls while the set is below its band probe
  size, after the initial build and after each band rebuild. G_self is used in training only when admitted.
- engineer-r<r> (incumbent T_{r-1}; T_0 = S):
  1. analysts (SkillOpt minibatch reflection): the incumbent's failed run-slice items, one failed current cell each,
     seeded order, items no earlier round analysed first; groups of 6, at most 4 engineer-role calls
     (`ANALYST_SYSTEM`), each shown card, procedures (id, description, hooks) and its group as the proposal call
     shows failures (with references on QA/table benches); ≤ 3 findings {pattern, items (shown only), helper},
     texts ≤ 300 chars. References the analysts saw count as disclosed for C4.
  2. proposal (`ENGINEER_SYSTEM_V2`): v1 payload over the incumbent's CURRENT cells (12 failures, 6 successes,
     re-sampled per round) + round, history (per earlier round: counts, flags and every proposal's kind, id, target,
     description excerpt ≤ 200 chars — none for a C4-stopped change — and fate), training (last round's feedback),
     lint (advisory replay-test reports), edits (budget vs S), analyses.
  3. checks as v1 except: description cut to 600 / header to 200 before C3 (recorded `truncated`); replay tests
     optional and advisory (lint); C7 = registrar checks (negative tests, reference tracker, bindings) only; up to 3
     fix calls per failing change with measured detail (C1 keys/types, C3 sizes, C4 flagged texts + adjudicator
     reason); a change beyond the step's edit budget vs S (MAX_CHANGES 3, via `rebase`) fails C3 unfixable;
     ≤ 10 engineer calls per unit; ids unique across rounds.
  4. candidate = survivors applied to the incumbent, `rebase`d to S (revisions of step-own procedures inherit their
     S-relative lineage; retired = S.retired + S procedures gone).
- train-r<r> (only with a candidate): routing pass (zero-call) of run items and admitted G_self items under T_{r-1}
  and T'; items whose enabled-id tuples differ are run in both arms (run items with the bench's registered runs,
  G_self once), scope `...:selftest`. Adoption (`train_verdict`): guards (own faults ≤ 2 % of S' cells, predicate
  faults ≤ 2 % of routed items, S' format violations − S's ≤ max(2, ceil(2 % of S' cells))) and gain (fixed >
  broken, net ≥ max(1, ceil(2 % of evaluated)), one-sided sign test p ≤ 1/4). Feedback per added/removed/narrowed
  procedure: enabled items, fixed, broken, ≤ 3 fixed and ≤ 3 broken examples (question ≤ 400, notes ≤ 700, current
  and candidate reply ≤ 240, pass shares, reference only when a round cell failed; never on ALFWorld); generated
  items as counts.
- Stop after 2 consecutive rounds without adoption (a round without candidate counts) or after 6 rounds.
- After the loop: no edit vs S → `not_run / no_training_gain` (smoke SX only: the last evaluated candidate takes the
  self-test and acceptance, recorded `exercise`); else one self-test (a block → `selftest_blocked`), acceptance and
  freeze as v1.

## Smoke stage SX (the owner's "real example")
The v2 step in smoke mode on the SearchQA smoke items [20:280] (run 100, accept 160) with the smoke solver and real
GLM-5.3 roles, after S-E6, on the smoke ledger with example caps (solver 80M, GLM 40M), consumption in the smoke
namespace of its own registry `<root>/units/SX/history`. Rows: unit, training (some train unit evaluated cells),
acceptance (decided accept/reject and reproduced from the sealed record), consumption, ledger. A smoke listing SX
reads the owner's waiver from `shared/owner-smoke-waiver-v2.json` (the earlier waiver stays where it is).
S-E6 of a main-v2 manifest prices engineer 6 × (10 + 4) calls, leakage 72, describer 3, examiner 21, research 192 per
step, the engineer request floor with the longer of the v2 engineer and analyst prompts.

## Deviations from what was told to the owner (to disclose)
- v1 run items are reused as training items (fixed-order cut).
- The description is still leak-checked (C4), only cut to its cap first.
- Per-round examiner generation and pooled detector validation are deferred (generation once per step + top-ups).
- G_self enters training only when the generator is admitted.
- SX exercise rule (acceptance on the last evaluated candidate when nothing was adopted) — smoke only.
- The routing pass uses one shared worker per package on non-SB benches (predicates are pure; C6 replays them).
