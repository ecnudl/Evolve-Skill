# coevo5 第一批代码 Codex 审查（第 5 轮，2026-10-17 19:02）

> 模型 gpt-6-astra（推理档位 ultra），只读沙盒。审查对象：按第 4 轮 2 条修改后的第一批代码（前几轮原文见 [r1](coevo5-code-review-b1-r1-20261017.md)–[r4](coevo5-code-review-b1-r4-20261017.md)）。原文如下，未改动。

Round-4 dispositions: **#1 PARTIAL**—the openpyxl warning and immediate-write paths are contained, but buffered output still escapes (finding 1). **#2 FIXED**—the actual receipt-parser reproduction now produces ledger detail `other` and monitor category `11:unclassified:other`; raw provider text stays in the cell record.

1. **MAJOR — Buffered output escapes after restoration.** [evaluation.py:73](../../skillopt/coevo5/evaluation.py#L73)

   Only the replacement sink is flushed. A native `printf()` or buffered write through a cached original `sys.stdout` can remain pending until after descriptors are restored, then enter operational logs.

   Reproduced using actual `contained()` with an anonymous pipe replacing its file sink: both deferred-write sentinels appeared externally; ordinary `print()` remained sealed.

   **Fix:** flush saved Python streams and native stdio before restoring descriptors, or retain sealed output bindings for the evaluation process’s lifetime. Add deferred-flush regression tests; the existing `os.write()` test bypasses buffering.

2. **MAJOR — Failure to persist an error exposes its original exception context.** [evaluation.py:272](../../skillopt/coevo5/evaluation.py#L272)

   If test loading raises `KeyError("SEALED_TEST_CONTENT")` and writing `status.json` fails—for example, with `ENOSPC`—the escaping `OSError` retains that original exception as its context. After containment restores stderr, ordinary traceback logging exposes the test text.

   Reproduced in memory through `_evaluate()`: the externally formatted traceback contained the sentinel despite its also reaching sealed diagnostics.

   **Fix:** enforce exception sanitization at the outer evaluation boundary, including failures during diagnostic/status writing. A safe exception raised `from None` must escape even when persistence fails. Add fault-injection tests for both writes.

3. **MINOR — A diagnostics flush failure leaves descriptors and containment state inconsistent.** [evaluation.py:74](../../skillopt/coevo5/evaluation.py#L74)

   Injecting `ENOSPC` from `sink.flush()` leaves `depth == 0`, retained saved state, and both descriptors still redirected, although Python stream references have been restored. Saved descriptors remain open; subsequent containment captures incorrect restoration targets.

   **Fix:** make restoration and resource cleanup exception-safe with `finally` blocks, and reset state consistently. Add teardown-failure tests. Normal nesting and overlapping-thread exits passed the in-memory checks.

Read-only validation: 71 core/accounting tests passed. The filesystem-writing suite could not run under this sandbox; findings above were reproduced without file writes.

VERDICT: NOT ACCEPTABLE
