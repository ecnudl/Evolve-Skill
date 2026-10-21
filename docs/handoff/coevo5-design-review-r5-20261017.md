# coevo5 正式登记的 Codex 设计审查第 5 轮（2026-10-17 16:31，结论 ACCEPTABLE）

> 审查对象：[正式登记第 5 版](coevo5-registration-20261016.md)。原样保存 Codex 的结论（没有必改项；2 条 SHOULD-FIX，已在第 5 版内改，见登记 §19）；只把链接里的本机绝对路径改成相对路径。

> 命令：`codex exec -m gpt-6-astra -c model_reasoning_effort='"ultra"' --sandbox read-only`。

Version 5 has **no remaining MUST-FIX**. Two SHOULD-FIX details remain. Acceptance concerns the design; §14’s implementation and prelaunch review requirements still apply.

| Finding | Status | One-line reason |
|---|---|---|
| Round 4 #1 | **PARTIALLY** | The material budget-stop and outcome errors are fixed; a non-dictionary receipt combined with cleanup failure still selects row 3 instead of row 1. |
| Round 4 #2 | **PARTIALLY** | Immediate pausing removes the impossible receipt-name-based cleanup, but the recovery check overlooks running orphan containers. |
| Round 3 #3 | **PARTIALLY** | Outcome categories now agree with the registration, apart from the remaining configuration-versus-cleanup precedence case. |
| Round 2 #2 | **RESOLVED** | Delivered-answer failures, undelivered requests and same-artifact remedies now have consistent treatment; the remaining precedence issue only changes the pause reason. |
| Round 1 #5 | **RESOLVED** | Qualification, completion-aware classification, conservative gate bounds and directional missingness analyses address the denominator problem. |
| Round 1 #21 | **PARTIALLY** | Manifest and restart choices are specified; the two exceptional pause/recovery details below still need tightening. |
| Round 1 #22 | **RESOLVED** | Conservative accounting remains intact, and wrapper-owned refusal state preserves budget stops when backend cleanup overwrites its reason. |

1. **SHOULD-FIX — Non-dictionary receipts can still lose configuration-error precedence.**

   I reproduced this through the frozen backend: an ALFWorld call returns `None`, then `env.close()` raises. The backend replaces `invalid_model_receipt` with `alfworld_cleanup_unconfirmed`; `classify(..., receipts=[None])` raises `CleanupUnconfirmed`, although registration row 1 requires `ConfigurationError`. The classifier scans prediction/scoring reasons before inspecting receipts. See [outcomes.py:139](../../skillopt/coevo5/outcomes.py#L139) and [backends.py:749](../../skillopt/continual_eval/backends.py#L749).

   **Concrete change:** Before budget and cleanup checks, reject any non-dictionary entry in the recorded solver receipts as row 1, and add this mixed-condition test. This is SHOULD-FIX because both current and required branches pause without producing a scored outcome or permitting automatic retries.

2. **SHOULD-FIX — The revised recovery check does not establish cleanup of running orphan containers.**

   [§13.4](coevo5-registration-20261016.md?plain=1#L594) checks exited/created containers and assumes running containers belong to other chains. However, a timed-out Docker client followed by failed container removal can leave this attempt’s container running. The bounded command kills the client process, while the executors separately attempt removal and report unconfirmed cleanup if it fails. See [sandbox.py:91](../../skillopt/skill_validation/sandbox.py#L91), [backends.py:174](../../skillopt/continual_eval/backends.py#L174), and [sheet_recalc.py:468](../../skillopt/continual_eval/sheet_recalc.py#L468).

   **Concrete change:** Before authorizing recovery, stop dispatching native work, drain legitimate active executions, and verify that no matching containers remain **in any state**, alongside the ALFWorld worker check. If cleanup cannot be verified, retain the pause or terminate. This avoids adding container-identity machinery.

I found no additional statistical, test-isolation, gate or budget-accounting defect requiring a MUST-FIX. **All 136 offline tests passed**, with workbook temporary storage redirected to memory. No files were edited, and no network calls or paid experiments were run.

VERDICT: ACCEPTABLE