# Route B v2 — stage reads: evaluate every step's package on all five test sets (2026-10-23)

## Owner decision (chat, verbatim)
- 2026-10-23 ~16:0x: "一会都跑好了演示和烟测之后直接启动主实验就行，我说的主实验是指在五个bench上逐个进化，并且每个进化之后
  都在所有的五个bench上评测的意思，请你把这一条记住，不是逐个在五个bench上进化，评测"
  → the main experiment = the five benches evolved one after another (SQ → OQ → LM → SB → ALF) AND, after EVERY step,
  that step's package evaluated on ALL FIVE test sets: a stage-by-stage table (row 0 = card only, row k = after step k).

## What v1/v2 had
One test read per chain at its end, five units (one per bench), arms F (final package), C (card only), P_F (placebo
notes), T_F (frozen descriptions as text), withholding twins F∖p; F = C → not read. Intermediate packages were never
evaluated on the test sets.

## Design (main-v2 only; `protocol.STAGE_READ`)
- Still ONE read per chain, at its end, in the SAME five units. Each unit adds stage arms `S<k>`: one per package that
  step k passed on, that holds a procedure, is not F and was not passed on by an earlier step (`evaluation.stage_rows`,
  from the chain's sealed `s<k>-<bench>/step.json` records). Row k of the stage table reads C (no procedure), F, or the
  stage arm of the first step that passed that package on.
- Why at the end and in the same units (not one read after each step): evaluation never feeds back into evolution, so
  the numbers are the same as reading after each step; reading all rows in one seeded interleaved order, at the same
  time, removes serving-drift between rows; the chain, its smoke and its pins stay as they are.
- Routing (zero calls, `evaluation.stage_plan`): each stage package is routed on every item. A predicate runs in a
  namespace of its own (sandbox worker.py), so where all of a stage package's procedures for the bench are F's (same id,
  byte-identical) its routes are taken from F's plan routes (no worker starts); otherwise it is routed in its own
  worker per item.
- Sharing (common random numbers): a stage cell sends nothing where its enabled procedures — ids and byte-identical
  procedures, in order — are those of a cell the unit runs: none → C's cell (`cells.share_cell`, the existing
  structural-zero rule); F's → F's cell; an earlier stage arm's running cell → that cell (`cells.share_same`). Then the
  solver request is identical, so a row differs from the previous one only on items whose enabled procedures changed.
  If the source cell did not actually run with the planned procedures (its recorded `enabled` differs, e.g. a
  predicate timeout), or recorded any fault (a faulted hook drops its notes without changing `enabled`, so its request
  is not the fault-free one), the stage cell runs itself after the blocks (`fallback`, counted); `share_same` refuses
  a faulted source as the second guard (Codex stage review #1).
- F's routes are reused for a stage package on an item only where none of the stage package's procedures faulted in
  F's routing of that item; such an item is routed in the stage package's own worker (Codex stage review #2). The unit
  record counts, per stage arm, the items whose route was taken from F's (`derived`).
- Consent: a main-v2 read needs the owner's `shared/consent.json` naming `multi_arm_arms` =
  ["F","C","P_F","T_F","twins","stages"] (`protocol.read_arms_of`); `chain.read_consent`, the read child and the unit
  itself (`evaluate(..., stages, run_configuration)`, before an attempt opens or a panel is read: Codex stage review
  #4) check the exact set for the configuration; a consent naming only the v1 arms leaves the chain waiting (no read
  attempt).
- Every stage read's unit record names the stage table's rows (`stages`), also when they are C and F alone (step 1
  already passed F on, or only the last step accepted): no stage arm runs then, the table is still reported (Codex
  stage review #3).
- Not read: in main-v2 only when no step passed on a package with a procedure (F = C alone no longer decides: a later
  step could delete every procedure while an earlier package still holds one; then F is that empty package).
- Readout (`readout.stage_table`): per bench and row: the row's arm, accuracy on L and H over the masked items, and the
  paired contrasts row − C and row − previous row (paired t with OfficeQA blocks / ALFWorld rooms, bootstrap beside it),
  description only. Stage arms are read on L like F. The unseal names the arm a shared cell reads (`shared_arm`).
- Budget: the estimate prices 4 + 4 procedure arms per fired item (`protocol.estimate_arms`); main-v2's read cells add
  4 × n per bench; the test-read cap follows main's rule: 3 × (maximum read 160.8M + 5 × 16 × 520,192) → 608M (main:
  407M); main-v2's solver cap → 2,055M (was 1,855M). At the high anchors the estimate is 144.1M (main 77.3M); the 1.3×
  start rule needs 187.3M ≤ 608M.

## v1 untouched
default/recommended/main: same arms, consent set, estimate arms (4), caps, not-read rule, records. The only shared
code paths that changed shape: `consent(shared)` without a configuration accepts either registered arm set (form
check; the configuration-specific checks are the gate), the unseal adds `shared_arm` per cell (None or "C" in v1), the
readout's `_source` reads `shared_arm` (absent → "C" as before).

## Codex review (one round, 2026-10-23 16:4x) and fixes
NOT ACCEPTABLE with 4 MAJOR, 0 BLOCKER (codex-review-stage.md); all four fixed with a test each, each test checked to
fail when its fix is reverted (5 reverted variants, all caught); no second round (the smoke validates the code).
