# coevo5 正式登记的 Codex 设计审查第 2 轮（2026-10-17 15:40 前后，结论 NOT ACCEPTABLE）

> 审查对象：[正式登记第 2 版](coevo5-registration-20261016.md)。原样保存 Codex 的结论（第 1 轮 22 条的状态表与新问题 13 条）。

> 命令：`codex exec -m gpt-6-astra -c model_reasoning_effort='"ultra"' --sandbox read-only`。

Version 2 makes substantial progress, but several decisions still need correction before launch. Both zero-call scripts reproduce the quoted figures substantially; that verifies their calculations, not empirical gate performance. I treated the early `coevo5` code only as feasibility context.

Section references below refer to the [revised registration](coevo5-registration-20261016.md).

The 22 round-1 findings map as follows:

| # | Status | Reason |
|---|---|---|
| 1 | PARTIALLY | §5.1 correctly withdraws the 3–4% guarantee and acknowledges dependence and nonexchangeability. However, §5.8 introduces another unsupported numerical estimate of false acceptance. |
| 2 | PARTIALLY | §5.5 now compares harm against the parent separately for each bench. The remaining safety language exceeds what the limited component simulations establish. |
| 3 | PARTIALLY | The error family is explicit, and a heuristic selector need not promise error control. The proposed chain-level “expected false acceptances” calculation remains unjustified. |
| 4 | RESOLVED | §§4–5.3 specify frozen triggers, complements, repetitions and insufficient-support handling, with fresh parent executions in every gate round. |
| 5 | PARTIALLY | Conservative gate bounds and final missingness analyses address unequal exclusions. Outcome classification, selective retries and the direction of bounds for inferiority conclusions still need correction. |
| 6 | PARTIALLY | Final placement, composition benefits and predetermined fallback are substantially clarified. Length trimming can still produce a final combination that was never tested. |
| 7 | PARTIALLY | §5.6 supplies useful illustrative simulations. It still describes C1-only power as acceptance power and incorrectly interprets rejection as evidence of a subthreshold effect. |
| 8 | RESOLVED | §§0/14 require all adapters, baselines and analysis to be completed and frozen before launch; smoke runs are training-only and evaluation outputs are sealed. |
| 9 | PARTIALLY | Future real-task access is prohibited within each chain, historical split identities are preserved, and resource use is reported separately. “Truly unseen bench” and equal *actual* unique-label access remain stronger than the contract supports. |
| 10 | RESOLVED | §9 provides typed checks, generic-token exceptions, semantic adjudication, archived decisions and test-data exclusion. This is a specified leakage-reduction procedure, although not a proof of zero leakage. |
| 11 | PARTIALLY | Sources, archives, consistency checks, generation limits and the selection-only interpretation are substantially specified. The permitted transfer-panel size remains contradictory. |
| 12 | RESOLVED | §12.3 separates noninferiority from superiority, uses an explicit macro-average margin and requires both baseline comparisons; the instruction-level comparison has its own rule. The margin’s effect-retention explanation needs narrower wording. |
| 13 | RESOLVED | Inference is explicitly conditional on realized histories; paired trajectories, bootstrap units and the primary sequence are specified. Additional superiority assertions need the clarification below. |
| 14 | PARTIALLY | Acquisition, signed forgetting, forward transfer and overall success are operationalized. Standalone Claim 2 still lacks the positive-learning prerequisite claimed by its rationale. |
| 15 | RESOLVED | Deepseek comparisons are restricted to its own trajectories and starting references, with the fixed GLM method-role model disclosed. |
| 16 | RESOLVED | Claims are explicitly limited to the five-instruction bundle and the fixed, development-informed bench order. |
| 17 | RESOLVED | §6 removes ALFWorld rubric revision, supplies feasible class-count requirements and shortfall behavior, and separates diagnostic revisions from fixed gate scoring. |
| 18 | RESOLVED | Examiner results are labeled selection measurements; all attempts are reported, and independent examiner improvement or causal attribution is expressly disclaimed. |
| 19 | RESOLVED | §5.9 specifies descriptive lenient-match diagnostics, acknowledges their failure modes and excludes them from gates and claims. |
| 20 | RESOLVED | Starting references are measured anew, shared records are identified, and historical test exposure is disclosed. |
| 21 | PARTIALLY | The prelaunch manifest and explicit defaults resolve most omissions. Overflow handling, transfer-panel cardinality and several outcome-dependent branches remain insufficiently determined. |
| 22 | PARTIALLY | Reproducible stage budgets and incomplete-chain reporting are provided. The stated hard caps are not enforceable as written, and some paid-role limits remain unspecified. |

The revision introduces or leaves the following concrete problems.

1. **MUST-FIX — SpreadsheetBench’s declared eligible population is not established.**  
   [§2](coevo5-registration-20261016.md?plain=1#L59) calls all 120 development tasks and 279 test tasks scorable. However, the [archived test results](../../docs/results-and-lessons.md?plain=1#L201) explicitly retain **93–111 unknowns among those 279 tasks**; excluding the one missing/misnamed asset did not establish scoring compatibility. Reference qualification may also leave fewer than 120 development tasks. Structural scoring limitations do not fit §5.4’s infrastructure-only definition of unknown, and automatic retries cannot reliably cure them.

   **Change:** distinguish asset eligibility from scoring qualification. Apply a frozen, automated reference-qualification procedure through the sealed evaluator, without exposing test contents to method roles or humans; freeze actual eligible IDs and denominators before candidate evaluation. Specify shortfalls, including fewer than 60 regression items, and retain a policy for candidate artifacts that remain unscorable despite reference qualification. This requires no paid model experiment.

2. **MUST-FIX — The new failure/unknown distinction does not determine which outcomes receive fresh answers.**  
   [§5.4](coevo5-registration-20261016.md?plain=1#L143) retries unknowns with new solver calls. Yet the existing backend can report missing generated workbooks and generated-program exceptions as unknown, while filter information can be lost when interpreting only the backend reason. These are concrete paths in [native execution](../../skillopt/continual_eval/native_worker.py#L86) and [receipt interpretation](../../skillopt/continual_eval/backends.py#L78). Treating every such unknown as transient infrastructure failure can selectively give defective answers additional attempts.

   **Change:** freeze a receipt-aware classification table covering model noncompletion, malformed actions/code, missing artifacts, proven program defects, scorer incompatibility, transport failures and unresolved causes. Retry scoring or execution of the **same artifact** where appropriate; unresolved artifact/scorer failures should not automatically trigger a new answer. Preserve both official and completion-aware outcomes.

3. **MUST-FIX — Post-test trimming bypasses verification of the deployed Skill.**  
   [§3 and §5.7](coevo5-registration-20261016.md?plain=1#L215) permit a composite to pass and then lose low-priority members to satisfy the byte cap. The resulting subset may behave differently, and it is unclear whether historical rules can be deleted despite append-only evolution.

   **Change:** keep the parent and initial instructions immutable; choose the fitting subset of current-step rules **before** composition testing, then accept exactly that rendered text. An inexpensive alternative is to accept only the highest-priority individually confirmed rule that fits, otherwise make no update.

4. **MUST-FIX — The new placebo calibration does not estimate false acceptance.**  
   [§5.8](coevo5-registration-20261016.md?plain=1#L226) compares pseudocandidates against three controls, whereas real candidates face four. More fundamentally, the four control texts change between rounds, so there is no persistent pseudocandidate whose two-round passage is defined; these fixed texts also do not reproduce adaptive proposal and placement selection. Multiplying this rate by the candidate count does not estimate expected chain-level false acceptances.

   **Change:** delete the two-round and expected-false-acceptance calculations. Keep single-round placebo passage rates as descriptive diagnostics, with no interpretation as candidate or chain error rates.

5. **MUST-FIX — Transfer-panel cardinality has two incompatible definitions.**  
   [§5.3](coevo5-registration-20261016.md?plain=1#L139) requires six probes, but [§8](coevo5-registration-20261016.md?plain=1#L287) permits two survivors per format, yielding four or five probes. That changes C4’s effective effect-size threshold.

   **Change:** explicitly permit 2–3 probes per format, freeze the actual 4–6-item panel before screening, and apply C4 to that panel; update the panel and budget descriptions accordingly. Alternatively require all six and demote on shortfall. Choose now, before observing generation success.

6. **MUST-FIX — Invalid examiner judgments make rubric selection ambiguous.**  
   [§4](coevo5-registration-20261016.md?plain=1#L109) excludes invalid judgments from agreement, while [§6](coevo5-registration-20261016.md?plain=1#L257) selects revisions using balanced accuracy and additional correct judgments. Separate exclusions give old and new rubrics different denominators; a class can even have no valid judgments, leaving balanced accuracy undefined.

   **Change:** use the entire frozen, officially labeled selection panel for both rubrics and count invalid judgments as incorrect. Report invalid rates separately. This removes the ambiguity without additional calls.

7. **MUST-FIX — The token limits are thresholds, not executable hard caps.**  
   [§13](coevo5-registration-20261016.md?plain=1#L418) stops new calls after accumulated usage reaches the limit. Concurrent requests and [internal client retries](../../scripts/weak_solver_probe.py#L277) may already commit further expenditure. Twice the expected call cost is not a conservative bound for missing usage. The deepseek chains’ paid GLM roles also lack explicit stage limits.

   **Change:** reserve a bounded allowance before dispatch, including in-flight requests, retries and unresolved usage; reconcile it after receipts arrive. Freeze caps for stage 0, baseline stages and both deepseek chains’ GLM roles, plus an overall paid-token ceiling. Specify whether an infrastructure stop terminates the chain and how its partial results are reported. The existing spending limits can remain unchanged.

8. **MUST-FIX — Adverse completion supports favorable claims, but does not establish inferiority.**  
   [§12.6](coevo5-registration-20261016.md?plain=1#L393) always completes missing outcomes against the tested method. That is appropriate for proving its superiority/noninferiority, but cannot validate the “inferior” classification in §12.3: complete-case results and pessimistic completion can both indicate inferiority while favorable completion reverses it.

   **Change:** register direction-specific sensitivity rules. A favorable claim must survive the method’s adverse completion; an inferiority claim must survive its favorable completion. Respect shared record identities when reused observations cancel, and compute the nonlinear clipped summaries directly rather than assuming every statistic is linear.

9. **MUST-FIX — Standalone Claim 2 can succeed without established learning.**  
   [§12.5](coevo5-registration-20261016.md?plain=1#L380) requires positive learning for Claim 1, but Claim 2 requires only P1–P4. Two accepted but useless updates can satisfy the update-count rule, noninferiority to weak baselines and lower signed forgetting without establishing any learning gain. Overall success is protected by Claim 1; standalone Claim 2 is not.

   **Change:** require Claim 1 plus P3 and P4 for Claim 2, or explicitly restrict Claim 2 to a signed trajectory comparison without the useful-learning interpretation.

10. **SHOULD-FIX — Simulation interpretations exceed the simulated quantities.**  
    In [§5.6](coevo5-registration-20261016.md?plain=1#L175), the approximately 85% figure is **C1-only passage**, excluding other gate criteria and composition. The [script](coevo5_power_sim.py#L86) subtracts the nominal harm from each probability and clips at zero, so “20-point harm” is not a 20-point aggregate decline; C2 also assumes exactly eight triggers. A stochastic rejection does not establish that the true effect was below the table’s effect sizes.

    **Change:** label the results illustrative component simulations, describe the actual decrement and panel assumptions, and remove general safety or full-acceptance interpretations. Keep the thresholds heuristic; a larger simulation project is unnecessary.

11. **SHOULD-FIX — The budget’s “upper” scenario is not a maximum.**  
    [§13](coevo5-registration-20261016.md?plain=1#L412) assumes 15 calls per ALFWorld episode despite the backend’s default 50-action limit; 20 KB does not guarantee 5,000 tokenizer tokens. The [budget script](coevo5_budget.py#L44) allocates 288 transfer-solving cells, whereas the literal maximum schedule of 16 full arms plus 16 control arms, each on 12 probes twice, requires 768.

    **Change:** correct the schedule counts and call this a high-cost planning scenario. Enforce hard caps separately and acknowledge that completion within them is uncertain.

12. **SHOULD-FIX — Baseline effective solver policies need explicit disclosure.**  
    [§11](coevo5-registration-20261016.md?plain=1#L330) matches nominal solver settings, but frozen v9 includes [one truncation recovery at 131,072 tokens](../../skillopt/continual_learning/recovery.py#L184), unlike the new completion-aware procedure. Its internal reuse policies also need an explicit exception to §0’s blanket no-cache statement.

    **Change:** retain and disclose these legacy learning policies as part of the baseline algorithms, with a common final evaluator. Describe the comparison as one between complete algorithms; matching nominal settings does not isolate the effect of validation-partition use.

13. **SHOULD-FIX — Tighten the statistical and access claims.**  
    [§12.3](coevo5-registration-20261016.md?plain=1#L352)’s sequence covers two noninferiority hypotheses followed by two forgetting hypotheses; separately declaring superiority adds different hypotheses. Noninferiority to those baselines also does not guarantee retaining half the instruction bundle’s gain. Meanwhile, [§§2/12.4](coevo5-registration-20261016.md?plain=1#L65)’s “truly unseen” language overlooks historical development exposure, target task cards and generated target-format probes; the check half also indirectly influences proposals through rubric selection.

    **Change:** make primary P1/P2 decisions noninferiority-only and label superiority exploratory; retain three points as a practical margin without an effect-retention guarantee. Say “no real examples from that bench used yet in this learning history,” “same available labeled pool,” and consistently “no separate held-out validation partition.” Explicitly describe the check half as adaptive training-side selection material.

These fixes preserve sequential five-bench evolution, the two specified solvers and the owner’s partition constraint. None requires additional paid experiments or complete-chain replications.

VERDICT: NOT ACCEPTABLE
