# BRIEF v2.22 — `main-v8`: instruction segments routed like procedures, cross-bench no-harm gate (2026-11-03)

Owner decision 2026-11-03 ~19:2x (verbatim): "同意，先写简报，等实验跑完再做 v2.22" — after the owner's reading of cross-v5
("在当前bench进化出来的包会对别的bench有很强的损害，我的想法是不要有损害 … 如何可以在不影响当前bench的情况之下弱化对于其他bench的有害影响").
Build order: this brief → Codex writes v2.22 on top of v2.21 (main-v7) → one read-only review → fix → the Linux full suite →
smoke → launch when a machine is free. Every older configuration stays byte-identical (fingerprints), rollback = run an older
configuration. The frozen GitHub state `route-b-v2.19-frozen-20261102` remains the rollback point. Nothing in the live runs
(`main-v7` on the old machine, `main-v6` G and `searchqa-hp-v6` on dl) is touched.

## 1. What cross-v5 showed (the motivation, with the numbers)

cross-v5 (v2.19, 2026-11-02 11:58 → 11-03 06:35; read-only extraction 11-03 07:52; `docs/handoff/cross-v5-readout-20261103/`)
held the chain-end package fixed and swapped the per-bench INSTRUCTION CARD: arm `X_s` on bench `t` = package + card of `s`
inside `t`'s shell, compared with `C_t` (card of `t`, no package).

1. The routed procedures caused no harm anywhere: on SearchQA, OfficeQA and SpreadsheetBench no procedure fires, `F − C = 0`
   exactly (both chains; F reads C's cells); on ZebraLogic (its shell carries no card) every `X_s` equals F
   (G +5.5…+7.0 vs F +6.5; D +13.0…+14.0 vs F +13.0).
2. Every negative cell is a card effect. Mechanisms (per-arm aggregates in `cross5-readout.json`, `readout/arms`):
   - answer-form mismatch with the official scorer: G SearchQA with the neutral Zebra card: official 85.3 → 73.8 while the
     lenient score rose 82.0 → 84.8 (tags present 399/400); the answer is found but not in the "minimal entity" form;
   - lost format requirement: G OfficeQA single-number replies 157/171 with its own card, 114 with the Zebra card, 134 with
     the ALFWorld card, 123 with the spreadsheet card → official 45.9 → 33.7 / 43.6 / 40.7; the SearchQA card keeps 156 single
     numbers and its "minimal value, match units and granularity" advice fits OfficeQA → +7.6 (24 good / 11 bad);
   - conflicting content guidance (weaker model): D OfficeQA with the SearchQA card: 156 single numbers but official 34.3 →
     15.1 (1 good / 34 bad); D's own SearchQA/OfficeQA cards are worth +17.8/+15.1 over blank, any foreign card falls to blank;
   - a card can hurt its own bench: D SpreadsheetBench C 56.4 < B 60.3 (35 vs 20 format violations); the neutral card 63.2.
3. The cards are not learned: they are the five zero-shot instructions frozen 2026-10-17
   (`v210-instructions-coevo5-v1.json`, generated from the public task card only), one per bench, never swapped in the real
   pipeline. So the method as run already has "no harm" for procedures by construction (routing → byte-identical requests);
   what v2.22 adds is the same construction for the instruction text, plus a gate that proves it on every other bench.

## 2. Design

### 2.1 Card = format block + routed content segments

- **Format block** `fmt_b` (per bench, fixed, short, scorer-aligned): the sentences of the historical card that describe the
  answer form the scorer needs (SearchQA: answer tag + minimal entity, exact match; OfficeQA: single number, digits already
  scaled; SpreadsheetBench: one python block, read `input.xlsx`, write `output.xlsx`; ALFWorld: one `<action>` per reply from
  `admissible_commands`; ZebraLogic: the registered neutral card). It is part of the bench shell's system prompt in EVERY arm
  except B (blank stays blank: no format block, no segments, no procedures) — so the historical B arm keeps its meaning.
- **Content segments**: the remaining sentences of each historical card, grouped into 2–5 segments per bench, each a
  *note procedure* of the package: `applies(view)` = a structural predicate over the public task (not the bench name:
  e.g. "evidence snippets present", "question asks a quantity with a unit/scale", "a workbook preview is present",
  "admissible_commands present"), `before_call` = emit the fixed text as a note (existing `NOTE_HOOKS`, note caps unchanged;
  `max_note_chars` ≤ 1,500 for a segment). Delivery, identity accounting and "touched" counting are the existing ones
  (v2.21: a touched item = request change or an emitted note).
- The chain starts from **P0 = the five benches' own content segments** (all with their home predicates). Arms at every read:
  `B` blank (unchanged), `C0` = format block only, `C` = format block + P0 (instruction only, now routed), `F` = C + learned
  procedures/segments, stage rows `S_k` as before. `C0` is new; `C` replaces the historical card arm. The historical card is
  kept as `C_hist` for ONE decomposition check (2.5), never as a read arm afterwards.
- The engineer may propose **segments** (text + predicate) as well as computational procedures; both go through the same
  training → confirmation → acceptance rule (v2.21). A segment's "fix" must come from its text being delivered (emitted note);
  predicates are written over task structure so that a segment learned on bench s can fire on items of another bench that
  share the structure — this is the intended "transfer to similar benches", and the gate below is what makes it safe.

### 2.2 Cross-bench no-harm gate (new, at confirmation and acceptance)

For every candidate change (new/edited procedure or segment, deletion, narrowing) that reaches confirmation on bench s:
1. **Firing check without a solver** on the registered *harm slices* of the other four benches (fixed, seeded, practice-side:
   60 items each; ALFWorld 20 games), using the sandbox router only (as `engineer_v221.inert_coverage` does): the set of items
   where the candidate package's request would differ from the parent package's (`v221_rule.same_request` semantics).
2. If the candidate fires on 0 items of bench t → identity proven for t at zero model cost; record `{bench: t, fired: 0}`.
3. If it fires on k > 0 items of bench t → run only those k items, parent vs candidate, 1 run each, and require on t:
   net fixed − broken ≥ 0 on the fired items AND whole-slice change ≥ −1 point (the v2.21 harm constant); otherwise the
   candidate is **narrowed** (its predicate restricted so it no longer fires on t's slice) and re-checked, or rejected if it
   cannot be narrowed. The home-bench rule (v2.21) is unchanged.
4. The gate's records (fired counts per bench, fixed/broken on fired items, decision) are written next to the acceptance
   decision; the chain-end read gets a `cross_identity` block per bench: how many test items any non-home procedure/segment
   touched (counted from the F cells; no extra calls).
Costs: ≤ 4 benches × k fired items × 2 runs per candidate reaching confirmation; k ≤ 60 (20 games); typical k = 0.

### 2.3 Card hygiene (own segments are candidates too)

At the start of each bench's step, before training, every own segment of P0 is a *deletion candidate* judged by the v2.21
rule on the first training slice (format block + other own segments vs with the segment). A net-harmful own segment (D's
SpreadsheetBench card: C − B = −5.4, 21 good / 32 bad in cross-v5) is dropped; a neutral one stays. Zero model cost beyond the
training slice already measured (the arms are the same slice; reuse identical requests).

### 2.4 Chain-end read

Same five benches, arms `B, C0, C, F` + stage rows; the cross matrix is no longer a separate run: the `cross_identity`
block proves 0 touched items per non-home bench, or lists them with their fixed/broken counts. A separate cross read like
cross-v5 is only needed when a segment's predicate fires off-home (then the fired items are read, parent vs candidate).

### 2.5 Decomposition check (S0 / smoke, practice side, zero or small cost)

For each bench, on a 100-item practice slice (ALFWorld 20 games), compare `C_hist` (historical card) with `C` (format
block + own segments): require whole-slice ≥ −1 point and the format counters (tag present, single number, program delivered,
action violations) not worse; if a bench fails, keep that card's content verbatim as ONE segment (predicate = home structure)
and move only its format sentences. This is the only place `C_hist` is run. Pre-registered: the split of each card into
format sentences and segments is written in the fixture `tests/fixtures/execskill/v222_cards/` (texts + sha256) and frozen
before S0.

### 2.6 What stays exactly as in main-v7

Benches and order, practice pools, slices and freshness registry, the touched-item rule constants, J3–J6 diagnostics, the
two-judge audit, early accept and keep improving, split sub-candidates, coverage feedback (now also reporting segments),
automatic infra retry, caps (add the harm-slice runs to the per-step caps: + 4 × 60 × 2 calls per confirmed candidate,
bounded by the registered maximum of candidates), consent fields (`sheet_test_qualification: true`), the delegated consent
writer (patch adds `main-v8`), the Linux full-suite pre-test, S0, the structural and measured smokes.

## 3. Deliverables for the writer

1. Modules (new, gated to `is_v222`): `v222_cards.py` (format blocks + segments fixture loading, pins), `v222_gate.py`
   (harm slices, firing check, fired-item runs, narrowing), `v222_hygiene.py`, the arm definitions (`C0`, `C`, `C_hist`
   check), coverage/feedback extensions, S0 and smoke extensions (structural: a segment fires at home and not elsewhere;
   measured: one cross-firing candidate narrowed by the gate), readout extension (`cross_identity`).
2. Fixtures: `v222_cards/` with the five decompositions; regression tests for every new rule; the mutation registry
   extended (a disabled gate must be detected); the 43 + 1 older configuration fingerprints byte-identical.
3. Ops: `m8-env/prep/smoke/launch/run.sh` modelled on `m7-*` (single quotes inside `python -c`), `patch-consent-v222.py`,
   `run-v222-pre.sh`, commit script; the driver judges every step by its LAST log line.
4. Validation record `V222-VALIDATION.json`, `V222-CHANGED-FILES.txt`, `V222-SOURCE-SHA256.json`, a v2.22 section in
   `V29-NOTES.md`. Constraints as before: no network, no model calls, no Docker, no /data, no commits, never open sealed or test
   data, no edits to the three living docs of the SkillOpt repo.

## 4. Pre-registered probe before the build (practice side, cheap; separate brief `PROBE-card-20261103.md`)

On 200 practice items of SearchQA and OfficeQA, both solvers: arms `hist` (historical card), `fmt` (format block only),
`fmt+own` (format block + the card's content as one note), `blank`. Outputs official/lenient accuracy and the format counters.
Expected if §1's mechanism is right: `fmt+own ≈ hist`, `fmt` recovers most of `hist − blank` on SearchQA for G (format-only
loss) but not for D (content loss). This probe does not read any test item and decides nothing by itself; it calibrates the
decomposition in 2.1/2.5.
