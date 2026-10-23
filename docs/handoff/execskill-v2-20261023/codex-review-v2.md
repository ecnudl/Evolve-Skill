# Codex review of route B v2 "train then accept" (one round) — 2026-10-23

- Reviewer: codexdl, `-m gpt-6-astra -c model_reasoning_effort="ultra" -s read-only`, on a mirror of the dl dev tree
  without `data/` (brief: the v2 specification `spec-v2.md` and the changed modules), 15:2x–15:3x.
- Verdict: **NOT ACCEPTABLE — 5 MAJOR, 0 BLOCKER.** Codex reproduced #3, #4 and #5 in memory; seven pure-function v2
  checks passed; no model call, no data access.
- Rule: one round; every MAJOR fixed (15:4x–16:0x); no second round unless the smoke fails.

| # | Finding (Codex) | Fix |
|---|---|---|
| 1 | `manifest.prompt_sha()` added the v2 prompts to every manifest: v1 manifests (default, recommended, main) would fail their key-set and smoke-equality checks. | `prompt_sha(configuration)`: v1 configurations bind exactly the original three hashes; only a training configuration (`protocol.LEARNING` = "train", i.e. main-v2) adds `v2` (engineer, analyst, examiner). |
| 2 | v1 smoke records changed: `smoke.make()` serialized the expanded plan and `summary()` reported `SX: not_required`, changing spec/result hashes (and so a waiver's binding). | `smoke.V1_STAGES`/`plan_of`: SX enters a spec's plan and its summary only when the spec lists SX; a v1 spec serializes, defaults and sums up exactly as before. |
| 3 | History could carry a SpreadsheetBench reference that C4 had forgotten: descriptions of proposals stopped before C4 stayed in the history while the disclosure set reset each round. | The history shows a description excerpt only for a change whose final version passed C4; the run-slice items whose table-shape references any earlier round disclosed are carried (`disclosed`) and counted by C4 in every later round, and read back from the sealed engineer records on a restart. |
| 4 | `engineer.Context` accepted foreign feedback through unchecked fields (history scalars, lint dicts, example task/cell pairs checked independently). | Exact field schemas for the history (`step._line`), the training feedback (`step._feedback`) and the lint (`_lint`); each example's cell is checked against its task, unit and round. |
| 5 | Large training feedback (full SpreadsheetBench reference maps) could exceed the 220,000-byte input after every trajectory was dropped, stalling the round on every resume. | `fit()` also trims the feedback deterministically (examples, then references) within `ROLE_INPUT_BYTES`, keeping the C4 disclosure tracking exact. |

Tests: new and changed tests in tests/test_execskill_v2.py and tests/test_execskill_v2_step.py; v1 behaviour pinned by the
existing protocol/smoke/manifest tests (the full suite at the GO commit: 1,469 passed).
