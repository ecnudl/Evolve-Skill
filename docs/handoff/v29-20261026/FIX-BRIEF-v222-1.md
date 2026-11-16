# FIX brief v2.22-1 — decisions on the three smoke blockers (2026-11-03 22:1x)

Decided under the owner's standing night mandate (2026-11-03 19:2x: explore freely, run experiments, build v2.22 after the
brief). These decisions revise BRIEF-v222-main-v8.md where it conflicted with the practice supply and with the call economics;
everything else in the brief stands. Configuration name stays `main-v8`; no older configuration may change (re-verify the 44
fingerprints after the fix).

## D1 practice_supply — available-count denominators instead of exact counts

- The decomposition check (C_hist vs C) and every cross-bench harm slice draw from ALL practice items of the bench EXCEPT the
  bench's own registered ACCEPTANCE allocation (that stays unseen). The run/training and confirmation allocations may be used
  (the cross gate only reports counts; its item rows never reach the engineer, which v222_feedback already guarantees).
- Sizes: decomposition = min(100, available) items (ALFWorld min(20, available) games); harm slice = min(60, available)
  (ALFWorld min(20, available)); seeded as now; the decomposition slice and the harm slice may overlap. Floor: available < 18
  stops S0 with the explicit reason (no silent reduction below 18).
- The ACTUAL sizes are registered in the manifest/S0 record (`v222_practice_supply`), the whole-slice floor is applied to the
  actual n, and `check_decomposition` / `check_measured` verify the registered actual counts instead of the literal 100/60.
- The optional SHA-pinned extra practice supply stays available but is not required.

## D2 hygiene_measurement — hygiene = ordinary measured candidates, no pause, no zero-call assumption

- Drop the "zero extra calls" requirement and the pre-training pause. A deletion of one own P0 segment is an ordinary
  candidate edit: the controller proposes at most ONE deletion candidate per training round (the segment whose touched items in
  the round's parent cells show the worst net, only when net < 0 on ≥ 3 touched items; else none), and that candidate goes
  through the unchanged main-v7 train → confirm → accept rules and the cross-bench gate like any engineer candidate, inside the
  existing per-round candidate caps (it counts as one of the confirmation candidates) and the existing training reservations
  (its touched-item cells are paid like any candidate's). No new caps, no new role calls.
- No hygiene on ALFWorld (import-only step, no training rounds) and none on a bench that fell back to the whole card (D3).
- Record `hygiene_mode = "measured_candidates"`; the `blocked_owner_measurement...` pending path is removed from main-v8.

## D3 verbatim_fallback_cap — whole-card fallback per bench

- If a bench fails the decomposition check (whole accuracy < −1 pp or format counters worse), that bench keeps its WHOLE
  historical card in the shell for every arm except B (exactly main-v7 behaviour for that bench), P0 has no segments for it,
  hygiene is off for it, and the record says `decomposition[bench] = "whole_card_fallback"` with the measured numbers. S0 and the
  smoke continue; the chain-end read's C arm for that bench is then format+whole card = the historical C. Remove the oversized
  verbatim-remainder path (no 1,500-character verbatim fallback, no truncation, no cap change).

## Also

- The m7 ops scripts exist outside this tree (operator side); keep your m8 templates as references, the operator adapts them.
- Add regression tests for D1 (actual-count registration, floor stop, acceptance allocation excluded, overlap allowed), D2
  (one candidate per round, net<0 on ≥3 touched items trigger, counted inside the caps, none on ALF / whole-card benches) and
  D3 (fallback keeps the historical card byte-identical to main-v7's C request for that bench; other benches unaffected).
- Then re-run the v214–v222 selections and the macOS-supported broad run, recompute the fingerprints, refresh
  V222-VALIDATION.json / V222-CHANGED-FILES.txt / V222-SOURCE-SHA256.json and the v2.22 section of V29-NOTES.md (append a
  "fix 1" paragraph), and report: what changed per decision, test counts, remaining blockers (expected: only "review and Linux
  full suite" and the real smoke).
- Constraints unchanged: no network/model/paid calls, no Docker, no dl or /data access, no commits, no secrets, never open sealed
  or test data, no edits to docs/current-workflow.md, docs/project-status.md, docs/results-and-lessons.md.
