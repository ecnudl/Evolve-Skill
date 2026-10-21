# coevo5 第一批代码 Codex 审查（第 4 轮，2026-10-17 18:48）

> 模型 gpt-6-astra（推理档位 ultra），只读沙盒。审查对象：按第 3 轮 3 条修改后的第一批代码（前几轮原文见 [r1](coevo5-code-review-b1-r1-20261017.md)、[r2](coevo5-code-review-b1-r2-20261017.md)、[r3](coevo5-code-review-b1-r3-20261017.md)）。原文如下，未改动。

Round-3 dispositions:

- **#1 FIXED:** [budget.py:147](../../skillopt/coevo5/budget.py#L147) quarantines guarded failures before unlocking; the single event replays closes and halt together. In-memory checks covered failures before/after persistence, failed refusal commits, and exception chaining.
- **#2 FIXED:** [calls.py:82](../../skillopt/coevo5/calls.py#L82) retains the attempt’s generation across waits/resends. Reservations check it under lock; recorder latches survive frozen-solver exception handling.
- **#3 FIXED:** [evaluation.py:48](../../skillopt/coevo5/evaluation.py#L48) accepts canonical ASCII attempt numbers, requires directories, and sorts numerically.

1. **MAJOR — Workbook content escapes through warnings before unseal.** [outcomes.py:347](../../skillopt/coevo5/outcomes.py#L347), [cells.py:124](../../skillopt/coevo5/cells.py#L124).

   A workbook containing `_xlnm.Print_Area=SEALED_TEST_CONTENT` makes openpyxl write `Print area cannot be set to Defined name: SEALED_TEST_CONTENT.` to stderr. Reproduced entirely in memory through actual `preflight()` and separately through the frozen solver’s input-workbook preview. Preflight accepted the workbook; the input-preview path emitted its content before any model reply. These warnings can therefore expose test content in operational logs.

   **Fix:** contain data-dependent warnings within coevo5’s evaluation execution, including preview, structural checks, and qualification. Keep raw diagnostics in sealed artifacts and expose fixed categories. Add stdout/stderr sentinel tests; existing record/monitor checks miss this channel. Frozen modules need no modification.

2. **MAJOR — Unvalidated provider diagnostics reach the shared ledger and monitoring records.** [calls.py:180](../../skillopt/coevo5/calls.py#L180), [evaluation.py:141](../../skillopt/coevo5/evaluation.py#L141).

   The frozen client accepts arbitrary string `finish_reason` values. A malformed response with `finish_reason="SEALED_TEST_CONTENT"` produces `error_type="finish_SEALED_TEST_CONTENT"`. That text reaches both global settlement details and `unknown_by_reason`, which `monitor()` exports. Reproduced through the real receipt parser, solver, classification, and counting functions; one such unknown among 20 cells remains below the infrastructure-pause threshold.

   This requires malformed provider metadata containing test text; it is not evidence that normal provider responses currently do this.

   **Fix:** allowlist externally visible diagnostic categories in coevo5, mapping unexpected values to a fixed category and retaining raw metadata only in sealed records. Add a sentinel regression covering both ledger details and monitor output.

Validation: 71 core/accounting tests passed. Findings were reproduced in memory; the filesystem-writing suite was not rerun. No files were modified.

VERDICT: NOT ACCEPTABLE
