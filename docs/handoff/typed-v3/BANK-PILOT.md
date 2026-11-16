# typed-v3 item bank: pilot decisions (2026-11-13)

Owner approval and additions of 2026-11-13 (verbatim, in order):

1. 16:3x on PRACTICE-ITEMS-DESIGN.md: "同意，尽快开始".
2. about 17:1x: "然后就是造题的时候可以写明一个code rubric，并且在造题之前可以通过deep search去深度搜索应该造怎么样的题，
   总之在造题的这一部分要充分利用coding rubric和deep search".
3. about 17:4x: "我的想法是可以有一个造题模块和专门用来运行造题的一个环境，你觉得这个想法是否可行，给出你的一些看法和依据，
   也可以修改，给出你认为可能的效果最优的做法" (answered: feasible and adopted, as a fixed pipeline with bounded repairs, a
   firewall against solver outcomes, and the chains' own judge code; decisions B2 to B4 below).

This file records how stage 0 of the design ("试产": make the bank, report yield and fidelity) is built. Code:
`skillopt/execskill/typed/bank/` and `scripts/run_bank.py`. Nothing here changes a frozen run.

## Decisions

- **B1 Scope and order.** The two benches whose practice pools are used up come first: OfficeQA (74/74) and
  SpreadsheetBench (91/91). OfficeQA number twins need neither research nor a sandbox and run first; new questions
  wait for the research brief (B8); the SpreadsheetBench part needs the sandbox, the recalculation engine and the
  machine-wide memory lock and runs when no chain reads on that machine (B10).
- **B2 Module and environment.** The bank is its own module with its own root (`/data/execskill-<date>-bank-v<n>`),
  ledger and token cap (`bank/env.py`). Inputs: the pinned training-side pool of a typed manifest (path and sha256)
  and that manifest's learn / gate slices. Tools are fixed code. Every model request and reply is stored before and
  after the call; a delivered reply or a model-side failure is final and never sent again; an infrastructure failure
  leaves no verdict. One process per ledger.
- **B3 Fixed pipeline, bounded repairs.** Research, brief, write item and rubric, run the rubric, fixed checks, at
  most one repair request that names the failed check, independent check, record. No free tool use by a model.
- **B4 Firewall.** A bank role never sees a solver chain's outcome on its items. The checker's verdicts are used by
  fixed code only (B7); a writer's repair request carries the fixed check's reason, nothing else. (Amended by B24:
  the diagnostician reads the checker's replies on REAL items of the shown side.)
- **B5 Same judge as the chains.** The bank process binds the same machinery snapshot as the chains
  (`run_typed.bind_machinery`), so the OfficeQA judge, the solver request builder and (later) the sheet scorer with
  its qualification are the chains' code. `bank.json` records the files and hashes they were imported from.
- **B6 OfficeQA made answers.** The judge is string equality after a light normalisation, with no numeric
  tolerance. A derivation counts only when its computed answer is judged equal to the parent's reference answer
  (the anchor). A made answer is plain digits with the decimals the question fixes, carries '%' only when the
  reference does, and is refused on a rounding tie or a trailing zero. A number twin changes every token occurrence
  of a changed literal in the document body (page headers and source URLs never change), never a selector (a year,
  a literal named in the question, a one-digit literal, a literal printed more than six times), and is refused when
  the parent's answer would still be judged correct.
- **B7 Checker.** The checker is the benchmark's solver request with the hand card, sent to the chain-G solver
  client (GLM-5.3), scored by the answer-tag scorer: two runs per parent, one per twin and a second when the first
  fails. A twin is dropped only when the checker solves the parent in both runs and the twin in none. A twin of a
  parent the checker does not solve every time stays, marked `unconfirmed`: a filter on "the checker solved it"
  would remove the hard items, which are the ones the diagnosis needs.
- **B8 Research before writing (deep search).** A researcher role answers fixed questions before any new question
  is written: question kinds, difficulty factors, known solver mistakes, domain conventions. Every finding carries
  a verbatim quote and its source; every fetched page is archived write-once before use. The brief steers the
  question writer and supplies the rubric's mistake list. Guard: a fetched page that quotes a test item is dropped
  by a sealed, counts-only overlap check before a role sees it; the researcher sees no benchmark item. The pilot
  compares questions written with and without the brief (yield, fidelity, difficulty spread). Not built yet.
- **B9 Code rubric.** Every made item carries an executable rubric (`oqa.rubric`): the derivation that computes the
  answer, and coded mistakes whose answers fixed code computes (operands exchanged; the writer's item-specific
  wrong readings with a registered label: wrong_period, wrong_series, wrong_table_or_page, other_vintage,
  wrong_operation, missing_step). `oqa.classify` names the mistake a wrong reply matches (format, order, rounding,
  percent_form, unit_scale, sign, a coded mistake, read_not_computed) or `other`. The benchmark's judge alone
  decides right and wrong; the rubric's labels feed the diagnosis step.
- **B10 SpreadsheetBench (planned).** Data twins: the parent's instruction on a changed copy of its workbook; the
  expected workbook comes from two independently written reference programs that both reproduce the parent's
  expected workbook under the benchmark scorer and agree on the changed copy; the expected file is recalculated by
  the engine (the scorer's drift guard needs engine caches) and the item must pass the reference qualification
  (the reference scored twice against itself), as the 91 real items did. Program runs and scoring take the
  machine-wide memory lock exclusively and one native slot. New workbook paths must not contain a forbidden word.
- **B11 Sides and clusters.** A parent of the learn slice gives items shown to writers; a parent of the gate slice
  gives items kept for judging; all items of one parent share its side and its family id. Statistics on made items
  cluster by parent. OfficeQA's judging side has at most 40 documents, whatever the number of items.
- **B12 Pages shared with test items.** The OfficeQA split is by item, not by document: by the id manifest's page
  references (ids, source file, page; no question, no answer), 9 of the 74 pool items share a page with an item
  outside the pool. Such parents get number twins (the parent's own question on changed numbers adds no fact of a
  test item); no new question is written on them.

- **B13 Stage log.** A pilot root may see several code versions: every stage writes
  `<root>/stages/<stamp>-<command>.json` with the hashes of the bank code it ran with. A bank handed to a chain is
  built by ONE code version in a new root (stored calls are keyed by unit and tag, so a rebuild resends nothing).
- **B14 What a twin is worth.** A number twin keeps the parent's question: the solver's behaviour on it is close to
  its behaviour on the parent, so twins of one parent mostly act like further runs of that parent (with the
  arithmetic varied), not like new independent items. They reduce run-to-run noise and they are the anchored
  sanity check of the made-answer machinery (the checker's pass rate on twins should match the parents'). New
  information comes from NEW questions on the documents (and new instructions on the workbooks), which is where the
  research brief and the coded mistakes are used. Reports state both counts and say which is which.
- **B15 Research sources as built.** English Wikipedia (frozen client), arXiv (API search; HTML full text when
  served, else the abstract), Stack Exchange (Stack Overflow, Super User). The screen drops every hit and page that
  names one of the five benchmarks or SearchQA's source show, so the benchmarks' own papers are never read. First
  run (2026-11-13, OfficeQA, probe root): 4 research questions, 14 role calls, 49 k tokens, 11 pages read, 1 page
  screened, 28 findings kept, 4 void; brief with 5 question kinds, 5 mistakes, 5 conventions; 7 arXiv searches
  failed with HTTP 502 or a read timeout (recorded, not retried).

- **B16 First pass and the certified evaluator.** Root `bank-b` (2026-11-13 17:07, the solver-side evaluator
  `compute`: + - * / and whole powers, 300 characters): 34 of 74 parents anchored (23 at the first request, 11 after
  the repair), 130 twins made. Not anchored: 18 refused (12 expressions outside the grammar: standard deviation,
  geometric mean, coefficient of variation, correlation, compound growth rates, sums of about thirty lines; 5 quotes
  that are not in the document, a correct refusal; 1 undefined name), 12 "not found" (several ask about a chart),
  8 replies cut at 16,384 tokens, 2 not numeric. From the second pass on (`bank/calc.py`): exact rational
  arithmetic plus certified sqrt, ln, log10, exp, fractional powers, mean, median, the variances and standard
  deviations, geomean and corr; named steps; 6,000 characters; up to 40 values; role requests of 32,768 tokens. An
  inexact value within 10^-9 of a rounding boundary is refused; an exact tie is refused for a made answer and tried
  both ways when a reference is reproduced. The first root stays as it is; the second pass has its own root.

- **B17 Second pass, OfficeQA (root `bank-d`, snapshot d, 2026-11-13 17:31 to 19:15; 1,308 sends, 7.9 M tokens).**
  Derivations: 54 of 74 parents anchored (46 at the first request, 8 after the repair); not anchored 20 (6 not
  found, 5 replies cut at 32,768 tokens, 5 not numeric, 2 quotes not in the document, 1 reference not reproduced,
  1 shape). Number twins: 198 made on 50 parents; the checker confirms 128, cannot confirm 47, drops 23. New
  questions on the 65 parents that share no page with an item outside the pool, three asked per parent and arm:
  plain 155 kept by the fixed checks of 196 written, 104 verified by the checker; brief 156 kept of 195, 117
  verified. Verified new questions by side: judging 124, shown 97. The checker on the 74 real parents: 35 solved
  in both runs, 15 in one, 24 in none (first-run pass 58.1 %). First-run pass on made items: twins 60.6 % (twins of
  parents solved every time 73.0 %, of parents never solved 19.4 %), new questions plain 63.2 %, brief 74.4 %.
  What the numbers showed, each handled below: the percent sign (B18), twins that contradict their document
  (B19), and new questions that are easier than the real ones (B22).
- **B18 The percent sign: a fixed sentence on the answer's form.** 165 of the 311 new questions name a percent
  and 8 say how to write the answer; a made answer never carries '%' (B6). 99 of the checker's 230 wrong replies on
  new questions differed from the made answer by the percent sign alone (plain 49 of 123, brief 50 of 107).
  Counting those replies as right, the first run passes 76.8 % (plain) and 87.8 % (brief). The real items word it
  both ways (26 of 74 name a percent, 3 references carry '%', several say "only report the value with no percent
  sign"). From bank v2 on, fixed code adds "Report only the value, with no percent sign." to a made question that
  names a percent and does not mention the sign (`oqa.form_sentence`), so a made item tests reading and
  computing; the real items keep testing the benchmark's own conventions.
- **B19 Twins of one parent stand or fall together.** 20 of the 23 dropped twins sit on 6 parents (4 parents lose
  all four). The tables print linked figures (totals, ratios, the same figure in a second table): a twin changes
  only the literals its derivation names, and a solver that takes another valid path through the document reaches
  another number; 9 wrong replies on dropped twins are the parent's old answer. From v2 on a parent with two or
  more dropped twins loses all its twins (`oqa_build.twin_statuses`), and a twin's wrong reply that the judge
  takes for the parent's answer is labelled `parent_answer`. Not solved: the 47 unconfirmed twins belong to parents
  the checker does not solve every time, so nothing confirms their answers; a chain should judge on confirmed
  twins and treat unconfirmed ones as a diagnostic set only.
- **B20 SpreadsheetBench as built.** Reference programs (two styles, the benchmark's sandbox and scorer, anchored
  when the scorer passes against the parent's expected workbook), data twins (every numeric data cell times one
  factor; expected workbook = the anchored program's output; kept when the answer cells change, a second anchored
  program agrees and the reference qualification passes twice), and NEW TASKS: a writer gives a new instruction,
  its answer position and a reference program on a training workbook; a second program is written from the new
  instruction, the workbook view and the answer position alone; the item is kept when both run, the answer cells
  are filled and agree, and the item passes the reference qualification twice. Two programs written by the same
  model can share a misreading: agreement stands in for the anchor, it is not one. The scorer stores an unknown
  verdict and repeats it for the same request, so an unknown is a failed check (reference programs) or a
  disqualification (twins, new tasks) with its reason; only an exception inside the scoring leaves an item open.
- **B21 One code version per handed bank: carried calls.** `run_bank.py carry` copies the stored calls (and the
  research archive and records) of an earlier root into a freshly prepared one; every trace, item, record and
  verdict is computed again by the new code, and a stored reply is used again only for the identical request
  (`BankEnv.call`, `solver_call`). Root `bank-v2-a` (snapshot g, VERSION typed-bank-v2) rebuilds the OfficeQA bank
  from the calls of `bank-d`: the derivation stage answered 89 of 89 requests from stored replies and sent none.
- **B22 Difficulty: what is still missing.** With the percent sign out of the way the checker passes 77 to 88 %
  of the new questions at the first run and 58 % of the real items: questions written without a diagnosis are
  easier than the benchmark, and the research brief makes them easier still (33 "read one value" questions against
  11) while it does enrich the rubric (coded mistakes per kept question 1.68 against 1.32). They serve as guard
  items. The attack items of the design need the diagnosis step (the solver's failed real items of the shown
  side, read by a diagnostician) and a way to trust a hard question's answer that does not ask the solver to
  solve it: planned as an AUDIT of the derivation (a second role checks each quoted figure against the question)
  calibrated on the anchored parents, whose correct derivations it must accept and whose coded mistakes it must
  refuse. Also seen: the rubric names 35 % of the checker's wrong replies on parents and twins (the rest is
  `other`), so the diagnosis has to read replies, not only labels.

- **B23 The audit of a derivation (registered 2026-11-13 before its first run).** A role request per derivation:
  the document, the question and the derivation (values with literal and quote, steps, expressions, decimals), never
  a computed answer; the auditor marks every value and the computation right or wrong and gives accept or refuse.
  `AUDIT_RUNS` = 2 independent requests; a derivation is ACCEPTED when both accept (a reply without a verdict
  counts as not accepting). Calibration set, from what the bank knows: the anchored derivation of a real parent is
  right; a coded mistake of that parent whose answer the judge refuses for the reference is wrong (the writer made
  these as plausible misreadings, so they are hard negatives). **Rule, fixed here:** the audit may vouch for a new
  question only when it accepts at least 80 % of the right and at most 10 % of the wrong calibration derivations
  (`AUDIT_RULE`). When the rule holds, a new question that the checker does not solve but the audit accepts gets
  the status `audited` (a hard question whose answer is trusted at the measured false-accept rate); when it does
  not hold, the audit vouches for nothing and the numbers are reported as a negative result. A question the
  checker verified stays verified whatever the audit says; the cross table is reported. (Amended the same evening,
  still before any audit run, after the code review: the rule can hold only on a COMPLETE calibration -- every
  record the bank's known derivations call for exists -- with at least 30 right and 30 wrong derivations; a
  calibration cut short by failures or by a limit authorises nothing.) Limits to state with any
  result: auditor, writer and solver are the same model; the negatives are one writer's idea of a mistake; with
  about 54 right and about 60 wrong derivations a measured 10 % has a wide interval.
- **B24 Diagnosis and the targeted arm.** `oqa-diagnose`: for every REAL parent of the SHOWN side that the checker
  failed at least once, a diagnostician reads the document, the question, the reference answer with its anchored
  derivation (when there is one) and the checker's replies (the wrong ones, and a right one when it has one), and
  names the cause, the kind (locating, period, computation, unit_scale, form, no_answer, other), a general
  weakness and what a new question must require to expose it. One more request merges the weakness and test
  sentences (no item content) into at most 8 weaknesses. `oqa-newq --arms target`: the writer receives these
  weaknesses, every question names the one it targets and codes the wrong derivation that the weakness leads to.
  This amends B4: the diagnostician is the one bank role that reads solver outcomes, and only on real items of the
  shown side (the same items and outcomes a chain's writers learn from); nothing about an outcome on the judging
  side reaches any role, and writers of judging-side questions receive the merged weaknesses, not cases. What the
  pilot must show for the arm to count: a lower first-run pass rate of the checker on targeted questions than on
  plain ones at a comparable audit acceptance, and wrong replies that match the coded mistake of the targeted
  weakness. In a chain the diagnosis reads the current skill's failures on the learning slice at each step; in
  the pilot it reads the checker's (the hand card alone).

- **B25 Instrument check (design section 6.3; registered 2026-11-13 before its run).** `oqa-contrast --config c0
  --card c0` runs the solver with the chain's arm C0 (the answer-format block alone) on the 74 real parents (two runs) and
  on the made items whose answers something vouches for (confirmed twins of parents that keep their twins, verified
  or audited questions; one run); `oqa-contrast-report --base c --config c0` pairs FIRST runs with the checker's
  (the hand card) and gives the gain of c0 over c on real and on made items, with 95 % intervals that resample
  parents. **Reading, fixed here:** let g_real and g_made be the two gains. The check is NOT INFORMATIVE when the
  interval of g_real contains 0 (no effect on real items to reproduce; it then counts neither as passed nor as
  failed, and is repeated with the chain-D solver, where the hand card matters more: `--solver-chain D`, once
  with `--config dc --card c` and once with `--config dc0 --card c0`, compared by `--base dc --config dc0`). Otherwise it PASSES when the
  interval of g_made minus g_real contains 0 and g_made has the sign of g_real, and FAILS when it does not (made
  items do not measure what real items measure: fix the making, do not start a run).
- **B26 Re-judging a card on more items (design section 11 step 2; registered before its run).** For a card round
  of a typed run on OfficeQA: (1) parity first, at no cost: the request the bank's checker sent for a real gate
  item must be the request the run's hand-card arm sent for it (equal request hashes), else stop; (2) routing:
  the contrast mounts a card on EVERY item, the run mounts it on the items its type map routes to the card's
  type, so the share of the run's gate cells that mounted the type is read from the cells and reported; (3)
  configurations with `--runs 3 --side judge`: the base is what the run's incumbent arm mounted (for step 2 of
  chain G: the step-1 card on the hand card), the candidates are the round texts (`s<k>/card-r<j>/writer.json`),
  each mounted by `typed.mount.system_card` on the hand card; (4) `oqa-contrast-report --base <base> --config
  <candidate>` applies the chain's own gate rule (`typed.gatestats`: tau = max(3 points, 2 x the standard error of
  the baseline's repeats); accepted when the gain reaches tau and more items got better than worse) to the real
  judging items (a fresh replication of the run's gate), to the made judging items and to both, each with the
  parent-resampled interval of the gain. **Reading, fixed here:** CONFIRMED when the rule accepts on real and
  made judging items together and that interval excludes 0; NO EVIDENCE when the interval contains 0; BELOW THE
  THRESHOLD otherwise. The made items of the judging side come from at most 40 documents: more items shrink the
  run-to-run noise, they do not add documents, and the interval that resamples parents is the honest one.
  (Amended 2026-11-14, before its run, after the review of B29: (a) parity is checked by code for the base AND
  every candidate: `oqa-parity --chain-dir <run>/G --step 2 --cards gs2b=..,gs2r1=..,gs2r2=..` compares, for
  every gate item for which the run holds a cell with the configuration's system card and no enabled program, the
  first request built here with what the run sent; it passes when no request differs and every configuration was
  compared on at least one item, and `oqa-contrast --cards` refuses to run without a passing record that covers
  its cards. (b) The base and the candidates run in ONE stage and meet each item together, in a seeded order per
  item (`oqa-contrast --cards .. --runs 3 --side judge`), as a gate unit orders its arms. (c) Card files are read
  verbatim: a writer's text ends with a newline, and a stripped text is another system card. (d) Every
  configuration is registered before any call on its card, solver, run count, side and ordered item list; the
  gate rule is decided only when both configurations hold a record for every registered item.)

- **B27 The one code review and what it changed (2026-11-13 22:0x, Codex gpt-6-astra, effort ultra, read-only).**
  Eight blockers and six majors, all confirmed against the code and fixed in commits `6b3c16e` and the one before
  it; twelve of the new tests were checked to fail when their fix is undone. Data-relevant: (1) the evaluator's
  inexact values now carry rigorous enclosures (interval arithmetic) through every operation and named step, and
  an answer is written only when both ends round alike (sixty digits alone had certified a cancelling
  expression); (2) number twins replace literals in one pass over the original text (numbered markers could be
  rewritten when a twin had more than ten changes and the document held a literal such as 10: a twin's document
  and answer could then disagree -- possible in roots `bank-b` and `bank-d`, whose twins are therefore not handed
  to a chain); (3) a question that asks for the percent sign is dropped; (4) one copied answer refuses a sheet
  reference program; (5) a sheet data twin needs two anchored programs that agree; (6) an all-empty answer region
  is refused; (7) the audit's calibration must be complete and large enough (B23); (8) new sheet tasks inherit
  the parent's family id (B11); (9) ONLY confirmed twins count as qualified, unconfirmed ones are reported apart
  as a diagnostic set -- the pilot's "396 usable items" was 349 confirmed (128 twins, 221 questions) plus 47
  unconfirmed twins; (11) a checker reply the model cut is a final wrong run and is never drawn again (the old code
  would have drawn again; it did not happen in roots `bank-b` and `bank-d`, whose check stages both ended in their
  first round with no run left without a verdict, so their pass rates are not lifted by redraws).
  Operational: (10) a ledger stop ends a stage with exit 3 instead of being counted as a task result; (12) a
  delivered call without its result file is recovered, not sent again; (13) a failed research call writes no
  record; (14) a machine failure on the second sheet program leaves the parent open. One narrow second review
  covered the evaluator rewrite only (22:3x): no wrong answer found; two majors, both fixed: the widened ends of
  an inexact value were carried digit for digit, so ordinary compounding such as `(g ** (1 / 12)) ** 60` hit the
  size bound (ends longer than 512 bits are now rounded OUTWARDS to 60 digits), and a rubric stored an inexact
  coded mistake as its midpoint, whose rounding could differ from the true one at a tie (such a mistake is now
  left out of the rubric). Checks kept as tests: 700 seeded random expressions against an independent 250-digit
  evaluation (the script behind it ran 3,118 with no value outside its enclosure), and against the evaluator
  before the rewrite the same expressions are accepted except one nested correlation it cannot certify.

- **B28 Re-judging a card on spare real items (design section 11 step 2 for a bench with unused practice items;
  registered 2026-11-14 before its run; the form below includes the fixes of B29). WITHDRAWN FOR ZEBRALOGIC the
  same day, before any call: its premise was wrong (see the note at the end of this decision).** `bank/spare.py`,
  `bank/rejudge.py`. ZebraLogic has 327 pool items in neither slice of the typed-v2 run (500 minus 73 learning
  and 100 gate items); they continue the seeded ranking the slices were cut from, so they are as exchangeable
  with the gate slice as the gate slice is with itself, and no writer saw them. Case: the two card rounds of
  chain G step 3 (+5.0 and +4.7 on 100 gate items against tau 7.1; refused).
  (1) `spare-parity --cards c,k1=<round 1 text>,k2=<round 2 text>`, at no cost: for every gate item for which
  the run holds a cell with the configuration's system card and no enabled program (the hand card: the noise unit;
  a round text: the round's cells on the items the run routed into the card's type), the first request this tool
  builds must be the request the run sent. A difference, or a configuration compared on no item, fails the check
  (exit 2), and the stage below refuses to run without a passing record that covers its cards.
  (2) `spare-contrast --cards c,k1=..,k2=.. --runs 3` on ALL spare items: `c` is the hand card alone (what the
  run's baseline arm mounted on this bench at that step), a round text is taken verbatim and mounted on the hand
  card by `typed.mount.system_card`; a cell is the chain's own (`typed.mount.solve`, the benchmark's judge), a
  model-side unknown is a final wrong run, an infrastructure unknown is run again (the gate's rules). Every
  configuration is registered before any call on its card, solver, run count and ordered item list. The three
  configurations meet each item together, in a seeded order per item, so a drift of the service during the stage
  is not read as a difference. (3) `spare-report --base c --config k<j>`: only when both configurations hold a
  record for every registered item (otherwise INCOMPLETE, no decision): the chain's gate rule (tau = max(3
  points, 2 x the standard error of the base's repeats); accepted when the gain reaches tau and more items got
  better than worse) on all spare items, the 95 % interval of the gain from resampling items, and the rule on the
  first 100 and 200 items of the ranking. **Reading, fixed here:** CONFIRMED when the rule accepts and the
  interval lies above 0; NO EVIDENCE when the interval contains 0; HARMFUL when it lies below 0; BELOW THE
  THRESHOLD otherwise. To state with the result: the card is mounted on EVERY spare item while the run mounted
  it on the items routed into the card's type (the share is read from the parity record); the readings are made
  days after the run; two candidates are judged, so one CONFIRMED of two is weaker than it looks; the base here
  is the hand card alone, not the library the run ended with (the accepted ZebraLogic program), so a CONFIRMED
  card says the 100-item gate missed a real gain of the card ALONE -- whether it adds to the program is a
  different question that this does not answer. The result changes nothing in the finished run and adds nothing
  to a library. Chain D's ZebraLogic cards (-45.7, -37.3) are not re-judged: their verdict is not in doubt.
  **Withdrawal (2026-11-14 16:2x).** The run's pinned ZebraLogic pool holds 173 items, not 500: the raw pool file
  has 500 puzzles (25 sizes, 20 each), `zebralogic.load_pool` keeps the registered domain of the benchmark's own
  panel (5 or 6 houses, 2 to 6 columns: 200 puzzles) and the run drops 27 earlier probe ids; 173 = 73 learning +
  100 gate items, so there is NO spare item of the gate's distribution (the "about 320 unused" of the design
  table counted the 300 puzzles of 2 to 4 houses, which are easier than the panel). The stage refused the empty
  item list at registration; nothing was sent. The parity of step (1) did run and passed on the real run (hand
  card 100 of 100 gate items with the run's request, each round text 96 of 96; 4 gate items were not routed by
  the run), so the tool is ready for a bench that has spare items (SearchQA: 400). What remains possible for the
  two ZebraLogic cards, neither registered nor run: more repeats on the run's own 100 gate items (the gate's tau
  is run-to-run noise on fixed items: R = 9 would bring it from 7.1 to about 4.1, and would say whether +5.0 is
  noise on THOSE items, not whether it holds on new ones), or new puzzles of the panel's sizes from a generator
  with a uniqueness check (design section 5, source "乙"; not built).
- **B29 The review of the re-judging code and what it changed (2026-11-14 16:0x, Codex gpt-6-astra, effort ultra,
  read-only, on commit `a0eb7a2`; before any re-judging run).** Six blockers and two test gaps, all confirmed and
  fixed: (1) a card file was stripped of its final newline, so the candidate would have been mounted as another
  system card than the run's (the parity check then covered only the hand card): card files are read verbatim
  and parity covers every configuration; (2) an item whose runs failed for an infrastructure reason dropped out
  of the report, and the "first 100" slid along: a configuration is registered on its ordered item list and a
  report decides only on complete records; (3) a configuration's identity was compared after new records could
  be written: its record is written and compared BEFORE any call, and every record already in its folder is
  compared too; (4) two configurations with different run counts gave pass rates above 100 %: refused; (5) the
  typed manifest's contents were not recomputed against its seal: `typed.prepare.verify`, also at `prepare` and
  in the sheet tools, and the slices must have their registered sizes; (6) a failed parity check exited 0: exit
  2, and the stage requires the passing record. Test gaps: the gate rule is now compared through the report at
  its threshold (a gain exactly at tau and one item below) against `typed.gatestats` and against the rule written
  out again; an item interrupted after one delivered repeat reuses that reply and pays for the missing one only.
  Found while fixing: real ZebraLogic ids contain a word the path guard refuses (`lgp-test-..`), so the first
  record would have stopped the stage: records and call tags are named by a hash of the id. Defects (2) and (3)
  also existed on the OfficeQA contrast path (reviewed on 11/13 without that finding) and are fixed there
  (`stage_contrasts`, `_gate_rule`); the instrument check of root `bank-v2-b` runs on the earlier snapshot h,
  whose single-configuration stage is guarded by its own pipeline (a contrast that is not complete ends the
  script before the report). 25 mutations of these fixes each fail a test.
  **Second round (16:2x, the one follow-up review, on `cd050a6`).** Seven of the eight findings fixed, one
  partly; three new blockers, all confirmed and fixed before any re-judging run (commit `7f36171`): (a) a parity
  record did not say for which learning step or request construction it was made, so a stale record could
  authorise a stage that builds other requests: the record and every configuration's registration now carry the
  step directory and a request identity (runtime table, hashes of this tree's bank code and of the bound
  machinery, the binding), and a stage runs only with the record of the same step and identity; (b) cells were
  matched by item and system card alone, so one round's candidate could pass as the base of a comparison with
  another round's: every configuration is compared with ITS OWN source (the base with the base- or incumbent-arm
  cells of the unit the step's gate compared against, named by the operator and never a card round; a candidate
  with the candidate cells of the round whose writer wrote exactly its text), and a report compares the run's
  base with a candidate of the same step and request identity, nothing else; (c) an OfficeQA item that lost its
  status after a configuration was registered stayed in the judged population: a contrast configuration is
  registered on exactly the judged items of now, a changed population stops the stage, and the gate rule is
  undecided when the judged items of now differ from the registered ones. The rest of (3): records made before
  registration existed are compared with the per-item run count before any call. Three test gaps closed (a
  shuffled ranking for the "first N" reports, a runtime that really changes the request, the enforcement tested
  through the function the command line calls). These second-round fixes were NOT reviewed again (one follow-up
  round); they are covered by 20 further mutations, each failing a test, and by the zero-call parity on the real
  run with the final code (snapshot j): OfficeQA step 2 of chain G, base against `noharm-t01` 38 of 38 gate items
  with the run's request, round 1 and round 2 texts 38 of 38 each (2 gate items were not routed by the run);
  ZebraLogic step 3 as stated in B28's withdrawal.
- **B30 The instrument's base must not be the runs that admitted the items (amends B25; written 2026-11-14 16:4x,
  after the first reading and after the second part was started at 16:18:40, before any report of the second part
  existed: `hc` stood at 140 of 563 tasks).** First reading (root `bank-v2-b`, `--base c --config c0`, chain-G
  solver): real items -10.81 points [-21.62, 0.0] (74 parents), made items -6.75 [-10.2, -3.19], made minus real
  +4.06 [-8.31, +15.9]. By B25 the check is NOT INFORMATIVE (the real interval touches 0), and that reading
  stands. What the first reading exposed is a flaw of the comparison itself: `c` is the checker, and the checker's
  runs are what ADMITTED the made items (a new question is verified by two passes of at most three runs, a twin is
  confirmed by a pass). Paired with those same runs, the hand card starts from a pass rate that its own admission
  pushed up, so any other configuration looks worse on made items than it is, whatever it does on real ones.
  **Amendment, fixed here:** on made items the base of an instrument comparison is a run that took no part in the
  admission: `hc` = the hand card run again on the same judged items (two runs per real parent, one per made
  item). The instrument reading is `--base hc --config c0` under B25's rule unchanged. `--base c --config hc`
  compares the same card with itself: on real items its gain estimates nothing but run-to-run noise, on made
  items it is the size of the admission effect, reported as such. The chain-D repeat that B25 already prescribes
  (`dc`, `dc0`) is made of two fresh runs of another solver and needs no change. **What a fresh base does not
  remove:** the admitted population is still the items that the chain-G solver with the hand card solves; when a
  card's effect differs between items, a gain measured on that population leans toward the hand card even with
  fresh runs. A reading on made items is a statement about the admitted population. In a chain's gate both arms
  run fresh, so the same-run effect cannot occur there; the lean exists when one arm is the hand card alone (the
  first step of a bench), and it works against the candidate (fewer wrong acceptances, more wrong refusals).
  **For the next bank:** admission should rest on something that is no solver run under a compared card: an
  answer that execution alone certifies (a generator with a uniqueness check, two anchored programs), a human
  audit of derivations, or a checker of another model family; and a report on made items names what admitted them.
- **B31 ZebraLogic made puzzles (design section 5, source "乙"; written 2026-11-14 17:3x, before any model saw a made
  puzzle).** Why now: B28 found the pool's puzzles of the judged sizes used up, and the first reading of B25
  showed what admission by a solver's success costs (B30). Built: `bank/zebra.py`, `bank/zebra_build.py`, commands
  `zebra-language`, `zebra-make`, `zebra-report`; no model is called.
  (a) **Language**, learned from the pinned practice pool by fixed code: every clue line is one of nine sentence
  patterns (in a house, not in a house, same house, directly left, somewhere left, somewhere right, next to, one
  house between, two houses between) over phrases that each name one value of one column. A phrase's meaning is
  not read off its words: it is the one value that fits the reference grid wherever the phrase occurs. Two proofs
  on the pool, repeated by every `zebra-language`: each puzzle is written back byte for byte, and each puzzle,
  solved from its parsed clues alone, has exactly one solution, its reference grid (the anchor of this bench).
  On all 500 pool rows (Mac, 2026-11-14): 5,169 clues, 150 phrases = 25 columns x 6 values, 500 of 500 written
  back, 500 of 500 solved to the reference alone, and a second solver written independently of the first agrees
  on all 500. No clue of a pool puzzle can be left out (0 of 5,169): the pool's puzzles are irredundant.
  (b) **Making**, as the benchmark's paper describes its own puzzles (arXiv 2502.01100, Algorithm 1): a random
  grid; its true clues, one sentence per fact (where a value is and is not; two values of different columns in one
  house; for a left and a right value one of "somewhere left" / "somewhere right"; for neighbours one of "directly
  left" / "next to"; one house between; two houses between; the left value named first, as in 465 of 465 such pool
  clues); the clues are gone through once in a random order weighted by kind, and a clue is taken away whenever
  the grid stays the only solution. The paper gives no weights: nine were fitted ONCE to the kind shares of the
  200 pool puzzles of the judged sizes (left and right tied) and frozen (`zebra.REMOVAL_WEIGHTS`: 0.53 for "same
  house" to 1.56 for "two houses between"; a heavier kind is tried earlier and survives less often). Another
  reading of "weighted" (draw a kind first, then one of its clues) was tried and refused: 22 of 30 comparisons of
  (d) below 0.05.
  (c) **Certificate**, from a made puzzle's TEXT and stored grid alone: read like a pool puzzle and written back
  exactly; both solvers find exactly one solution, the stored grid; no clue can be left out. Nothing is admitted
  by a model's success, so a made puzzle leans toward no configuration (B30).
  (d) **Made against real, by fixed code** (`zebra.compare`, part of every `zebra-report`): for every size and
  three measures (the mean number of clues, the shares of the nine kinds, the share of puzzles the first solver
  settles without search) the real puzzles of the size are compared with random groups of made puzzles of the
  same number, drawn from a reference sample of 300 per size that is made for the comparison alone. On the Mac
  (100 per size against the 200 pool puzzles of the judged sizes): 2 of 30 comparisons below 0.05 (1.5 expected
  by chance), none below 0.001; the lowest is the number of clues at 6 houses x 4 columns (real 16.85, made 17.8,
  0.004). **Reading, fixed here:** the comparison is descriptive; a size with a comparison below 0.001 is named in
  every report that uses its items.
  (e) **Limits to state with any result:** the weights are fitted to the pool, so the pooled kind shares agree by
  construction (the numbers of clues, the shares within a size and the solver measures are not fitted); no
  generator code of the benchmark was found, so "made the same way" is a reconstruction checked by (a) and (d),
  not a known identity; a made puzzle is compared with the pool's texts only, not with the sealed panel (no
  access: it would take the same grid, the same listing orders, the same clues and the same clue order).
  (f) **Model checks, registered here before any run** (command `zebra-contrast`, to be built on
  `spare.stage_spare` with its parity and registration rules, kind `made`): configurations on the run's 100 real
  gate items AND on the bank's 200 made puzzles of the judging side, in one stage. Costs from the run's cells:
  about 4.5 to 5.3 k tokens a call.
  *Check D* (chain-D solver, 2 runs per item): `c` (the hand card alone, the run's base) and `dk1` (the first card
  of chain D's step 3: the run's gate measured it at -45.7 points on the 100 gate items, from -8 at two columns
  to -48 and below at four to six). PARITY of difficulty: the pass rate under `c`, made minus real, with a 95 %
  interval that resamples items within a size: PARITY when it contains 0, else EASIER or HARDER. KNOWN EFFECT: the
  gain of `dk1` over `c` on real and on made items and their difference with its interval: REPRODUCED when the
  made gain's interval excludes 0 with the sign of the real gain and the interval of the difference contains 0,
  NOT REPRODUCED otherwise.
  *Check G* is the re-judging B28 left open: `c`, `gk1`, `gk2` (the two card texts of chain G's step 3: +5.0 and
  +4.7 at the run's gate, tau 7.1), 3 runs per item; difficulty parity read from `c` as above; the chain's gate
  rule on the real gate items (a fresh replication of the run's gate), on the made items and on both; reading as
  B26 and B28 (`spare.reading`): CONFIRMED when the rule accepts on real and made together and that interval lies
  above 0, NO EVIDENCE when the interval contains 0, HARMFUL when it lies below 0, BELOW THE THRESHOLD otherwise.
  It starts only after check D gave PARITY and REPRODUCED;
  without parity for the chain-G solver its made-item part is reported as not interpretable.
  (g) **Amended 2026-11-14 18:0x after the one review (B32), before any model run on a made puzzle.** *A bank is
  one thing:* its plan (how many puzzles of which sizes, which numbers are shown to writers, the weights, the
  language's pool) is written before the first puzzle and is the plan of every later call; a puzzle whose text
  is a pool puzzle's or an earlier made puzzle's is refused before anything of it is written; the list of the
  finished bank is written after the last puzzle; an item is handed out only from a finished bank, and only when
  the hash of everything a solver and the judge read of it (id, size, question, columns, grid) is the hash its
  record certifies. *The population of a check* is the run's gate slice (every size of the bank equally often
  [wrong for the run's slice: corrected in (h)]) followed by the WHOLE judging side of the finished bank; it is registered with every configuration (for each
  item its group and size, and the hash of the bank's list), and a report groups and stratifies by what was
  registered and refuses any other gate slice or bank. *Each chain's check has its own records* (`maded`,
  `madeg`) in the one root. *Check G starts only when* `check-d.json` of the same bank says PARITY and
  REPRODUCED; that record is written by the report of chain D's check on the first card round of its step and
  by nothing else. *Readings:* the gate rule on the real items alone is always read; the reading on real and
  made items together is withheld ("NOT INTERPRETABLE") when the made puzzles are not at PARITY for the solver
  of the check. *The comparison of (d)* is the bank's write-once record `comparison.json`; no contrast stage
  starts without it, and every model report names the sizes it puts below 0.001.
  (h) **Amended 2026-11-14 18:2x, before any model run on a made puzzle: the gate slice holds its sizes unequally
  often.** A count that calls no model (the run's manifest against the pinned pool, done before the launch) showed
  what (g) had assumed wrongly: the 100 gate items of typed-v2 are 12, 13, 6, 10 and 9 puzzles of 5 houses with 2
  to 6 columns and 12, 10, 11, 10 and 7 of 6 houses, while the judging side of the bank holds 20 of every size.
  The stage of (g) would have refused the slice before any call. Counted item by item the made group holds more
  of the large sizes than the real one, so a difference of the two groups would mix a difference of sizes into a
  difference of difficulty or of effect (chain D's card costs 8 points at two columns and 48 and more at four to
  six). **Fixed here:** the population is the run's gate slice as it is (every size of the bank, no other size)
  followed by the whole judging side. Wherever made is compared with real -- PARITY, the KNOWN EFFECT, and the
  made gain whose interval REPRODUCED needs -- the made puzzles of a size weigh what that size weighs among the
  gate items (its share of the 100); the report gives these numbers as "made at the sizes of the gate items"
  beside the item-by-item ones. The real items' numbers stay the plain ones (a fresh replication of the run's
  gate), and intervals resample within a size as before. The gate rule on the made items and on real and made
  together counts every registered item once, as a chain's gate would: that reading is a statement about the 300
  registered items, whose sizes the report lists. Tests: three cases with ten and four gate items against ten
  and ten made puzzles, their expected numbers computed by hand (one where the item-by-item count would read
  HARDER by 21 points and one where it would read NOT REPRODUCED, both wrongly); 13 mutations of the change each
  fail a test. *Second look of the reviewer* (this change only, as it decides readings; narrow brief, 18:1x,
  on commit `ce589d5`): ACCEPTABLE. Found sound: the estimator (weights = the shares of the real gate items,
  fixed across draws; all 2,000 draws checked against a count-based formula with the ten real size counts), the
  three readings against (f)-(h), the population's refusals, the hand calculations of the tests. One minor
  finding: no test held the real items' part of the parity interval; answered with three tests (each side's
  part of the parity interval, the made puzzles' part of the known-effect interval), 17 mutations of the change
  in all, each failing a test. The first paid check (check D) was started on the reviewed code (dl snapshot m =
  `ce589d5`) at 18:16, after this verdict.
- **B32 The one review of the ZebraLogic code and what it changed (2026-11-14 17:4x, Codex gpt-6-astra, effort
  ultra, read-only, on commit `f1c5573`; before any model run on a made puzzle).** Found sound: the certificate
  (the nine relations against their sentences, square grids, distinct houses, uniqueness, irredundancy), the
  language (strict reading, refusal of a second reading, column membership, capitalisation, the anchored learning
  of phrases), the making (the true clues, the weighted order, reproducibility from the seed; the halving search
  of `thin` is justified by monotonicity and a kept clue stays necessary), the unchanged behaviour of the
  spare-item stage, the chain D / chain G client, token bound and identity wiring, the pairing, denominators and
  stratified resampling of the report, and the comparison's computation. Six blockers and three majors, all
  confirmed and fixed (B31 (g)): (1) a stored item's grid or columns could be changed without its record
  noticing (only the question's hash was bound); (2) a made puzzle with the text of a pool puzzle was refused
  only after its files were written, and could then be loaded; (3) a bank interrupted after its first
  judging-side puzzle could become the population of a model check; (4) a report grouped and stratified by the
  lists a caller handed in, so the same registered ids could be read as EASIER or as HARDER; (5) chain G's
  re-judging could start without check D, and a re-judging reading was given on made puzzles that were not at
  parity; (6) the reading of a harmful card differed from the text of B31 (f) (the text was amended before any
  run: HARMFUL, as B28); (7) a stage interrupted between an item and its record could be resumed with other
  sides; (8) a size named by the comparison did not reach the model reports; (9) the report's tests survived
  three statistical mutations (the two interval conditions of REPRODUCED, resampling across sizes). The reviewer
  also showed that one of my two "equivalent" mutants is not equivalent: without the "settled house" rule no
  solution changes, but the search count does, and with it the comparison's third measure; the counts of twelve
  fixed puzzles are now pinned. These fixes were NOT reviewed again (one round). Mutation checks: 47 changes of
  `zebra.py` and the first `zebra_build.py` (46 fail a test after the added tests; 1 equivalent: the write-back
  proof of `learn` under the strict reader), and 37 changes of the review fixes in `zebra_build.py` and
  `zebra_check.py`: 34 failed a test at once; the other 3 showed conditions no test held (that the made gain has
  the sign of the real one, that the judging side of the bank is whole, that the list of a bank is of its plan);
  each now has a test, and all 37 fail one. The first list was run again in full on the final tree (18:3x): 43 of
  its 47 changes still apply (4 lines were rewritten by the fixes and are among the 37); 41 failed a test, the
  equivalent one did not, and one more did not: the check that a puzzle ALREADY in the bank has no pool puzzle's
  text had lost its test when the fix moved the first check before the writing; it has a test again. With the 13
  and 4 changes of (h): 97 changes of the final code, 96 failing a test and 1 equivalent.
- **B33 Check D of the ZebraLogic made puzzles, read 2026-11-14 18:54 (rules of B31 (f)-(h); dl snapshot m =
  `ce589d5`, root `/data/execskill-20261114-bank-zm-a`, logs `logs-zma`).** Bank: the 173 pinned pool puzzles
  written back and solved to their reference alone; 300 made puzzles certified (100 shown, 200 judging); the
  comparison of (d): 1 of 30 below 0.05 (6 houses x 4 columns, number of clues, 0.0275), none below 0.001, no
  size named. Zero-call parity with the run's requests: `c` 100 of 100 gate items, `dk1` 96 of 96 (4 gate items
  had no cell with the card in the run). Stage: 600 tasks, 1,200 sends, 5,196,659 tokens (deepseek-v4-flash),
  18:16:21 to 18:54:47, no ledger stop. Pass rate in per cent under `c` / `dk1`:

  | items | `c` | `dk1` | gain, points | the chain's gate rule |
  |---|---|---|---|---|
  | 100 real gate items | 86.50 | 40.50 | -46.00 [-52.5, -39.0] | tau 5.10, 1 better, 68 worse |
  | 200 made, item by item | 82.00 | 39.00 | -43.00 [-48.25, -37.75] | tau 4.58, 7 better, 134 worse |
  | 200 made, at the sizes of the gate items | 83.87 | 41.88 | -42.00 [-47.2, -36.68] | |
  | all 300, item by item | 83.50 | 39.50 | -44.00 [-48.0, -39.83] | tau 3.50, 8 better, 202 worse |

  **PARITY:** made minus real under `c` -2.63 [-8.25, +3.2]. **KNOWN EFFECT REPRODUCED:** gain on made minus
  gain on real +4.0 [-4.83, +12.67]; the made gain's interval excludes 0 with the sign of the real gain; the real
  gain replicates the run's gate (-45.67). Re-judging readings of this harmful card: HARMFUL on the real items
  and on all 300. Wrong runs without a complete reply: 29 (`c`) and 28 (`dk1`) of 600 each. By size both groups
  move alike (`c` -> `dk1`, real (n) | made (20 each)): 5*2 100 -> 83.3 (12) | 100 -> 80.0; 5*3 100 -> 50.0 (13) |
  100 -> 50.0; 5*4 100 -> 33.3 (6) | 92.5 -> 40.0; 5*5 60.0 -> 30.0 (10) | 82.5 -> 30.0; 5*6 72.2 -> 11.1 (9) |
  77.5 -> 15.0; 6*2 100 -> 70.8 (12) | 95.0 -> 72.5; 6*3 100 -> 50.0 (10) | 90.0 -> 40.0; 6*4 81.8 -> 18.2 (11) |
  72.5 -> 37.5; 6*5 75.0 -> 20.0 (10) | 67.5 -> 15.0; 6*6 64.3 -> 7.1 (7) | 42.5 -> 10.0 (single sizes hold 6 to
  13 real items and are not read alone). `check-d.json` holds PARITY and REPRODUCED, so check G started in the
  same root at 18:55 as registered (parity `c` 100 of 100, `gk1` and `gk2` 96 of 96 each; 900 tasks, 3 runs).
  **What this does not show:** another solver; a small effect (the known effect is 45 points, a card's gain at
  a gate is 5); that made puzzles have the benchmark's own distribution beyond the three measures of (d). The
  OfficeQA bank failed the same kind of check (B25, B30): the difference is that nothing here is admitted by a
  solver's success.
- **B34 Blind audit of made OfficeQA items by a model of another family (registered 2026-11-14 21:5x, before any
  verdict exists).** The owner (11/14 about 21:4x) delegated the audit of B22 to Claude ("由你来替我做吧") and ties
  OfficeQA's next step to its result. **What it is:** an audit by Claude models (Anthropic), a family that took no
  part in making, computing, checking or admitting the items (GLM-5.3 did all of that; deepseek only solved). It
  is NOT a human audit and is never to be reported as one. **Sample:** the blind sample of B22 (seed 20261114):
  100 admitted items (25 each: number twins, plain / brief / target questions) and 40 items that passed the fixed
  checks and that the checker did not admit (10 each), plus a calibration of the auditor itself: 20 anchored
  derivations of real practice items (known right: the code answer equals the reference) and 20 coded mistakes of
  20 other real items (known wrong: the judge refuses the answer for the reference; 6 wrong period, 6 wrong
  operation, 7 wrong series, 1 missing step). 180 items with opaque ids; the fields that show admission, arm,
  targeted weakness, checker replies and truth are removed (checked by a search of the batch files). **Two
  independent passes:** A (Claude Fable 5.2) and B (Claude Opus 5.5), each its own seeded shuffle into 9 batches
  of 20; every batch is read by a fresh-context agent that sees only its batch file. **Verdict per item:**
  correct (the stated answer is the answer to the question as written, from the document as given, to the stated
  decimals) / wrong / flawed (the question cannot be answered unambiguously from the document, or the changed
  document contradicts itself where it matters) / unsure, with the auditor's own recomputed value and one
  sentence. **An item's result:** correct when both passes say correct; not correct when both say wrong or
  flawed; split otherwise (reported apart, and counted as not correct in the rates below).
  **Auditor rule, fixed before unblinding:** the audit vouches for something only if on its calibration it calls
  correct at least 18 of the 20 known-right items and at most 2 of the 20 known-wrong ones.
  **Readings:** the share of correct items among the admitted (per kind and together) and among the non-admitted,
  with Wilson 95 % intervals; each pass's own calibration and the agreement of the two passes beside them.
  **What it decides for OfficeQA (owner: by this result):** (甲) the auditor rule holds, at least 90 of the 100
  admitted and at least 32 of the 40 non-admitted items are correct: a code answer can be trusted without a
  solver's success; admission by a solver is dropped for OfficeQA (fixed checks only) and the instrument check is
  repeated on that population before any use in a gate. (乙) the auditor rule holds and at least 90 of 100
  admitted are correct, but fewer than 32 of 40 non-admitted: made OfficeQA items stay guard items (they may show
  harm, they do not judge gains) until the maker is improved; what is wrong with the non-admitted items is
  listed by kind. (丙) fewer than 90 of 100 admitted are correct, or the auditor rule fails: made OfficeQA items
  are not used until the maker (or the auditor) is fixed. **Limits to state with the result:** a model audit;
  the auditors may share with the makers a blind spot about what a reasonable reading of a question is; both
  auditors are of one family; a human spot check of a subset remains the stronger evidence.
- **B35 Check G of the ZebraLogic made puzzles, read 2026-11-15 01:4x (rules of B31 (f)-(h); dl snapshot m =
  `ce589d5`, root `/data/execskill-20261114-bank-zm-a`, logs `logs-zma`).** Started 18:55:51 after `check-d.json`
  held PARITY and REPRODUCED (B33), as registered; contrast stage ended 23:43:28. Population: chain G's 100 real
  gate items of step 3 and the 200 judging-side made puzzles of the same bank (bank list `a826e1e0...`).
  Configurations: `c` (the hand card alone, the run's base), `gk1` and `gk2` (the card texts of rounds 1 and 2 of
  chain G's step 3; the run's gate measured +5.00 and +4.67 points with tau 7.12 and refused both). Zero-call
  parity with the run's requests: `c` 100 of 100, `gk1` and `gk2` 96 of 96 each. 3 runs per item and configuration:
  900 tasks, 2,700 sends, 15,811,698 tokens (GLM-5.3; the root's ledger holds 3,900 sends and 21,008,357 tokens
  after both checks), no ledger stop; 1 wrong run without a complete reply per configuration. Pass rate in per
  cent (gain in points with its 95 % interval; the chain's gate rule with tau, better / worse items):

  | items | `c` | `gk1` | gain | rule | `gk2` | gain | rule |
  |---|---|---|---|---|---|---|---|
  | 100 real gate items | 73.33 | 77.67 | +4.33 [-2.0, +10.67] | tau 6.46, 29 / 20, refused | 77.33 | +4.00 [-3.33, +10.67] | tau 6.46, 33 / 26, refused |
  | 200 made, item by item | 74.83 | 78.50 | +3.67 [-0.67, +8.0] | tau 4.71, 61 / 46, refused | 79.33 | +4.50 [0.0, +9.17] | tau 4.71, 66 / 48, refused |
  | 200 made, at the sizes of the gate items | 73.93 | 78.92 | +4.98 [+0.67, +9.43] | | 79.80 | +5.87 [+1.13, +10.73] | |
  | all 300, item by item | 74.33 | 78.22 | +3.89 [+0.22, +7.33] | tau 3.81, 90 / 66, accepted | 78.67 | +4.33 [+0.22, +8.22] | tau 3.81, 99 / 74, accepted |

  **PARITY for the chain-G solver too:** made minus real under `c` +0.6 [-6.15, +7.5]. **Re-judging readings**
  (B26, B28, `spare.reading`): on the real items alone NO EVIDENCE for both cards (a fresh replication of the
  run's refusal: +4.33 and +4.00 against tau 6.46); on real and made items together CONFIRMED for both (the rule
  accepts and the interval lies above 0). The measure of check D's known effect, informational here (not a
  registered reading of check G): made gain minus real gain +0.65 [-7.17, +8.45] (`gk1`) and +1.87 [-6.7, +10.3]
  (`gk2`). Per-size numbers are in the evidence files. **What this shows:** for both solvers the made puzzles
  are as hard as the real gate items at the gate's sizes, they move with a card as the real items do (a harmful
  card of 45 points for chain D, two helpful cards of 4 to 5 points for chain G), and with the 200 made puzzles
  added the chain's own rule accepts the two cards the 100-item gate could not see. **What it does not show:**
  the lower ends of both intervals on the 300 items are +0.22, a thin margin; the two cards are revisions of one
  another from one step, not two independent confirmations; one bench; the report mounts the card on every item
  (a run mounts it on the items routed into its type); no test item was read, so nothing here is a test-panel
  effect; a re-judging after a run is not an acceptance in that run (typed-v2 stays frozen, its S3 does not hold
  these cards). The population is calibration-like (natural weights, the gate's sizes); typed-v3's attack items
  are targeted and are not what this check measured. Evidence: SkillOpt
  `docs/handoff/typed-v3-bank-20261114/evidence/zebra-check-g-c-gk1.json`, `zebra-check-g-c-gk2.json`.
- **B36 The blind model audit of B34, read 2026-11-15 02:0x (both passes complete before the key was opened).**
  Pass A (Claude Fable 5.2): 9 batches; 5 finished 11/14 22:01 to 22:20, the other 4 (A2, A5, A7, A9) died on
  network failures without writing a verdict and were run again by fresh agents 11/15 01:49 to 02:00 with the same
  instructions plus saving after every item. Pass B (Claude Opus 5.5): 9 batches, 11/15 01:47 to 02:01. The model of
  every agent was checked in its transcript (every pass-A agent `claude-fable-5-2`, every pass-B agent
  `claude-opus-5-5`); every batch holds 20 verdicts, 360 in all, none unsure. The key (sha256 `08bb0f6f...`) and the
  instructions stay in the private scratch folder; aggregation by `aggregate.py` as registered.
  **Calibration:** pass A called 19 of 20 known-right items correct and 0 of 20 known-wrong ones; pass B the same;
  both passes together 19 and 0: **the auditor rule holds.** The known-right item both passes called wrong is an
  anchored derivation of a Theil index that rounds `T - 0.0005` to three decimals to reproduce the reference 0.011,
  while the index (0.011761) rounds to 0.012: the derivation was fitted to the reference by an adjustment the
  question does not state (whether the benchmark's reference truncates was not checked further).
  **Result** (correct = both passes correct; not correct = both wrong or flawed; split counted as not correct):
  admitted 78 of 100 correct (Wilson 95 % [68.9, 85.0]; 9 not correct, 13 split): number twins 7 of 25, plain
  questions 23 of 25, brief 25 of 25, target 23 of 25; not admitted 19 of 40 [32.9, 62.5]: twins 0 of 10, plain 5,
  brief 7, target 7 of 10. Agreement of the passes: the same verdict on 162 of 180 (90.0 %), the same correct / not
  correct on 165 of 180 (91.7 %), kappa 0.808. **Reading (registered): 丙** (fewer than 90 of 100 admitted items
  correct): made OfficeQA items are not used until the maker (or the auditor) is fixed; typed-v3's OfficeQA steps run
  with J = R, as typed-v2, and the maker registry records why.
  **What is wrong, by kind.** (1) Number twins: an edit changes a total without its parts (or parts without their
  total), so the changed document contradicts itself. Both passes called 6 admitted twins flawed; on 12 more pass A
  said correct and pass B flawed: the registered words "where it matters for the question" were read narrowly by A
  (only the figures the question uses) and widely by B (any identity the edited figure belongs to). The calibration
  held no changed-number item, so it cannot say which reading is right; under either reading the twin maker must keep
  identities consistent or refuse the twin. Three twins inherit the Theil adjustment above and are wrong under both
  readings. (2) New questions: 71 of 75 admitted ones are correct; the other 4 read a wrong column of a parsed table
  whose header lost or merged a column (2), used a column labelled "Total investments" that is the balance total (1),
  or leave the rounding of a repeating decimal unstated (1, split). Not admitted: 19 of 30 correct; the wrong ones
  are mostly the same column misreadings, plus a wrong period and a simple rate where a continuous one is asked.
  Admission by the checker removes wrong answers (71 of 75 against 19 of 30) and biases difficulty (B30): neither
  population is usable as it is. **Limits:** a model audit by one family, never a human one; the auditors may share
  a blind spot with the makers about what a reasonable reading is; the calibration holds no changed-number item; one
  agent per batch, no repeat of a pass. Cost: Claude subagents outside the project's model budget, about 0.2 M tokens
  a batch.

## Reuse

`compute.exact` / `rounded` / `number` (exact evaluator), `envs/officeqa/evaluator.exact_match` (judge),
`continual_eval.backends.solve` and `_score_answer_tag` (checker request and scoring), `v222_cards.historical_text`
(hand card), `typed.units.Ledger` / `CallRecorder` / `write_json` (accounting, records, path-word guard),
`typed.prepare.load_pool` (pinned pool), `run_typed.bind_machinery` / `run_inputs` (binding, clients). Earlier
generators consulted: `scripts/generate_officeqa_tasks.py` (2026-10-14; the tie and trailing-zero rules, "every
figure matters"), `generators/officeqa.py` (reproduce the reference first), `research.py` (verbatim-quote findings
over a write-once archive; to be extended for B8).

## Open points

- Questions about a chart (a count of local maxima, a year read off a plotted line) have no derivation from the
  parsed text and stay without a code rubric and without twins.
- A sealed text-overlap check of new questions against test questions needs its own consent record; B12's page
  rule avoids the need for the pilot.
- The typed-v3 chain side (diagnosis, selection from the bank, the two-way acceptance rule, grouping slices by
  parent) is not built; `typed/__init__.py` still names typed-v2.
- A verified new question is one the checker (the chain-G solver with the hand card) solves twice: the verified
  set leans toward what that solver can already do. Until the audit of B22 exists, verified new questions are
  guard items for chain G; whether they discriminate for the weaker chain-D solver is not measured.
- The SpreadsheetBench stages have not run on real workbooks yet (they wait for the machine-wide memory lock).
