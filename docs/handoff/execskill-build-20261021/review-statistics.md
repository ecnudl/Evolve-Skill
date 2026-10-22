# Review: acceptance and readout correctness (route B, protocol fivebench-execskill-v1)

Date: 2026-10-22. Lens: acceptance and readout correctness. Reviewer: adversarial code review, read-only.

## What I looked at

- **Code:** `dl:/data/execskill-dev` (git 010d453 plus the untracked route-B files), read through the SSHFS mirror
  `/Users/dulin/remote/dl`.
- **Against:** `docs/handoff/execskill-registration-v1-20261021.md` (§3.2-3.4, §4.4 scorer v2, §6.1-6.6, §7.1-7.2,
  §8.1-8.3, §9.4, §13 table, §14 #15, §20 Codex F1/F5/F6/F7/F9/F20-F22) and
  `docs/handoff/execskill-implementation-plan-v1-20261021.md` (§1, §2, §8).
- **Modules read:** `acceptance`, `stats_ext`, `router`, `validity`, `detectors` (mechanical categories, `validate`,
  `bootstrap_p`), `trajectories` (masked views), `judge`, `outcomes_ext`, `readout`, `evaluation` (`test_plan`,
  `sealed_cell`, `unseal`), `protocol`, `donors`, `placebo`, `package` (`edits`, `for_bench`), `registry` states,
  `supply` (LiveMath slices), `cells.share_cell`; frozen `coevo5/data.ranked` and `coevo5/step.answered`.
- **Notes and tickets read:** A7, A9, integration B3, integration B5; tickets A7-1, A7-2, A9-2, A9-3.
- **Tests read:** `test_execskill_acceptance.py` (T-ACC-1..8), `test_execskill_stats_ext.py` (T-STATS-1..7),
  `test_execskill_validity.py` (T-VAL-1..4), `test_execskill_readout.py` (T-READ-1), `test_execskill_judge.py`
  (T-JUDGE-1).
- **Tests run on dl:** the acceptance, stats_ext, validity, readout, detectors, judge, router, placebo and
  integration_b3 files. **160 passed** in 61 s.
- **Probes:** four zero-call probes on dl, sent through stdin. Nothing was written into the tree. The outputs are in the
  appendix.
- **Rules kept:** no code edited, no paid call, no test pool opened, no key or `.env` printed.

**On the lens's "|A\*| < 15":** the registration raised the minimum to |A\*| >= 30, and to >= 20 rooms on ALFWorld
(§6.4, Codex F1). The code uses 30 and 20 (`protocol.py:282-283`, `router.py:196-197`), and T-ACC-7 tests 29 against 30.
The code is correct; 15 is the superseded value.

## Checked and found as registered

- **A\* by edit type** (`router.py:166-179`):
  - new: the items where the new procedure fires in S';
  - revision: the items where the old version fires in S or the new one fires in S';
  - deletion and narrowing: the items where the procedure fired in S;
  - the round's A\* is the union.

  A too-small A\* dispatches nothing and releases every item of A as `routed_not_dispatched` (`acceptance.py:216-231`;
  T-ACC-7).
- **Primary test** (`stats_ext.py:65-122`): a one-sided paired t. Blocks are weighted by size, the variance is pooled
  within blocks and df = items - blocks. On ALFWorld the test runs on room means weighted by games, with
  df = rooms - blocks; `acceptance.py:298-301` passes blocks and rooms. T-STATS-1/2 check this by hand.
- **The sensitivity analyses never decide.** The sign-flip flips whole rooms. It enumerates exactly when
  2^units <= n; otherwise it draws 100,000 seeded patterns with p = (1 + hits)/(n + 1) (`stats_ext.py:126-143`). The
  Wilcoxon is the tie-corrected normal approximation. Both are stored under `sensitivity` only
  (`acceptance.py:311-325`). J1 and J2 read `p_t` (`:460-463`). T-STATS-4 catches mutation (24).
- **J1, J2 and the IUT** (`acceptance.py:457-463`):
  - J1 needs `p_t <= alpha` and a whole-batch mean sum(d)/|A| >= 0.02.
  - J2 is S' - P_y with the same design, at 5 %.
  - When the upper 95 % bound of P_y - S is below 0, J2 is "not informative" and J1 runs at 2.5 %. The accept wording
    then says that the content/effort explanation is not excluded (`:493`).
  - A helpful sham is reported (T-ACC-5).
- **J3** (`acceptance.py:327-336`, `:464-466`; `router.py:193-195`): the numerator is the fault items over the whole
  slice A. It counts, in S' or P_y and in any run:
  - routing faults of changed procedures, from the sealed plan (the new id for a revision, the old id for a deletion
    or narrowing);
  - execution faults of changed procedures;
  - `unknown_fault`.

  The share is an integer comparison against |A|, and the T10 boundaries are tested (T-ACC-3).
- **J4** (`acceptance.py:339-343`, `:467-470`): item counts over any run, a margin of max(2, ceil(0.02 |A\*|)), integer
  comparison (T-ACC-4).
- **J5 thresholds** (`:471-480`):
  - infrastructure unknown <= 10 % per non-twin arm;
  - reasoning mismatch after resends <= 1 % (`judge.py:258` reads the logical receipts);
  - shared unanswered <= 10 % of A\*;
  - the arms' median start times within 5 % of the round's duration.
- **J6** (`:521-531`): a two-sided paired t with the round's design; p < 0.01 makes the round undetermined. See finding 2.
- **J7 rule** (`:391-400`): a gain >= 10 points with one-sided p < 0.05 rejects. The LiveMath decision slice holds
  meta-absent items only (`supply.py:320-331`).
- **Item scores** (`stats_ext.py:44-54`): S' and the twins are read on L (unknown and `unknown_fault` count as wrong),
  the controls on H. Shared-unanswered items leave every acceptance contrast (`acceptance.py:281-288`, `:440-441`).
- **Seeds:**
  - twins: `ranked(items, 20261021, "execskill-v1:withhold:<unit>:<p>")[:n//2]` (`router.py:107-110`;
    `coevo5/data.py:173-176` hashes `[seed, tag, task_id]`). At most 2 per item, changed procedures first, then
    inherited ones by firing count (`router.py:113-125`, `:182-192`).
  - yoke: items and donors are each put in their `execskill-v1:yoke:<unit>` order, and the k-th item is paired with
    donor k mod |donors|. Reuse is counted (`router.py:128-140`).
  - P_y's discouragement seed: `execskill-v1:discourage:<unit>:<cell>` (`acceptance.py:206-209`; T-ACC-6).
- **`validity.status`** (`validity.py:103-126`):
  - fewer than 8 rounds: not_evaluable, for both outcomes;
  - refuted takes precedence over validated;
  - refuted: >= 2 disagreeing rounds under the covariance-adjusted pooled SE, or a duplicate interval on the generated
    items that excludes 0;
  - validated: Spearman rho > 0 with permutation p < 0.05 (10,000 permutations, seed 20261021), and a duplicate that is
    clean on both item sets.

  T-VAL-1..4 cover this.
- **The detector residual is defined on the masked view** (`detectors.py:446-455`):
  - the mechanical categories come from `MECHANICAL_MASKED` on the masked view;
  - the residual is the cells that have no masked category and that no accepted detector flags;
  - precision and base rate are computed on the residual;
  - the cluster bootstrap resamples rooms (ALFWorld) or items;
  - Holm runs over the step's candidates at 10 %;
  - recall >= 0.15;
  - the Jaccard against accepted detectors is taken on the full hold half (`:466-480`, `:490-504`).
- **v2 >= official:** v2 equals the completion-aware final token, except for a JSON rescue of a scored fail. Both
  invariants are asserted on every cell (`judge.py:87-91`), and T-JUDGE-1 runs the registered conflict fixtures. See
  findings 6 and 25.
- **Q1** (`readout.py:133-145`): F - C, a one-sided paired t with the read's blocks, Holm over |L|, established at 5 %.
- **Q3 arithmetic** (`readout.py:172-204`): an equal-weight mean with Satterthwaite df. The one-sided 95 % lower bound
  must exceed -5 points under both the complete-case and the adverse reading. An enable rate below 10 % reads as
  "cannot act".
- **Code-vs-text readings** (`readout.py:208-230`) and the **label priority table** (`:262-291`) match the wording
  of §8.2.

## Findings

Summary: 1 BLOCKER, 7 MAJOR, 18 MINOR. Each finding gives its severity, where it is, why it matters and the fix.
BLOCKER here means that the component produces a false registered reading on realistic data and must be fixed before
it is used.

### 1. BLOCKER: the readout scores one shared cell on two opposite sides, which yields false code-vs-text claims

**Where:**
- `readout.py:54-62`: `side` reads F and the twins on L and every other arm on H.
- `readout.py:133-145`, `:158-169`, `:184-204`, `:208-230`: the contrasts that use `side`.
- `evaluation.py:20-21` and `cells.py:401-415`: structural-zero sharing.
- `evaluation.py:625-627`: `unseal` passes `shared_with`, but no readout reads it.

**Why:**
- When F enables nothing on a test item, F, P_F and T_F share C's cell. §8.1 says of this sharing: "结构性零共享 …
  这既不偏" (structural-zero sharing is unbiased). One cell has one token.
- The readout reads F on L and C or T_F on H. So if the shared cell is unknown, F - C = -1 and F - T_F = -1, on an
  item where both arms are literally the same cell.
- Code vs text has no enable-rate guard. On a bench where the package never fires, every F - T_F difference is a
  structural zero, and a handful of shared unknown cells decides the reading.
- Probe 4 used 134 ALFWorld-sized items, with F, C, T_F and P_F identical and nothing enabled:
  - 2 or 3 unknown cells already give "code_transfer_not_worse" and "text_transfer_not_worse" for two arms that never
    differed;
  - 4 unknown cells (3 %) give **"text_better"**, with the two-sided interval [-0.059, -0.001];
  - Q3 correctly says "cannot_act_by_construction" for the same data.
- Probe 3 used 40 items with 4 shared unknown cells:
  - code vs text reads `["text_better", "text_transfer_not_worse"]`;
  - Q3's adverse mean is -0.10, while its complete-case mean is 0.
- The §6.3 mask "所有组都没送达的题退出所有对比" (items no arm got any reply on leave every contrast) is applied
  nowhere in `readout.py`.
- Effects:
  - Q1 and Q2 are biased downward.
  - Q3's adverse reading imputes two different outcomes to one cell.
  - The text readings of code vs text are anti-conservative.
- "The text implementation is better" is the very risk that §8.2 registers in advance, so a false positive there is
  the worst place for this bias.

**Fix:**
- Score items per cell, not per arm. When F (or T_F, or P_F) shares C's cell, the item's difference is 0 by
  construction: either drop such items from the test and report their count, or set d = 0. Apply this to F - C,
  F - T_F and F - P_F.
- Apply the §6.3 shared-unanswered mask before every readout contrast.
- Give code vs text the same guard as Q3: below the enable threshold, report "按构造不起作用" (cannot act by
  construction), never a transfer reading.
- Add a T-READ test with shared unknown cells.

This blocks producing any readout. It does not block data collection: the readout is a pure function of the sealed
cells and can be recomputed after the fix.

### 2. MAJOR: J6 checks one duplicate pair even when two are registered, so a broken pair can be accepted

**Where:** `acceptance.py:521-531`. `validity.py:76-81` uses the same precedence.

**Why:**
- `_duplicate` tests (S_dup, S) when `dup` is set, and (C, S) only otherwise.
- J6 says "每个登记的同文本重复对 … p < 0.01 → 暂停，不出决定" (each registered same-text pair; p < 0.01 → pause,
  no decision).
- Both pairs exist on a realistic pilot path. If step 1's candidate is rejected, S at step 2 is the empty package, so
  S and C are byte-identical (`card_is_parent = not parent.for_bench(bench)`, `:121`). OfficeQA's step 2 also
  registers S_dup (§7.2).
- Probe 2: such a round, with C drifting (S - C = -0.50, two-sided p = 0.0), is decided **accept**. J6 reports only
  {S_dup-S, p 1.0, ok}.
- The S = C pair is the only check of the card arm's empty-package worker path, and C is the test read's primary
  comparator.

**Fix:**
- Test every byte-identical pair the round ran: S - C whenever `card_is_parent`, plus S_dup - S.
- Pause if any of them fails, and record all of them.
- Add a T-ACC-2 case with `dup=True` on an empty parent.

### 3. MAJOR: OfficeQA's two acceptance time blocks run back to back; the registered 2-hour gap is neither enforced nor checked

**Where:**
- `acceptance.py:216-235`: `dispatch` runs the blocks one after another in a single loop.
- `protocol.py:281`: `BLOCK_GAP_SECONDS = {"officeqa": 7_200}` is used nowhere in `skillopt/` or `scripts/`.
- `acceptance.py:238-262`: `runner`.

**Why:**
- §3.3 registers OfficeQA acceptance as "50 × 4，分两段时间各 25 题（相隔至少 2 小时；按段分层）" (two time blocks of
  25 items each, at least 2 hours apart, stratified by block).
- The gap is the design's guard against serving-time drift. §14 #15 cites drift of up to 22-24 points between time
  periods.
- The decision record holds no block start or end times, so the gap cannot be verified afterwards either.
- The B5 note raises a gap only for the test read (open item 6).

**Fix:**
- Make `dispatch`, or the step driver, wait until `BLOCK_GAP_SECONDS[bench]` has passed since the previous block's
  last finish.
- Record each block's dispatch and finish window in the decision.
- In `decide`, return "undetermined" when the measured gap is shorter than the registered one.
- Add a test.

### 4. MAJOR: undetermined rounds never pause, and the documented recipe marks their items "decided"

**Where:**
- `acceptance.py:484-491`: `decide` only writes "undetermined".
- `acceptance.py:216-222`: the `dispatch` docstring says "The caller decides with ``decide`` and then marks the items
  decided".
- Ticket A9-3, step 3: call `registry.decide(...)` after `acceptance.write`, for every verdict.
- `registry.py:38`: the states are registered, dispatched, decided and released.
- `step.py` does not exist (ticket A12-2; see finding 1 of the isolation review).

**Why:**
- J5 (infrastructure, reasoning) and J6 say "暂停" (pause).
- §13's table says "仪器坏了（同文本重复不过、推理不一致 > 1%、交错不平衡）→ 暂停，不出决定；该批记'消耗但未决'" (a
  broken instrument: pause, make no decision, record the batch as consumed but undecided).
- No code raises `Pause`.
- A start-balance failure is labelled "no decision this round" without a pause (`:490`), although §13 lists an
  imbalance among the pause cases.
- Following ticket A9-3 marks an undetermined round's items "decided".

**Fix:**
- In the step driver, raise `cells.Pause` (owner recovery) on any J5 or J6 failure, balance included.
- Call `registry.decide` only for accept and reject. Leave the A\* and probe items of an undetermined round
  "dispatched", which is the registry's form of "consumed but undecided".
- Amend ticket A9-3 and the `dispatch` docstring.
- Cover this in T-STEP-1.

### 5. MAJOR: the reports registered in §6.2, §8.1 and §8.3 are not implemented, and `unseal` drops their inputs

**Where:**
- `readout.py:311-321`: `readout` returns only Q1-Q3, code vs text, labels and format withholding.
- `evaluation.py:605-631`: `unseal` keeps token, v2, kind, `shared_with`, enabled, block, format and flags. It drops
  official, lenient, faults, `fault_kinds`, `worst_delivery`, `dispatch_ts` and `finish_ts`, which `sealed_cell`
  keeps (`:189-214`).
- `protocol.py:323`: `TIME_WINDOW_SECONDS = 900` is unused.
- `decide` reports no per-15-minute series.
- B5 open item 5 acknowledges that the §8.1 splits are missing.

**Why:** nothing computes the following registered reports.
- **§8.3**, per arm and bench, next to every accuracy:
  - official, official completion and lenient scores;
  - the unknown counts;
  - truncation, `over_nominal` and reasoning mismatch;
  - the format flags. `judge._format` has no flag at all for "formula only", "glued code fence" or the level-1
    normalisation share;
  - procedure faults and the enable rate;
  - the short-answer share per 15 minutes.

  Absolute accuracies must also be labelled "本时段" (this period).
- **§8.1:** OfficeQA stratified by answer status and split by "bulletin in training"; LiveMath split by meta option.
- **§6.2:** in every acceptance round, per arm and per 15 minutes, the short-answer share, the answer-format share and
  the reply length. No reply length is kept in any sealed or unsealed record.

**Fix:**
- Carry official, lenient, faults, delivery state and timestamps through `unseal`.
- Add the §8.3 table and the §8.1 splits to `readout`, and the §6.2 time series to `decide`. Store the visible
  completion tokens per cell for the length series.
- Test them in T-READ.

### 6. MAJOR: a SearchQA reply without an answer tag gets two guesses under scorer v2

**Where:**
- `judge.py:28-29` (the disclosed residual) and `:84-91`.
- The frozen `searchqa/evaluator.py:28-39`.
- Note A7, lines 107-109. There is no ticket.

**Why:**
- The registration promises "一种格式不会多一次猜的机会" (a second format never buys a second guess; §4.4, Codex F7).
- Probe 1:
  - `{"answer": "Lyon"}\nParis` passes on the official last line;
  - `{"answer": "Paris"}\nLyon` passes through the JSON rescue (official fail, v2 pass).

  So a reply carrying JSON X and a final line Y passes when either is correct.
- For SearchQA the registration's two promises, v2 >= official and no second guess, contradict each other. The code
  silently chose the first one.
- A procedure that induces JSON-plus-line replies therefore gains on SearchQA. SearchQA is a similar bench in Q2, a
  code-vs-text bench, and the formal chain's acceptance bench. J4 catches this only in acceptance, and only above its
  margin.

**Fix:** an owner or registrar ruling, recorded in a v1.1 note. Either
- (a) treat the tagless last line as SearchQA's official carrier, so that JSON is consulted only when the last line
  is itself the JSON object; or
- (b) keep the rescue, and report a "two-channel" pass count per arm next to every SearchQA number.

Then add a T-JUDGE fixture for the chosen rule.

### 7. MAJOR: ALFWorld readouts ignore room clustering, and unsealed cells carry no rooms

**Where:**
- `readout.py:99-115`: `estimate` passes only strata.
- `readout.py:133-145`, `:184-204`, `:208-230`, `:234-246`: Q1, Q3, code vs text and τ.
- `evaluation.py:605-631`: no room anywhere in `evaluation.py`.

**Why:**
- §6.4 registers the room-cluster t (df = rooms - blocks) as the ALFWorld model, and the readout's docstring says
  that all intervals use "the registered primary model".
- On ALFWorld, the following treat games as independent:
  - Q1 (the recommended pilot learns ALFWorld);
  - Q3 (ALFWorld is the only dissimilar bench in the default pilot);
  - code vs text and τ.
- So the favourable readings ("noninferiority_established", "code/text_transfer_not_worse", "general") rest on
  understated SEs.
- The size of the design effect on the test split depends on the number of `valid_unseen` scenes, which nobody has
  checked.

**Fix:**
- Carry each test game's room through `test_plan`, `sealed_cell` and `unseal`; `supply.task_folder` derives it.
- Pass `clusters` to `paired_t` on ALFWorld, and record the number of rooms.
- Get the owner to confirm that the §8.2 bounds use the §6.4 model.

### 8. MAJOR: the acceptance dispatch order is not the registered single seeded order, and the owner has not signed off

**Where:**
- `acceptance.py:157-169` (`_ordered`) and `:172-196`.
- Ticket A9-2, request 2: still open.
- `tests/test_execskill_acceptance.py:170-180` asserts the new order.

**Why:**
- §6.2 puts every cell of a round into "一个种子顺序 … 绝不按组排序（cal-1/D1 的做法，step.py:105-121）" (one seeded
  order, never sorted by arm, as in cal-1/D1).
- The code instead blocks the order by (set, item, run) unit and seeds the arm order inside each unit.
- Statistically this is benign, perhaps even better for pairing. But it makes the J5 balance guard close to vacuous by
  construction.
- It is still a change to a registered protocol element without sign-off.
- The probe items are placed in the first block (`:190-192`), which is not registered either.

**Fix:** either record the owner's sign-off as a v1.1 amendment (the order, the probe's block and what the guard now
means), or revert to one uniform seeded order and re-derive the balance guard.

### Minor findings

9. **MINOR: J7 cannot be verified, and its sides favour the candidate.**
   - Where: `acceptance.py:186-192`, `:238-262`, `:391-400`.
   - Why:
     - No module builds the options-only view (question stem masked). Probe items are dispatched with whatever
       `tasks[item]["public"]` the caller passes. With the full stem, a genuine improvement would be rejected as a
       shortcut.
     - S' is read on L and C on H. This understates the probe gain, so the guard leans toward accepting.
     - J7 runs in the formal chain only.
   - Fix: build the options-only view inside acceptance from the sealed probe and assert it in a test. Read both probe
     arms on the same side, or count unknowns against S'.

10. **MINOR: the harmful-sham switch uses an unregistered interval.**
    - Where: `acceptance.py:452-459`.
    - Why:
      - The P_y - S 95 % interval that triggers the 2.5 % rule is a donor-clustered percentile bootstrap, with no
        blocks or rooms.
      - Donors are run-slice trajectories (item × run). Two runs of one donor item give the same static note content,
        yet count as separate clusters.
    - Fix: register the method, cluster by donor item, and add blocks and rooms.

11. **MINOR: the separate fault report that J3 requires is missing.**
    - Where: `acceptance.py:464-466`, `:495-511`.
    - Why: J3 says "孪生格与 C、S 组的故障单独报告" (faults in twin cells and in the C and S arms are reported
      separately). The decision record has no such counts.
    - Fix: add per-arm fault-item counts for the twins, C and S.

12. **MINOR: the twin τ intervals ignore the design.**
    - Where: `acceptance.py:373-388`; `readout.py:234-246`.
    - Why: τ's bootstrap uses no blocks and no rooms.
    - Fix: pass `_design` in acceptance, and the read's strata and rooms in the readout.

13. **MINOR: the inherited-twin threshold is counted on A\* instead of A.**
    - Where: `router.py:189-190`.
    - Why: §6.5 says "在本 bench 验收段启用 ≥ 15 道" (fires on at least 15 items of the bench's acceptance slice). The
      code counts firings inside A\* only, so fewer inherited procedures get twins.
    - Fix: count on A (twins are still drawn inside A\*), or register the A\* reading.

14. **MINOR: `decide` raises instead of returning "undetermined".**
    - Where: `acceptance.py:442`; `stats_ext.py:65-88`.
    - Why: when shared-unanswered items or lost rooms leave items <= blocks (or rooms <= blocks on ALFWorld),
      `decide` raises a ValueError. This case should go through J5.
    - Fix: return "undetermined" with J5's reason.

15. **MINOR: the infrastructure guard leaves out the twins.**
    - Where: `acceptance.py:439`, `:471-472`.
    - Why: J5 says "每组" (every arm), but the twin arms are excluded from both the infrastructure share and the
      balance check.
    - Fix: include them, or register the exclusion.

16. **MINOR: the registered MDE is not recorded.**
    - Where: `acceptance.py:120`; ticket A9-3.
    - Why: `mde_registered` is whatever the caller passes, or None. The table in §3.3 registers per-bench estimates:
      SB about 12, OQ about 10, ALF about 9.7, LM 9-10 and SQ about 3.4 points.
    - Fix: transcribe them into `protocol.py`.

17. **MINOR: the validity computation is incomplete.**
    - Where: `validity.py:41-68`, `:71-90`, `:103-126`.
    - Why:
      - The registered sign-agreement rate is not computed.
      - `status` takes a single duplicate control, with no rule for combining the step-1 S = C control with a later
        S_dup.
      - Paused or undetermined rounds still count.
      - `se_gen` and `se_real` ignore OfficeQA's blocks.
    - Fix: add the sign-agreement rate, take a list of controls, exclude paused rounds, and use stratified SEs.

18. **MINOR: the masked residual on the QA benches reads the last reply.**
    - Where: `detectors.py:213-215`, `:249-253`.
    - Why: when the second call was truncated or undelivered, the shell falls back to the first reply. The last reply
      is then not the scored one, so the residual depends on the delivery state.
    - Fix: keep the deciding reply's index in the masked view (it is not answer content) and use it.

19. **MINOR: detector retirement is not implemented.**
    - Where: `detectors.py:518` (`retired_at` is always None); `protocol.py:355` (`DETECTOR_RETIRE_MISSES` is unused).
    - Why: §7.1 says "连续两次不达标就撤掉" (retire a detector after two consecutive misses). This is open item 5 of
      the B5 note.

20. **MINOR: the detector bootstrap seed is unregistered.**
    - Where: `detectors.py:388-389`.
    - Why: the seed is `sha256(SEED:candidates:id)`, not seed 20261021. It is reproducible but not written down
      anywhere.
    - Fix: record it in the registration note.

21. **MINOR: the label Holm families are split by statement type.**
    - Where: `readout.py:249-259`.
    - Why:
      - §8.2 wants the τ intervals Holm-corrected over procedure × bench.
      - The code runs three separate Holm step-downs, "positive", "negative" and "noninferior", each at 2.5 %.
      - These are not simultaneous intervals, and the error rate over the three families is not stated.
    - Fix: register this reading, or use one family of Holm-adjusted (Bonferroni-type) intervals.

22. **MINOR: OfficeQA blocks are ignored outside Q1.**
    - Where: `readout.py:158-169`, `:208-230`, `:234-246`.
    - Why: Q2, code vs text and τ use no strata.

23. **MINOR: Q3's "cannot act" result omits the bound.**
    - Where: `readout.py:190-191`.
    - Why: §8.2 says "同时报告实际下界" (report the actual lower bound as well).
    - Fix: compute the bounds and report them descriptively.

24. **MINOR: P_F is never read, and the code-vs-text sides are asymmetric.**
    - Where: `readout.py:54-57`, `:208-230`.
    - Why:
      - P_F, a registered arm of the test read, appears in no readout, not even a descriptive F - P_F.
      - On cells that are not shared, reading T_F on H against F on L still favours the "text_*" readings whenever
        unknowns occur.
    - Fix: report F - P_F. Read code vs text under both side assignments, as Q3 does.

25. **MINOR: the v2 >= official invariant is enforced by a crash.**
    - Where: `judge.py:90-91`.
    - Why:
      - A cell whose final token is below official (for example, an unknown verdict on a reply that the frozen scorer
        passes) raises a ValueError. That stops the unit instead of recording the conflict.
      - The only coverage is synthetic fixtures; the S0 check on archived v3 and cal-1 cells has not run.
    - Fix: run the judge over the archived cells at S0 and report every conflict.

26. **MINOR: the test-read twins differ between the two chains.**
    - Where: `evaluation.py:175`.
    - Why: `unit = "<chain>/test/<bench>"`, so chains G and D withhold different seeded halves of the same items. This
      matches the registered tag form, but it makes the chains' τ incomparable item by item. B5 raised it for the
      owner.

## Appendix: probe outputs

All four probes were zero-call, ran on dl and were sent through stdin.

```
P1 '{"answer": "Lyon"}\nParis' official=pass final=pass v2=pass carrier=json
P1 '{"answer": "Paris"}\nLyon' official=fail final=fail v2=pass carrier=json
P1 'Lyon\nParis' official=pass final=pass v2=pass carrier=none
P1 'Paris\nLyon' official=fail final=fail v2=fail carrier=none
P2 card_is_parent True dup True
P2 J6 {'pair': 'S_dup-S', 'p_two_sided': 1.0, 'ok': True} decision accept S-C mean -0.5 p2 0.0
P3 code_vs_text identical cells: mean=-0.100 readings=['text_better', 'text_transfer_not_worse']
P3 q3 identical cells: adverse mean=-0.100 lower=-0.181; complete mean=0.000; reading=noninferiority_not_established
P4 unknown=2 mean=-0.0149 ci95=[-0.0357, 0.0059] readings=['code_transfer_not_worse', 'text_transfer_not_worse'] q3=cannot_act_by_construction
P4 unknown=3 mean=-0.0224 ci95=[-0.0478, 0.0030] readings=['code_transfer_not_worse', 'text_transfer_not_worse'] q3=cannot_act_by_construction
P4 unknown=4 mean=-0.0299 ci95=[-0.0590, -0.0007] readings=['text_better', 'text_transfer_not_worse'] q3=cannot_act_by_construction
```

Set-ups:
- P1: `tests.test_execskill_judge.run("searchqa", reply)`.
- P2: `seal(tmp, "empty", dup=True)` from the acceptance tests, with the C arm always passing.
- P3: 40 synthetic ALFWorld items, F = C = T_F, 4 of them unknown, F enabled on half.
- P4: 134 items, F = C = T_F = P_F, nothing enabled.
