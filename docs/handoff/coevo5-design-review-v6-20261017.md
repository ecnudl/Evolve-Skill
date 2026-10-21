# coevo5 登记第 6 版：Codex 设计审查（唯一一轮，2026-10-17 19:5x，原文）

模型 gpt-6-astra，推理档位 ultra，只读沙盒；提示词见会话存档。逐条处理见登记第 6 版 §21。

---

1. **MAJOR — §§4, 5.2–5.5, 13: shrinking \(B_r\) breaks same-position controls.**  
   At OfficeQA, one candidate can retain `{SearchQA, LiveMath}`, while another loses its LiveMath panel and retains only `{SearchQA}`. The registered similar controls still occupy all three sections, so the second candidate lacks the promised same-position comparator.

   **Fix:** freeze actual placement sets before constructing controls, and provide four controls per distinct placement set—or explicitly register a common placement policy. With separate groups, OfficeQA’s maximum becomes **24 control arms / 1,776 cells**, rather than 16 / 1,184. Under the existing high-cost assumptions, its learning estimates become approximately **57.25M / 74.37M tokens** for E/I, exceeding the 55M/70M stage caps. Reconcile the schedule and stage/chain caps while retaining the owner’s total cap.

2. **MAJOR — §§3, 8: OfficeQA forward questions do not activate the target section’s applicability condition.**  
   OfficeQA rules explicitly apply to **U.S. Treasury Bulletin page text**, whereas the new forward questions supply Wikipedia tables. The frozen solver instructs it to use Skill guidance only where applicable. After removing Shared, neither the OfficeQA copy nor the SearchQA copy necessarily applies to these questions. C4′ can therefore pass without exercising the intended target rule.

   **Fix:** freeze an OfficeQA applicability condition that truthfully covers both real tasks and these generated proxies, or explicitly revise the permitted material/routing contract. Do not label Wikipedia material as Treasury material.

3. **MAJOR — §4 steps 5–6: research rewriting bypasses deduplication and lacks a failure rule.**  
   Deduplication occurs before step 5b. Rewriting can make two proposals identical, reproduce a parent rule, or produce malformed/overlength text. The registration does not say whether an invalid rewrite retains the original, discards the rule, retries, or invokes the entire-step “analysis failed twice” rule.

   **Fix:** specify one deterministic rewrite failure policy and its call limit. After rewriting, revalidate the rule format and 600-character limit, repeat normalized deduplication against the parent and other proposals with a fixed tie-break, then perform leakage and rendered-length checks.

4. **MAJOR — §§3–4: the length check precedes determination of the placement it measures.**  
   Step 6 checks the suggested similar placement, but its defining \(B_r\) is assigned and pruned only in step 8. Checking all provisional targets can discard a rule that would fit after forward-panel failure; checking the final targets produces a different experiment. There is also no explicit treatment for a short candidate that fits while a longer matching control exceeds 20,000 bytes.

   **Fix:** freeze/prune \(B_r\), construct exact arm texts, and then check rendered length before screening. State whether an oversized similar arm causes whole-candidate rejection or own-placement fallback. Explicitly define whether diagnostic controls share the cap and what happens if they exceed it.

5. **MAJOR — §§7–8, 13.1: the method-call maximum is not fully operationalized.**  
   The budget assumes **eight model calls per research request** and **one material-research request per generation call**, up to five generation calls per candidate/forward target. Section 7 bounds search rounds, terms, and pages, but does not translate those into an enforced model-call ceiling. Section 8 does not explicitly fix material-request cardinality. Invalid research/rewrite outputs also lack sufficiently specific dispatch rules.

   **Fix:** register these ceilings and retry/failure transitions explicitly, including whether malformed requests consume their allowance. Derive the method-call table from that bounded workflow. The solver maxima—18 full arms, 14 at ALFWorld, and 288 forward cells—otherwise match the stated maximum schedule.

6. **MAJOR — §§12.5, 12.8: success labels exceed the registered estimands.**  
   Q1–Q3 concern **category averages**. They can all pass while individual benches decline; Q3 permits an average loss approaching two percentage points; OfficeQA→SpreadsheetBench is excluded from the positive-transfer category. Consequently, “the transfer pattern is established” cannot establish the owner’s per-bench, all-similarity-edge requirement. The unchanged P-family “overall success” label also needs qualification because it can hold when Q2 fails.

   **Fix:** retain the chosen tests but call their conjunction the **registered aggregate transfer criterion**, explicitly limiting its interpretation. Describe Q3 as mean noninferiority within two points. Keep P and Q independent, but distinguish P-family success from evidence for the new transfer requirement.

7. **MAJOR — §12.8: failure to establish Q2 is incorrectly explained exclusively by low power.**  
   The statement that Q2 failure “only means this scale cannot detect” improvement is false. It can reflect no benefit, harm, missing-data uncertainty, or low power; the observed interval could support a negative effect.

   **Fix:** state that positive average transfer was not established, and report the estimate, interval, and missingness results. Low power is a possible explanation, not evidence that an underlying improvement exists.

8. **MAJOR — §§5.5–5.6, 12.8, 20.3: several simulation claims misdescribe what was computed.**  
   Three corrections are needed:

   - The approximately 0.6 probability is **two-round C4′ passage on one target**, not actual similar placement. Actual placement also requires C1–C3, potentially another target, and applicable composition decisions.
   - The Q simulation’s advertised “true +4/+2-point” effects are cumulative **pre-clipping probability shifts**. Under its fitted model, actual category-average gains are approximately **+2.8/+1.45 points**; nominal +6/+3 gives approximately **+4.0/+2.1**.
   - The strict forward comparator requires one additional successful **cell**, although the text specifies one **item** measured through per-item averages. With two repetitions, the cell threshold must be two.

   **Fix:** correct the comparator and regenerate its figures; label shifts and component probabilities accurately. Qualify “helpful rules unaffected,” and report sensitivity at the permitted eight-item endpoint: the existing simulation gives roughly **0.15–0.18** passage under a −10-point shift there, versus approximately 0.10–0.12 with twelve items. These corrections do not invalidate choosing the more permissive C4′ or one-sided bounds.

9. **MINOR — §§5.2, 5.7, 20: confirmation/fallback summaries contradict the detailed algorithm.**  
   Section 5.7 correctly confirms the own arm of a tentative similar candidate **only if that own arm passed screening**. Similar-confirmation failure then permits fallback only if the own arm passed both rounds. The summaries describe both-arm confirmation and fallback without those qualifications.

   **Fix:** make the summaries match §5.7. Also define the parent’s forward-panel union using the **active similar arms in that round**, excluding candidates already restricted to own placement.

10. **MINOR — §8: the eight-item minimum has no distinctness rule.**  
    Repeated questions across the five generation calls can satisfy the numerical minimum while supplying fewer than eight distinct questions. Cross-panel duplicates also leave the parent’s “union” scheduling ambiguous.

    **Fix:** freeze a canonical context/question identity, remove duplicates within each panel before selecting its first twelve valid items, and report duplicate removals. Specify whether identical questions across different rule panels share a parent measurement or receive separately identified fresh executions.

11. **MINOR — §4 step 5b; §7: the researcher’s no-question boundary is not enforced before dispatch.**  
    The researcher receives proposed rule text and free-form research questions before leakage checking. An analyst who saw training questions can copy one into either field, contradicting §7’s promise that the researcher sees no bench questions. This concerns current training material, rather than a demonstrated test/future-data leak.

    **Fix:** check or sanitize both payloads before research dispatch, using only permitted current-training data, and retain the post-rewrite leakage check.

VERDICT: NOT ACCEPTABLE
