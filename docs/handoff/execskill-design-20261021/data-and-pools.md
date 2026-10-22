# Data and pools: fresh, never-used training batches per benchmark for route B

Status: COMPLETE (2026-10-21, read-only subagent). No repository file and nothing on dl was modified. Every dl read
used `python3 -I -B` (no bytecode writes) and printed counts / set relations only. No test file was opened, and no test
id or item content was printed. The scripts I ran are in
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/understand-scripts/`
(pools.py, scan.py, scan4.py, scan5.py, scan6.py, scan7.py, scan8.py, alfscan.py). They can be re-run read-only with
`ssh ... 'cd / && python3 -I -B -' < script`.

**Bottom line.**
- Inside the five registered training pools almost nothing is fresh. Every v1 and v3 training execution ran all of
  OfficeQA (74), all of SpreadsheetBench (91 qualified of 120) and all of ALFWorld (57).
- SearchQA has 45 of 600 pool items and LiveMath 141 of 283 that no coevo5 chain, cal-1, smoke run or 10/20–21
  feasibility study executed. Even these were inputs to the v1 SkillOpt/GEPA baselines and to older learners, so
  "never used" holds only on the method side.
- Real fresh supply exists only outside the pools, and every source below needs an owner decision:
  - SearchQA: 11,380 HF `validation` rows never sampled. The sealed blocks C and D hold another 2,000.
  - ALFWorld: 3,514 `json_2.1.1/train` games outside the pool, plus 122 `valid_seen` games.
  - LiveMath: 200 evaluation-block items. e01 was read by an evaluation on 10/14 and e02 in part, so 150 are unread.
- No fresh items exist for OfficeQA or SpreadsheetBench:
  - OfficeQA upstream holds 246 items, and all 246 are in the split.
  - SpreadsheetBench Verified 400 is fully placed. The 912-task original release is not on dl.
- Conclusion: a fresh run batch plus a fresh acceptance batch at every step is possible at scale only for SearchQA and
  ALFWorld. LiveMath supports one or two small steps. OfficeQA and SpreadsheetBench support none. These two are the
  first two benches in design-v0's order.

## 1. Scope and files read

Repository files (verified by reading):

| file | lines | what was read |
|---|---:|---|
| skillopt/coevo5/data.py | 358 | all |
| skillopt/coevo5/protocol.py | 357 | L1-30, L54-86, grep of every constant |
| docs/handoff/coevo5-registration-v6-20261017.md | 1120 | §2 L80-128, plus L771, L802, L849 by grep |
| scripts/make_searchqa_fresh_sample.py | 145 | all |
| data/README.md | 237 | all |
| data/{searchqa,officeqa,livemathematicianbench,spreadsheetbench}_id_split, data/alfworld_path_split | n/a | split_manifest.json and train/val items.json (counts and keys); **test/items.json not opened** |
| data/searchqa_fresh_20261012/sample_manifest.json and the sub-block items.json files | n/a | ids only |
| docs/handoff/prompt-chain-confirmation-blocks-20261013.json | 274 | structure |
| docs/handoff/cal1-registration-20261020.md | 152 | L1-80 |
| scripts/make_extension_study.py | 322 | L1-50, L88-128, grep |
| docs/results-and-lessons.md | 666 | grep: L144, L204, L217, L225 |
| docs/current-workflow.md | 552 | grep: L50, L56 |
| docs/project-status.md | 492 | L116-124, L336-342 |
| docs/handoff/active-evidence-learn-from-b-design-20261012.md | 313 | grep: L26-30 |
| docs/handoff/feasibility-20261021/E5/report.md | 949 | L110-130, L623-660; E5/critic-result.json (missing #7) |
| docs/handoff/feasibility-20261021/{D6,D14,D10}/report.md | 865 / 310 / 786 | grep (D6 L215, L409; D14 L87) |
| docs/handoff/feasibility-20261021/D5/critic-result.json | n/a | missing #4 |
| docs/handoff/direction-review-20261021/critiques/{paper-feasibility,stoploss-evidence,transfer-evidence,paper-evidence}.md, synthesis.md, docs/handoff/direction-recommendation-20261021.md | 543 / 369 / ... | grep |
| skillopt/envs/officeqa/tool_runtime.py | 552 | grep L70-71, L201, L316 |

Files on dl, all read-only:
- Run manifests: /data/coevo5-20261019-v3-run-manifest.json (v3) and /data/coevo5-20261017-run-manifest.json (v1).
- /root/fivebench-split-20261005-v2/split_manifest.json (ids and counts only).
- /root/extension-20261013/{officeqa,livemath}/layout.json.
- SpreadsheetBench qualification records:
  - /data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json (v3)
  - /data/coevo5-20261017-sheet-train-e/sheet/qualification.json (v1)
- /root/officeqa-upstream-20261013 (only the uid column was counted; README; directory names).
- /root/livemath-upstream-20261013/data (directory names only). **The `qa_*_final.json` files were not opened**,
  because the hard rule forbids "final" in a file name.
- /root/continual-alf-prep-20260928/{data/json_2.1.1 (file counts; valid_unseen counted, never listed), items.json, train-items.json, prepare_alf_assets.py, qualify_alfworld_v2.py}.
- /root/continual-spreadsheet-20260928-a/{source/source_snapshot.json, source/UPSTREAM_README.md, prepared/preparation_summary.json}.
- Id scans over /data/feasibility, /data/coevo5-20261017-run, /data/coevo5-20261019-v3-run, /data/coevo5-20261020-cal1,
  /data/coevo5-20261017-pre, /data/coevo5-20261019-{v2,v3}-pre and /root/fivebench-g-2026101{2,3,4}-*. Each scan
  skipped every path containing test/final/holdout/held_out/reserve/evaluation/.

Mac: the SearchQA HF cache at `~/.cache/huggingface/datasets/lucadiliello___searchqa/default/0.0.0/c1a97906.../searchqa-{train,validation}.arrow`, key column only.

## 2. Facts

**F1. Protocol constants** (verified in skillopt/coevo5/protocol.py):
- L10: `VERSION = "fivebench-coevolution-v3"`.
- L13: `ORDER = ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")`.
- L56: `DATA_SEED = 20261017`.
- L60-61: `TRAIN_ROLLOUT = {"searchqa": (200, 2), "officeqa": (74, 2), "livemath": (100, 2), "spreadsheetbench": (120, 1), "alfworld": (57, 2)}`. The SpreadsheetBench 120 is nominal: the registered draw is "every qualified item" (L58-59).
- L62: `GATE_RUNS = {"searchqa": 2, "officeqa": 2, "livemath": 2, "spreadsheetbench": 1, "alfworld": 1}`.
- L63-64: `POOLS = {"searchqa": (400, 200), "officeqa": (50, 24), "livemath": (155, 128), "spreadsheetbench": (80, 40), "alfworld": (39, 18)}  # (historical train, historical val)`.
- L65: `TEST_SIZES = {"searchqa": 400, "officeqa": 172, "livemath": 125, "spreadsheetbench": 279, "alfworld": 134}`.
- L66: `REGRESSION_ITEMS = 60`. L68: `SHEET_MIN_QUALIFIED = 30`.
- No data constant carries a "v2" or "v3" marker, so v1, v2 and v3 used identical draws. This is verified for the
  regression panels in F6.

**F2. Pools are the historical train and val parts, with labels kept.**
- `pool()` (data.py:155-166) loads both parts through `_load`. It asserts the sizes equal `POOLS[benchmark]`
  (L163-164) and that the parts are disjoint (L165).
- The registration table is at coevo5-registration-v6-20261017.md:82-88.
- L90: "抽样都用固定种子，写进清单。回归面板在开跑前抽一次，所有链共用" (every draw uses a fixed seed and is written into the manifest; the regression panels are drawn once before launch and shared by all chains).

**F3. Dev-machine paths are pinned.**
- `DEV_MACHINE` (data.py:45-64) maps:
  - train: SearchQA `/root/continual-searchqa-long-20261001-study/data/panel.json`; OfficeQA and LiveMath `/root/extension-20261013/{b}/dev_panel.json`; SpreadsheetBench `/root/continual-spreadsheet-long-20261001-study/baseline/data/panel.json`; ALFWorld `/root/continual-alfworld-long-20261001-study/data/panel.json`.
  - val: SearchQA `/root/fivebench-split-20261005-source/data/searchqa_split/val/items.json`; OfficeQA and LiveMath `/root/extension-20261013/{b}/val_panel.json`; SpreadsheetBench `/root/continual-spreadsheet-20260928-a/prepared/panels/skill_confirmation.json`; ALFWorld `/root/fivebench-split-20261005-source/data/alfworld_path_split/val/items.json`.
  - `alfworld_data`: `/root/continual-alf-prep-20260928/data`. `upstream`: `/root/officeqa-upstream-20261013` and `/root/livemath-upstream-20261013`.
- `pin()` demands these exact key sets (data.py:79-81) and records a SHA-256 for every file (L82).
- The v3 manifest holds the same paths and 16 hashes (dl, verified).

**F4. Seeded draws.**
- `ranked(items, seed, tag)` sorts by `sha256(json.dumps([seed, tag, item["task_id"]]))` (data.py:173-176).
- `training_items` uses the tag `"train:" + benchmark` and takes the first `TRAIN_ROLLOUT[b][0]` items (for
  SpreadsheetBench, every qualified item) (L188-196).
- `regression_items` uses the tag `"regression:" + benchmark` and takes the first `min(60, len(items))`. It returns
  none for `ORDER[-1]` (ALFWorld) and none for SpreadsheetBench below 30 qualified items (L199-205).
- The two tags give independent orders over the same pool, so the two panels overlap by chance (F6).

**F5. SpreadsheetBench qualification** (registration §2.1 L92-111; `qualified()` data.py:179-185).
- Each reference workbook is scored as an answer twice by `qualified_lo_recalc_v7_v1`, with 0 model calls.
- The v3 and v1 qualification files are identical (dl, verified): 91 of 120 qualified (58 train-part, 33 val-part).
- 29 are excluded: `reference_recalculation_failed` 22, `read_view_unverifiable` 6, `reference_cache_mismatch` 1.

**F6. Re-derivation on dl** (pools.py, verified).
- The regression panels re-derived with `ranked(..., 20261017, "regression:<b>")` equal both the v3 and the v1
  manifest lists for all five benches.
- Training (focal) draws:

| bench | focal draw | train-part / val-part | focal ∪ regression | overlap |
|---|---|---|---:|---|
| SearchQA | 200 | 127 / 73 | 231 | 29 |
| LiveMath | 100 | 57 / 43 | 142 | 18 |
| OfficeQA | all 74 | | 74 | regression ⊂ focal |
| SpreadsheetBench | all 91 qualified | | 91 | regression ⊂ focal |
| ALFWorld | all 57 | | 57 | no regression panel |

**F7. Use in coevo5 runs on dl** (scan.py, ids only, verified).
- For SearchQA and LiveMath, only focal ∪ regression ids appear in:
  - v1 `/data/coevo5-20261017-run/{E-glm,I-glm}`;
  - v3 `/data/coevo5-20261019-v3-run/{E-ds,I-ds}`;
  - cal-1 `/data/coevo5-20261020-cal1` (the 200 focal items, also registered at cal1-registration-20261020.md:21);
  - the v1, v2 and v3 pre/smoke directories.
- The v1 baselines SkillOpt-glm and GEPA-glm received the whole pool as input: all 600 SearchQA ids in
  `s1/learning/attempt-1/learning/panel.json` and all 283 LiveMath ids in `s3/.../panel.json`. This matches
  registration L121: "基线在第 k 步只用第 k 个 bench 的历史 train（学习）与历史 val（挑选）" (at step k the baselines use only bench k's historical train for learning and its historical val for selection).
- Inferred, not verified: that the baselines actually solved every one of those items.

**F8. SearchQA feasibility runs that executed pool items outside focal ∪ regression** (scan4.py; "executed" means the
id appears in a cell-record file; verified).

| study | items | notes |
|---|---:|---|
| D1-v2 pilot | 130 | `/data/feasibility/D1/v2/pilot/d1v2pilot/searchqa/attempt-1/cells`, 1,560 cells; 92 train-part |
| E5-P1 | 180 | `/data/feasibility/E5/v2/pilot/run1/cells`; drawn as 600 − 200 − 60 − 130 = 239, first 180 by tag `e5p1-fresh:searchqa` (E5/report.md:628-636); 116 train-part |
| E8 | 100 | 91 outside focal ∪ regression plus 9 regression-only; overlaps D1 by 34 and E5 by 43 |
| E7 | 1 | overlaps D1 |

- The union outside focal ∪ regression is 324. That leaves **45 SearchQA pool items never executed by any coevo5,
  cal-1 or feasibility run** (35 historical-train, 10 historical-val).
- 8 of those 45 were generation sources in E10 (E10 drew 102 generated items from 68 real pool items, 61 of them
  outside focal ∪ regression; scan8.py). That leaves **37 untouched by any solver or generator** (29 train, 8 val).
- The E5 critic's "Never-used training items are down to 59 of 600 (200 focal, 31 regression, 130 D1-v2, 180 E5-P1)"
  (E5/critic-result.json missing #7) does not count E8.
- The 35 train-part items also appear in the panels of the 10/12 SearchQA learners
  `/root/fivebench-g-20261012-searchqa-active-{le,lh,lz}2x` (scan7.py; listed there, execution not verified).

**F9. LiveMath pool usage.**
- No feasibility study executed LiveMath pool items outside focal ∪ regression (scan6.py). D10 only lists 24 more, in
  `upstream-ids/`.
- That leaves 141 of 283 never executed by any coevo5, cal-1 or feasibility run (74 train-part, 67 val-part).
- They are not fresh in the absolute sense:
  - the 10/13–14 extension-study learners used "训练池155题每阶段取128、验证128题" (128 of the 155 train items per stage, plus all 128 val items) (results-and-lessons.md:217);
  - the v1 baselines received all 283 (F7).

**F10. LiveMath upstream.**
- The layout builder assigns every upstream record of `data/*/qa_*_final.json` to test, eval, val or train
  (make_extension_study.py:91-127; docstring L21-25: "608 items"). Layout counts: train 155, val 128, eval 200, test 125.
- The upstream directory on dl has 8 months, 202511..202606; no newer month was downloaded.
- The 200 eval items are the 10/13 headroom pilot's draw (months 2026-03..06), in 8 blocks `block_e01..e08` of 25
  (make_extension_study.py:57, L176-182). Layout exposure: "solved once by four fixed Skill texts in the headroom pilot
  of 2026-10-13; no learner has seen them".
- Later use:
  - on 10/14 the evaluation of block l1-e02 was interrupted after 19 calls (results-and-lessons.md:204);
  - "LiveMath 评测（l1 剩余 7 块、l2 8 块）…没开始；由负责人定" (the remaining LiveMath evaluation, 7 l1 blocks and 8 l2 blocks, has not started and awaits the owner) (project-status.md:340);
  - so e01 was evaluated (inferred) and e02 partly; e03..e08 (150 items) were read by no evaluation. This rests on
    the docs; separately, no eval-block id appears anywhere under /data/feasibility or the coevo5 directories on dl
    (verified).
- project-status.md:119 lists "LiveMath 评测块" (the LiveMath evaluation blocks) among the sealed, unread hold-outs.

**F11. OfficeQA upstream.**
- `officeqa_full.csv` has 246 rows (246 unique uids), and every uid is in the layout's train, val or test part: 0 are
  outside (dl, uid column only, verified).
- `officeqa_pro.csv` has 133 uids, all inside the same 246.
- Layout exposure:
  - `eval`: "none: every item is in the split";
  - `train_val`: "solved once by four fixed Skill texts in the headroom pilot of 2026-10-13; the paper's checkpoint Skill was learned and selected on them".
- The split is not document-disjoint: train and test share 40 bulletins (current-workflow.md:56).
- Corpus:
  - 697 issues according to the upstream README; dl has 700 files in `treasury_bulletins_parsed/jsons`;
  - **dl has no `treasury_bulletins_parsed/transformed`** (the Mac copy has 698 files there);
  - data.py:265 passes `root/"treasury_bulletins_parsed"/"transformed"` to `build_oracle_parsed_pages_context`. tool_runtime.py:70-71 falls back to the directory itself when `transformed/` is missing. I did not trace this further.

**F12. SpreadsheetBench upstream on dl.**
- Source: `/root/continual-spreadsheet-20260928-a/source/spreadsheetbench_verified_400.tar.gz`, revision
  `ab0b742b0fc95b946f212d80ac7771b5531272e4`.
- Preparation summary: `source_tasks` 400, `split_policy` "original_80_40_280_unchanged", 1 unresolved test task
  (hence 279).
- The upstream README names the original release `all_data_912.tar.gz` (912 instructions, 2,729 test cases). It is
  not on dl.
- Runtime (v3 manifest):
  - solver image `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd`, timeout 300 s, 4,096 MB, 1 cpu;
  - recalculation image `sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790`, timeout 120 s;
  - engine qualification `/data/coevo5-20261019-v3-sheet-q23-f/qualification.json`;
  - scorer `qualified_lo_recalc_v7_v1`.

**F13. ALFWorld on dl** (`/root/continual-alf-prep-20260928/data/json_2.1.1`, counted).
- Game counts:

| folder | task folders | games |
|---|---:|---:|
| train | 2,435 | 3,553 |
| valid_seen | | 140 |
| valid_unseen | | 134 |
| valid_train | | 200 |

- The pool is 39 games from `train` (ids train:0000..train:0038) and 18 from `valid_seen`
  (data/alfworld_path_split/{train,val}/items.json).
- The split comes from the SkillOpt paper release (`source_split_files` split_train/val/test.json). No selection script
  is in the repository.
- `TEST_SIZES` 134 equals the size of `valid_unseen`, so the test set is very probably `valid_unseen`. This is
  inferred: the test panel was not opened, and D6/report.md:409 says the overlap is unknown and must be checked by code
  with test access.
- No study on dl used a game outside the 57: D3, D4, D14 and the v1 baselines reference only these (verified by id and
  path scans).
- Runtime: `alfworld_split` "train", `max_steps` 50, `timeout_seconds` 60, `seed` 42.
- Cost: 28.5k tokens per E-ds episode and 105.7k per I-ds (task-card) episode (D14/report.md:87).

**F14. SearchQA sources** (verified on the Mac HF cache, key column only, and against the dl split manifest ids).
- Revision `c1a979068ba118d85467179b704031d113d689cc` has 117,384 train rows and 16,980 validation rows.
- fivebench-split-v2 parts for SearchQA: train 400, val 200, test 400, reserve 1000.
- The native train 400 lie in HF train. The native val 200, the canonical test 400, the reserve 1,000 and the fresh
  sample 4,000 all lie in HF validation.
- So **11,380 HF validation rows were never sampled** by any native part or by the fresh sample (this count is before
  normalized-question dedupe; the 10/12 draw found 0 duplicates in 4,447 rows). Another 116,984 HF train rows lie outside
  the native parts.

**F15. The SearchQA fresh sample** (scripts/make_searchqa_fresh_sample.py; data/searchqa_fresh_20261012/sample_manifest.json).
- seed "searchqa-fresh-20261012", `source_rows` 16,980, `native_items_excluded` 2,000, skipped `native_id` 447,
  duplicates 0, 4 blocks of 1,000.
- The order is `random.Random(seed).shuffle(sorted keys)` (L61-62), so extending `--count` keeps the first 4,000
  unchanged.
- Block A was used by the 10/12 study: the A1/A2, A01..A10 and Q01..Q40 sub-blocks all fall in block A positions 1-1000
  (verified by id).
- Block B is fully used: R01..R10 are positions 1-250 and S01..S30 are 251-1000 (verified; the `source` field of
  prompt-chain-confirmation-blocks-20261013.json says the same).
- Blocks C and D "stay on the operator's machine, unread, for the one-time hold-out read"
  (active-evidence-learn-from-b-design-20261012.md:29; also current-workflow.md:50, results-and-lessons.md:225,
  project-status.md:119).
- cal-1 used the 200 focal pool items, not fresh blocks (cal1-registration-20261020.md:21).

**F16. New SearchQA blocks need approval.** The 10/21 reviews say a new block needs owner approval and an id-level
exclusion of blocks A–D, the 600-item pool and the 400-item test. Because that exclusion reads test ids outside
evaluation, it must be registered before use (critiques/paper-feasibility.md:190; critiques/stoploss-evidence.md:325-332).

**F17. Earlier MDE estimates** (cited, not recomputed by me):
- Test panels at 1 run: SearchQA 4–5, OfficeQA 6.6–7.7, LiveMath 10–11, SpreadsheetBench 7–7.7, ALFWorld 9–10 points
  (D5/critic-result.json missing #4: "TEST_SIZES 400 / 172 / 125 / 279 / 134, 1 run").
- At 2 runs: 3.7 / 6.3 / 7.3 / 6.5 / 8.0 (E5/critic-result.json refuted #4, with about 177 judgeable SpreadsheetBench items).
- With Holm correction: SearchQA 4.6–7.3, OfficeQA 8.2–9.6, the others 11.6–12.9 (D11 critic, quoted in critiques/paper-evidence.md).
- Run noise varies 2–3x between time windows (D11 critic, quoted in critiques/transfer-evidence.md).

**F18. Cost anchors.**
- SearchQA: about 2,251 charged tokens per cell averaged over a parent, a five-seed and a control cell; most arms are
  near 1,350 (cal1-registration-20261020.md:33).
- ALFWorld: see F13.

## 3. Interfaces an implementer would call or must replace

Signatures are quoted from skillopt/coevo5/data.py. `require(cond, msg)` comes from `skillopt.continual_eval.core`;
I did not read which exception class it raises.

- `pin(config) -> {"paths": deepcopy(config), "sha256": {abs_path: hex}}` (L76-82).
  - Refuses with "Invalid data configuration" unless the key sets match `DEV_MACHINE` exactly.
  - Hashes the bytes of every input, including the split manifest and the test panels, without parsing them.
- `pool(pinned, benchmark) -> list[{"benchmark", "task_id", "family_id", "part", "public", "private"}]` (L155-166).
  - Train items come first, then val.
  - Refuses an unknown bench, a hash mismatch, a test id, a partition label other than development/skill_confirmation
    (`PARTITION` L38), a panel that differs from its pinned part, or a size other than `POOLS`.
- `ranked(items, seed, tag) -> list`: pure; needs only `item["task_id"]` (L173-176).
- `qualified(items, qualification) -> list`: filters SpreadsheetBench by `qualification["qualified"]` (L179-185).
- `training_items(items, benchmark, seed, size=None) -> list` sorted by task_id (L188-196). Raises "Pool smaller than
  the registered draw".
- `regression_items(items, benchmark, seed) -> list` of at most 60, sorted by task_id (L199-205).
- `test_ids(pinned, benchmark) -> frozenset` of ids only (L114-117). `_refuse_tests` (L120-124) checks only the split's
  `"test"` part and `partition == "final"`.
- `sheet_tolerances(qualified_count) -> (t_k, t_b) | None` (L208-228). Loads docs/handoff/coevo5_power_sim_v2.py by path.
- `TestAccess(unit)` (L232-239) and `test_panel(pinned, benchmark, *, access) -> (tasks, report)` (L332-358) are for
  the evaluation step only. OfficeQA and LiveMath render from upstream after `_proof` (L314-329) shows the renderer
  reproduces the frozen training panels.
- `datasets.import_alfworld(path, data_root=..., partition=..., revision=..., family_map=...)` (called at data.py:140-142)
  is the loader a fresh ALFWorld games file would go through.
- `scripts/make_searchqa_fresh_sample.build(dataset, native_dir, output, *, count, blocks, seed, dataset_name, revision) -> (record, chosen)` (L39-101).
  - Writes `block_<x>/items.json` and `sample_manifest.json`.
  - Refuses an existing directory (L46-47) and any output in the repository outside `data/` or named `*_id_split`
    (L42-45).
  - `main()` requires the offline HF cache (L125-133).
- `scripts/make_extension_study.layout_livemath(upstream, id_split, seed, *, val=128)` (L91-127) and `data(...)`
  (L157-200) build LiveMath parts and evaluation blocks.

## 4. Reusable unchanged vs. must be generalized

**Reusable unchanged:**
- `ranked()`: a pure, input-order-independent seeded order.
- `_part_ids` / `test_ids` / `_refuse_tests`: the test firewall for pool items.
- `pool()`: for the leftover SearchQA (45 or 37) and LiveMath (141) items, if route B uses them.
- `qualified()`, the 91-item qualification record, and the frozen scorer, images and engine qualification for
  SpreadsheetBench, if pool items are reused.
- The `pin()` / `_checked()` hashing pattern.
- `TestAccess` / `test_panel`: for the per-step test readout, since the test sets are unchanged.
- The exclusion and dedupe logic and the deterministic order of `make_searchqa_fresh_sample.py`, to extend past 4,000.

**Must be generalized, and why:**
1. **`DEV_MACHINE` and `pin()`** (data.py:45-64, 79-81) fix exact key sets. They have no slot for fresh-batch sources: a
   new SearchQA block, an ALFWorld game list, the LiveMath evaluation blocks, or the SpreadsheetBench 912 set. A new
   protocol version needs extra keys and hashes.
2. **The test firewall knows only the split's `test` part.** SearchQA's 1,000 `reserve` ids come from the same HF
   validation split as the test set, and the reserve is sealed. `_refuse_tests` does not refuse them, and it does not
   know blocks C/D either.
   - A fresh reader drawing from HF validation must exclude test ∪ reserve ∪ blocks A–D ∪ the pool by id.
   - That reads sealed ids outside evaluation, so it needs registration (F16).
3. **`training_items()` assumes one fixed seeded draw per bench, identical for every chain.** Route B needs per-step
   disjoint slices: run_k, then accept_k, each used once.
   - Implement this as one seeded order per bench over the fresh supply, cut into consecutive slices, with a ledger of
     consumed ids written before dispatch.
   - Independent tags overlap by chance (29 / 18 / 60 items in F6).
4. **`TRAIN_ROLLOUT`, `GATE_RUNS` and `REGRESSION_ITEMS`** bake in v3's per-bench sizes and run counts. Route B needs
   (n_run, n_accept, runs) per bench per step, plus a stop rule for when the fresh supply is exhausted.
5. **`regression_items` / v3 regression panels**: design-v0 replaces them by generated self-test sets of earlier benches.
   If real regression panels are kept, they must be disjoint from every acceptance batch.
6. **`pool()`'s `POOLS` size assertion and `_load`'s partition labels**: a fresh reader needs new partition labels or
   sources, and new id namespaces. ALFWorld pool ids are `train:0000..0038` and `val:0000..0017`, so new games must not
   reuse `train:NNNN`.
7. **ALFWorld fresh games** need:
   - an items file (`gamefile`, `id`, `task_type`), stratified by task type (the pool has 6 types);
   - a test-exclusion step by game path against the test panel, run with test access;
   - and possibly a zero-call qualification: the game loads, and perhaps the expert solves it within `max_steps` 50.
     I could not determine whether the pool games were qualified this way.
8. **SpreadsheetBench new sources** (all_data_912) would need a download, an id-overlap check against Verified 400, and
   the same two-scoring reference qualification. Its yield is unknown; Verified items qualified at 91/120.
9. **The LiveMath evaluation blocks** are an evaluation set (`check_evaluation_block`, current-workflow.md:56). Using them
   as training-side acceptance batches needs an owner release and a new protocol version.

## 5. Per-benchmark freshness table and MDE

"Method-side never used" means not executed by any coevo5 E/I chain, cal-1, smoke run or 10/20–21 feasibility study on
dl. "Absolute" also counts inputs to the v1 baselines and older learners.

| bench | pool (train+val) | burned by v1/v3 training and gates (focal ∪ regression) | burned by other method-side runs | method-side never used | absolute never used | fresh real supply outside the pools | max fresh batches, step 1 (run + accept) | step 2 |
|---|---|---|---|---|---|---|---|---|
| SearchQA | 400+200 = 600 | 231 (200 + 31 regression-only) | 324 more (D1-v2 130, E5-P1 180, E8 100, overlapping) | 45 (35 train, 10 val); 37 if E10 generation sources count | 0 (in v1 baseline and 10/12 learner panels) | HF validation: 11,380 never sampled (owner approval and registered exclusion needed). Sealed blocks C/D: 2,000 (owner). HF train: 116,984 (another source split) | pool only: 45 in total, e.g. 0 + 45 (accept MDE ≈ 12–15). New block: e.g. 200 + 1,000 (2.5–3.2) | new block: the same again; the supply allows about 9 such steps |
| OfficeQA | 50+24 = 74 | 74 (all; regression ⊂ focal) | headroom pilot 10/13, probes 10/15–16, D11, D12 | **0** | 0 | **none**: upstream full = 246 = 50+24+172, all placed; Pro 133 ⊂ full. Only the 172 test items remain (owner consent would consume the test set) | **0 fresh**. Reusing the 74 (not fresh): accept 74 gives 10.1–11.7; a 37/37 split gives 14.2–16.6 | 0 |
| LiveMath | 155+128 = 283 | 142 (100 + 42 regression-only) | none beyond focal ∪ regression | 141 (74 train, 67 val) | 0 (extension learners 10/13–14; v1 baselines) | eval blocks: 200, of which e01 read, e02 partly read (19 calls), e03–e08 = 150 unread (sealed hold-out; owner). Upstream months ≥ 202607: not downloaded | 141 only: 41 + 100 (11.2–12.3) or 70 + 71 (13.3–14.6). With e03–e08: 70 + 150 (9.1–10.0) | 141 only: nothing left. With 291 total: about 70 + 71 |
| SpreadsheetBench | 80+40 = 120 (91 qualified) | 91 (all qualified; regression ⊂ focal) | D3/D14 sheet pilots (within the 91; not traced per item) | **0** | 0 | **none**: Verified 400 = 80+40+280 (1 unresolved). all_data_912 has about 512 more tasks; not downloaded, not qualified, overlap unknown | **0 fresh**. Reusing the 91: 12.3–13.5; a 46/45 split: 17.2–19.0 | 0 |
| ALFWorld | 39+18 = 57 | 57 (all) | D3, D4, D14 used the same 57 | **0** | 0 | `json_2.1.1/train`: 3,514 games outside the pool. `valid_seen`: 122 outside the pool. `valid_unseen` (134) is presumably the test set: never use | e.g. 57 + 134 (9.0–10.0) or 57 + 200 (7.4–8.2). Supply is not binding; cost is | the same again |

Acceptance MDE (points, 1 run per item per arm) at other batch sizes:
- SearchQA: n=200: 5.7–7.1; 300: 4.6–5.8; 500: 3.6–4.5; 1,000: 2.5–3.2; 2,000: 1.8–2.2.
- OfficeQA: the 172 test items give 6.6–7.7.
- LiveMath: n=200: 7.9–8.7.
- SpreadsheetBench: a hypothetical 200 fresh qualified items would give 8.3–9.1.
- ALFWorld: n=300: 6.0–6.7; 500: 4.7–5.2.

**MDE assumptions** (computed by me, not measured):
- Scaling: `MDE(n) = MDE_test * sqrt(n_test / n)`, starting from the earlier test-panel estimates (F17). This keeps
  their per-item variance: a paired S' − S contrast on the same items, 1 run per item per arm, two-sided α = 0.05,
  power 0.8 (factor 2.80).
- Implied discordance π = n·(MDE/2.8)²: SearchQA 0.08–0.13, OfficeQA 0.10–0.13, LiveMath 0.16–0.19,
  SpreadsheetBench 0.17–0.21 (at n = 279), ALFWorld 0.14–0.17.
- Not included:
  - Holm correction over the 3 contrasts of design-v0's 4-arm acceptance (S' vs S, task card, placebo): about ×1.2–1.3;
  - drift of run noise between windows: 2–3x on π;
  - the δ² term (first-order formula only).
- A one-sided α = 0.05 multiplies these MDEs by 0.888.
- 2 runs per item reduce only the run-noise share. Item variance dominates, so more items beat more runs (E5 R2).

Items needed per acceptance for design-v0's stated minimum effects (same assumptions):

| bench | target | items needed | supply |
|---|---|---|---|
| SearchQA | 3 / 3.5 / 4 points | 712–1,112 / 523–817 / 400–625 | only a new HF-validation block or C/D |
| OfficeQA | 10 points | 75–102 | **0** fresh; the pool is 74 and burned |
| LiveMath | 5 points | 500–606 | at most 291 (and 10 points needs 125–152) |
| SpreadsheetBench | 7 points | 279–338 | **0** fresh |
| ALFWorld | 10 points | 109–134 | ample (3,514) |

So design-v0's LiveMath target (about 5) and SpreadsheetBench target (about 7) cannot be reached on fresh real items,
and its OfficeQA target (about 10) is not on fresh items at all.

Token cost per fresh acceptance with 4 arms at 1 run, from the F13 and F18 anchors:
- SearchQA, 1,000 items: 4,000 cells × 1.35–2.25k tokens = about 5.4–9.0M.
- ALFWorld, 134 games: about 56.7M with the task card (105.7k per episode), or about 15.3M at the E-ds rate (28.5k).

## 6. Gaps and risks for route B in this area

1. **No fresh real items for OfficeQA or SpreadsheetBench**, and these are design-v0's first two benches
   (SpreadsheetBench → OfficeQA → ...). The rule "one decision per fresh batch, never reused" cannot be met there.
   - Acceptance there would run on reused items, which risks adaptive overfitting.
   - The alternative is generated items with program-computed answers, as a screen only. Their predictive validity is
     not established (E1: +13 on generated items, 0 on real ones).
2. **Even the "never-used" pool items are only method-side fresh.** Earlier learners and the v1 baselines had every
   pool item as training or selection input (F7–F9). Route B's engineer has never seen them, but the five task cards were
   written after the development data had been viewed (registration §2.2 L113-128).
3. **The SearchQA firewall gap**: `_refuse_tests` does not refuse the `reserve` (1,000) ids or blocks C/D. A new-block
   builder must exclude them, which reads sealed ids outside evaluation and needs registration.
   - The existing fresh-sample script also reads native test questions to dedupe (L50-56).
4. **ALFWorld test identity is inferred, not verified** (134 = `valid_unseen`). New games also need an id namespace,
   test exclusion, perhaps qualification, task-type stratification, and a large token budget.
5. **LiveMath evaluation blocks are a sealed hold-out**, partly read (e01, part of e02). Releasing them changes their role.
   - LiveMath also has fixed-option artefacts (`STRONGER_OPTION`, protocol.py:222) that make generated variants and
     shortcut checks bench-specific.
6. **dl lacks OfficeQA's `treasury_bulletins_parsed/transformed`** (F11). Rendering from upstream on dl, for the test
   readout or for examiner item generation from real tables, is unverified there.
   - For generated items, bulletins cited by test items carry test answer values. Excluding them needs test-side
     `source_files`, which is a test read.
7. **Independent-tag draws overlap** (F6). Never draw the run and acceptance batches with separate tags. Cut one order
   and keep a consumed-id ledger.
8. **MDE figures borrow run noise from one time window** (2–3x drift, F17). Interleaving all arms in the same window
   (design-v0 step 6) is required for them to hold.
9. **SpreadsheetBench all_data_912**:
   - CC-BY-SA-4.0;
   - references not verified (that is why Verified 400 exists);
   - qualification yield and id overlap with Verified 400 unknown;
   - the download needs the dl proxy and owner approval.

## 7. Open questions for the designer

1. **Owner releases.** Which fresh sources does the owner release for route B?
   - (a) A new SearchQA HF-validation block (11,380 available) and/or blocks C/D (2,000)?
   - (b) LiveMath evaluation blocks e03–e08 (and e01/e02?) as training-side acceptance material?
   - (c) ALFWorld train games outside the pool?
   - (d) A download of SpreadsheetBench all_data_912, or newer LiveMath months?
2. **OfficeQA and SpreadsheetBench.** Is acceptance on reused pool items acceptable if it is labelled "not fresh,
   adaptive reuse"? Or do those benches skip real acceptance and keep only a generated-item screen?
3. **What "never used" means.** Does it mean never used by route B's own history, or also never used by baselines and
   older learners (the absolute sense, which gives 0 everywhere in the pools)?
4. **ALFWorld test identity.** Is the test set `valid_unseen`? This needs a check by code that holds test access.
5. **Newer LiveMath months.** Have months after 202606 been published on HF? I did not check; it needs the network.
6. **SpreadsheetBench 912.** Is all_data_912 available, and how do its ids overlap with Verified 400?
7. **The "154 non-meta LiveMath items".** critiques/stoploss-evidence.md F7 says v3 stage 3, D7, D9 and D10 reused them.
   My scan shows those studies touched only focal ∪ regression (142 ids). I could not reconcile the two.
8. **Exact assumptions behind F17.** The D5 critic's variance assumptions live in its scratchpad scripts
   (`.../scratchpad/feas/D5-critic/crit*.py`), which I did not read. My scaling inherits whatever they assumed.
9. **E7 and E10 classification.** I classified E7's 70 listed ids and E10's `prereg.json` lists (148 non-focal ids) as
   listed only. E10's 102 generated items name 68 real pool items as sources. Depending on the definition of "used",
   SearchQA never-used is 45 (solver only) or 37 (solver and generator).

---
## Appendix: raw working notes (superseded by the sections above)

- data.py 358 lines: DEV_MACHINE L45-64; pin L76-82; _part_ids L103-111; test_ids L114-117; _load L127-152; pool
  L155-166; ranked L173-176; qualified L179-185; training_items L188-196; regression_items L199-205; sheet_tolerances
  L208-228; TestAccess L232-239; _officeqa_rows L249-280 (docs dir L265); _livemath_rows L283-300; _proof L314-329;
  test_panel L332-358.
- protocol.py 357 lines: VERSION L10; ORDER L13; DATA_SEED L56; TRAIN_ROLLOUT L60-61; GATE_RUNS L62; POOLS L63-64;
  TEST_SIZES L65; REGRESSION_ITEMS L66; SHEET_MIN_QUALIFIED L68; TRIGGER_RUNS L72; PARENT_REGRESSION_RUNS L74;
  MAX_UNKNOWN_SHARE L84.
- v3 manifest focal tolerances: searchqa 7, officeqa 6, livemath 9, spreadsheetbench 7, alfworld 5. Regression
  tolerances: 5 / 6 / 8 / 6.
- The fivebench-split-v2 manifest also holds bigcodebench (400/128/484/128) and korbench (500/250/250/250).
