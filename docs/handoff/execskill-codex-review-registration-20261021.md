Reviewed read-only; no paid calls or test-pool data were accessed. The calculation script reproduces its stored output exactly.

References: **R** = [registration](execskill-registration-v1-20261021.md), **P** = [implementation plan](execskill-implementation-plan-v1-20261021.md), **C** = [calculation script](execskill-calc-20261021.py). Line numbers below refer to these files.

1. **BLOCKER — The claimed ≤5% false-acceptance guarantee is false for the registered mean-effect null.**

   **Location:** R §6.4, lines 435–449; glossary line 988, which says sign flipping requires no distributional assumptions; P line 331.

   **Why:** Sign flipping requires appropriate sign symmetry or exchangeability. Zero mean alone does not suffice. An exact counterexample uses permitted OfficeQA four-repeat increments: with 15 A* items, let each difference be +0.25 with probability 0.8 and −1 with probability 0.2. The true mean is zero. Fourteen positive differences give sign-flip p = 0.044921875; fifteen also reject. Their combined probability is **16.71%**. Both cases exceed the whole-batch +0.02 threshold when A contains 50 items. If parent and placebo scores coincide, both IUT tests reject together: the IUT does not repair the invalid marginal tests.

   **Fix:** Specify the estimand, null and sampling/randomization assumptions. For mean superiority, use an appropriate bounded-mean confidence procedure or justified, calibrated cluster-level method. Alternatively restrict the claim to the exchangeability null actually tested. Include skewed, heterogeneous nulls in verification.

2. **MAJOR — “No validation set” misdescribes the selection mechanism.**

   **Location:** R lines 26–28, 199–206 and 259–275.

   **Why:** A candidate is constructed without A*, then accepted using A*: this is a one-use validation/acceptance subset. Calling its source “training” does not change its function. Moreover, SpreadsheetBench and OfficeQA have zero historically unused and zero method-side unused items. The new registry prevents future reuse; it cannot remove historical adaptation.

   **Fix:** Say **“no reusable validation set; one-use acceptance batches drawn from training pools.”** Preserve the historical-reuse disclosure and distinguish development/selection evidence from independent generalization evidence.

3. **MAJOR — Joint power is not calculated from the model used for the MDEs.**

   **Location:** R lines 247–255 and 466–479; C lines 20, 59–61 and 78–85.

   **Why:** Multiplying marginal power by a constant 0.85–0.90 is unsupported. Under equal-variance normal contrasts with correlation 0.5, the script’s 1.135 MDE multiplier gives approximately 80.27% joint power at the quoted MDE—consistent with its calibration. Yet the same model gives joint power at +5 points of approximately **0.172 for SpreadsheetBench and 0.246 for OfficeQA**, versus the claimed 0.27–0.29 and 0.35–0.37. The corresponding independent-step probability of accepting neither is approximately **0.625**, versus 0.45–0.48. The alternative 0.13/0.18 figures are inserted constants.

   **Fix:** Calculate MDE and joint power from one explicit covariance model. Show sensitivity to placebo effects, A* coverage, room/yoke dependence and guard failures. Distinguish two-test power from the probability of passing all J1–J7 criteria.

4. **BLOCKER — Dynamic yoked placebos cannot follow the registered sealing and interleaving schedule.**

   **Location:** R lines 274–275, 402, 411–425; P line 50.

   **Why:** Another acceptance item’s ALFWorld state at the same step, or its sheet-feedback output, does not exist until its trajectory executes. Nevertheless, placebos must be sealed before dispatch and all arms must run in one interleaved schedule. No donor arm, dependency schedule or donor-call budget is defined. Waiting for donor trajectories can also deadlock occupied episode slots.

   **Fix:** Use a frozen training-side donor corpus or outputs computable solely from public inputs before dispatch. Specify donor eligibility, pairing, unavailable steps and content hashes. Otherwise register a staged experiment with different timing controls and costs. Account for cross-item yoke dependence in inference.

5. **MAJOR — The harmful-placebo fallback does not exclude the claimed alternative explanation.**

   **Location:** R lines 409–416 and 953–954.

   **Why:** Superiority over the parent at 2.5% cannot exclude benefits from generic scaffolding or additional inference. Wrong-task numbers and randomly discouraged actions can actively harm the placebo. Also, running the same repair-trigger function on different trajectories does **not** enforce identical call counts, contrary to line 953.

   **Fix:** When the sham is harmful, report only superiority over the parent. Require a prespecified adequate content/call control before making an execution-specific claim. Replace “exact call-count matching” with the actual rule and report call-count differences.

6. **MAJOR — Revision, deletion and narrowing controls are not defined correctly.**

   **Location:** R lines 306, 402 and 453–455.

   **Why:** With one revision, candidate−parent estimates replacing the old procedure with the new one; withholding the new procedure estimates its presence versus absence. These are different effects. For deletion, the deleted procedure is already absent from the candidate, so withholding it changes nothing. “Parent plus shams for changed procedures” is likewise incomplete for deletion/narrowing.

   **Fix:** Define an explicit transformation table for each edit type: A* uses old/new routing where applicable; deletion uses restoration controls; revision distinguishes replacement from presence effects; every edit has a defined placebo. Restrict the single-change shortcut to cases where the estimands actually coincide.

7. **MAJOR — Scorer v2 awards multiple guesses through different answer formats.**

   **Location:** R lines 319–321 and 439–440; P line 51.

   **Why:** Under “official correct **OR** JSON correct,” `<answer>A</answer> {"answer":"B"}` can pass when either A or B is correct. The frozen scorer reads A from the tag ([backends.py:491](../../skillopt/continual_eval/backends.py#L491)), while the frozen single-letter format check still passes ([checks.py:35](../../skillopt/coevo5/checks.py#L35)). Thus J4 does not necessarily prevent this metric exploit.

   **Fix:** Choose one answer using reference-independent precedence. For example, use a valid official answer carrier first, and JSON only when that carrier is unusable. Add conflicting-tag/JSON fixtures. Supporting additional formats should not grant additional guesses.

8. **MAJOR — Generator “truth” can be accepted by construction.**

   **Location:** R §7.2, lines 502–508; P lines 63 and 338.

   **Why:** Reproducing one OfficeQA answer does not establish that a proposed formula remains correct after perturbation. Evaluating an examiner-supplied LiveMath expression accurately does not establish that it answers the generated question. Spreadsheet qualification explicitly submits the reference workbook as the prediction and scores it against itself ([qualify.py:38](../../skillopt/coevo5/qualify.py#L38), [qualify.py:101](../../skillopt/coevo5/qualify.py#L101)). Recalculation also cannot update literal answers without a reference transformation.

   **Fix:** Restrict generation to independently verified transformation families with fixed reference functions or simulators. Separate semantic correctness from scorer/engine qualification. Drop transformations without an independently specified answer mapping.

9. **MAJOR — Predictive validity is statistically dependent and operationally undecidable.**

   **Location:** R lines 518–524; P lines 68 and 339.

   **Why:** The contrasts share outcomes and obey identities such as  
   `S′−P_y = (S′−S) − (P_y−S)`. Eight contrast rows are not eight independent comparisons. Selection by a real-effect interval excluding zero also excludes genuine null controls from eligibility. The regression, permutation unit, covariance treatment and “negative controls pass” threshold are unspecified. `P_y−S` is not a known-zero control: §6.1 expressly allows helpful/harmful shams. Finally, positive slope and two large disagreements can coexist, permitting both “validated” and “refuted.”

   **Fix:** Define independent evidence units, preferably fresh candidate rounds; specify the complete covariance-aware analysis and numerical control criteria. Use genuine duplicate controls, account for paired generated/real uncertainty, and make statuses mutually exclusive.

10. **MAJOR — The ten-step ALFWorld detector mask still reveals early termination.**

    **Location:** R lines 486–495; P lines 336–337.

    **Why:** A prefix of `min(T,10)` steps reveals whether an episode ended before ten steps. The frozen loop exits on `won` or `done` ([backends.py:768](../../skillopt/continual_eval/backends.py#L768)). Consequently, prefix length and terminal observations can distinguish early successes without learning a failure mechanism. Testing only a `len(steps)==50` detector misses this.

    **Fix:** Define a landmark prediction task among episodes still active immediately before step ten. Supply a fixed-length nonterminal view, handle infrastructure censoring explicitly, and report early terminations separately. Test short successful trajectories and terminal-text leakage.

11. **MAJOR — Detector validation ignores room dependence and candidate selection.**

    **Location:** R lines 218–219, 348–354 and 493–498; P line 62.

    **Why:** ALFWorld detector author/validation halves are split by task and bootstrapped by task, although multiple games share rooms. The same room can occur in both halves; six tasks may represent only two rooms. Up to three detectors are selected using individual 90% bounds without a declared family-error policy. If Jaccard is calculated on residual cells, overlap with existing detectors is zero by construction.

    **Fix:** Split and resample by room, require enough independent rooms, and recalculate feasibility. Freeze candidates before validation and specify multiplicity handling or label selection exploratory. Calculate Jaccard on the full masked validation half before residualization.

12. **MAJOR — Frozen preflight defeats the registered second-call fallback.**

    **Location:** R lines 159–160 versus P5 at line 332; P lines 52, 54 and 206.

    **Why:** The text disagrees about whether a delivered but truncated repair is used. More importantly, frozen [cells.py:196](../../skillopt/coevo5/cells.py#L196) invokes preflight before scoring/classification. Preflight applies delivery checks ([outcomes.py:215](../../skillopt/coevo5/outcomes.py#L215)), which inspect the last receipt ([outcomes.py:256](../../skillopt/coevo5/outcomes.py#L256)). A failed repair can therefore turn a valid first program into unknown/fail before the proposed classification wrapper runs.

    **Fix:** Adapt preflight as well as classification: scan all receipts for mandatory stops, score the deciding receipt, and record worst delivery separately. Test valid-first/failed-second and valid-first/truncated-second cases through actual scoring.

13. **MAJOR — Replay confuses transport sends with logical solver calls.**

    **Location:** P lines 54, 332 and 358: “ORDERED list of sends.”

    **Why:** The frozen recorder may send several times for one logical call, recording each send but returning only the final receipt ([calls.py:214](../../skillopt/coevo5/calls.py#L214), [calls.py:268](../../skillopt/coevo5/calls.py#L268)). Replaying unsuccessful transport attempts as solver replies changes control flow and request matching.

    **Fix:** Persist logical-call boundaries, returned receipts and associated send indices. Replay logical replies; retain transport sends for accounting. Add a combined resend + two-call repair + reexecution fixture.

14. **MAJOR — Per-worker cleanup will reject legitimate concurrent workers.**

    **Location:** P lines 246–251.

    **Why:** Each cleanup requires the entire `execskill-sbx-` container prefix to be absent, while six workers may legitimately coexist. Closing one worker will find the others and raise `CleanupUnconfirmed`. Frozen native cleanup checks the specific UUID-named container ([backends.py:158](../../skillopt/continual_eval/backends.py#L158), [backends.py:190](../../skillopt/continual_eval/backends.py#L190)).

    **Fix:** Verify removal of the exact owned container. Check prefix-wide absence only after draining the unit. Test closing one of two live workers.

15. **MAJOR — Qualification reuse produces falsely versioned new artifacts.**

    **Location:** P lines 63 and 71; R lines 67–79.

    **Why:** The plan imports `qualify.qualify` unchanged. That function imports frozen v3 `VERSION` and writes a v3 qualification record ([qualify.py:24](../../skillopt/coevo5/qualify.py#L24), [qualify.py:124](../../skillopt/coevo5/qualify.py#L124)). New generated, fixture and evaluation qualifications would violate the new-protocol identity invariant.

    **Fix:** Copy the record-producing qualification closure into `execskill`, retaining frozen scoring helpers. Accept v3 records only through the explicit historical-import path.

16. **MAJOR — The copied evaluation path does not provide hash-only storage.**

    **Location:** R lines 283–284; P lines 54, 70, 109 and 189.

    **Why:** Frozen evaluation calls ordinary cells ([evaluation.py:379](../../skillopt/coevo5/evaluation.py#L379)). Those cells persist full predictions and receipts, not merely hashes ([cells.py:97](../../skillopt/coevo5/cells.py#L97), [cells.py:187](../../skillopt/coevo5/cells.py#L187), [cells.py:224](../../skillopt/coevo5/cells.py#L224)). ALFWorld predictions include observations. Sealing console output does not remove these artifacts.

    **Fix:** Specify an evaluation-specific persistence adapter, transient replay storage and destruction/retention rules. Search every resulting artifact for canary test content. If sealed raw artifacts are required, explicitly amend the storage promise and access policy.

17. **MAJOR — Freezing “continue/stop” does not make the later repeated test read confirmatory.**

    **Location:** R lines 539–540, 237–245 and 633.

    **Why:** Pilot test results are revealed before the formal-chain addendum fixes the remaining design. They can influence later sizes, implementation, procedures or reporting even if the binary continuation decision was already written.

    **Fix:** Freeze the complete continuation protocol and permitted adaptations before pilot unsealing, with an information barrier; alternatively use independent final evaluation data. Otherwise describe subsequent reads as repeated-test development evidence.

18. **MAJOR — Budgeted cell counts do not cover permitted workloads.**

    **Location:** R lines 306, 453–462, 512, 516–517 and 618–629; C lines 115–117, 134–136 and 160–171.

    **Why:** Acceptance budgets assume 0.75 twins per item for SB/OQ and 0.5 for ALFWorld. Three new plus three inherited procedures can require three twins per item in step two. Using the script’s own high token assumptions gives **71.55M ALFWorld acceptance tokens**, already above its **66.9M ledger cap before any ledger inflation**. OfficeQA becomes approximately 19.34M, or 29.01M at the permitted 1.5 ratio, versus its 20.5M cap. Additionally, two parameter adjustments permit three difficulty trials, but the script budgets two; G_acc says “all arms,” while the script budgets four.

    **Fix:** Derive counts from an explicit maximum schedule or cap procedure/twin counts accordingly. Resolve G_acc arms, retries and adjustment counts. Include reservation headroom: frozen [budget.py:283](../../skillopt/coevo5/budget.py#L283) needs room for a full next reservation, not just expected settlement. S-E6 cannot repair missing workload counts merely by measuring per-cell cost.

19. **MAJOR — The smoke criteria contradict their deliberate reasoning probe.**

    **Location:** R S1/S2, lines 664–665; P lines 414–420.

    **Why:** S1-e deliberately omits `reasoning_effort` and requires detection of reasoning mismatch. S2 then requires **all receipts in S1+S2** to contain zero reasoning tokens. Successful execution of the positive-control probe therefore violates the overall pass criterion.

    **Fix:** Separate deliberate fault/control receipts from production-configuration receipts. Require the positive control to trigger the expected classification, then require at least 300 explicitly enumerated production-configuration receipts with no reasoning leaks. Define whether retries count separately.

20. **MAJOR — Code-versus-text conclusions exceed what the comparison identifies.**

    **Location:** R lines 531–533 and 560–562; P line 66.

    **Why:** `F > T_F` by any amount is used to claim an execution benefit; `T_F ≥ F` is used to claim text transfers at least as well. Neither follows from a noisy point estimate. The text arm also changes dynamic information and potentially call opportunities. Its timing and ±20% length matching are unclear for stateful, calculation and repair hooks.

    **Fix:** Specify text-arm behavior for every hook, including call budgets and variable/empty outputs. Describe the estimand as the difference between these implementations unless information is controlled. Require superiority/noninferiority bounds; otherwise report inconclusive.

21. **MINOR — The “mutually exclusive” procedure labels overlap.**

    **Location:** R lines 563–568.

    **Why:** “Home-only” can coexist with “harmful elsewhere” and “inactive elsewhere.” The inactivity label is determined solely by activation despite the statement that activation never determines labels. Nonsignificant transfer also does not establish absence of transfer.

    **Fix:** Use an explicit priority table or separate descriptors. Prefer “benefit established only at home” when other effects remain uncertain.

22. **MAJOR — The fault gate lacks an executable numerator and denominator convention.**

    **Location:** R lines 132–133, 330, 438–440; P lines 159 and 172.

    **Why:** J3 fixes the denominator as items in A but does not specify whether its numerator counts faulty items, cells, procedures or hook invocations; whether repeated runs and placebo/twin arms count; or how planning faults and replay faults combine. These choices materially change the 2% gate. J4 also mixes an absolute cell count with a percentage without an explicit rounding rule.

    **Fix:** Define exact formulas and eligible arms/stages. For example, separately report routing item faults and candidate-cell execution faults, then specify which bounded item-level aggregate decides J3. Add boundary examples for each benchmark’s repeat count.

23. **MINOR — Empty-package equivalence remains internally contradictory.**

    **Location:** R line 134 versus line 653; P lines 194–197 and 324.

    **Why:** §2.3 promises unconditional equivalence, while later sections correctly exempt ALFWorld normalization. Frozen [backends.py:752](../../skillopt/continual_eval/backends.py#L752) executes the extracted raw action; normalization changes transitions and subsequent requests. New `shell` metadata also makes literal whole-prediction equality impossible.

    **Fix:** Put the exception in §2.3 and define the exact request and prediction projections compared.

24. **MINOR — Stale references and operational wording weaken reproducibility and owner readability.**

    **Location:** R lines 57, 388, 751–752 and 1034–1046; P line 406.

    **Why:** The cited v3 code is already tracked at `010d453`, contrary to “untracked/not yet published.” §5.7 refers to nonexistent §8.4. Important arithmetic/evidence sources point to an ephemeral scratch directory despite an archived design directory being available. The connectivity recipe starts with `ssh -O check`, whereas the supplied repository instructions require trying the exact normal SSH alias first.

    **Fix:** Correct the tracked/publication state and section references; link durable, reviewed evidence with hashes. Give the exact SSH-alias-first sequence. Keep owner-facing definitions accurate—particularly the sign-flip and “no validation set” explanations.

What is sound:

- A fixed conjunction of **valid** superiority tests is an IUT and needs no Bonferroni correction between those two tests.
- Pre-outcome A* routing, whole-batch effect reporting and withholding estimates kept outside selection are useful choices.
- Historical reuse, low power and likely unevaluable examiner results are disclosed.
- Keeping generated accuracy out of pilot acceptance avoids a known selection failure.
- Separate protocol identities, frozen scorers, explicit B/M handling, Linux snapshot provenance, fake backends and mutation tests are good engineering foundations.
- The stored arithmetic is reproducible; the principal problems are assumptions, workload coverage and inferential interpretation.

**VERDICT: NOT ACCEPTABLE — 2 BLOCKER items and 19 MAJOR items.**
