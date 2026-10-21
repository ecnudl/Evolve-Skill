# Shared context for the feasibility explorations (written 2026-10-20 by the main session)

You are one of ~14 explorers. Each explores ONE direction for the next version of the project described here and
returns a structured, evidence-based feasibility verdict. Read this whole file first. Everything in it was verified by
the main session unless marked "(claim)". Work in English; the `verdict_cn` field of your output must be plain Chinese
for the owner, who does not read English and dislikes jargon (explain every abbreviation you use there).

## 1. The project in one paragraph
Repository: /Users/dulin/Documents/Paper/SkillOpt (local Mac; package `skillopt/coevo5/`, ~10k lines; registration
documents in `docs/handoff/coevo5-registration-20261016.md`, `coevo5-registration-v2-delta-20261019.md`,
`coevo5-registration-v3-delta-20261019.md`, `cal1-registration-20261020.md`; living docs `docs/current-workflow.md`,
`docs/results-and-lessons.md`, `docs/project-status.md` -- read them, never edit them).
A "Skill" is plain text (<= 20,000 bytes) appended to the solver model's system prompt: five sections, one per
benchmark, each headed by a fixed "Applies when" line; a learned "rule" is <= 600 characters inside a section. The
method learns rules from TRAINING failures and must prove every rule on held-out TRAINING items before accepting it
(the owner forbids a fixed validation set). Benchmarks (stages, in order, the Skill carries over): SearchQA (retrieval
QA, short answers) -> OfficeQA (document QA) -> LiveMath (multiple choice with a "meta" option such as "none of the
above") -> SpreadsheetBench (edit a workbook; scored by executing in docker) -> ALFWorld (text embodied agent).
Solver: deepseek-v4-flash (thinking off, temperature 0, max_tokens 32768) through the PJLAB token route. Every method
role (examiner = per-failure diagnosis with a fixed code taxonomy; analyst = proposes rules from failures; leakage
adjudicator; forward checker for generated items) is GLM-5.3 (thinking on, reasoning low, temperature 0, 16384 max).
Owner's yardstick: learn from experience with NO fixed validation set; the learned Skill must transfer to SIMILAR
benchmarks (SearchQA<->OfficeQA, OfficeQA<->LiveMath, OfficeQA<->SpreadsheetBench are the registered "similar" pairs)
without dropping on dissimilar ones; the question is whether a learned rule beats a GOOD instruction (the public task
card), not an empty prompt. The owner also wants the generated-task pathway ("the method writes new test items for
similar targets") to run every step, with many items and guaranteed-correct answers, as the co-evolution story.

## 2. How a step works today (protocol v3, `skillopt/coevo5/step.py`)
train (parent Skill on 200 training items x 2 runs) -> halves (proposal half / check half, re-drawn per step) ->
examiner diagnoses each failed run with a code from the taxonomy (`protocol.py` TAXONOMY) -> analyst sees <= 40 failed
examples (16 OfficeQA, 20 SpreadsheetBench) + <= 4 contrasts in ONE ~220 KB call and proposes <= 5 rules, each citing
evidence items and target codes, placement local|similar -> prepare: evidence/codes consistency (inconsistent => the
rule is void, no re-ask), leakage checks (mechanical: reference answers/words/numbers/option text in the rule text =>
silent drop; word hits => GLM adjudication), trigger set = check-half FAILED items whose diagnosis code is among the
rule's codes (MIN_TRIGGER = 4, else "insufficient_support") -> selftest (the rule must fix its own evidence items) ->
screen (gate round: rule arm vs parent vs 4 irrelevant-text controls on the trigger items at 4 runs; focal rest at 2
runs; regression panels of earlier benchmarks; criteria C1 gain >= 1 whole item AND rule_L > max control_H, C2 no
harm on the rest within tolerance, C3 regression within tolerance and <= 2 extra format violations, C4' no-worse on
similar targets for `similar` rules) -> confirm (the same round re-run for screen passers; parent re-measured) ->
composite -> merge -> test evaluation (reused when the Skill is unchanged).

## 3. What happened (facts, verified on the machines)
- v3 run (2026-10-19/20, 139M tokens): BOTH chains accepted ZERO rules in five stages. Funnel over both chains: 49
  proposals -> 28 reached selftest -> 14 screened -> 2 passed screen -> 0 survived confirm. The chain seeded with the
  task-card instructions (I-ds) and the chain seeded with an empty scaffold (E-ds) both ended with the step-0 Skill, so
  every stage's test score equals step 0 by construction.
- Noise floor: the SAME Skill text re-run on the same 194 items at temperature 0 moves 30 of 194 items (16%);
  rules' net effects (+1/2, +3/4, 0) lie inside the four placebo controls' range. Paired sign tests: p >= 0.25 for all
  17 screened/confirmed arms; discordant items per panel 0-5; n >= 6 discordant needed for ANY p < 0.05.
- Dead items: over the 143 trigger items of the 15 screened rules, 50.3% score 0 for all six arms on every run
  (knowledge failures no text fixes); only 28.7% are rule-vs-parent discordant. Effective panel ~29% of nominal.
- Of 15 screened rules, 14 failed C1 (absolute gain >= 1 item) and 1 failed C2; the control-margin sub-condition was
  never the sole blocker.
- Generated-task pathway never ran: all 49 proposals got placement `local`; the analyst chose `similar` once (died on
  insufficient_support); two replies that mentioned transfer were silently voided for a malformed `transfer` slot.
- LiveMath: 63% of training failures are "did not pick the meta option" (taxonomy code D1); every rule targeting it
  was dropped by the leakage layer (quoting the meta-option sentence counts as option-text leakage) -- a registered
  self-contradiction between the taxonomy and the leakage policy.
- Truncation (32768 max_tokens, no retry): 93 gate cells and 18 test cells; I-ds OfficeQA 15 truncations vs NoSkill
  0 -> I-ds's 48.3% OfficeQA is a lower bound (ceiling 57.0%); flips no verdict.
- Earlier line (v8-v11, Oct 2026): any reasonable instruction beats the empty Skill by 10-20 points; learned clauses
  on top of a good instruction: +3 to +5, not significant; a KOR +7 did not replicate.
- cal-1 (calibration, pre-registered 2026-10-20, docs/handoff/cal1-registration-20261020.md): 11 arms (parent:A,
  parent:B = the same empty scaffold dispatched twice; ids-full = the five task-card seeds; seed-only; seed-rule;
  seed-rule3; cand = the v3 E-ds s1-r1 text; control:1..4 = placebos) x the same 200 SearchQA training items x 4 runs.
  Status: 7,189 of 8,800 cells have verdicts (82%, evenly over arms; 4,901 pass / 2,268 fail / 15 unknown http_503);
  the round paused on its 25M-token cap; a resume of the remaining 1,611 cells is prepared and awaits the owner's
  launch. Preview from the v3 data: I-ds seeds vs empty scaffold on the same 200 items = 36 up / 12 down, mean +0.089
  [0.044, 0.133]. The completed cells are usable NOW for noise/power analyses (see §6 for paths).

## 4. The audit (2026-10-20) and what is being fixed in parallel (protocol v4, NOT your job)
Seventeen defects are being fixed right now by another workflow: codes/evidence double declaration; transfer/placement
double authority; leakage drops without recorded reason; illustrative examples dropped mechanically; identical re-ask
without validator feedback; adjudicator lacks the task card; SearchQA format check vs scorer fallback; per-run instead
of per-item diagnosis; analyst example cap starving codes; forward items outside the shared-unanswered exclusion; an
unjudgeable SpreadsheetBench item; option-text leakage threshold; solver prompt wording; two Skill hash conventions;
stale constants/comments; pause kinds; truncated role replies. Prompt improvements being implemented: conditional rule
template ("when <observable condition>: <bounded action>; otherwise <default>") with trigger items derived by an
applicability judge over the WHOLE check half (not failures only); one worked example per role; re-ask with the
validation error; reason-then-label + 3-vote majority for judging roles; analyst decomposed per diagnosis code with
balanced evidence. Assume these land; your direction is about what comes AFTER (v5 and the paper).

## 5. The directions (one per explorer; yours is named in your prompt)
D1  Version-level acceptance on fresh batches (paired mean difference + confidence bound; each step draws a fresh batch
    of never-proposed-on training items; batch returns to the pool after the decision; whole-step package accepted or
    rejected; leave-one-out attribution only after acceptance).
D2  Case/experience memory instead of (or beside) rules: retrieve 2-3 similar past cases ("task feature -> failure ->
    fix") into the prompt at solve time (ExpeL, Agent Workflow Memory, Dynamic Cheatsheet, ACE, Reflexion lineage).
D3  Executable skills for SpreadsheetBench and ALFWorld (Voyager-style helper programs / checklists verified by
    execution) within this harness (docker image, native pools, solver loop).
D4  Rules as classifiers: every rule carries a checkable "when" predicate; measure its precision/recall against the
    diagnosis codes on the training halves BEFORE any solver call; use it to size trigger panels and kill dead items.
D5  Lowering the measurement noise floor: quantify per-item nondeterminism from the cal-1 cells (parent:A vs parent:B
    are the SAME text), the gain from k-vote majority at the evaluation layer, batch-invariant / seeded inference
    options on the PJLAB deepseek route (test `seed`, `top_p`, concurrency 1), and the item count needed per effect size.
D6  Generated tasks with guaranteed answers: typed task specification -> executable reference solution -> constrained
    question rendering, per benchmark; two-of-two agreement as a filter not a guarantee; audit protocol; how many items
    per step; how the generated panels become the "similar target" test (C4') and a training signal.
D7  LiveMath D1 policy: analyze the meta-option failures in the v3 cells; define "task-structure" rules (allowed) vs
    "answer-distribution" rules (leak); estimate what a structural rule could gain; pilot if permitted.
D8  Statistical protocol for v5: positive-control calibration as a standing fixture, non-inferiority margins for C2/C3,
    futility stopping, minimum useful effect delta, multiplicity over <= 5 rules per step -- with numbers from cal-1.
D9  Headroom: how much can ANY text instruction add on top of the task card? Oracle per-item hints vs generic
    instruction on SearchQA/OfficeQA (ceiling of text-skill learning); fraction of instruction-fixable failures.
D10 Paper positioning and related work: prompt optimizers (DSPy/MIPRO, GEPA, OPRO, ProTeGi, TextGrad, PromptAgent),
    memory agents (ACE, AWM, ExpeL, Dynamic Cheatsheet), negative-result/preregistration precedents in LLM evaluation;
    what claims the current evidence supports; what one more experiment would make the paper.
D11 Reporting standard: LLM-evaluation error analysis (Miller 2024 "Adding error bars to evals"; variance in
    benchmarks; paired designs; clustered SEs); produce the reporting template and the formulas for our stage tables.
D12 Cross-domain transfer measurement: how transfer to SIMILAR benchmarks should be measured without a validation set;
    what the v3 forward machinery (`forward.py`, `research.py`) lacks; design of similar-target panels; power.
D13 Proposal quality: read the 49 v3 proposals (texts, codes, outcomes) and the cal-1 arm texts; cluster what the
    analyst produced; estimate what a per-code, condition-based proposer would have produced; propose the prompt and
    examples (feed-forward to v4/v5).
D14 ALFWorld and SpreadsheetBench specifically: is the text-skill paradigm fundamentally limited there? What the
    literature reports for learned text guidance on ALFWorld (ExpeL, AutoGuide, Reflexion) and spreadsheet agents; what
    our v3 stage-4/5 data shows; what to change.

## 6. Machines, code, data, how to run things
NEW machine (preferred for all work; root): `ssh -o BatchMode=yes <datatools-login>`
  - Python with every dependency: /root/continual-alf-prep-20260928/env/bin/python
  - Working copy of the repository (synced 2026-10-20 18:35, no .git, no outputs/): /data/skillopt-work
  - Completed v3 run (read-only, 683 MB): /data/coevo5-20261019-v3-run ; manifest /data/coevo5-20261019-v3-run-manifest.json
    frozen v3 code snapshot: /data/coevo5-20261019-v3-source-f ; earlier runs /data/coevo5-20261017-* and *-v2-*
  - Benchmark training pools are pinned in the manifest ("data" section) under /root/...; the API clients are
    `scripts/weak_solver_probe.Client` (see below). Network: external calls need the shell proxy: run commands as
    `ssh ... "bash -ic 'proxy_on >/dev/null 2>&1; cd /data/skillopt-work && /root/continual-alf-prep-20260928/env/bin/python your_script.py'"`.
  - Write your outputs under /data/feasibility/<your-direction-id>/ on the new machine (create it) and copy anything
    the main session must read to the local scratchpad directory named in your prompt.
OLD machine (read-only for you, except API probes): `ssh -o BatchMode=yes PJ-CL4MIND-DULIN` -- same python path; the
  cal-1 data lives ONLY there until it completes: /data/coevo5-20261020-cal1/cal1/searchqa/attempt-1/cells/*.json
  (one JSON per cell: cell.arm, cell.task_id, cell.run, final.token in {pass, fail, unknown}, final.reason,
  attempts[].prediction, sends[] receipts with usage); the pre-round: /data/coevo5-20261020-cal1/cal1-pre/searchqa;
  arms texts: /data/coevo5-20261020-cal1/arms-cal1-searchqa.json; analysis code (pre-registered):
  /data/coevo5-20261020-cal1-ops/cal1_analyse.py and cal1.py. Never write under /data/coevo5-20261019-v3-run or
  /data/coevo5-20261020-cal1. Scratch on the old machine: /data/feasibility-scratch/<direction-id>/.
API clients (both machines), from the repo root with the proxy on:
    import sys; sys.path.insert(0, "/data/skillopt-work")   # or the frozen snapshot on the old machine
    from scripts.weak_solver_probe import GATEWAY, Client
    glm = Client("/root/continual-noskill-bcb-20260928-a", "glm-5.3", proxy=GATEWAY, max_tokens=4096, read_timeout=300)
    ds  = Client(None, "deepseek-v4-flash", proxy=GATEWAY, max_tokens=2048, read_timeout=300,
                 route="pjlab_token", route_env="/root/.config/weak-solver/pjlab-token.env")
    r = glm.call("<system>", "<user>")   # dict: ok, status, response (text), usage, attempts
  Verified 2026-10-20 18:45: GLM works from both machines; the deepseek token route returned 503 x4 from the NEW
  machine and 503 x2 then 200 from the OLD machine (the route is flaky right now). If deepseek keeps failing on the
  new machine, run deepseek pilots from the old machine (outputs under /data/feasibility-scratch/) and say so.
Costs (for estimates): a SearchQA solver cell ~3,400 tokens (incl. prompt); GLM role call ~2-8k tokens. The owner has
  authorized free use of deepseek and GLM for pilots. Keep a pilot <= ~3M tokens unless your prompt says otherwise.
The main session's local scratchpad (Mac): the directory named in your prompt; the local repo is read-only for you.

## 7. Hard rules (violations invalidate your work)
- NEVER read, list, or copy test/holdout pools: any path containing `TestAccess`, `test_panel`, `s*/evaluation/`,
  `shared/test/`, or files whose names/labels contain final|test|holdout|held_out|verifier_calibration|reserve.
  Training pools only. If unsure whether a file is a test pool, do not open it.
- Never print `.env` files, API keys, tokens, or proxy credentials; never copy credential files.
- Never write under a completed run directory; never modify the repository (local or /data/skillopt-work) -- put your
  scripts under your own output directory.
- No interactive commands (vim, top, python REPL); commands longer than ~2 minutes go to the background (nohup/tmux)
  with a log file you then read.
- If the permission system denies a paid API call or a launch, do NOT retry or work around it: prepare the script,
  write the exact launch command and the cost estimate into your output (`pilot.blocked_by`), and continue with the
  free parts (reading data, literature, design).
- Report numbers with their denominators; never dress up a weak or negative finding.
