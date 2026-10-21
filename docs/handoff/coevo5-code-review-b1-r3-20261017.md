# coevo5 第一批代码 Codex 审查（第 3 轮，2026-10-17 18:19）

> 模型 gpt-6-astra（推理档位 ultra），只读沙盒。审查对象：按第 2 轮 6 条修改后的第一批代码（第 1、2 轮原文见 [r1](coevo5-code-review-b1-r1-20261017.md)、[r2](coevo5-code-review-b1-r2-20261017.md)）。原文如下，未改动。

1. **MAJOR — R2 #2 PARTIAL: reconciliation releases capacity before halting.** [calls.py:161](../../skillopt/coevo5/calls.py#L161). After an uncertain reservation commit, `_fail()` settles the unsent reservation at zero, releases the ledger lock, then separately calls `halt()`. Another endpoint can reserve and send between those operations. A crash there leaves the ledger admitting calls without recovery authorization.

   Reproduced in memory using the actual transition and endpoint methods: `reserve → settle → reserve → settle → halt`; the competing client sent once. The regression at [test_coevo5_calls.py:344](../../tests/test_coevo5_calls.py#L344) explicitly expects separate settlement/halt events and checks only the resulting state.

   **Fix:** quarantine bookkeeping failures under the original ledger lock where possible; make compensating settlement and halt one replayable event. Test concurrent admission and crash prefixes around failure reconciliation.

2. **MAJOR — R2 #3 PARTIAL: halt generations do not cover resend cooldowns or slot waits.** [calls.py:188](../../skillopt/coevo5/calls.py#L188), [calls.py:86](../../skillopt/coevo5/calls.py#L86), [budget.py:209](../../skillopt/coevo5/budget.py#L209). Each `reserve()` invocation captures a fresh generation. If another process halts and the owner resumes while an existing cell is in its five-minute cooldown, its next resend accepts the new generation and continues the original attempt. Waiting for a concurrency slot before entering `reserve()` has the same gap.

   Reproduced: HTTP 429 → cooldown containing halt/resume → successful resend from the original recorder. Two calls were sent; `recorder.broken` remained `None`. The current regression covers only waiting *inside* `reserve()`.

   **Fix:** bind pending work to a halt generation before blocking, retain it across resends and slot waits, and check that expected generation atomically during admission. Authorized recovery should create fresh attempt-bound state. Add both interleaving tests.

3. **MINOR — Malformed Unicode attempt names crash enumeration.** [evaluation.py:51](../../skillopt/coevo5/evaluation.py#L51). `isdigit()` accepts `²`, but `int("²")` raises `ValueError`. An `attempt-²` entry therefore breaks both `monitor()` and `_next_attempt()` instead of being ignored. Reproduced with an in-memory directory fixture.

   **Fix:** validate canonical ASCII positive integers before conversion and require directory entries. Extend the malformed-name test with Unicode suffixes.

The six round-2 dispositions are:

| R2 | Status | Evidence |
|---|---|---|
| 1 | **FIXED** | [calls.py:142](../../skillopt/coevo5/calls.py#L142) latches before persistence; [budget.py:71](../../skillopt/coevo5/budget.py#L71) applies settlement and breach halt from one event. |
| 2 | **PARTIAL** | Uncertain reservation identity and endpoint/recorder latches work; [cells.py:179](../../skillopt/coevo5/cells.py#L179) forces a ledger pause despite frozen-solver exception handling. Finding 1 remains. |
| 3 | **PARTIAL** | Generation changes reject callers already polling inside `reserve()`. Finding 2 remains. |
| 4 | **FIXED** | [evaluation.py:89](../../skillopt/coevo5/evaluation.py#L89) holds the qualification lock through attempt selection and pause publication; interrupted directories also require recovery authorization. |
| 5 | **FIXED** | Registry entries, predecessors, unit records and every reuse-resolution source enforce the run identity at [evaluation.py:113](../../skillopt/coevo5/evaluation.py#L113), [147](../../skillopt/coevo5/evaluation.py#L147), and [218](../../skillopt/coevo5/evaluation.py#L218). |
| 6 | **FIXED** | Numeric ordering fixes the reported 9→10 error. Finding 3 is a separate malformed-name edge case. |

No additional normal-path §0 exposure was found in the inspected readers, monitoring output, or global journal summaries.

Validation: 71 core/accounting tests passed; the three findings were reproduced in memory. The full filesystem-writing suite was not rerun in this read-only sandbox. No files were modified.

VERDICT: NOT ACCEPTABLE
