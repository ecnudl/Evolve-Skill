# Direction-review brief (2026-10-21 morning, after the overnight exploration)

## The question
The project owner asks (verbatim): "所以综合以上派生的subagent的探索结果，我后续的方向应该怎么改比较合适"
— given everything the overnight feasibility explorations (23 of 24 directions), the cal-1 calibration
experiment and the v3 co-evolution run found, how should the research direction change?
The owner reads the answer themselves (plain Chinese, no jargon, no dressing up of negative results).

## Owner's two core objectives (verbatim, 2026-10-20 evening)
"1. 协同进化，skill进化，验证端coding rubric进化 2 评测指标是泛化性，可以考虑不同的bench去刷一下分，
但是必须还是要在一个bench上进化，然后其余bench上评测"
Yardstick set 2026-10-10 and refined 10/17: generalization across datasets WITHOUT a validation set
("不要去为了某一个数据集而去做一些过拟合的优化"); the target pattern is transfer along a similarity map fixed
before launch (SearchQA–OfficeQA, OfficeQA–LiveMath, OfficeQA–SpreadsheetBench, ALFWorld none): evolve on bench A
cumulatively, test all five; A improves, similar benches improve somewhat, dissimilar benches do not drop.
DeepResearch is narrowed to one job: after seeing TRAINING results, produce better generated tasks or better rule
text so that no validation set is needed. The owner prefers the more effective design option when it is
pre-registered and honestly costed ("采用效果好一点的方法"). Negative or pending results are never presented as
positive. Five benches since 10/13: SearchQA, OfficeQA, LiveMath, SpreadsheetBench, ALFWorld
(solver deepseek-v4-flash via the PJLAB route, method roles GLM-5.3).

## What is established — read the sources yourself; do not take this list on faith
- v8–v11 (2026-10-08..12, earlier five-bench work): a learned Skill's gain over a reasonable generic instruction
  was not established on any bench (SearchQA: total +12.1, a generic instruction alone gives +7.5/+9.2, one learning
  step on top of generic +2.9 [−1.1, +7.2]; KOR +7 did not replicate). Ledger: docs/results-and-lessons.md
  (search "10/12"), memory note "active-evidence-v11-progress".
- fivebench-coevolution-v3 (launched 10/19, analysed 10/20): BOTH chains accepted 0 rules over 10 steps;
  funnel 49 proposals → 28 selftest → 14 screen → 2 passed screen → 0 survived confirm. Same text re-run at
  temperature 0 moves 30/194 items (≈16% per-item non-reproducibility); a rule's net effect is smaller than that
  churn; 50% of trigger-panel items score 0 for every arm ("dead"); paired sign tests p ≥ 0.25 for all 17 arms;
  the cross-domain / forward (generated-task) path never ran (0 forward panels). Sources: docs/results-and-lessons.md
  ledger entries dated 10/19–10/20 (lines ~140–148), docs/handoff/coevo5-midrun-analysis-20261019.md,
  docs/handoff/coevo5-registration-v6-20261017.md (training-pool table at lines 84–88: SearchQA 600, OfficeQA 74,
  LiveMath 283, ALFWorld 57 items; SpreadsheetBench at line 87), docs/handoff/coevo5-registration-v3-delta-20261019.md.
  v3 cost ≈ 139M tokens with every post-step-0 test evaluation reused (a successful run would cost more).
- cal-1 calibration (2026-10-20): docs/handoff/cal1-registration-20261020.md (results in the dispatch log at the
  end). 11 texts × 200 SearchQA training items × 4 runs = 8,800 solver calls, 27,481,897 tokens (≈3.1k tokens per
  call). Known-good full Skill +0.094 [0.05, 0.14]; seed-only +0.089; rule-sized bridges +0.004/−0.030/−0.026;
  C1 gate passage for the +9-point Skill at n=11 = 75.8% (pre-registered inconclusive band 50–80%); null 0%;
  placebos (irrelevant text in the rule slot) −0.098 / +0.036.
- Overnight feasibility exploration (2026-10-21, 24 directions D1–D14 and E1–E10, Opus agents, training pools
  only): owner report docs/handoff/overnight-report-20261021.md (§6 has the three headline findings, the critic
  table 6.5 and the per-direction results table); synthesis of the first 13 directions:
  docs/handoff/feasibility-exploration-20261021-cn.md; per direction: docs/handoff/feasibility-20261021/<ID>/
  result.json (explorer's structured result; verdict_cn), critic-result.json (adversarial critic: verdict,
  corrected_feasibility, refuted_claims, confirmed_claims, notes_cn), report.md. Direction definitions:
  docs/handoff/feasibility-20261021/context-D1-D14.md and context-E1-E10.md.
  Important corrections made by the critics (do not repeat the refuted versions as facts): the E4 "+7 generic
  instruction gain" is mostly tag-dropping + the LiveMath meta-option artefact; the "placebo −9.8" is mostly
  JSON-formatted answers scored wrong (−0.25 with JSON accepted); D9's "a rule has 0–3 points of headroom" was not
  measured with a "card + one rule" arm; D3's ALFWorld gain depends on a modified harness.
- v4 (17 bug fixes + 7 prompt improvements of the v3 protocol) is specified and planned but NOT implemented:
  docs/handoff/v4-plans-20261021/spec.md, G1..G6.v2.md. Whether v4 should be implemented at all, as is, or
  changed, is part of the direction question.
- Current project state: docs/project-status.md (§0, §4, §5).

## Rules for this review
- Read-only on the repository. No model API calls, no experiments, no SSH to any machine. Write only your
  assigned file under the scratchpad directory given in your prompt.
- Never open test pools or anything named final/test/holdout/held_out/verifier_calibration/reserve, TestAccess,
  test_panel, s*/evaluation/, shared/test/. Never print .env or credentials.
- Every factual claim you rely on must carry a source (file path plus line, section or JSON field) so a critic can
  check it. Distinguish engineering fixture / archived replay / real model run / independent method-effect evidence.
  "Code exists" is not evidence of an experiment. Costs must be anchored to measured actuals (cal-1 ≈3.1k tokens
  per solver call; v3 ≈139M per run; feasibility pilots' own cost fields).
- The owner cannot follow jargon: any text addressed to the owner (summary_cn, synthesis) must be plain Chinese and
  explain each code name (D9, E4, C1, I-ds, v3, v4 …) the first time it appears.
- If the honest answer is "stop X" or "the evidence does not support Y", say so plainly.
