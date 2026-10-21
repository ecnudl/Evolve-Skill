# coevo5 第三批代码审查（唯一一轮，Codex gpt-6-astra，推理 ultra，只读）原文

日期：2026-10-17。审查提示见同目录的说明；以下为审查输出原文，未改动。

VERDICT: NOT ACCEPTABLE

1. **BLOCKER — [baseline.py:203](../../skillopt/coevo5/baseline.py#L203): baseline calls ignore global halts.** Once its stage reservation succeeds, the frozen learner makes subsequent calls without checking the global ledger’s halt generation. A concurrent chain can trigger an assumption breach or ledger failure while the baseline continues dispatching—even across a halt followed by resume. This violates §20.2 and §13.4. **Smallest fix:** guard every frozen-client dispatch against the captured generation, latch violations outside the learner’s exception handling, settle existing attempts, and pause.

2. **MAJOR — [baseline.py:136](../../skillopt/coevo5/baseline.py#L136): unreadable ledgers can settle as zero.** `Path.glob()` suppresses directory permission errors. If `call_intents/` and `calls/` become unreadable after paid submissions, both scans can appear empty; `_settle()` charges zero and releases the reservation without halting. This violates §24’s explicit full-reservation settlement and global halt for unreadable ledgers. **Smallest fix:** create the expected ledger directories before execution and enumerate them using operations that propagate errors; missing or unreadable expected directories must enter the 93M breach path.

3. **MAJOR — [prelaunch.py:157](../../skillopt/coevo5/prelaunch.py#L157): preparation spending can disappear from the overall cap.** Calls remain in memory until `roles.json` is written. Killing preparation after paid calls loses their records. Even an orderly failed preparation A followed by successful preparation B leaves `generate()` deducting only B’s text-generation spending. This violates §13.2–§13.3 and §24’s inclusion of all prelaunch GLM usage. **Smallest fix:** maintain a durable prelaunch intent/settlement ledger covering every preparation attempt and deduct its settled plus outstanding usage.

4. **MAJOR — [prelaunch.py:190](../../skillopt/coevo5/prelaunch.py#L190): preparation ignores reservation-assumption breaches.** The preparation endpoint has no budget, so it does not enforce usage bounds; `prior_usage()` subsequently discards `ledger.settle()`’s breach flag. A receipt reporting prompt tokens above request bytes plus 512 therefore permits further preparation and launch. This violates §13.2 and §13.4. **Smallest fix:** enforce bounds during preparation and refuse manifest generation while a recorded breach remains unresolved.

5. **MAJOR — [baseline.py:168](../../skillopt/coevo5/baseline.py#L168): unreadable cleanup evidence loses its cleanup classification.** The frozen learner can return `native_cleanup_evidence_unreadable`, but `_handoff()` rereads the malformed artifact before entering its cleanup guard. The resulting exception becomes `configuration` or `exception`, rather than `cleanup`, obscuring the mandatory cleanup recovery condition. This violates §24 and §13.4. **Smallest fix:** include evidence enumeration and reading inside the cleanup guard and classify unreadable cleanup evidence as `Pause("cleanup", ...)`.

6. **MAJOR — [prelaunch.py:216](../../skillopt/coevo5/prelaunch.py#L216): an infeasible baseline setup does not prevent launch.** Qualification retaining only historical train SpreadsheetBench items passes manifest generation/loading. E-glm can then incur paid work before a baseline reaches stage 4 and rejects its empty val partition. The successful `check-baselines` result is also not a launch prerequisite. This violates §2.1’s explicit “不开跑” condition and §24. **Smallest fix:** reject either empty qualified partition and require successful validation of all ten baseline manifests and their client setup before allowing any chain to launch.

7. **MAJOR — [prelaunch.py:224](../../skillopt/coevo5/prelaunch.py#L224): foreign baseline settings are accepted.** The generator copies model/service fields from any sealed protocol without establishing study F’s identity or comparing nominal settings with the study solver. A foreign GLM protocol using `reasoning_effort="high"` and a matching service passes the frozen checks while coevo uses `low`. This violates §11 and §24. **Smallest fix:** validate the registered source protocol and explicitly compare the learning model settings with the evaluation solver settings.

8. **MAJOR — [prelaunch.py:223](../../skillopt/coevo5/prelaunch.py#L223): foreign research archives are accepted.** An internally consistent archive containing a different document set—even one answer-bearing document—passes `research.Archive()` and becomes available to the researcher. Neither the registered 21-file roster nor `sources.json` is validated. This violates §7 and §24. **Smallest fix:** require the exact documentation/card roster, verify card bytes and source URLs, and bind the source-provenance record.

9. **MAJOR — [prelaunch.py:219](../../skillopt/coevo5/prelaunch.py#L219): text provenance is not checked against the generated treatments.** Texts prepared before an instruction/rubric prompt change retain the same protocol version and cards and pass these checks under the new launch code. The generator never connects stored instructions/rubrics to the recorded requests and responses; filled texts with an empty call list also pass. This violates §0 and §§22/24. **Smallest fix:** verify preparation prompt/settings identities, expected generation labels, successful replies, and the texts derived from them.

10. **MAJOR — [manifest.py:88](../../skillopt/coevo5/manifest.py#L88): the frozen openpyxl version is not enforced.** Changing the installed package after manifest generation leaves repository hash verification successful, while workbook structural checks use the changed library. Recording its old version in provenance does not prevent this. This violates §0’s frozen structural-check version. **Smallest fix:** compare the installed version with the manifest at process startup and through the verification hook.

11. **MAJOR — [prelaunch.py:229](../../skillopt/coevo5/prelaunch.py#L229): an unusable I-chain starting Skill passes preflight.** Successful instruction responses can produce a combined, rendered Skill exceeding 20,000 bytes. Preparation reports no missing text and manifest generation succeeds; failure occurs only when an I chain constructs its initial Skill, potentially after earlier paid chains. This violates §3 and §14’s prelaunch validation. **Smallest fix:** validate exactly five nonblank instructions and construct `Skill.seeded(...)` before publishing the manifest.

12. **MAJOR — [run_coevo5.py:130](../../scripts/run_coevo5.py#L130): the report command can write scores into the run.** `report --out <run>/reports` passes the sole destination check and writes `report.json` and `report.md` there. This violates §24’s prohibition on report writes into the run directory. **Smallest fix:** resolve the destination and reject the run root or any descendant, including paths through symlinks, before writing.

13. **MAJOR — [readout.py:336](../../skillopt/coevo5/readout.py#L336): unavailable E-glm updates become negative conclusions.** If E-ds ends while E-glm remains active, the report correctly excludes E-glm’s records, but `registered()` treats its absent updates as zero. Markdown then states “方法几乎没有更新” and “相似位置未被使用”; dependent claims become false instead of unavailable. This violates §12.5, §12.8, and §24’s ended-chain restriction. **Smallest fix:** pass terminal states into the readout, distinguish unavailable records from zero updates, and propagate unavailable dependent conclusions.

14. **MAJOR — [report.py:193](../../skillopt/coevo5/report.py#L193): required attempts, deviations, and costs are omitted.** An interrupted attempt, an authorized cap increase, and a successful retry produce a report without the discarded attempt, recovery decision, deviation, or its spending. The report also omits the required per-stage label/call/token accounting. This violates §13.4 and §2.2. **Smallest fix:** add read-only summaries of attempts, recovery decisions, ledger events, costs, and label usage; include discarded-attempt costs while excluding their scores from readings.

15. **MAJOR — [report.py:109](../../skillopt/coevo5/report.py#L109): denominator exclusions and unknown categories disappear.** If SpreadsheetBench qualification reduces 279 items to 200, the report displays denominator 200 without the 79 exclusions or their reasons. OfficeQA exclusions and evaluation unknown categories are likewise omitted. This violates §2.1 and §10. **Smallest fix:** carry qualification/registry exclusion summaries and each unit’s unknown categories into both report formats.

16. **MINOR — [prelaunch.py:154](../../skillopt/coevo5/prelaunch.py#L154): preparation continues after the mandated rubric stop.** Two invalid SearchQA rubric replies return `None`, but preparation continues making paid calls for the other five rubrics. §22 explicitly requires stopping preparation and awaiting the owner after two invalid replies. **Smallest fix:** stop immediately, retain call records, and publish the incomplete preparation status.

17. **MINOR — [report.py:285](../../skillopt/coevo5/report.py#L285): P3/P4 imputation columns are reversed.** The table labels `KNOWN, LOW, HIGH` as known, unfavorable, favorable for every reading. For reduced forgetting, `LOW` is favorable and `HIGH` unfavorable. Decisions use the correct variant, but the displayed robustness evidence contradicts §12.6. **Smallest fix:** display `KNOWN, HIGH, LOW` for P3/P4 or label numerical low/high explicitly.

18. **MINOR — [report.py:165](../../skillopt/coevo5/report.py#L165): rewrite attempts are undercounted.** A dispatched rewrite returning unchanged text (`kept`) or an invalid answer (`rewrite_failed`) is filtered out, allowing Markdown to report zero rewrites despite actual rewrite calls. This violates §12.7’s required rewrite counts and before/after records. **Smallest fix:** retain every attempted rewrite, its status and before/after text, distinguishing attempts from changes.

19. **MINOR — [prelaunch.py:93](../../skillopt/coevo5/prelaunch.py#L93): redirects are followed before being rejected.** The default urllib redirect handler issues a second request after a 302; the later `geturl()` check rejects it only afterward. This violates §24’s stop-on-redirect rule. **Smallest fix:** install a redirect handler that refuses the redirect before another request is issued.

Validation: all 10 memory-only readout tests passed. The full suite was blocked by the read-only sandbox’s denial of temporary-file creation. No files were modified; no network or model calls were made.

---

## Smoke fix review (2026-10-18, one round)

Change: `skillopt/coevo5/examiner.py` `_edits` accepts and drops a key the revision prompt gives only to other
operations (an add's `id`, a remove's `text`/`check`); new test
`test_a_key_of_another_op_is_dropped_and_an_unknown_key_refused`. Trigger: the GLM-5.3 smoke's revision reply
(registration §25). Codex (`gpt-6-astra`, reasoning effort ultra, read-only sandbox) verbatim:

> No defects found. The leniency soundly follows explicit `op` semantics, strips inapplicable keys before application and recording, preserves valid-reply behavior, and has adequate test coverage for this small change by inspection (pytest was unavailable).

Local: coevo5 suite 633 passed, 1 skipped; ruff clean.
