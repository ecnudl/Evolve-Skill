# coevo5 正式登记的 Codex 设计审查第 3 轮（2026-10-17 16:02，结论 NOT ACCEPTABLE）

> 审查对象：[正式登记第 3 版](coevo5-registration-20261016.md)。原样保存 Codex 的结论（第 2 轮 13 条与第 1 轮未完全解决各条的状态表、新问题 6 条：3 条 MUST-FIX、3 条 SHOULD-FIX）；只把链接里的本机绝对路径改成相对路径。

> 命令：`codex exec -m gpt-6-astra -c model_reasoning_effort='"ultra"' --sandbox read-only`。

Version 3 resolves most methodological objections, but the new budget and outcome-classification rules still have MUST-FIX gaps. This was a read-only review: no network calls or paid experiments. The 91 pure-layer tests pass; the budget figures and registered calibration tolerances reproduce. Passing tests do not establish consistency where the tests encode a different rule from the registration.

Section references below refer to the [version-3 registration](coevo5-registration-20261016.md).

For the 13 round-2 findings:

| # | Status | Reason |
|---|---|---|
| 1 | **RESOLVED** | §2.1 separates asset eligibility from scorer qualification, fixes qualification independently of candidate outcomes, and specifies training-panel shortfalls and candidate-artifact unknowns. Inference is now limited to the qualified population. |
| 2 | **PARTIALLY** | §5.4 specifies receipt-aware outcomes and generally prevents fresh answers from replacing delivered answers. However, its new implementation disagrees with that contract on receipt precedence, scorer-failure categories and malformed workbooks; see finding 3 below. |
| 3 | **RESOLVED** | §§3/5.7 preserve the parent, choose the fitting subset before composition testing, and accept exactly the tested text. The fallback is an individually confirmed rule. |
| 4 | **RESOLVED** | §5.8 removes two-round placebo calibration and expected chain false acceptances. Single-round placebo passage is expressly descriptive. |
| 5 | **RESOLVED** | §§5.3/8 consistently allow 2–3 probes per format and freeze each 4–6-item panel before screening. |
| 6 | **RESOLVED** | §6 uses the entire fixed, officially labeled panel for both rubrics, counts invalid judgments as incorrect and reports invalid rates separately. |
| 7 | **PARTIALLY** | §13 now specifies reservations, stage/chain/global limits and incomplete-chain reporting. The baseline reservation uses an invalid request-size bound, and settlement lacks a conservative rule for several missing-usage cases. |
| 8 | **RESOLVED** | §12.6 uses adverse completion for favorable claims and favorable completion for inferiority, while respecting shared-record identities. The registered claim statistics are linear; clipped summaries remain descriptive. |
| 9 | **RESOLVED** | §12.5 explicitly makes Claim 2 depend on Claim 1, including established positive learning and sufficient updating. |
| 10 | **RESOLVED** | §5.6 now identifies component simulations, states the clipping and eight-trigger assumptions, and separates C1 passage from acceptance. Rejection no longer implies a small or absent effect. |
| 11 | **RESOLVED** | §13.1 distinguishes planning scenarios from hard maxima and acknowledges ALFWorld’s 50-action ceiling. The revised budget script reproduces the table, including 336 transfer-solving cells under its specified scheduling interpretation. |
| 12 | **PARTIALLY** | §11 discloses truncation recovery, replay/cache exceptions and the complete-algorithm comparison. Its claim that the frozen baselines have a 6,000-byte Skill limit is incorrect: v9 inherits 32,000 bytes. |
| 13 | **RESOLVED** | §§2.2/12.3/12.4 narrow the access claims, make primary P1/P2 decisions noninferiority-only, and remove the effect-retention guarantee. The check half is correctly described as adaptive training-side selection material. |

The round-1 findings previously marked PARTIALLY now stand as follows:

| Round-1 items | Status | Reason |
|---|---|---|
| **1, 2, 3** | **RESOLVED** | Unsupported error-rate and safety guarantees have been withdrawn; the gate is explicitly heuristic. |
| **5** | **PARTIALLY** | Qualification and missingness inference are addressed; outcome-classification consistency remains unresolved. |
| **6, 7** | **RESOLVED** | Final-text verification and the interpretation of simulated power/rejection are corrected. |
| **9, 11** | **RESOLVED** | Access claims, source restrictions and transfer-panel construction are sufficiently specified. |
| **14** | **RESOLVED** | Claim 2 now requires established learning through Claim 1. |
| **21** | **PARTIALLY** | Most branches are fixed, but the classification contract and interruption/restart rules still need reconciliation. |
| **22** | **PARTIALLY** | The new reservation scheme has the accounting gaps below. |

The revision introduces or exposes these remaining problems:

1. **MUST-FIX — The baseline block reservation is not a valid worst-case bound (§§11, 13.2).**

   [§13.2](coevo5-registration-20261016.md?plain=1#L518) bounds input by the longest training question plus 6,000 bytes and a template. Frozen v9 actually inherits a **32,000-byte** Skill limit through [recovery.py](../../skillopt/continual_learning/recovery.py#L62). Reflection prompts contain batches of execution feedback, and ALFWorld prompts contain evolving observations and history; neither is bounded by the longest question.

   **Change:** Correct §11’s baseline limit. For block reservations, use the frozen ledger’s enforced **240,000-byte total prompt limit** plus framing allowance ([ledger.py](../../skillopt/continual_learning/ledger.py#L240)), or meter actual baseline requests through the common reservation wrapper. Recalculate the baseline stage/chain allowances while retaining the global ceiling.

2. **MUST-FIX — Settlement is undefined for potentially billable responses without valid usage (§13.2).**

   [The settlement rule](coevo5-registration-20261016.md?plain=1#L515) covers reported delivery usage and selected failure categories. But the frozen client can return a completed answer with `usage={}`, or discard usage for an HTTP-200 malformed/model-mismatch response ([client receipt handling](../../scripts/weak_solver_probe.py#L238)). These cases cannot safely release their reservations.

   **Change:** For every attempt, charge valid reported usage when available; otherwise retain the full per-attempt allowance unless a frozen rule establishes rejection before generation. Apply the same conservative settlement to baseline missing-usage attempts and unclosed calls, rather than settling only to reported-token subtotals.

3. **MUST-FIX — The new outcome implementation does not implement one consistent classification contract (§5.4).**

   Three concrete discrepancies affect denominators or stopping decisions:

   - The [registration’s scorer-failure row](coevo5-registration-20261016.md?plain=1#L192) assigns reference/candidate recalculation failures and reference-cache inconsistency to **artifact unknown**. [The classifier](../../skillopt/coevo5/outcomes.py#L253) assigns reference-side failures and selected environment/manifest failures to **infrastructure unknown**. This changes whether the 10% threshold pauses the chain and enables a whole-unit rerun.
   - A wrong-model receipt with `finish_reason=length` becomes **failure** through the frozen backend and classifier, although §5.4 treats wrong-model delivery as infrastructure failure. Receipt/model validation needs precedence over truncation classification.
   - [The workbook validator](../../skillopt/coevo5/outcomes.py#L231) checks only two ZIP member names. The test fixture passes that check despite being unreadable by openpyxl; malformed workbook packages can consequently become artifact unknown instead of the registered invalid-artifact failure.

   **Change:** Freeze an ordered receipt/reason decision table and align the registration, adapter/classifier and tests. Explicitly distinguish malformed workbook structure from supported-but-unscorable workbook semantics. These corrections can remain outside the frozen backend.

4. **SHOULD-FIX — Qualification introduces unsupported empty-population branches (§§2.1, 11, 12.6).**

   Qualification can leave an empty historical train or val subset even when their combined population exceeds 30; frozen baseline manifests require both to be nonempty ([contracts.py](../../skillopt/continual_learning/contracts.py#L124)). Zero qualified test items, or zero complete-pair units for a comparison, also leave registered statistics undefined.

   **Change:** Register a prelaunch no-go rule for empty baseline learning/selection pools. For an empty qualified test population or complete-pair analysis stratum, report the affected claims as **not evaluable**; never silently drop a bench or change macro-average weights.

5. **SHOULD-FIX — Authorized unit reruns need an explicit primary-attempt rule and complete scope (§§0, 5.4, 13.4).**

   §0 says reruns require a new version and the original remains primary, whereas [§13.4](coevo5-registration-20261016.md?plain=1#L545) permits fresh execution of every cell in an interrupted unit. Its restart-unit list also omits method-role work and baseline learning stages.

   **Change:** Make authorized infrastructure recovery an explicit exception, specify which attempt supplies the trajectory, and retain all earlier attempts and charges. The simplest rule for interruptions outside the listed units is chain termination. Whole-unit recovery with sealed scores is not inherently cherry-picking, but its treatment must be fixed beforehand.

6. **SHOULD-FIX — Two small presentation corrections (§§5.3, 5.6).**

   State explicitly that each shared candidate solves **its own** transfer panel, while the parent/shared controls solve the required union; this is the interpretation supporting the 336-cell schedule. Also change the four-trigger, `f=.75` C1 range from **0.68–0.71** to **0.67–0.71**, matching the full zero-call simulation.

These fixes preserve the owner’s partition constraint, sequential five-bench evolution and solver choices. None requires additional paid experiments.

VERDICT: NOT ACCEPTABLE