# coevo5 正式登记的 Codex 设计审查第 4 轮（2026-10-17 16:22，结论 NOT ACCEPTABLE）

> 审查对象：[正式登记第 4 版](coevo5-registration-20261016.md)。原样保存 Codex 的结论（第 3 轮 6 条中 5 条已解决；新问题 2 条：1 条 MUST-FIX、1 条 SHOULD-FIX）；只把链接里的本机绝对路径改成相对路径。

> 命令：`codex exec -m gpt-6-astra -c model_reasoning_effort='"ultra"' --sandbox read-only`。

Version 4 fixes the budget defects and most prior gaps. **One MUST-FIX remains:** the ordered classifier can mask mandatory stops and turn solver failures into infrastructure unknowns.

This was a read-only review with no network calls or paid experiments.

The six round-3 findings:

| # | Status | Reason |
|---|---|---|
| 1 — Baseline reservation | **RESOLVED** | The enforced prompt bound gives `60,000,000 + 88 × 371,584 = 92,699,392`, covered by the 93M reservation; the baseline Skill limit is correctly 32,000 bytes. |
| 2 — Missing-usage settlement | **RESOLVED** | Potentially billable attempts without valid usage retain their allowance; unclosed calls retain the full reservation, including baseline calls. |
| 3 — Outcome classification | **PARTIALLY** | The three original discrepancies are corrected, but overlapping conditions still violate the new first-applicable-row contract; see finding 1 below. |
| 4 — Empty populations | **RESOLVED** | Empty baseline pools prevent launch; zero qualified tests stop evaluation; empty analysis strata are not evaluable without changing weights. |
| 5 — Authorized reruns | **RESOLVED** | The unit list is complete, the completed replacement supplies the trajectory, and earlier attempts remain archived and charged. |
| 6 — Presentation corrections | **RESOLVED** | Candidate-specific transfer panels are explicit, and the corrected C1 range of 0.67–0.71 reproduces. |

The older findings still marked partial in round 3:

| Finding | Status | Reason |
|---|---|---|
| Round 2 #2 | **PARTIALLY** | Mixed-condition classification still changes failure/unknown status and potentially permits whole-unit recovery. |
| Round 2 #7 | **RESOLVED** | Reservation bounds and conservative settlement now address the accounting defects. |
| Round 2 #12 | **RESOLVED** | Baseline recovery, caching and the correct 32,000-byte Skill limit are disclosed. |
| Round 1 #5 | **PARTIALLY** | Qualification and missingness inference are specified, but classification remains inconsistent. |
| Round 1 #21 | **PARTIALLY** | Restart scope and attempt selection are fixed; classification precedence remains unresolved. |
| Round 1 #22 | **PARTIALLY** | Accounting is fixed, but the mandatory budget-stop signal can still be swallowed by the frozen backend. |

The revision introduces or exposes these concrete remaining problems:

1. **MUST-FIX — The ordered table does not preserve precedence when multiple conditions apply.**

   I reproduced three counterexamples offline:

   - **ALFWorld budget refusal plus cleanup failure:** the frozen backend first catches `BudgetStop`, then its `finally` block overwrites the result with `alfworld_cleanup_unconfirmed`. The classifier returns row 7 infrastructure unknown instead of enforcing row 2’s budget stop. See [backend cleanup](../../skillopt/continual_eval/backends.py#L749) and [stop detection](../../skillopt/coevo5/outcomes.py#L155).
   - **ALFWorld truncation plus cleanup failure:** a receipt containing `finish_length` likewise becomes row 7 unknown instead of row 4 noncompletion failure. Receipt-based noncompletion is checked only for selected backend reasons. This changes missingness and can trigger whole-unit recovery. See [receipt classification](../../skillopt/coevo5/outcomes.py#L162).
   - **Spreadsheet generation defect plus configuration error:** a `missing_output` prediction accompanied by a scorer case reporting `spreadsheet_case_count_mismatch` becomes row 8a failure instead of row 1 configuration pause. The generation branch bypasses inspection of the scorer’s configuration reason. This nested reason is an actual frozen-adapter output shape. See [classification](../../skillopt/coevo5/outcomes.py#L188) and [numeric adapter](../../skillopt/continual_eval/sheet_numeric_adapter.py#L108).

   **Change:** Check configuration errors across all relevant records before classifying outcomes. Preserve budget refusal in wrapper state outside the backend’s return value. Apply receipt-based rows 3–4 independently of the backend reason, then process later rows. Add mixed-condition tests using the frozen backend with mocked environments.

   The same correction should reconcile `undelivered(None)`, which currently requests resending despite row 1’s non-dictionary-receipt pause, and completed blank OfficeQA/LiveMath replies, which currently bypass row 4 and become ordinary scored failures. These changes require no frozen-code edits or paid calls.

2. **SHOULD-FIX — The new cleanup instruction requires an identity absent from frozen receipts.**

   [§5.4](coevo5-registration-20261016.md?plain=1#L218) requires another cleanup attempt using this run’s container name. Both frozen executors create UUID names locally but omit them from returned cleanup-failure records: [generation](../../skillopt/continual_eval/backends.py#L144), [generation receipt](../../skillopt/continual_eval/backends.py#L181), and [recalculation](../../skillopt/continual_eval/sheet_recalc.py#L443). The prescribed recovery cannot use those receipts alone.

   **Change:** Simplify this branch to an immediate pause on unconfirmed cleanup, with verified cleanup required before authorized recovery. Retaining automatic cleanup would require a specified, tested way to preserve exact container identities.

Verification: **127 offline tests passed**, with workbook fixture storage redirected to memory for the read-only sandbox. Both zero-call scripts reproduce the registered figures and calibrations. The counterexamples above concern combinations absent from those tests. I found no new statistical, partition-isolation, or accounting defect requiring additional experimental machinery.

VERDICT: NOT ACCEPTABLE