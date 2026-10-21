# Addendum for the SECOND batch of explorations (E1-E10), written 2026-10-20 ~19:15

Read `context.md` in this directory first (project, verified facts, machines, API snippet, hard rules). This addendum
adds the owner's framing for this batch and what the first batch (D1-D14, running in parallel) already covers.

## The owner's two core purposes (verbatim, then the reading you must work under)
"1. 协同进化，skill进化，验证端coding rubric进化  2. 评测指标是泛化性，可以考虑不同的bench去刷一下分，但是必须还是要在一个bench上
进化，然后其余bench上评测"
Reading: (1) CO-EVOLUTION: the solver-side Skill evolves AND the verification side evolves -- the owner calls the
verification side's artifact a "coding rubric" (read it as a rubric that may be expressed as executable code/checks
and/or as text criteria that drive task generation and judging; consider both readings and say which is more
promising). The verification side's evolution should show up as generated test items that measure generalisation
better and better, feeding back what is genuinely learnable. (2) The METRIC is GENERALISATION: evolve on ONE
benchmark, evaluate on the OTHER benchmarks. The owner is open to choosing different benchmarks to obtain measurable
gains ("刷分" = get a score improvement), as long as the design stays "evolve on one, evaluate on the rest".
Everything you propose must serve one of these two purposes explicitly; say which.

## Already covered by the first batch (do not duplicate; cross-reference by id when relevant)
D1 fresh-batch version-level acceptance; D2 case memory; D3 executable skills for SpreadsheetBench/ALFWorld; D4 rules
as classifiers; D5 noise floor / nondeterminism; D6 generated tasks with guaranteed answers; D7 LiveMath meta-option
policy; D8 statistical protocol; D9 headroom of text instructions (SearchQA/OfficeQA); D10 paper positioning; D11
reporting standard; D12 measuring cross-domain transfer; D13 proposal quality; D14 ALFWorld/SpreadsheetBench.

## Extra facts for this batch
- The current five benchmarks and their pools are pinned in the v3 manifest (`/data/coevo5-20261019-v3-run-manifest.json`,
  "data" section; training pools only). Test panels exist but are FORBIDDEN to you (see hard rules).
- The v3 stage order was SearchQA -> OfficeQA -> LiveMath -> SpreadsheetBench -> ALFWorld with one Skill carried
  across; the registered "similar" pairs: (searchqa, officeqa), (officeqa, livemath), (officeqa, spreadsheetbench).
- Earlier project line (v8-v11, Oct 2026) measured on the canonical test split: any reasonable instruction beats the
  empty Skill by 10-20 points; learned clauses on top of a good instruction +3 to +5, not significant. Those archives
  (training-side artifacts) live under /root/fivebench-g-2026101*/ on the OLD machine (read-only; not copied to the
  new machine; ~7 GB) and the F/G study dirs under /root/continual-fivebench-20261003-f-study etc. on both machines.
- Repository modules of interest: skillopt/coevo5/ (current protocol), skillopt/continual_learning/{verifier,feedback,
  skillopt}.py (the earlier rubric/research verifier line), skillopt/continual_eval/ (benchmark backends and scoring),
  docs/results-and-lessons.md and docs/current-workflow.md (history), docs/handoff/*.md (reviews and registrations).
- Budget for this batch: the owner says tokens are plentiful. A pilot may use up to ~4M tokens unless your assignment
  says otherwise; both deepseek-v4-flash and GLM-5.3 are allowed; the old machine's deepseek route is currently
  busy finishing the calibration run (12 concurrent slots) -- prefer the NEW machine for pilots and keep concurrency
  <= 6 there.
- Your outputs: /data/feasibility/<id>/ on the new machine; copy the report to the Mac scratchpad path named in your
  prompt; `verdict_cn` in plain Chinese for the owner.
