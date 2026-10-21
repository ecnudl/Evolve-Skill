# Codex 设计审查：第 3 版改动登记（一轮，2026-10-19 12:03–12:07）

> 原文照录（gpt-6-astra，推理强度 ultra，只读；只把本机绝对路径的链接改成相对链接）。审查的是改动登记的初稿与当时（第 2 版）的代码；行号对应当时的文件。提示词见文末。处理见 [第 3 版改动登记](coevo5-registration-v3-delta-20261019.md) §12。

1. **(must-fix before launch)** **Complete the chain/readout migration.** `NoSkill-ds` is absent from [chain registration](../../skillopt/coevo5/units.py#L37) and [caps](../../skillopt/coevo5/protocol.py#L288); smoke is fixed to E-glm, while [readout](../../skillopt/coevo5/readout.py#L286) still selects GLM chains. Register the reference’s cap and stage-0-only behavior, parameterize smoke, and explicitly map I-ds primary/E-ds secondary/NoSkill-ds reference throughout reporting.

2. **(must-fix before launch)** **Make PJLAB selection opt-in end to end.** [Client](../../scripts/weak_solver_probe.py#L206) currently selects the backend globally by model; [manifest construction](../../skillopt/coevo5/manifest.py#L94) passes only `router_env`. Thread explicit backend/credential-path settings through prelaunch, smoke and manifest without changing existing callers. Validate every response against the PJLAB-specific model-ID allowlist; preserve frozen retry, resend and receipt semantics.

3. **(must-fix before launch)** **Self-test must own the final candidate record.** [Downstream orchestration](../../skillopt/coevo5/step.py#L562) currently screens, confirms and merges rules from `prepare`. Inserting a self-test call alone can therefore test or merge obsolete text. Produce an immutable self-test plan/hash and use it everywhere downstream; update smoke/report forward-panel lookups, funnel counts and accounting.

4. **(must-fix before launch)** **Bound complete role inputs.** [§6–7](../../docs/handoff/coevo5-registration-v3-delta-20261019.md?plain=1#L128) allows 320,000 OfficeQA context characters before other fields; revision can include 30 solver responses. [Roles.ask](../../skillopt/coevo5/roles.py#L77) has no aggregate input guard. Specify deterministic message budgeting, repeated-task deduplication and truncation markers while preserving final answers/errors. The 16,384-token role output cap does not bound input.

5. **(must-fix before launch)** **“Shared unknown” cannot be implemented from outcome tokens alone.** [Infrastructure unknown](../../skillopt/coevo5/outcomes.py#L46) also includes failures *after* delivered programs/actions. Derive “no answer ever delivered” from receipts/attempts. Use one round-wide mask across all scheduled arms, retain the unfiltered pause guard, and apply exclusions consistently—including format violations, unknown denominators and each composite member’s four-trigger minimum. Per-candidate masks would change acceptance bias.

6. **(should-fix)** **The format check can pass a broken backend.** [§2](../../docs/handoff/coevo5-registration-v3-delta-20261019.md?plain=1#L60) accepts E=I=NoSkill=0/20, and “single letter” omits LiveMath’s [mandatory answer tags](../../skillopt/continual_eval/backends.py#L463). Use scorer-compatible format extraction plus a declared absolute completion/format floor. Empty-Skill byte identity is feasible with the proposed opt-in layout; preserve exact whitespace and the legacy default.

7. **(should-fix)** **Bind spreadsheet views to the exact scored artifacts.** [Scoring directories](../../skillopt/coevo5/cells.py#L158) vary by scoring attempt; [answer projections](../../skillopt/coevo5/step.py#L210) omit receipt links. Recalculated workbooks survive in JSON receipts, not necessarily `.xlsx` files. Follow the final score’s case-specific receipt hashes, verify bindings, and use the scorer’s adapted read view. Show case, typed values, availability and scorer-equivalence; native reference caches alone are not the actual comparison operands.

8. **(should-fix)** **Expanded spreadsheet references need contextual leakage adjudication.** [Mechanical checks](../../skillopt/coevo5/leakage.py#L106) index instructions, while [ordinary adjudication](../../skillopt/coevo5/leakage.py#L258) sees only rule text. Copied cell constants disguised as examples can evade both. Supply bounded proposal-half cell facts to veto-only adjudication for original and revised rules; keep its private evidence out of analyst feedback.

9. **(should-fix)** **Quota failures are not a spending cap.** [§9](../../docs/handoff/coevo5-registration-v3-delta-20261019.md?plain=1#L190) leaves DeepSeek uncapped, and its endpoint receives [no budget](../../skillopt/coevo5/units.py#L94). The unknown-share guard runs after batches. Add a separate finite request/token allowance. Report persisted sends’ known usage plus unknown-cost attempts: earlier internal retries retain statuses, not complete usage, so final-receipt totals are lower bounds.

10. **(should-fix)** **Qualify the self-test justification.** [§7](../../docs/handoff/coevo5-registration-v3-delta-20261019.md?plain=1#L156) overstates what evidence-item failure predicts about C1. Strict improvement on 2–8 noisy items can reject useful rules; fresh C2 responses still reuse optimized evidence items, whose gains can offset other-item harm. Remove the near-implication and disclaim inherited error-rate calibration. Also disclose that revision eligibility reveals check-half support membership, although its contents remain hidden.

11. **(should-fix)** **Remove “same injected prompt, therefore no comparison effect.”** [§9](../../docs/handoff/coevo5-registration-v3-delta-20261019.md?plain=1#L187): hidden instructions can interact with Skill/layout, and token overhead neither identifies them nor establishes stability. Describe upstream behavior as unknown and retain endpoint-qualified conclusions.

Overall verdict: viable design, but not launch-ready until the must-fix items are addressed.

## 提示词

```text
You are reviewing a DESIGN (one read-only round; no edits; be concrete and brief). The owner has said: do not run
endless re-reviews -- this is the only design review, so report what matters.

Repository: the current working tree. Pipeline: `skillopt/coevo5/` (code currently = protocol
`fivebench-coevolution-v2`), solver prompt in `skillopt/continual_eval/backends.py` (`solve`), solver client
`scripts/weak_solver_probe.py` (`Client`). Documents (Chinese):
- docs/handoff/coevo5-registration-v3-delta-20261019.md  <- THE DESIGN UNDER REVIEW (v3 changes relative to v2)
- docs/handoff/coevo5-registration-v2-delta-20261019.md  (v2 changes relative to v1)
- docs/handoff/coevo5-registration-v6-20261017.md         (v1 registration)
- docs/handoff/coevo5-pipeline-audit-20261019.md           (the audit that motivated v3; facts from v1/v2 runs)
- docs/handoff/coevo5-pipeline-audit-codex-20261019.md     (your earlier read-only audit)

Context: v1 (GLM-5.3 solver) accepted rules in 1 of 5 stages (chain E) and 0 of 5 (chain I). The v2 smoke found a
prompt-layout bug (the answer-format contract appended after the Skill fell under the scaffold's last section,
ALFWorld; 79% of OfficeQA answers lost the <answer> tag). The owner chose: fix bugs + make failure causes visible +
a proposal-half self-test; I chain primary; ALFWorld reported as "not testable" when triggers are insufficient; and
now: run with the weaker deepseek-v4-flash as the SOLVER (method roles stay GLM-5.3), via a new PJLAB token endpoint.
The v1 test scores were opened before this design (stated in the document).

Please check:
1. Does each change do what it claims, and is any change unsafe or self-defeating? In particular:
   a. prompt_layout "contract-first-v1": empty-Skill prompt byte-identical? any caller/runtime/manifest that would
      silently change for frozen v1/v2 snapshots or other studies? is a format check criterion sensible?
   b. shared-unknown exclusion in the gate (§3): definition per round, effect on C1/C2/C3/C4'/composite/undetermined
      share, the "<4 trigger items after exclusion -> undetermined" rule, interaction with the pause guard; can it be
      gamed or bias acceptance (e.g. an arm-dependent filter)?
   c. analyst per-rule validation and the "conditions only on visible information" criterion in adjudication.
   d. SpreadsheetBench/OfficeQA views (§6): leakage risks, payload sizes vs a GLM-5.3 role call, whether the
      recalculated values can be found reliably from the stored scorer artifacts (cells.py `_score`, the numeric
      adapter's `recalculations/` receipts), anything that makes diagnosis inconsistent with the scorer.
   e. the self-test unit (§7): selection effects on the gate's error properties (gate cells are fresh, C1 uses
      check-half triggers, C2 the full focal panel which INCLUDES the proposal-half evidence items), the pass rule
      sum L(rule) > sum H(parent) on 2-8 evidence items, the single revision, leakage/dedup of revised texts, moving
      forward panels after the self-test, and whether anything breaks the "analyst sees only the proposal half" rule.
   f. readings (§1): I-ds primary; anything wrong or missing; NoSkill-ds reference.
   g. deepseek via the PJLAB token endpoint (§9): injected-system-prompt risk, uncapped deepseek usage, response model
      id checks, concurrency, the frozen client's retry/receipt semantics.
2. Anything in the current code that the design forgets and that would make v3 crash or silently misbehave
   (e.g. smoke.py fixed to E-glm, readout/report hard-coding E-glm/I-glm/NoSkill-glm, chain caps for a new
   NoSkill-ds chain, prelaunch/manifest assumptions about clients or the deepseek "free route").

Output: a numbered list, most important first; for each: (must-fix before launch | should-fix | optional), the
problem with file:line where relevant, and the minimal change. Then one line: overall verdict. Do not propose new
experiments; do not restate the design back.
```
