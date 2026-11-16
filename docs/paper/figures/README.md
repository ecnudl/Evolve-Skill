# Paper figures: route B, executable-skill co-evolution

A preview page of every figure with its data tables exists as a private page of the owner (not published).

Six vector figures for a two-column paper. The diagrams are sized for a 3.3 in column. The two-chain heatmaps
are 6.07 in wide (`figure*`). Everything here is written by the two scripts in this directory; nothing was edited
by hand afterwards.

| Figure | Size (in) | Placement | Shows |
|---|---|---|---|
| `architecture.svg` (+ `.pdf`, `.png`) | 3.30 × 3.62 | one column | one learning step of route B in configuration `main-v7` |
| `protocol-timeline.svg` (+ `.pdf`, `.png`) | 3.30 × 2.61 | one column | the sequential bench protocol, frozen packages S1–S5 and the chain-end 5×5 read |
| `heatmap_implant-v5.svg` (+ `.pdf`, `.png`, `.csv`) | 6.07 × 3.27 | `figure*` | implant-v5 readout, chains G and D: **post-hoc upper bound** |
| `heatmap_cross-v5.svg` (+ `.pdf`, `.png`, `.csv`) | 6.07 × 3.27 | `figure*` | cross-v5 card-transfer matrix, chains G and D: **post-hoc upper bound** |
| `heatmap_main-v6-D.svg` (+ `.pdf`, `.png`, `.csv`) | 3.26 × 3.43 | one column | main-v6 chain D readout (read-only extraction) |
| `heatmap_main-v6-G.svg` (+ `.pdf`, `.png`, `.csv`) | 3.26 × 3.55 | one column | main-v6 chain G readout (read-only extraction, opened 11/04 09:48) |

For LaTeX, include the PDFs (`\includegraphics[width=\columnwidth]{architecture.pdf}`). They are vector files
with embedded font subsets. The SVGs keep text as text in Helvetica (Arial fallback; the metrics are the same).

## What each figure shows

### `architecture.svg`: one learning step (main-v7)

- **Left lane, per item.** Practice items of bench k (train, confirmation and acceptance slices, plus items the
  examiner writes) go to the **router**. The router runs every procedure's `applies(x)` predicate in the sandbox
  without a model call (`router.py`). Fired procedures' hooks add notes or computed facts. The **fixed shell**
  sends the request to the **frozen solver** (GLM-5.3 in chain G, deepseek-v4-flash in chain D; `solver.py`), and
  the **frozen scorer** gives pass or fail (`judge.py`, scorer v2; this is the bench verdict, not the LLM judges).
  When nothing fires, the request is byte-identical to the card-only arm C ("≡ C").
- **Right lane, per round.** The **skill package S** is an ordered list of at most 24 procedures plus the fixed
  instruction card of the bench (`package.py`). The **engineer** (LLM) reads failures and coverage and writes at
  most 3 procedure edits (new, revise, delete, narrow; `engineer.py`). The candidate S′ passes the fixed **checks
  C1–C9** (parse, syntax, static bans for leakage and shortcuts, zero crash, firing check; policy failures are
  hard) and the **two LLM judges** (GLM-5.3 and deepseek-v4-flash, v2.9 audit).
- **Decision bar.** This is the main-v7 rule, "gain and no harm on the touched items" (`v221_rule.py`). T is the
  set of items whose S′ request differs from S's (on ALFWorld: episodes where a changed procedure emitted a note).
  With net = fixed − broken on T, a stage passes iff net ≥ max(3, ⌈0.10·|T|⌉), broken ≤ ⅔·fixed and the whole batch
  S′ − S ≥ −1 point. The rule is applied at training, confirmation and acceptance, each on fresh items, and S′
  replaces S only if all three pass.
- **Bottom row.** At step end the package is frozen as S_k and becomes the parent of the next bench. Test
  panels are opened only at chain end.
- **Colours.** Blue is the frozen solver, orange an LLM method role, aqua the learned program, and gray is
  deterministic (no LLM).
- **Simplified or not drawn.** The examiner's other jobs are not drawn: diagnosing run failures (detectors) and the
  mandatory research before generating items. Also not drawn:
  - main-v7's judge rule: a procedure is removed only if both judges find its notes untrue AND its own touched
    confirmation items show broken > fixed.
  - The acceptance read samples touched items by routing until |T| ≥ 60.
  - Split re-judging of multi-edit candidates (main-v6 change 1), the coverage sentence in the engineer feedback
    (main-v7 change 4), and the single automatic retry of infrastructure pauses (change 5).
- **Sources.** The route-B paragraphs of `docs/current-workflow.md` (10/22–11/03),
  `execskill-v29/docs/handoff/v29-20261026/BRIEF-v221-main-v7.md`, and the module docstrings of
  `skillopt/execskill/{step,acceptance,v221_rule,router,routes,engineer,judge,package,solver,cells}.py` in the
  execskill-v29 tree.

### `protocol-timeline.svg`: the sequential protocol and the chain-end read

- **Steps.** Each chain learns SearchQA → OfficeQA → ZebraLogic → SpreadsheetBench, then imports the fixed
  ALFWorld package (alfworld-v11) at step 5. Each step freezes a package S_k, starting from S_0 = card only (arm C);
  S_5 = F.
- **Chain-end read.** Every S_k is read once on all five sealed test panels; the cell is S_k − C in accuracy points.
- **Analysis roles** (main-v5 readout design, kept by main-v6 and main-v7):
  - own bench (diagonal): gain, one-sided paired t;
  - related benches (dashed: SearchQA–OfficeQA, OfficeQA–SpreadsheetBench): descriptive 95% CI;
  - other benches: no harm, −5-point non-inferiority. ZebraLogic and ALFWorld are related to no bench.
- **Arms on every panel.** F = S_5 + card, C = card only, B = blank, and the stage arms S_1…S_4. Byte-identical
  requests share one solver call (main-v6 change 2).
- **Chains.** G and D differ only in the solver.

### Heatmaps: how to read them

- Cell = stage package (or cross arm) − card-only arm C on the same test items, in accuracy points.
- **Colour and the large number** are the *primary* analysis. It is the registered analysis, and conclusions follow it
  (owner rule of 10/31, `docs/current-workflow.md`).
- **The number in parentheses** is the *second* analysis, in which items whose solver requests are byte-identical
  in both arms count as 0. It is shown only where it differs from the primary.
- **"≡" alone** means every request was byte-identical to C and the arm shared C's cell: 0 by construction, not
  a measurement.
- **A small "≡" in the corner** means every request was byte-identical to C, but the arm was dispatched separately.
  The primary value there is same-text re-run noise; the second analysis is 0.
- **Outlined cell**: own bench (row k on bench k); in cross-v5, own card (F − C).
- **Colour scale.** The diverging scale is clipped at ±20 points (the arrows on the colour bar); the printed numbers
  are exact.
- **Rows** of the implant-v5 and main-v6 figures are the package after step k. "= C", "= S3" and "= F" say which
  earlier package the row is identical to.

### `heatmap_implant-v5.svg` (evidence label `implant_v5_test_read`, post-hoc upper bound)

- **What was run.** main-v5 unchanged and **no learning**: steps 1, 2 and 4 were skipped, so the package is
  unchanged there.
  - Step 3 appends a fixed ZebraLogic program: in G `p-zebralogic-3-3` (main-v5 G step 3 round 2), in D the
    hand-picked v3r4 used in v2.13.
  - Step 5 imports the alfworld-v11 package.
- **What the figure shows.** Only ZebraLogic and ALFWorld move:
  - ZebraLogic: G +9.0 primary / +5.0 second, D +13.0 / +13.5.
  - ALFWorld: G +7.5, D +17.2.
- **Re-run noise, not effects.** The F row's SearchQA, OfficeQA and SpreadsheetBench values (for example G −8.8 on
  SpreadsheetBench) come from byte-identical requests. They are re-run noise; the second analysis gives 0.
- **Limits.** These are programs selected after the fact, so the figure is an upper bound, not evidence of learning.

### `heatmap_cross-v5.svg` (evidence label `cross_v5_test_read`, post-hoc upper bound, transfer matrix)

- **What was run.** implant-v5 unchanged except the chain-end read: on each panel t, the cross arm X_s sends the
  chain-end package with the registered instruction card of bench s (row) in t's card position. ZebraLogic's card
  is the registered neutral card.
- **Cell.** X_s − C_t; the diagonal is F − C. The package is the same in every row, so off-diagonal differences
  come from the card.
- **Where the package also acts.** On ZebraLogic (†) the shell sends no card text, so X_s differs from C only where
  the package fires (48 items in G, 192 in D). That column shows the package's own effect. On ALFWorld the package
  fires as well, so those cells mix package and card.
- **Card effect alone.** X_s − F is in the CSV column `x_minus_f_pts`.
- **Limits.** As implant-v5, this is a post-hoc upper bound.

### `heatmap_main-v6-D.svg` (configuration main-v6, chain D)

- **Rows.** The stage rows were C, C, S3, S3, F: steps 1, 2 and 4 accepted nothing, step 3 learned
  `p-zebralogic-3-3`, and step 5 imported the alfworld-v11 package (three procedures).
- **ZebraLogic.** +10.0 points (21 better, 1 worse; 95% CI 5.6 to 14.4).
- **ALFWorld.** +17.9 points. This comes from the imported package, not from this chain's learning. It is a room-level
  analysis with 4 rooms (95% CI −6.1 to +41.9).
- **Other panels.** All other cells share C's cell and are 0 by construction.
- **Provenance.** The read label is `owner_requested_read_only_extraction_main_v6_not_registered_unseal_chains_D`:
  a read-only extraction the owner requested, not the registered unseal.

### `heatmap_main-v6-G.svg` (configuration main-v6, chain G)

- **Rows.** The stage rows were C, C, S3, S3, F, as in chain D: steps 1, 2 and 4 accepted nothing, step 3 learned
  `p-zebralogic-3-5`, and step 5 imported the alfworld-v11 package (three procedures).
- **ZebraLogic.** +21.0 points (42 better, 0 worse; 95% CI 15.3 to 26.7; second analysis +20.0). The procedure fired
  on 155 of the 200 test items; the other 45 requests were byte-identical to C.
- **ALFWorld.** +3.0 points (6 better, 2 worse; 95% CI −6.3 to +12.3), inside the same-request noise. As in chain D
  this is the imported package, not this chain's learning.
- **Other panels.** All other cells share C's cell and are 0 by construction.
- **Provenance.** The read label is `owner_requested_read_only_extraction_main_v6_not_registered_unseal_chains_G`,
  opened on the owner's request on 11/04 09:48 (ledger entry of that time).

## Palette and legibility

- **Validation.** All colours come from the dataviz reference palette and were checked with its validator
  (`validate_palette.js`) on a white surface.
- **Diagram colours.** Blue `#2a78d6`, orange `#eb6834` and aqua `#1baf7a` (categorical slots 1–3).
  - `--pairs all`: all checks pass. Worst CVD ΔE is 9.2 (aqua–orange, deutan); worst normal-vision ΔE is 24.0.
  - Aqua is 2.82:1 on white, so it carries visible labels and never colours text.
- **Diverging scale.** The blue arm is the documented ramp (steps 100–700). The red arm has the same OKLCH lightness
  per step at the documented categorical red's hue; step 400 is the documented `#e34948`. The neutral midpoint is
  `#f0efec`.
  - Both arms pass the ordered-ramp checks: monotone lightness, adjacent ΔL ≥ 0.06 and a single hue. The light-end
    contrast "fail" is the documented by-design case for a diverging scale whose light end means "near zero".
  - The poles stay apart under CVD at equal magnitude: ΔE 11.3, 23.6 and 19.0 at steps 200, 400 and 600.
- **Type.** Diagram text is 7.5 pt (titles) and 6.2–6.5 pt (labels) at the printed size. `make_diagrams.py` refuses
  to write a figure in which any label is wider than its box (Helvetica AFM widths). Heatmap values are 7.5 pt, the
  second analysis is 6 pt, and cell labels are white or near-black, whichever contrasts more with the fill.

## Regenerate

```sh
cd docs/paper/figures
# heatmaps: matplotlib 3.10 (conda env "skill" on the owner's Mac)
python make_heatmaps.py --png        # from the source JSON files below
python make_heatmaps.py --from-csv   # from the CSVs here (same output)
# diagrams: standard library only; --export adds PNG and PDF through headless Google Chrome
python3 make_diagrams.py --export
```

`--from-csv` reproduces the four heatmaps exactly from the committed CSVs, so the figures can be rebuilt after the
job scratch files below are gone. Each CSV is also the table view of its figure, with confidence intervals,
one-sided p values, better/worse counts and identical-request counts that the figure does not print.

## Data provenance

| Figure | Source file (owner's Mac, job scratch) | sha256 | Fields used |
|---|---|---|---|
| implant-v5 | `<local-scratch>/dash/imp5_cells.json` | `aefbefea08a33fd3…fd9e5d35` | rows by `chain`, `k`, `bench`: `d1` (primary), `d2` (second), `n`, `same_req` |
| main-v6 D | `<local-scratch>/v219/m6-D-readout.json` | `e291bf6f438c2223…fd5ac309` | `chains.D.stage_rows`, `per_bench[b].pairs["S3-C" / "F-C"].{primary,secondary}.estimate.mean`, `items_reading_one_cell` |
| main-v6 G | `docs/handoff/main-v6-readout-20261103/m6-G-readout.json` (in the repo; the D file is also there as `m6-D-readout.json`, byte-identical to the scratch copy) | `e797094cdbb1fbcb…` | same fields under `chains.G` |
| cross-v5 | `<local-scratch>/v219/cross5-cells.json` | `0f9fda57069ed4e6…2d77d966` | rows by `chain`, `k` (card source), `bench` (panel): `d1`, `d2`, `n`, `same_req`, `xf1` |

Full hashes: implant `aefbefea08a33fd3c6f19a57a3b2fb98b49f9a1500cb675073be4e52fd9e5d35`, main-v6 D
`e291bf6f438c22234d24bbda7fe8f0c556487b1e6b40cd2cca8c2d553f5ac309`, cross-v5
`0f9fda57069ed4e667b43e6df422e8384997a009eb460f086dd8b2232e77d966`, main-v6 G
`e797094cdbb1fbcb3018e3b38c699b18e8e602af24da369814a0df52c6841a05`.

- **Test panel sizes.** SearchQA 400, OfficeQA 172, ZebraLogic 200, SpreadsheetBench 204 and ALFWorld 134 (4 rooms).
- **Values.** All are accuracy differences in points on the sealed test panels as read at chain end. No model was
  called to make these figures.

## `typed-skills-method-v5-r2.png` / `.pdf`：typed-v3 方法总览（11/16 21:2x 加入）

负责人 11/16 选了 Claude Fable 5.2 画的版本并要求修改，这是修改版 r2。17.5 × 10.4 cm，通栏。左：一步学习（诊断 → 造练习题 → 写卡或程序 → 返修 → 初筛 → 门槛），画成自我改进循环；右中：带题型的技能库；右上：推理时按题型挂载；底部：五个基准依次学习、每步之后读五个封存测试集。**第 2 站的 deep search 和 coding rubric 是下一版设计，正在跑的 `typed-v3` 没有使用；“self-improvement loop”只是循环的名字，不表示已证明有效。** 可编辑的 PowerPoint 版和 LaTeX 源文件在论文材料目录，未公开。
