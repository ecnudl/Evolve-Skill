# Route B v2.2 — change specification as implemented (2026-10-24)

## Owner decisions (chat, verbatim)
- 2026-10-24 ~12:0x: "你的门槛设的太高了，请你根据具体的进化情况重新设计一下门槛怎么样才合适，我觉得acc变化五个点以上都可以算是有效果，
  不用要求那么高" — redesign the gates from the observed evolution; a 5-point accuracy change counts as an effect.
- 2026-10-24 12:1x, answers to three questions (AskUserQuestion):
  - "新门槛按上面的方案改，可以吗？" → "按这个方案改 (推荐)" — the scheme below, as proposed.
  - "新版本准备好后，现在正在跑的这一轮怎么办？" → "新版好了就停掉旧的 (推荐)" — stop main-v2-1 once v2.2 is ready
    (waiting for a step verdict that is close).
  - "新目录需要一份读测试集的同意书，谁来写？" → "授权你代写，内容同上次 (推荐)" — the read consent of the new root is
    written by the agent under this delegation, with the same content as last time (the owner's main-v2 consent, as
    the delegated main-v2-1 consent was); its note discloses the delegation.

## Why (main-v2-1, run 0eef0699…, 2026-10-24 04:05 – 12:05)
- The engineer wrote 33 programs: 8 passed the checks at once, 19 after fix calls, 14 died (C9 7, C4 4, C3 2, C6 1).
  17 training rounds completed: 12 trained a candidate, 3 adopted one (G s3 LiveMath 2 fixed / 0 broken of 22 items;
  D s3 LiveMath 7 / 3 of 113; G s4 SpreadsheetBench round 1, 12 / 5 of 31), 5 had no candidate. Rejected rounds
  include G s2 round 1 (1 fixed / 0 broken: the sign test needs p <= 1/4).
- Two acceptance gates decided everything that reached acceptance:
  - G s3: not run, |A*| = 12 < 30 (A* = the acceptance items the package routes differently; a narrowly firing
    package can never reach the fixed floor of 30).
  - D s3: run on 91 A* items (1,128 cells): S' - S +9.9 points over A* (+9.0 over the whole batch, one-sided p 0.003),
    but S' - P_y +1.1 (p 0.38) -> rejected by J2 (the yoked sham, same predicates, length-matched irrelevant note,
    did nearly as well: P_y - S +8.8). J3-J7 held.
- D s3's adopted pair contained `p-livemath-3-3`, a detector that fired on no item and rode along with the effective
  procedure.

## Changes (configuration main-v2-2 only; every earlier configuration is unchanged)
1. Training gate (`step.train_verdict(..., sign=False)`, `protocol.TRAIN_SIGN[main-v2-2] = False`): the one-sided
   exact sign test of fixed against broken is recorded (`p_sign`, `sign_required: false`) and no longer required.
   Adoption still needs every guard (S' cells with a fault of a changed procedure or `unknown_fault` <= 2 %, predicate
   faults <= 2 % of the routed items, format violations at most max(2, 2 %) above S) and fixed > broken and
   net >= max(1, ceil(2 % of the evaluated items)).
2. Idle-procedure pruning (`step.prune_idle`, `protocol.PRUNE_NON_FIRING[main-v2-2] = True`): in `_train_eval`, after
   the zero-call routing pass and before any cell, every procedure the round wrote (not in the incumbent) that the
   pass enables on no evaluated item and on which no predicate faults is withheld (`package.withhold`, re-validated
   against the step parent). A predicate is a pure function of the view (C6), so the pruned candidate routes every
   evaluated item exactly as the proposed one: the round's cells and verdict are unchanged, only code without any
   evidence is dropped (a revision that fires nowhere leaves its old version retired: the round tests the deletion it
   routed). The pruned package is saved; the unit records `proposed_sha256` and `pruned`; the round's history shows
   the fate `pruned_no_firing`; the round's candidate, an adoption, the self-test and acceptance use the pruned
   package.
3. Acceptance (`acceptance.prepare(..., rule=PRACTICAL_RULE)` from `protocol.ACCEPT_RULES[main-v2-2]`): the rule is
   sealed in `sealed.json` (`rule`) with its |A*| floor in the firing plan (`minimum`); `decide` replaces J1 and J2
   (`acceptance._practical`, exact arithmetic on the per-item differences over the answered A* items, the whole batch
   dividing by |A|):
   - J1 holds when the whole-batch S' - S is at least 5 points, or, on SearchQA only, at least 2 points with the
     one-sided paired t p <= 0.05 (SearchQA's 1,000-item slice has an MDE of 3.4 points);
   - J2 records S' - P_y and labels the effect "content" (at least 5 points over P_y) or "form"; it never decides;
   - J3 (faults <= 2 %), J4 (format), J5/J6 (instrument guards -> undetermined), J7 (LiveMath options-only probe)
     unchanged; every recorded contrast (S' - S, S' - P_y, S' - C, S - C, P_y - S by donor, P_i - S, tau) unchanged;
   - |A*| floor min(30, max(ceil(5 % of |A|), blocks + 2)), ALFWorld also min(20, blocks + 2) rooms: LiveMath 5,
     OfficeQA 4, SpreadsheetBench 3, SearchQA 30, ALFWorld 8 games / 6 rooms. Below ceil(5 % of |A|) items no package
     can gain 5 points over the whole batch (an item gains at most 1); blocks + 2 keeps the blocked t-test of the
     recorded contrasts defined with one unanswered item (`decide` needs more answered items than blocks).
   - A round sealed without a rule (every earlier configuration and every existing record) is decided exactly as
     before (`decide` reads `sealed.get("rule")`).
4. Freshness label `route_b_v2_1_slices_reused` (`protocol.ACCEPT_FRESHNESS`): main-v2-2 reuses the fixed-order cut
   (fresh consumption namespaces G-v2-2 / D-v2-2), and main-v2-1 dispatched chain D's LiveMath acceptance slice and
   probe and chain G's SpreadsheetBench acceptance slice. The gates were chosen after seeing main-v2-1's acceptance
   results, so every v2.2 acceptance decision is selection evidence only; the method effect is judged on the test
   split (the stage reads and the chain-end read, unchanged).
5. Plumbing: `MAIN_V2_2` in CONFIGURATIONS (PILOTS copy), LEARNING train, FIX_ECHO False and META_COUNTERFACTUAL True
   (v2.1's engineer rules), STAGE_READ, TEST_READ_CELLS and every CONFIG_* table as main-v2, COST_CHECK_PAUSES False,
   REAL_RUN_EVIDENCE `main_v2_2_real_run`, root `/data/execskill-20261024-main-v2-2`, manifest
   `/data/execskill-20261024-main-v2-2-manifest.json`, namespaces G-v2-2 / D-v2-2; `routes.check_pins` requires
   chain D's route-B pin. Prompts and their hashes, slices, caps, schedules and factors are main-v2's.

## Known limits (registered, to disclose)
- The gates were set after seeing main-v2-1's acceptance; under them D s3 would have been accepted (+9.0 points,
  label "form", J3-J7 held). Acceptance decisions under v2.2 are selection evidence, never a method-effect claim.
- 5 points over the whole batch is below the registered MDEs of SpreadsheetBench (12.1), OfficeQA (10), ALFWorld
  (9.7) and LiveMath (10): at these slice sizes an accepted gain can be noise (cal-1: 30 of 194 items move when the
  same text is re-run). The label "form" marks a gain a length-matched sham produces as well.
- Without the sign test a round adopts on one fixed item and none broken; the self-test and acceptance remain.
- A small A* (e.g. 4 OfficeQA items x 4 runs) gives a noisy t-test; only SearchQA's significance path uses p.
- A pruned procedure might have fired on test items; it is dropped for lack of any training evidence.
- Under the rule a round whose answered A* items leave the t-test no degree of freedom (no more answered units --
  rooms on ALFWorld, else items -- than the blocks they fall in) is undetermined: the chain pauses for the owner's
  recovery, the batch consumed but undecided (Codex review MAJOR 1; before the fix it raised).

## Validation (zero-call)
- Real records: main-v2-1's D s3 sealed round and cells re-decided with snapshot-g code and with v2.2 code: the
  recorded decision reproduces exactly under the registered rule (reject, J2); under PRACTICAL_RULE it is "accept"
  ("J1 (practical-v2-2: +9.0 points over the whole batch) and J3-J7 hold; placebo label form"), the same contrasts and
  J3-J7. G s3's plan (|A*| 12) would run under its floor of 5. Report `/root/ops2-20261022/logs/v22/validate-v22.json`.
- Tests: `tests/test_execskill_v22.py` (14 tests: configuration, floors, training verdict, pruning, sealing,
  the rule's decisions and boundaries, SearchQA's significance path, two T-STEP-V2 steps under main-v2-2 -- one
  accepting under the rule, one pruning a procedure that fires on no evaluated item -- and, after the Codex review,
  a round left with too few answered units, the ALFWorld rooms check and the harmful-sham label); four existing
  tests adapted
  (the protocol test's exact tables and namespace set; the B1 integration test's exact namespace set; v2.1's
  engineer-rule sets now include main-v2-2).

## Codex review (one round, 2026-10-24 15:0x)
Verdict NOT ACCEPTABLE, 1 MAJOR and 2 MINOR, no BLOCKER; all three fixed (`codex-review-v22.md`, this folder): (1)
under the rule, too few answered units for the t-test give an explicit undetermined decision instead of an exception
(`acceptance._too_few_units`); (2) a training round's record names the package its cells ran (the pruned one), the
engineered one as `proposed_sha256`; (3) a harmful sham under the rule is labelled `harmful_sham_reported`. Every
earlier configuration's records are unchanged; the D s3 what-if re-run with the fixed code is identical.

## Launch (zero-call preconditions, then the run)
As for v2.1: the smoke of record is the v2 smoke on snapshot e (S-E6 projected main-v2; SX passed; S2.format waived
by the owner's v2 waiver). main-v2-2 is priced exactly as main-v2 (`main22_delta.priced_as_main_v2`), so the test-read
estimate is the record S-E6 projected. Snapshot h = g + the reviewed v2.2 patch; `main22_delta.py` checks e -> h
exactly (snapshot lists, git parents and the three reviewed patch hashes, code map, clients, runtime, echo sets,
q23-h vs q23-e). Order: registered test selection → commit h → `main22-snapshot.sh h` → `main22-q23.sh` →
`main22-consent.sh` (delegated) → main-v2-1 stopped (owner 12:1x "新版好了就停掉旧的"; G s4's running acceptance is
let finish when it is close) → `main22-go.sh` (no route-B process or container left) → `main22-pins.sh` →
`main22-manifest.sh` → `main-tls.py` → chain G → G's first-call confirmation → chain D on route A → D's
confirmation.
