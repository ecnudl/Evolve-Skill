# Codex 代码审查：第 3 版（一轮，2026-10-19 12:51–12:55）

> 原文照录（gpt-6-astra，推理强度 ultra，只读；只把本机绝对路径的链接改成相对链接）。审查对象是第 2 版冻结快照到第 3 版的全部改动（28 个改动文件、2 个新文件，约 3,700 行的 diff；第 2 版文件取自开发机快照，逐个核对过哈希）；行号对应审查时的文件。提示词见文末（其中 diff 的路径是本机临时目录）。处理见 [第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §13。

1. **(major; check 3)** [step.py:686](../../skillopt/coevo5/step.py#L686), [gate.py:121](../../skillopt/coevo5/gate.py#L121): Excluding evidence from C2 also excludes it from the unknown-share calculation. Concrete case: 60 focal items; four triggers × four runs pass for the rule and fail for parent/controls; eight evidence items × two runs are unknown only for the rule; remaining items pass. Actual unknown share is **16/128 = 12.5%**, yet the verdict is **pass**. Composite has the same defect at [gate.py:197](../../skillopt/coevo5/gate.py#L197). **Fix:** calculate unknown share over all scheduled items after shared exclusion, independently of C2’s evidence omission.

2. **(major; checks 1–2)** [smoke.py:219](../../skillopt/coevo5/smoke.py#L219), [smoke.py:231](../../skillopt/coevo5/smoke.py#L231): An accepted analyst reply containing `[{}, valid_rule]` retains the malformed first row with `text=None`. When a smoke fallback path remains, `paths()` selects that row; `leakage.mechanical(None, corpus)` raises `ValueError`, pausing smoke before stage 2. **Fix:** select an eligible valid-text proposal; record the path as unavailable when none exists.

3. **(major; checks 2–3)** [step.py:456](../../skillopt/coevo5/step.py#L456): A healthy parent first round followed by one revised candidate with one infrastructure-unknown cell out of four pauses the **entire chain**. Round 2 guards candidate arms, whereas round 1 guards only the parent. **Fix:** preserve the parent/control pause rule; candidate unknowns should determine that candidate’s outcome.

4. **(major; check 5)** [step.py:488](../../skillopt/coevo5/step.py#L488): Five failing OfficeQA rules, each retaining one task with 20,000 ASCII context characters and two 4,000-character Chinese answers, already consume 220,000 bytes before metadata. Trimming stops at one task per rule and sends an oversized payload; the reproduced payload was **223,318 bytes**. **Fix:** permit deterministic removal of the final example and enforce the bound before dispatch, rejecting fixed-field overflow without dropping required fields.

5. **Checks 4, 6, 7, 8: no finding.** Also no finding in the DeepSeek scopes, PJLAB routing, response-model allow-list, or evaluation subprocess wiring.

Overall verdict: **launch-ready after fixes.**

## 提示词

```text
You are reviewing CODE (one read-only round; no edits; be concrete and brief). The owner has said: do not run endless
re-reviews -- this is the only code review of this version, so report what matters for a correct launch.

Repository: the current working tree. Protocol `fivebench-coevolution-v3` in `skillopt/coevo5/` plus
`skillopt/continual_eval/backends.py` (solver prompt layout) and `scripts/weak_solver_probe.py` (solver client).
The complete v2 -> v3 change is the unified diff
/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/71911d5c-9ef2-4e75-83fd-f7a5a6cb76ca/scratchpad/v3/v3.diff
(v2 = the frozen v2 snapshot, verified by hash; 28 changed files, 2 new: `skillopt/coevo5/sheetview.py`,
`tests/test_coevo5_v3.py`). The design is docs/handoff/coevo5-registration-v3-delta-20261019.md (Chinese; §12 lists how
your earlier design review's 11 items were handled). Earlier versions' registrations: v2 delta
docs/handoff/coevo5-registration-v2-delta-20261019.md, v1 docs/handoff/coevo5-registration-v6-20261017.md.
Offline tests: `python -m pytest -q tests/test_coevo5_*.py tests/test_weak_solver_probe.py` (713 passed, 1 skipped).

What v3 will do next (on the Linux development machine): snapshot the code; redo the SpreadsheetBench engine
certification and training-side qualification on the snapshot; `build-archive --previous`; `import-texts`; a few
deepseek probe calls; `smoke-make --chain I-ds --deepseek-env <600-mode file> --engine-qualification ...
--sheet-qualification ...` then `smoke` (stage 0 = the format check, then two learning stages, training data only);
`make-manifest --deepseek-env ...`; `check-baselines`; consent; then launch the chains NoSkill-ds, I-ds and E-ds
concurrently (deepseek-v4-flash solver through the PJLAB token endpoint, 12 shared slots; GLM-5.3 method roles,
10 slots), each evaluating on five test sets at stages 0-5 (NoSkill-ds: stage 0 only).

Please check, with file:line and a concrete failing input/state for each finding:
1. Launch blockers: anything that would crash, deadlock, refuse every call, or silently misbehave in the smoke or the
   formal run -- in particular the deepseek ledger scopes (budget.rooted / deepseek_scope / chain.caps /
   evaluation_scopes / units.endpoints / smoke), the PJLAB route through prelaunch -> manifest -> _clients -> Client,
   the response-model allow-list, and the evaluation subprocesses of ds chains.
2. Self-test: does every downstream unit (screen, confirm, composite, merge, smoke paths, report) read the self-test
   plan when it exists and only then; revised texts (dedup, leakage, length, `before_selftest`), the second round
   against the parent's first round, statuses, resume/identity of the new unit (a rerun after a pause must not mix
   attempts or re-ask with different inputs).
3. Shared exclusion (receipt-based), the trigger minimum (verdict and composite), C2 leaving out evidence items, the
   pause guard unchanged; any arm-dependent filtering.
4. Format check: denominators, unknown handling, the floor and the margin, the stop status and how the manifest then
   refuses the smoke.
5. Views and bounds: sheetview binding to the final scoring's receipts (wrong case/attempt/receipt, stale directory),
   anything that could put a test item or hidden data into a role call, `roles.fit` never exceeding the bound or
   silently dropping required fields, leakage adjudication values.
6. The layout: empty-Skill byte identity, the historical order for callers without the option, ALFWorld.
7. Readout/report: ds family registration, NoSkill-ds stage 0 only, primary/secondary, deepseek cost columns.
8. Frozen behaviour: anything in the diff that changes v1/v2 snapshots' or other studies' behaviour (they import
   `skillopt.continual_eval.backends` and `scripts/weak_solver_probe.py`).

Output: a numbered list, most severe first; for each: (blocker | major | minor), file:line, failing input/state ->
wrong result, minimal fix. Say "no finding" for any of 1-8 where you found nothing. Do not restate the design; do not
propose new experiments or redesigns. Then one line: overall verdict (launch-ready after fixes or not).
```

## 补充审查：PJLAB 后端写明推理模式（一轮，2026-10-19 13:23–13:24）

> 原文照录（同上设置）。审查对象是快照 a 到快照 b 的改动（`scripts/weak_solver_probe.py` 的后端条目带上 `thinking: enabled`，及其测试）与开跑前探查的用量记录；提示词在本机临时目录，要点见[第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §9。

1. **minor** — [docs/handoff/coevo5-registration-v3-delta-20261019.md:221](../../docs/handoff/coevo5-registration-v3-delta-20261019.md?plain=1#L221): “other settings unchanged” omits the new experimental control. Record `thinking=enabled`, the probe denominators, and historical rationale; sync the affected workflow, results-ledger, and status entries.

Verdict: Code acceptable across smoke format checks, gate cells, evaluation subprocesses, and ALFWorld steps; free-router, BigModel, and frozen v1/v2 behavior remain unchanged. No receipt, reservation, or manifest-schema change needed; generate smoke/launch manifests from the patched snapshot. Enabled matches historical thinking behavior; the supplied evidence gives no reason to prefer disabled.

## 第二次补充审查：PJLAB 后端改为不推理并逐次核对（一轮，2026-10-19 13:36–13:38）

> 原文照录（同上设置；链接改成相对路径）。审查对象是快照 b 到快照 c 的改动（`scripts/weak_solver_probe.py` 的后端条目改为
> `thinking: disabled`，回复带推理文字记 `thinking_mismatch`；`skillopt/coevo5/outcomes.py` 第 4 行加入这一类型；协议注释；两份
> 测试）与 48 次探查的记录；提示词在本机临时目录，要点见[第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §9。

1. **minor** — [docs/handoff/coevo5-registration-v3-delta-20261019.md:221](coevo5-registration-v3-delta-20261019.md): §9 still specifies `enabled`. Update the current registration and living summaries to `disabled`, the new probe counts, and the mismatch → resend → infrastructure-unknown policy; preserve historical records.

Verdict: Code feasible on static review—all listed v3 callers and receipt consumers are covered, frozen callers remain unchanged, and the supplied evidence favours `disabled`.

## 第三次补充审查：存档带入检查（一轮，2026-10-19 13:58–14:00）

> 原文照录（同上设置）。审查对象是快照 c 到快照 d 的改动（`skillopt/coevo5/prelaunch.py` 的 `check_archive` 带入规则，及
> `tests/test_coevo5_prelaunch.py` 的新测试）；起因、改法与开发机上的零调用试运行见[第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §13。

No finding

Verdict: Accept. The rule handles v2 and v3, rejects omitted or changed carried pages, and is consistent with the callers; no other v2-only archive assumption found in the pre-launch path.

## 第四次补充审查：SpreadsheetBench 做题提示 `contract-first-v2`（一轮，2026-10-19 14:4x）

> 原文照录（同上设置；链接改成相对路径）。审查对象是快照 d 之后的改动（`skillopt/continual_eval/backends.py` 的新排版值与
> SpreadsheetBench 格式句、`skillopt/coevo5/protocol.py` 的运行时、`tests/test_coevo5_v3.py`），起因是格式检查没通过与负责人的选择，
> 见[第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §2 修订与 §13。

1. **major** — [texts.py:75](../../skillopt/coevo5/texts.py) still quotes the old contract as what the solver “always receives.” Imported cards carry this into analyst inputs (`analyst.py:135,146`) and self-test revision (`step.py:486`). **Minimal fix:** supply a runtime-aware effective contract to these role views, including imported-card paths, and test it against v2. Preserve historical generation cards and provenance.

2. **minor** — [current-workflow.md:66](../current-workflow.md) still specifies v1 and unchanged empty-Skill prompts; registration §2 agrees, while [project-status.md:332](../project-status.md) still awaits the owner’s decision. **Minimal fix:** append the dated amendment and update current workflow/status to v2 with the rerun pending; preserve the failed check.

Verdict: fix the stale views before rerunning; solver routing across all requested execution paths, frozen-caller compatibility, and the wording’s workbook semantics otherwise look correct.

## 第五次补充审查：格式检查的下限只卡 E、I（一轮，2026-10-19 16:5x）

> 原文照录（同上设置）。审查对象是快照 e 到快照 f 的改动（`skillopt/coevo5/smoke.py` 的 `FORMAT_FLOORED`，`tests/test_coevo5_smoke.py`
> 的新测试）；起因与负责人的选择见[第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §2 第二次修订。

No finding

Verdict: Matches the owner's amended rule; consumers remain compatible. Empty shares and unknown counts stay recorded; an unknown-heavy empty arm can make the margin nonbinding, but E/I's floors still apply.
