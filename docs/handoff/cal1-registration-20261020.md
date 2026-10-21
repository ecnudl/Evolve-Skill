# cal-1: calibration of the v3 gate's C1 on SearchQA — pre-registration (2026-10-20)

Status: registered before dispatch of the comparison round. Reviewed once by Codex (2026-10-20); the corrections it
required are incorporated (independent selection measurement, rule-shaped bridge arms, "C1 passage" as the endpoint,
C2 masks, null calibration, decision table). Scripts: `/data/coevo5-20261020-cal1-ops/cal1.py` (dispatch),
`cal1_analyse.py` (analyses), `run-cal1.sh` (launcher). Output root: `/data/coevo5-20261020-cal1/`. The completed v3
run `/data/coevo5-20261019-v3-run/` is read for integrity checks and for the archived training rollout only; nothing is
written under it. Code: the frozen v3 snapshot `/data/coevo5-20261019-v3-source-f` (the launch manifest's `verify_code`
runs at start); interpreter `/root/continual-alf-prep-20260928/env/bin/python`.

## Question

Does the registered C1 arithmetic of `fivebench-coevolution-v3` (`gate._benefit`: candidate lower-bound total minus
parent upper-bound total >= 1 item, and candidate strictly above every one of four irrelevant-text controls) pass a
prompt intervention whose benefit is known from an independent measurement? This is a calibration of **C1 passage** on
one benchmark. It does not validate the full acceptance path (C2/C3/C4', screen then confirm with different control
texts), and whichever way it comes out it does not identify the cause of the v3 null by itself (decision table below).

## Items, runs, dispatch

- Benchmark: SearchQA. Items: the 200 stage-1 training focal items of v3 (`data.training_items(pool, "searchqa",
  DATA_SEED=20261017)`), asserted equal to the item set of the v3 E-ds stage-1 screen parent arm. No test item is read.
- Pre-round (unit `cal1-pre/searchqa`): `parent:A` alone, 2 runs per item (400 cells). Eligibility for the prospective
  subsets = items with at least one non-pass run; frozen to `eligibility-pre.json` before the comparison round starts.
- Comparison round (unit `cal1/searchqa`): 11 arms x 200 items x 4 runs (`TRIGGER_RUNS["searchqa"]`) = 8,800 cells.
  All cells of a unit are shuffled by the protocol's seeded hash order and dispatched through the same recorder, scorer
  and decision table as v3 (16 workers, 12 deepseek slots, `temperature 0`, `max_tokens 32768`). Each cell is keyed by
  (unit, arm, item, run) and sends its own request; no response cache exists.
- Unknown outcomes: as registered (unknown = fail for a judged arm's L, = pass for the parent's/controls' H;
  `shared_unanswered` items leave every criterion; the infrastructure guard pauses the unit above 10% unknown cells of
  a parent or control arm). A paused unit is redone in a fresh attempt only after a recorded decision.
- Budget: own ledger `shared/ledger` with scopes `deepseek`, `deepseek:cal1`, cap 25,000,000 tokens (reservation
  enforced). Expected spend ~15M (smoke: 2,251 charged tokens per cell averaged over a parent, a five-seed and a control
  cell; most arms are near 1,350). The v3 ledger is untouched.

## Arms (rendered through the v3 `Skill` renderer; exact texts and SHA-256 in `arms.json`)

| arm | text | role |
|---|---|---|
| `parent:A` | E-ds initial Skill: `Skill(scaffold=True)` (five empty sections) | comparison parent |
| `parent:B` | identical text, separate arm | same-round noise floor; judged as a pseudo-candidate (null passage rate) |
| `ids-full` | I-ds initial Skill: `Skill.seeded(instructions)` (all five task-card seeds) | broad positive control (known SearchQA effect: test 331 vs 289 of 400; train preview net +17.75 of 200) |
| `seed-only` | scaffold + the SearchQA seed alone (`Skill(seeds=(("searchqa", seed),), scaffold=True)`) | isolates the other four sections |
| `seed-rule` | scaffold + Rule: "Answer with the minimal entity or value requested, not a full sentence: e.g., a name, a date, a title, a number." (verbatim seed sentence, 108 chars) | rule-shaped bridge, unvalidated positive-control candidate |
| `seed-rule3` | scaffold + Rule: the sentence above plus the seed's two other answer-form sentences (unit/granularity; one of several), verbatim, ~420 chars | rule-shaped bridge, learned-rule length |
| `cand` | scaffold + Rule `s1-r1`: the frozen E-ds s1-r1 text (passed C1 in v3 screen +7/4 and confirm +2; failed C2 −15/2) | the best learned rule, re-measured |
| `control:1..4` | scaffold + `PLACEBOS_SCREEN[0..3]` via `text_with` | the registered irrelevant-text controls |

## Pre-registered analyses (`cal1_analyse.py`, seed 20261020, 2,000 subset draws per size)

- **A1, primary — C1 passage on failure-enriched subsets.** For n in {6, 11, 20}, draw 2,000 subsets without
  replacement from an eligibility pool, the same subset for every judged arm, and compute the registered C1 of each
  judged arm (`ids-full`, `seed-only`, `seed-rule`, `seed-rule3`, `cand`, and `parent:B` as the null) against
  `parent:A` with the four controls. Pools, in order of standing: (i) archived v3 training rollout of the same empty
  parent, >= 1 failed run of 2, restricted to the check half (the pipeline's selection population, no new calls);
  (ii) the pre-round, >= 1 failed run of 2; (iii) diagnostics, deliberately coupled: `parent:A`'s own 0/4 items;
  `parent:B`'s 0/4 items. A pool smaller than n yields "insufficient_eligible". Report passage rate, the rate of
  `gain >= 1` alone, P(control blocks | gain >= 1), and passage under each of the six two-control pairs. Monte Carlo
  SE at a rate of 0.8 is ~0.009; this is sensitivity to panel composition conditional on this measured item bank.
- **A1 replay** — the registered C1 of every judged arm on each frozen v3 E-ds stage-1 trigger set (r1: 6, r2: 6, r3: 11,
  r4: 7, r5: 4 items), with their original provenance.
- **A2 — noise floor:** `parent:B` vs `parent:A` on all 200 items: discordant-item rate, net difference, sign test,
  paired mean with t and item-bootstrap 95% CIs, and whether |net| exceeds the registered C2 tolerance (7); a
  diagnostic at 4 runs, not a calibration of registered C2's error rate.
- **A3 — candidates:** every candidate vs `parent:A` on all 200 items (paired mean, CIs, up/down/tie). For `cand`:
  the registered C1 on its frozen 6-item trigger set; C2 on the items outside its trigger set **and** its 8 proposal
  evidence items, both at 4 runs and at the registered schedule (run indices 0-1 on non-trigger items), tolerance 7.
- **A4 — observed all-arm failures:** items on which every arm scores 0/4 (reported as observed outcomes, not as
  intrinsically unsolvable items), and `parent:A` 0/4 items unmoved by every arm.
- **A5 — controls:** each control vs `parent:A` on all items.
- **A6 — heterogeneity:** histogram of per-item differences for every candidate.
- Also reported per arm: totals (L, H), unknown runs, truncated runs.

## Decision table (pre-registered; A1 on pool (i), n = 11, arm `ids-full`, with `seed-rule3` as the rule-shaped reading)

| result | supported conclusion and next action |
|---|---|
| the positive effect reproduces (A3 `ids-full` CI above 0) and C1 passage >= 80% | C1 detects this intervention under this selection policy. Keep the threshold provisionally; the next work goes to proposal relevance (condition-specific rules) and panel power, not to the threshold. |
| the effect reproduces on the intended trigger population and passage < 50% | C1 has poor sensitivity here. Identify which registered component (panel size, control competition, the one-item floor) explains it before replacing the threshold. |
| the positive effect does not reproduce | the positive control failed to qualify contemporaneously; no instrument conclusion. |
| excessive null passage (`parent:B` >= 20% at n = 11), an incomplete dispatch, or insufficient eligible items | no favourable validity conclusion, whatever the positive controls show. |

Between 50% and 80%: inconclusive; report A3/A5 and the bridge arms and decide with the owner. Detecting the broad seed
does not exonerate C1 for narrow effects; the bridge arms are the only rule-shaped evidence and are themselves unvalidated.

## What this experiment is not

Not a Skill-evolution run, not evidence of learned generalisation, not a test of C2/C3/C4' or of confirm, and not a
test-set measurement. The registered v3 protocol, scores and artifacts are unchanged.

## Frozen arm texts (written before dispatch to `/data/coevo5-20261020-cal1/arms-cal1-searchqa.json`)

| arm | bytes | SHA-256 |
|---|---:|---|
| `parent:A` | 593 | 717618d4591180a5b06aa986a9e8fe0dd8a930c1f4e10e9eb083e6113734986a |
| `parent:B` | 593 | 717618d4591180a5b06aa986a9e8fe0dd8a930c1f4e10e9eb083e6113734986a |
| `ids-full` | 12681 | cd3944ac26a26123620241357dcbfd673bbe930c099bbec18d8becba1898677d |
| `seed-only` | 2442 | f1c48a6d2f0ad8b4ebb44723bbd09f40cbff14d68400ac7f4f163f88709dea24 |
| `seed-rule` | 709 | 95e4e62b29ba18d1043208444c37bc9ab63202a0eb6b8df056ae8d58626e7d5d |
| `seed-rule3` | 1016 | 96da1c1baf685b132faec3e9674cab948c1ca05becbf9b2c566702c7ed589cf0 |
| `cand` | 885 | e2505ba85682a16ff09a0be062cb9b5ae479a8f9dbf27192304c2130448be311 |
| `control:1` | 779 | df68a35c045defa41a501aeeff5a592ffbde371153683b5ab2fc0c7f64a54daa |
| `control:2` | 788 | 65a4c96a12345a8221ad0a68fe603742b66071527e1adc6fff77fde1db907203 |
| `control:3` | 779 | c245e31eae19fa1ca02fb4e70534e884910cad046bbb5b892cc76d9240c1544e |
| `control:4` | 768 | f275ee1ecb6f1d2d0a016f0a072ab2d08df46595b84132de218e01bf9f05b07b |

## Dispatch log

- 2026-10-20 15:59:30 pre-round `cal1-pre/searchqa` launched; 16:03:44 complete: 400 cells, parent:A 135/200 (2 runs),
  1 truncated run, 0 unknown; 74 items with >= 1 failed run frozen in `eligibility-pre.json`; 537,761 tokens.
- 2026-10-20 16:04:19 first main launch crashed before any call (write-once `arms.json` collision with the pre-round);
  renamed per unit; 16:07:17 `cal1/searchqa` launched: 8,800 cells.
- 2026-10-20 18:13:08 `cal1/searchqa` **paused on the registered 25,000,000-token deepseek cap** (`PAUSED budget:
  model_call_exception:BudgetStop`; ledger settled 24,868,834) after 7,205 of 8,800 cells (7,189 with a verdict:
  4,901 pass, 2,268 fail, 5 noncompletion, 15 unknown `http_503`; 16 cells interrupted without a verdict). Cells are
  spread evenly over the arms (634-679 each), so no arm is complete. Real cost ~3,400 tokens per cell, twice the
  smoke estimate behind the 15M pre-launch estimate. **Dispatch incomplete** (decision-table row 4) until resumed.
- 2026-10-20 18:30 resume prepared and dry-run verified (`cal1_resume.py`, `run-cal1-resume.sh` in the ops
  directory): the same unit, arms, items, runs and identity continue in `attempt-2` as the unit runner requires
  (owner's recorded decision in `attempt-1/recovery.json`); the 7,189 verdict cells are kept unchanged, the 1,611
  cells without a verdict run now (parent:A 161, parent:B 134, ids-full 143, seed-only 167, seed-rule 142,
  seed-rule3 133, cand 168, control:1 123, control:2 155, control:3 142, control:4 143); the cap is raised to
  35,000,000 through the ledger's `raise_cap` (**a recorded deviation**: the pre-launch cost estimate was wrong, the
  design is unchanged). The 15 `http_503` unknowns are kept as unknowns (as the registered pipeline would).
  `cal1_analyse.py` now reads every attempt directory (a cell without a verdict is skipped; a later attempt's verdict
  overrides). The launch itself was refused by the session's permission classifier and awaits the owner:
  `tmux new-session -d -s cal1-resume 'bash -i /data/coevo5-20261020-cal1-ops/run-cal1-resume.sh /data/coevo5-20261020-cal1 --raise-cap 35000000 --workers 12 > /data/coevo5-20261020-cal1-ops/resume.log 2>&1'`.
- 2026-10-20 19:06:36 resume launched by the owner (tmux `cal1-resume`); 19:56:50 **complete**: attempt-2 ran the
  1,611 pending cells; unit `cal1/searchqa` complete (8,800 cells; 21 unknown runs, all transport; 0 excluded);
  ledger settled 27,481,897 tokens (cap in force 35,000,000; declared 25,000,000). Resume cost 2,613,063 tokens
  (1,622 per cell).
- 2026-10-20 23:43 pre-registered analysis run (`cal1_analyse.py`, read-only; `analysis.json` 40 KB in the output
  root). Results (A1 on pool (i) = archived v3 train check half, 27 eligible; registered endpoint n = 11, `ids-full`):

  | analysis | result |
  |---|---|
  | A3 positive effect, 200 items, 4 runs | `ids-full` mean +0.0938 [0.0505, 0.137], 48 up / 13 down / 139 tie; `seed-only` +0.0887 [0.051, 0.1265], 47/10/143 |
  | A3 rule-shaped bridges | `seed-rule` +0.0037 [−0.031, 0.039] (26/24/150); `seed-rule3` −0.030 [−0.066, +0.006] (26/38/136); `cand` −0.026 [−0.072, +0.020] (37/44/119) |
  | A1 C1 passage, pool (i), n = 11 | `ids-full` **75.8%**, `seed-only` 63.2%, `seed-rule` 0%, `seed-rule3` 0%, `cand` 7.7%, `parent:B` (null) **0%**; control blocks given gain ok: 0% |
  | A1 at n = 6 / n = 20 | `ids-full` 47.9% / 99.0%; `seed-only` 39.9% / 94.4% |
  | A1 other pools, n = 11 | pre-round pool (74): `ids-full` 94.1%, null 0.75%; parent:A 0-of-4 pool (45): 93.3%, null 0.55%; archived all-failures pool (55): 54.3%, null 0.1% |
  | A1 replay on the frozen v3 trigger sets | `ids-full` passes C1 on s1-r1 (n 6), s1-r2 (6), s1-r3 (11), s1-r5 (4), fails s1-r4 (7, gain −3/4); `cand` passes only s1-r3 (gain 1); `parent:B` passes none |
  | A2 noise floor (parent:A vs parent:B, same text) | mean +0.0075 [−0.0125, 0.0275]; 22 up / 18 down / 160 tie; 20% discordant at 4 runs; sd of the per-item difference 0.144 |
  | A5 placebo controls vs parent:A | `control:1` −0.035 [−0.063, −0.007]; `control:2` **+0.036 [+0.006, +0.066]** (39/16, sign p 0.003); `control:3` **−0.098 [−0.136, −0.059]** (16/58); `control:4` +0.003 [−0.028, +0.033] |
  | A3 `cand` under the registered criteria | trigger n 6: gain 1/2 (C1 fails), margin 1; C2 rest 186 items: −7 at the registered 2-run schedule (within tolerance 7), −17/2 at 4 runs (outside) |
  | A4 | 25 of 200 items score 0 in every arm on every run; parent:A fails all 4 runs on 45 items, 25 of them unmoved by any arm |

  **Decision-table reading**: the positive effect reproduces (row 1 condition) and the null passage is 0% (row 4 not
  triggered; dispatch complete after the resume); passage at the registered n = 11 is 75.8%, i.e. **between 50% and
  80%: inconclusive by the pre-registered table**, close to the upper bound. The rule-shaped bridges carry no
  detectable effect at all, so nothing rule-sized was available to calibrate C1 on, and two of the four irrelevant
  control texts move the score significantly (−9.8 and +3.6 points per 100 items).
