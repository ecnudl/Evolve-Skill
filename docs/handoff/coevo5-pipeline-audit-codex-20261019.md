# Codex 只读排查：整条管线有没有 bug（一轮，2026-10-19 11:27–11:33）

> 原文照录（gpt-6-astra，推理强度 ultra，只读；只把本机绝对路径的链接改成相对链接）。提示词见文末。处理见 [管线排查](coevo5-pipeline-audit-20261019.md)。

I found three concrete defects, but **none is established as the cause of v1’s low acceptance**. I found no code that truncates an accepted Skill or silently drops accepted rules. All work was read-only.

1. **Undisclosed analyst field limits can discard an entire proposal batch — B/C.**  
   **Code:** [analyst.py:133](../../skillopt/coevo5/analyst.py#L133), [analyst.py:196](../../skillopt/coevo5/analyst.py#L196), [analyst.py:218](../../skillopt/coevo5/analyst.py#L218).  
   **Failing input → result:** An otherwise valid proposal with `adds` containing 301 characters is rejected with `Invalid: text`; 300 passes. The prompt and its `limits` omit this constraint. They also omit `covered≤200`, `rationale≤500`, each research question≤300, and `transfer.none≤300`. One offending field invalidates all sibling proposals; two invalid replies produce `method_failure` and zero proposals. Reproduced the 300/301 boundary.  
   **v1/v2:** The rationale/question omissions are inherited; no resulting proposal loss is established in finished v1. The additional `covered`/`adds`/`transfer` omissions affect v2.  
   **Minimal fix:** Publish every enforced field limit in the analyst prompt/payload.

2. **Spreadsheet scoring silently discards seconds from ordinary time values — E.**  
   **Code:** [evaluator.py:50](../../skillopt/envs/spreadsheetbench/evaluator.py#L50), reached through [spreadsheet_compat.py:255](../../skillopt/continual_eval/spreadsheet_compat.py#L255) and [sheet_recalc.py:613](../../skillopt/continual_eval/sheet_recalc.py#L613).  
   **Failing input → result:** Reference `datetime.time(12,34,1)` and prediction `datetime.time(12,34,59)` both become `"12:34"` under `str(v)[:-3]`, so different times compare equal. Reproduced using the actual comparator. The comment describes removing fractional precision, not seconds.  
   **v1/v2:** This inherited scorer defect exists in both paths. Whether any finished-v1 item exercised it is unknown; it does not establish an explanation for rare updates.  
   **Minimal fix:** In a new scorer version, use an explicit consistent precision, such as `v.isoformat(timespec="milliseconds")`. Preserve frozen historical scores.

3. **Rubric revision receives check names without the parameter schema it must satisfy — B/C.**  
   **Code:** [examiner.py:374](../../skillopt/coevo5/examiner.py#L374), [checks.py:74](../../skillopt/coevo5/checks.py#L74), [checks.py:91](../../skillopt/coevo5/checks.py#L91).  
   **Failing state → result:** When the current rubric lacks an example of `answer_pure_number`, the reviser sees only its name. An addition using `{"name":"answer_pure_number","params":{}}` fails because the undisclosed mandatory parameter is `allow_percent: bool`. Likewise, `answer_max_words` requires `n` within 1–50. The initial rubric writer receives these schemas ([texts.py:102](../../skillopt/coevo5/texts.py#L102)); the reviser does not.  
   **v1/v2:** Shared omission. Actual v1 impact is unestablished—the documented invalid revisions were attributed to length. V2 still rejects the affected edit, although it now preserves valid sibling edits.  
   **Minimal fix:** Include required parameter names, types, and bounds in the revision library payload.

**Coverage:** **A: no finding**—item sets, run counts, parent sharing, thresholds, fractions, confirmation, and composition matched registration. **D: no finding**—training, gates, test evaluation, and ALFWorld actions receive the corresponding complete rendered Skill. No additional reachable scoring/classification bug was found beyond item 2; OfficeQA’s string-exact numeric matching is explicitly frozen behavior.

**Design defects (registered behaviour that is systematically unfair or self-defeating)**

- **Shared infrastructure failures can veto every candidate.** Three shared unknown items on a 60-item regression panel produce three rule-side format violations and zero parent-side violations: `3 > 2`, while 5% unknowns do not trigger the infrastructure pause. This follows [step.py:121](../../skillopt/coevo5/step.py#L121), [step.py:140](../../skillopt/coevo5/step.py#L140), and [gate.py:53](../../skillopt/coevo5/gate.py#L53). Explicitly retained in v2.

- **Support and gain requirements eliminate small, specialized improvements.** Three distinct check-half trigger items remain untestable regardless of repeated failures; eligible rules must then gain ≥1 item and strictly beat the best of four controls in both rounds. See [step.py:342](../../skillopt/coevo5/step.py#L342) and [gate.py:33](../../skillopt/coevo5/gate.py#L33). This matches the supplied low-C1 bottleneck; it is not an off-by-one error.

- **Gold-dependent instructions are admitted although their conditions are unavailable during solving.** The analyst receives references ([analyst.py:125](../../skillopt/coevo5/analyst.py#L125)), but validation checks structure/evidence, not whether a rule’s condition is observable. Thus “when the reference is a pure number…” can survive preparation while the solver receives only public fields ([backends.py:43](../../skillopt/continual_eval/backends.py#L43)). This remains in v2.

- **Registered views can remove the evidence needed to improve a rule.** An OfficeQA table after character 6,000 disappears from the analyst’s examples; a final answer after character 4,000 disappears from its answer view. Spreadsheet diagnosis lacks the solver’s workbook preview and expected/actual cell values. See [examiner.py:145](../../skillopt/coevo5/examiner.py#L145). V2 widens OfficeQA diagnosis, but leaves these analyst limits and spreadsheet omissions.

- **V1’s mechanical leakage policy rejected incidental ordinary words.** “Three” inside ordinary advice could match a training answer and drop the rule. This was registered, not an erroneous match implementation. V2 mitigates single-word collisions with adjudication; other mechanical drops remain ([leakage.py:23](../../skillopt/coevo5/leakage.py#L23)).

The short output itself follows the representation: each accepted rule is capped at 600 characters ([protocol.py:47](../../skillopt/coevo5/protocol.py#L47)). Two accepted rule bodies therefore contain at most 1,200 characters before section text or duplicated placement; the 20,000-byte Skill limit is only a ceiling.

## 提示词

```text
You are auditing a research pipeline for BUGS (one read-only round; be concrete; no edits).

Repository: the current working tree. Pipeline: `skillopt/coevo5/` (protocol `fivebench-coevolution-v2`; the v1 run used
the same design minus the v2 delta), entry `scripts/run_coevo5.py`, solver prompt/scoring in
`skillopt/continual_eval/backends.py` and the scorers it calls. Design documents (Chinese):
- docs/handoff/coevo5-registration-v6-20261017.md (v1 registration: the intended behaviour)
- docs/handoff/coevo5-registration-v2-delta-20261019.md (what v2 changed)
- docs/handoff/coevo5-midrun-analysis-20261019.md (what the finished v1 run did; sections 3.3-3.13)

The owner's complaint: across five benchmark stages the method accepted rules in only 1 stage (chain E) and 0 stages
(chain I): 50 proposals -> 18 "insufficient_support" (fewer than 4 distinct check-half trigger items), 5 leak drops,
27 gated, 6 passed the screen, 2 passed confirmation. The final learned Skill is two short rules, while the baselines
(SkillOpt, GEPA) produce 4-15 KB Skills. The owner asks: is there a bug that makes updates rare or the Skill short?

Facts already found from the v1 run records (do not re-derive; check the code paths they touch):
1. 1-4 SearchQA items get HTTP 400 on EVERY arm of a gate round (content filter; cell kind "infrastructure",
   token "unknown"). Under the L/H rule (rule unknown = fail, parent/control unknown = pass) each such item costs
   every rule 1 item in C2/C3 and, on a regression panel, 1 extra "format violation" (rule unknowns count, the
   parent's do not; the allowance is 2).
2. About 4 of 60 proposed rules are conditioned on information the solver never sees ("When the reference is a pure
   number ...", "only when the reference truly shows blank").
3. Most gated rules gained 0-1 items over the parent on their own trigger items (C1 gain), so the content, not only
   the gate's noise, is a bottleneck.

What to look for (report only what you can point to in code, with file:line and a concrete failing input/state):
A. Anything that makes a rule's comparison systematically unfair beyond the registered conservative L/H rule
   (wrong arm/item sets, items scheduled with different run counts than intended, parent results shared or reused in
   a way the registration does not say, wrong tolerance/panel, ordering effects, off-by-one in MIN_TRIGGER/MIN_GAIN,
   fractions/rounding, "undetermined" triggered wrongly, composite/merge dropping accepted rules).
B. Anything that silently degrades what the diagnosis or the analyst sees (missing/truncated reference, wrong code
   meanings, wrong half, examples or evidence ids that cannot match, contrast examples, task views that drop the
   decisive part of the task, current Skill rendered differently than the solver sees it).
C. Anything that makes a proposal untestable for a reason other than the data (trigger computation, code sets, key
   mismatches between diagnoses and answers, evidence validation rejecting valid replies, leakage checks firing on
   ordinary words, dedup, overlength).
D. Anything in how the Skill reaches the solver (train, gate, test evaluation, ALFWorld per-action prompts) that
   differs from the gate's tested text, or loses sections/rules.
E. Scoring/outcome classification errors in the scorers coevo5 uses (SearchQA exact match normalisation, OfficeQA
   numeric matching, LiveMath letter extraction, SpreadsheetBench, ALFWorld), and unknown-vs-fail classification.

Output: a numbered list, most severe first. For each: title; file:line; failing input/state -> wrong result; whether
it affected the finished v1 run (if you can tell from code) and whether v2 still has it; minimal fix. Then a separate
short list "design defects (registered behaviour that is systematically unfair or self-defeating)", each with the
evidence. Say "no finding" for any of A-E where you found nothing. Do not restate design choices as bugs; do not
propose new experiments.
```
