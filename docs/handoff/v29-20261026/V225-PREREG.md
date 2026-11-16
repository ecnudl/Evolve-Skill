# Route B v2.25 — main-v9 preregistration

Date: 2026-11-04. This is an offline engineering implementation in
`<repo-root>`, governed by
[the brief](BRIEF-v225-main-v9.md) and [the decision overlay](DECISIONS-v225.md).
The overlay wins. No model experiment, Linux validation, native S0, measured smoke,
test-panel read or launch has been performed by this writer. There are no
method-effect results here.

## Owner direction and scope

Owner direction, 2026-11-04 11:0x, verbatim:

> 通过之前cross-v5的结果来看，大部分的跨bench的伤害来自指令的损害，这次能不能避免一下，最简单的方式就是只有跑当前bench的时候才注入指令，或者说指令可以让meta-LLM先看过训练集再去写一份指令，我觉得后一种方法更符合学习进化的理论，当然你也可以再优化一下，找到更好的方法

Owner definition of 5×5, verbatim:

> 每个bench进化完，无论有没有包收下，都要在五个bench的测试集上真正的跑一遍测试集得到结果

Thus every completed bench step schedules all five sealed panels even when no
package changes. The reads use fresh model cells; identical requests do not
justify sharing or a structural zero. Only the read children may access panels.
Learning never consumes the sealed cells, scores or aggregates. Unsealing remains
subject to the existing explicit per-run owner approval.

This tree adds `main-v9`; v2.23/v2.24 live elsewhere. The files ending
`main-v9-draft.md` and `DECISIONS-v225-draft.md` describe v2.26: no seeded QA
procedures, calculator extension, provenance exemption, after-answer hook,
shared-draft change, sparse confirmation or extra G runs is introduced here.
Rollback means running main-v8 or another old configuration in its original
snapshot/root. It does not relabel a new run or overwrite old artifacts.

## Decisions taken

| Overlay decision | Registration |
|---|---|
| O1/O2 | Three card rounds; at most 3,000 characters and 12 bullets. |
| O3 | Public task card, fixed format block, current routed card, at most 12 practice failures and 6 successes; references only for failures; never the historical zero-shot card. |
| O4 | Cross cards on SearchQA–OfficeQA and OfficeQA–SpreadsheetBench, through the positive gain rule, only into empty slots. |
| O5 | I, cards only, once at chain end. |
| O6 | QA/sheet draft changes deferred to v2.26. |
| O7 | C0 read at chain start is the actual row-zero start; no C0 end reread. |
| O8 | C is the whole historical card; one fresh C_end repeats it at chain end for descriptive drift measurement only. |
| O9 | Only SearchQA confirms cards: 40 fresh acceptance-pool items. OfficeQA/sheet exhaust their acceptance pool after one card acceptance comparison and skip procedures with `skipped_pool_exhausted`. |
| O10 | No ALFWorld card; step 5 remains the fixed v11 import, not learning. |
| O11 | Cards: net ≥ max(3, ceil(0.05 T)), broken ≤ 2/3 fixed, whole batch ≥ −0.01. Procedures retain the frozen 10% rule. |
| O12 | Stage reads overlap the next learning step; a learning pause does not cancel reads already launched. |
| O13 | Route by the item's registered bench, not structural quantity/evidence predicates. |

Exact consent arm order: `B, C0, C, S1, S2, S3, S4, S5, I, C_end`.
There are eight read events (`anchor`, `s1`–`s5`, `i`, `c_end`), 40 units and
50 panel-arm reads per chain. F aliases S5, with no extra calls. Multiplicity is
**10 arms × 5 panels × 2 chains**, replacing the brief's superseded nine-arm
count. Every registered contrast is reported; no panel-arm cell is selected by
its result. C_end−C is descriptive drift, not a new method contrast.

## Rules, prompts and immutable identities

R1 copies the entire main-v8 registration by value before main-v9-only overrides.
The dated root string is `/data/execskill-20261104-main-v9` (never accessed in this
work); namespaces are G-v9 and D-v9. Changing the launch date/root requires new
reviewed pins and S0, not editing a frozen launch in place.

R2 represents each card by the exact constants-only V225 template, with no hooks,
worker execution or describer entry. Five card slots and four card edits are
separate from the existing 24 procedures, 64,000 source bytes and three procedure
edits. Length, format markers, practice IDs/paths, reference copying and public
example eight-grams are checked deterministically. A card is composed once,
before the unchanged format block, only in its route bench's request; B remains
blank. The engineer cannot revise the card.

R3 uses GLM-5.3, the method credentials and engineer reasoning/timeout settings,
32,768 output tokens and a 120,000-character input ceiling. Each round permits
one screened retry, at most six writer calls per bench and 24 per chain. Public
views use 3,000-character head/tail truncation; replies retain first 300 and last
1,200 characters; references are capped at 300. Successes are dropped first to
fit the input ceiling. Confirmation, acceptance, harm and read rows cannot enter
the learner's writer examples. The immutable writer call-record file hash is
the card lineage.

The exact three writer texts, retry reasons, Zebra task card and hashes are
vendored in [the card fixtures](../../../tests/fixtures/execskill/v225_cards/)
and returned by `v225_cards.prompt_pins()`. No prose paraphrase in this document
replaces those exact pinned bytes. S0 also pins task cards rendered under its
runtime, format hashes, the card template/policy, routing, constants, cap identity,
literal audit and parent capture. The inherited D1 draw and ALFWorld reset-view
overlay remain bound by value; no decomposition measurement or fallback runs.

R4 runs write → train → SearchQA-only confirm → fresh acceptance, stopping on
first acceptance. Training uses the full run slice at its registered run count;
candidate cells are fresh each round and only exact, fault-free parent requests
may reuse earlier card-training cells. Acceptance counts are SearchQA 60×1,
OfficeQA 32×4, ZebraLogic 40×1 and SpreadsheetBench 36×2. Every examined prefix
is consumed, including rejection. SearchQA consumes 40+60 for a full attempt;
the Zebra procedure confirmation slice is untouched. Accepted-card candidate
training cells seed the procedure phase; card rounds do not spend procedure
patience. Card provenance stays outside the engineer's exact history schema.

R5/R6 require byte identity off route. Cross copies retain exactly the home
text, never replace an occupied slot, never re-export a cross copy, and cannot
be narrowed after a failed gain gate. A later accepted own card replaces an
earlier cross copy. Production cross gates use the registered D1 target slice,
one fresh pair per item, with the card's positive 5% gain rule. Other benches
must be identical without model calls.

R7 keeps the procedure machinery, format blocks, two-judge audit, diagnostics,
freshness, early acceptance, split/merge, infrastructure retry, solver routes,
environment locks and fixed ALF import by value. P0 and card hygiene are off.

R8 seals fresh reads under each chain's `test/<event>/<bench>` directory.
Status receipts outside that tree let the controller schedule/observe units
without reading results. The anchor precedes learning and requires exact owner
consent and sheet qualification. Before events, both solver/read scopes must
cover 1.3 times the SE6 estimate for remaining units. The existing canary scan
classifies all nested stage units as reads before approved unsealing.

R9 emits the fivebench aggregate schema and CL metrics, with anchor_C, anchor_C0,
anchor_B, same_side_L, changed_only and same_text blocks, plus explicit first-call
touch counts separate from the reference's full-request-sequence ties. The reference is copied
from `<docs-repo>/docs/paper/scripts/cl_metrics.py` to
both required public fixture locations. Its actual SHA256 equals the brief's:
`587883bf35392fd3d7739fce98407519515c2090fa4eef705d4b5f59bfb0a994`.
anchor_C uses its formulas field for field, for both P and S analyses. Unchanged
package rows are reported as same-text variation, never transfer/forgetting.

## Honest motivation and limitations

The brief reports cross-v5 card harm on 5/16 off-diagonal cells for G and 10/16
for D; no-harm rates 68.8%/37.5%. That was a post-hoc card-swap diagnostic, not
the real pipeline swapping its own cards, and not evidence that routed
procedures harmed other benches. Practice-only card probes indicate format-only
may lose about six points on G SearchQA and about fifteen on D OfficeQA; moving
content after the format increased missing SearchQA tags from 11/200 to 36/200.
These are brief-supplied measurements, not re-extracted or independently verified
in this offline writing session.

Two simulations in the brief are **arithmetic under a model**, not experiments:

1. Independent items, measured flip-rate assumptions, a share 2f unstable, a card
   fixing 1.25Δ and breaking 0.25Δ, 1,500 seeded trials per cell. Under the 10%
   three-stage SearchQA rule, a true +10-point card passes about 0.16; the offered
   5% rule raises this to about 0.60. Null adoption is at most about 0.05 under
   that simulation. Small-bench acceptance probabilities remain limited by
   supply and noise. These numbers do not calibrate actual main-v9 power.
2. Under the former pure no-harm cross gate, routing probabilities at effects
   −10/−5/0/+5/+10 points were OfficeQA .14/.31/.58/.81/.91, sheet
   .13/.27/.56/.80/.92 and SearchQA .04/.15/.67/.93/.98. Thus it admitted null
   cards 56–67% and −5-point cards 15–31%. The overlay chooses a gain gate;
   these are not acceptance probabilities for that new gate.

The supplied same-text flip rates are G 4.5/17.2/34.8/21.1% and D
1.1/11.9/25.0/20.1% for SearchQA/OfficeQA/Zebra/sheet; D Zebra used 16 items.
Serving drift and sampling noise enter independent stage reads. C_end measures
historical-card drift descriptively, without changing learner decisions.

The panel sizes are 400/172/200/279 registered (204 scored for the sheet)/134.
Prior-exposure counts in the brief (as of 11/03, before subsequent reads) are
ALF G5/D8, SearchQA and OfficeQA G5/D6, sheet G4/D5, Zebra G3/D5. **Exact exposure
counts at S0 are unknown here**: this writer is prohibited from Linux/registry
access. The operator must record current counts before S0. The new schedule
adds ten reads of each panel per chain, twenty for both.

An accepted card or cross route is a practice decision, not an accepted test
effect. I−C measures cards versus historical instructions; I−C0 measures their
addition over the format shell; F−I measures procedures given cards. ALF F−C
mixes the fixed import and removed historical content, while F−C0 isolates the
import within this design. Imported behavior is not learned generalization.

## Cap arithmetic and costs

Both paired card arms are reserved at the 1.6 procedure factor, with no reuse,
early-stop or exhausted-pool discount. Step caps total **6,966,400,000**.
The overlay adds C_end: four shell-card arms plus six package arms produce
574,000,000 derived read tokens, plus the largest unit retry 80,000,000 =
654,000,000. The registered read cap remains max(743,000,000, 654,000,000) =
**743,000,000**. Redo is **1,152,700,000**; rounding their sum to five million
gives **8,865,000,000 solver tokens** per chain. Writer reservation is
24 × 613,120 = 14,714,880, so method cap is **7,607,505,664**. Total is
**16,472,505,664 per chain; 32,945,011,328 both chains**.

These are ceilings, not spend forecasts. The brief estimates nine-arm spend
G69–98M/D76–96M; C_end adds approximately one five-panel read (roughly G4.6–5.9M,
D5.6–6.5M under its historical scaling). No actual v2.25 cost or runtime is
measured here. Writer/cross-card smoke additions are bounded separately at three
writer calls and sixty paired solver cells; the price sample exercises all
registered arm kinds on reserved practice/authored smoke items.

## Deviations and prerequisites

- Baseline SHA check: all 1,579 permitted entries match the 1,582-entry fix-5
  manifest. Three source filenames are explicitly prohibited by the user's
  stronger filename rule and were not opened: `scripts/evaluate_fivebench_test.py`,
  `scripts/finalize_coevolution_v6.py`, `skillopt/coevolution_v3/tasks_holdout.py`.
  This is a verification limitation, not a verified equality claim for those files.
- The existing ROLE_* objects are global scalar registrations. The writer role
  uses a new configuration-specific role block instead of mutating those scalars;
  legacy manifest role fields remain byte-identical.
- `protocol.record`/`verified`, package validation and the existing cell, engine,
  registry and precheck evidence validators admit the exact new evidence label
  by a conditional. The latter four modules are necessary additions to the
  brief's named-file list. Frozen protocol tables, including EVIDENCE, are not
  rewritten. Unknown future labels are still rejected.
- A static-rejected card round has no candidate-training trajectories. A revision
  then reuses only the original allowed run examples, with the rejected text and
  static clause; no fresh acceptance/confirmation rows are substituted.
- The ≤10-item cross-card smoke conflicts with the production D1 minimum of 18.
  An explicit smoke-only gate option admits the mini slice for smoke/engineering
  evidence; ordinary main-v9 method gates retain the production minimum.
- The mutation harness copies only reviewed public source and authored fixtures
  into plain-named scratch roots, excluding protected filenames, symlinks,
  caches and secret files. It also copies the exact public historical-card
  fixture needed by routing detectors. This is a harness adaptation to the
  writer's filesystem restriction; old mutation definitions are unchanged.
- The source literal audit records all current matching lines in the 22 named
  files. The brief's 94-site count refers to its earlier source enumeration;
  the fixture binds the current source locations and fails on any new literal.
- Main-v9 removes the old decomposition/card-source pins. The same seeded
  practice draw now serves smoke pricing; the required ALF routing overlay
  retains its historical draw-provenance label by value without decomposition
  execution.
- The structural and SX commands use authored cells and injected external-call
  boundaries while executing production selection, gates, controller, handoff,
  read planning, aggregates and metrics. They do not certify native runtimes.
- SE6 needs a separate price set: B/C0/C and a pinned executable P containing a
  maximal card (the fixed import alone for ALFWorld). The 60-cell bound covers
  only the new card and cross-card probes; the price set and inherited narrowing
  probes have their own existing smoke reservations.
- New smoke probes use serial dispatch and dedicated 1,000,000 solver-token
  and 1,839,360 method-token scopes, in addition to parent scopes. A narrow
  `rounds.py` hook enforces 60 solver attempts before dispatch; the writer
  wrapper enforces three attempts. These durable reservations conservatively
  count interrupted attempts that may never reach transport. A maximum-cost
  reservation can stop the probe below its actual-token ceiling (G
  SearchQA/OfficeQA reserves at least 264,192 per call, before input charges).
  This is fail-closed accounting, not permission to raise the registered caps.
- The exact current panel-exposure registry, Linux full suite, source review,
  native S0 and measured smoke remain operator work. No local fixture pass is
  evidence that these operational checks passed. Templates are reviewable text,
  not a launch or commit authorization.

The final [validation record](V225-VALIDATION.json) records actual test counts,
mutation outcomes, final deviations and unresolved smoke blockers. The
[changed-file list](V225-CHANGED-FILES.txt) and [source inventory](V225-SOURCE-SHA256.json)
identify this implementation without rewriting the historical v2.22 inventory.

## Exact writer text pins

### card_write_system

SHA256: `b20a6db677bd00459bfa42ded45780080864bd4a944ecb893431328aee297a1a`.

```text
You write the instruction card (a "Skill") that is placed in the system prompt of another language model which solves tasks of one kind; the fixed answer-format block shown to you is always placed after your card, unchanged. You are given the public description of the task kind, that format block, the card the solver currently receives (possibly empty), and examples of the solver's attempts on practice tasks of this kind with their scored outcome (for failed attempts also the reference answer).

Write the guidance that will most improve the solver on NEW tasks of this kind: what to pay attention to, how to use the supplied material, which recurring mistakes the examples show and how to avoid them, and how to decide when unsure. Keep it general for the task kind. Never quote or copy an example's text, names, numbers, identifiers or reference answers, and never refer to a specific example: the card is checked against the examples and their references and is rejected if it contains any of them. Do not restate or change the answer format, and do not write answer, action or calc tags or code fences: the format block owns the output contract.

Output only the card text in plain Markdown, at most 12 bullet points and at most 3,000 characters, with no preamble and no closing remark.
```

### card_revise_system

SHA256: `b0c9e32dce278d5d1651619c2455364d484c806eb79ff9f9c355ca04921ea6c4`.

```text
You revise the instruction card (a "Skill") that is placed in the system prompt of another language model which solves tasks of one kind; the fixed answer-format block shown to you is always placed after your card, unchanged. You are given the public description of the task kind, that format block, your previous card, the counts of its test on practice tasks (tasks it fixed and broke, the rule it had to meet and the clause it missed), and examples of the solver's attempts WITH your previous card on practice tasks, with their scored outcome (for failed attempts also the reference answer).

Revise the card so that it fixes the recurring failures without losing what worked. Keep it general for the task kind. Never quote or copy an example's text, names, numbers, identifiers or reference answers, and never refer to a specific example: the card is checked against the examples and their references and is rejected if it contains any of them. Do not restate or change the answer format, and do not write answer, action or calc tags or code fences: the format block owns the output contract.

Output only the revised card text in plain Markdown, at most 12 bullet points and at most 3,000 characters, with no preamble and no closing remark.
```

### card_retry

SHA256: `9579bac5bda833ae6bb0a3bd0427256a78d1867e2963024d9a6e08d1e85a2a4c`.

```text
Your reply could not be used as the card: {reason}. Reply again with only the card text, following every rule of the system message.
```

## Fix 1 — reviewed execution and validation corrections

The first read-only review identified nine implementation issues; all are
corrected without changing registered models, card/procedure gain floors,
practice allocations, prompt bytes or token caps. Completed card phases rebase
the selected package onto the step parent while preserving explicit cross-gate
candidate/hash bindings. Unchanged composed guidance is rejected before solver
dispatch. Actual fault-free request changes and a fully touched selection are
required before consuming a card decision read; public identity screening alone
does not consume acceptance supply.

Writer dispatches now have immutable durable reservations before transport,
bounded by two per round, six per bench and 24 per chain. Persisted replies are
reused across unit attempts. A reserved call without a persisted reply stops
without resending; its delivery is unknown and requires review. This conservative
failure case does not authorize extra calls or a higher cap. The smoke-only C0
selector requires smoke/engineering-fixture evidence on both incumbent and rows.

Mutation 146 now changes production read dispatch, with tests of identical arms
and unchanged stages. Main-v9 short-answer diagnostics use each arm's own first
dispatch as origin while retaining absolute timestamps. Protocol termination
remains pending until read futures finish; unsealing also checks owned read locks
in both chains. Historical configurations keep their previous behavior.

The consent patcher validates the actual emitted arm field. The pre-suite ALONE
guard recognizes direct pytest entrypoints and registered experiment/read
drivers, uses a shared cooperative machine lock, and retains explicit operator
confirmation. Process diagnostics expose driver/PID identifiers, not arguments.

Fix-1 validation freezes source, tests, fixtures, operator templates and this
preregistration before the complete macOS-supported broad run. Requested result
metadata is written afterwards. Every remaining failure/error is classified by
node name in V225-VALIDATION.json; no new regression is accepted as an inherited
platform limitation. These remain offline engineering checks, not native S0,
measured smoke or evidence of a learned method effect.

## 2026-11-05 amendment — small procedure confirmation slices

Owner decision, 2026-11-05, verbatim:

> 可以，放宽确认规则，改完冒烟通过后直接启动 main-v9

This rule was changed after the first smoke passed and before any main-v9 chain
ran. That chronology is supplied by the owner; this local writer did not inspect
remote receipts. No test number informed the change: main-v9 test numbers do not
exist yet. The motivation is the four-item OfficeQA/SpreadsheetBench procedure
confirmation slice: the owner reports that all four main-v7 candidates passing
training stopped at confirmation (fixed/broken: 0/1, 0/1, 2/0, 1/0).

Only main-v9 procedure confirmation with `items < 30` now requires net fixed ≥ 1.
The other conditions remain broken ≤ 2/3 of fixed and whole-batch mean change
≥ −0.01 (−1 percentage point). Thus on four items 1/0, 2/0, 3/0, 4/0 and 2/1
pass; 0/0, 0/1, 1/1 and 1/2 fail. `v225_phase.procedure_confirmation` applies
the clause; the serializable rule records `gain_floor=1` and
`small_slice_clause=true`, with decision/reason/passed derived from that rule.
The two constants and unchanged harm/whole-batch floors are registered under
main-v9's `confirmation_small_slice` identity for manifest/S0 binding.

This is the sole exception to the earlier O11/R7 procedure-preservation text.
Training, acceptance, procedure confirmation on at least 30 items (including
SearchQA/ZebraLogic's 40), all card rules and main-v8/older configurations remain
unchanged. Calls without an explicit configuration, including
`v221_learning.structural_smoke`, keep the previous rule. No historical run or
older pin is relabeled. This amendment is local engineering work only; the
current task prohibits network/model calls and launch, so the quoted follow-up
smoke/launch direction is recorded but not executed by this writer.

## 2026-11-05 second amendment — engineer priority and truthful inert feedback

This change was made by the operator under the owner's standing mandate to fix
defects and improve the method, not on an owner sentence approving this text.
The earlier quoted owner decision concerns the small-confirmation rule only.
The source is the post-hoc analysis of main-v6 and main-v7 practice records in
[zebra-candidates-v6-v7-20261105.md](<docs-repo>/docs/paper/zebra-candidates-v6-v7-20261105.md),
sections 4.3 and 7. That analysis was written knowing that a learned ZebraLogic
solver helped on the held-out panel in main-v6. Main-v9's ZebraLogic result is
therefore influenced by earlier results and must be reported as such, rather
than as an independently chosen protocol. Main-v9 has not run, no main-v9 number
existed when this change was made, and its effect has not been measured.

Only main-v9's `v225_cards.engineer_sentence()` gains this exact text:

> Coverage does not outrank a complete solution: when an item's whole answer can be computed and verified from its public input, propose that program first and keep repairing it across rounds, even at low coverage. A note that does not settle the answer leaves the answering model to re-solve, so its fixed and broken counts may only measure re-run noise; do not treat a near miss from such a note as progress.

The second change corrects main-v9's existing low-coverage inert repair request:
`never_fires` requires the routing check's `C6b.fires_on == 0`; a procedure that
fired but produced notes on fewer than three items uses the existing
`empty_notes` cause and receives its diagnostics alongside coverage counts.
The condition setting `report['inert']`, the cause vocabulary, repairable-cause
set and every gate remain unchanged. Main-v8 and older prompt bytes, labels,
evidence and pins remain frozen; only main-v9's prompt fixtures/pins change.
Local validation is recorded in [V225-ENGINEER-20261105.json](V225-ENGINEER-20261105.json).
No model, measured smoke or main-v9 chain is run by this offline writer.

## 2026-11-06 amendment — main-v9 route-B thinking field

The operator reports these facts in Beijing time; this offline writer did not
contact dl or independently inspect the remote ledgers or probe artifacts:

- The northgate route's `deepseek-v4-flash` returned reasoning despite
  `reasoning_effort: "none"`: the first real-ledger reply was at 00:11:47, with
  26 such replies in the membase ledger between 00:11 and 00:58, versus none in
  the 13,500 settled calls before 00:00.
- At 00:36, chain D v2.24 GEPA learning reported 29,662 completion tokens,
  including 26,907 reasoning tokens, against `max_tokens=16384`; stage
  settlement halted that ledger at 00:47.
- At 00:58:32, a chain D membase ALFWorld read reported 6,144 completion tokens
  above its bound; the shared membase ledger halted and stopped chain G too.
- Route probes at `/data/membase-20261105-ops/route-probe` on dl used the same
  puzzle prompts, temperature 0 and `max_tokens=1024`, retaining usage numbers
  only: at 01:15, effort-none alone yielded reasoning in 4/100 replies,
  thinking-disabled alone 0/100, and both fields 0/100; the `deepseek-flash`
  alias delivered 0/100 because of HTTP refusal.
- At 01:17, effort-none alone yielded reasoning in 11/800 replies and both
  fields 0/800; mean completion among all replies was 50.7 versus 45.0 tokens,
  respectively, as supplied by the operator.
- Further provider observations on 2026-11-06 between 01:44 and 01:56:
  northgate also refused requests with `max_tokens > 4096` with HTTP 400
  (`"expected a value <= 4096"`), under both request shapes. The operator
  reported about 3–4% refusals above 4096, with cap-specific estimates of about
  0.7% at 8192 and 3–4% at 16384 and 65536; exact counts and denominators were
  not supplied.
- Replies carrying reasoning reported about 25 more prompt tokens than
  ordinary replies on the same prompt. These are observations only, without
  an inferred provider mechanism or a change to request caps or guards.

Only main-v9's chain D route-B request adds `"thinking": {"type": "disabled"}`
alongside `"reasoning_effort": "none"`; all other body fields stay unchanged.
Earlier chain D data used `reasoning_effort` alone, and no earlier number is
relabelled as having used this new shape. These observations motivate a new
snapshot and attempt, not a change to historical protocols or scores, and do
not establish a method-effect improvement or a guarantee against reasoning.

The optional shape is explicit in the solver config, the main-v9 route pin and
`clients.solver.D`; both exact field sets are validated before client creation.
The main-v9 adapter retains the frozen receipt checks, resend behavior and
ledger bounds. Older configurations keep their exact client source pin,
request shape and identity; chain G's solver and all GLM roles are unchanged.
The observations, path inventory and local checks are recorded in
[V225-ROUTE-THINKING-20261106.json](V225-ROUTE-THINKING-20261106.json).
No external service, model, probe, smoke or chain is launched by this writer.

Decision, 2026-11-06: main-v9's S1 schedule stays first-call confirmation plus
three northgate length probes; no S1-e call is added. The tested
`v225_client.control_client` adapter, which drops both fields, stays unused in
production. This resolves the earlier scope question without a source-code or
call-schedule change.
