# E3: Candidate benchmark scan for the transfer setting (serves purpose 2)

Explorer report, 2026-10-21. Serves the owner's **purpose 2**: the metric is generalisation, so a Skill is
evolved on ONE benchmark and evaluated on the OTHERS, and benchmarks may be swapped to get measurable gains.
Labels used below: **[measured]** = computed in this work from data or model calls; **[verified]** = checked
against a file, API response or licence text in this session; **[claim]** = from papers, READMEs or memory, not
re-checked; **[estimate]** = my own judgement.

## 0. Provenance (what was run, by whom, and what I re-checked)

- The headroom pilot ran 2026-10-21 00:18-03:18 (machine clock, UTC+8) on the NEW machine, launched by an
  earlier attempt at this same direction, which was interrupted before it wrote a report. I did not trust
  its output blindly. I re-read every script (`scan.py`, `texts.py`, `write_cards.py`, `download.py`), checked
  the download receipts, read sampled replies, and recomputed the analyses.
- Training splits only **[verified]**. `download.py` asserts that every file name contains "train" and none
  of test/valid/dev/holdout/final. The receipts list exactly: HotpotQA `distractor/train-0000{0,1}-of-00002.parquet`,
  TAT-QA `tatqa_dataset_train.json`, FinQA `dataset/train.json` (GitHub czyssrs/FinQA), MATH `*/train-00000-of-00001.parquet`
  (7 subjects), MBPP `full/train-00000-of-00001.parquet` (task ids 601-974), GSM8K `main/train`, NQ-open `nq_open/train`.
  No test/validation file was downloaded or read. No project test pool was touched.
- New in this session (all zero-cost except the probe): a format-versus-content re-score (`content_rescore.py`);
  a contamination probe (`probe_contam.py`, which had been written but never run); a scan of what is stored
  locally on both machines; split sizes from dataset metadata; DeepSeek-V4 model-card facts.
- Solver settings **[verified in `scripts/weak_solver_probe.py` and the cell records]**: deepseek-v4-flash on the
  pjlab_token route, temperature 0, thinking "disabled" (replies that carry reasoning text are rejected as
  `thinking_mismatch`), max_tokens 12,288 (v3 used 32,768). Prompt layout: the system prompt is a base sentence,
  then the answer contract, then "Frozen skill guidance (use only where applicable):", then the arm text. The
  user message is the JSON public view. This mirrors the layout of `continual_eval.backends.solve`, but it is not
  the coevo5 solver prompt byte for byte.

## 1. Bottom line

1. **Headroom over a good instruction is small at the content level.** On five classic candidates
   (HotpotQA, TAT-QA, FinQA, MATH level 5, MBPP; 80 training items each, 2 runs), an expert-written skill beats
   the task-card instruction by -3.7 to +3.7 points of content accuracy. None of the five differences is
   significant (sign-test p >= 0.29). The card itself beats NoSkill in content on only two candidates:
   HotpotQA +6.2 points [95% CI +2.5, +10.6] (9 items up, 0 down, p = 0.004) and FinQA +4.4 [0.0, +9.4] (8 up,
   1 down, p = 0.039). This matches the project's earlier finding: learned clauses on top of a good instruction
   gave +3 to +5 points, not significant.
2. **The large instruction effects are answer-format conventions under strict scorers.** MATH: card vs NoSkill
   +36.2 points strict, but +5.0 content (the gain is answer-tag use). TAT-QA: expert vs card +27.5 strict
   (26 items up, 3 down) but +3.7 content (the gain is stating the scale word: "thousand", "million", "%").
   FinQA: one ambiguous line in my own expert skill ("answer with a plain number ... % only for percentage
   answers") made the model drop "%" on all 42 percentage items. That cost -40.6 points strict and 0.0
   content. A learned rule could pick up such conventions from training failures (the failures show them),
   but each convention belongs to one scorer.
3. **Unscoped transfer between "similar" benchmarks is strongly negative.** I applied the v3 task-card seed
   of the nearest current benchmark to each candidate (SearchQA->HotpotQA, OfficeQA->TAT-QA and FinQA,
   LiveMath->MATH, SpreadsheetBench->MBPP; 1 run). It lost 17 to 54 points strict against the candidate's own
   card on all five. Content losses: MATH -25.6 (the multiple-choice-letter instructions hurt free-form math),
   MBPP -54.4 (the model writes openpyxl workbook programs), FinQA -6.2 (p = 0.016). HotpotQA and TAT-QA were
   content-neutral. Similar by topic does not mean compatible by output contract. Transfer must therefore be
   measured as **target card + transferred rules versus target card alone**, never as the source text
   replacing the target's card.
4. **What helps measurement.** On the QA/table candidates the card arm is much more repeatable than v3
   SearchQA: 2-5 of 80 items flip between two identical runs (MBPP 1) (v3 SearchQA: 30/194 = 15.5%). Cells are cheap:
   0.2-1.9k tokens versus 4.7-7.9k for OfficeQA and 28-106k for ALFWorld in v3. HotpotQA has the lowest
   per-item difference SD (0.147 for expert vs card), so about 68 items detect a 5-point effect (alpha 0.05,
   power 0.8). TAT-QA/FinQA need 650-900 items (an upper bound: their SD is inflated by the big format effect); MATH needs 424 because 21-26% of items flip between identical
   runs. MBPP (90.6% NoSkill, 8/80 movable items), GSM8K (86.7% NoSkill) and closed-book NQ-open (49/60
   dead items) have no usable headroom.
5. **Recommendation for purpose 2** (details in section 7). If the owner wants a benchmark set where
   "evolve on one, evaluate on the rest" can produce a measurable gain, the best-supported set from this scan
   is a **multi-hop QA family with one shared scorer**: evolve on HotpotQA; evaluate on SearchQA, 2WikiMultihopQA
   and MuSiQue, which all use SQuAD-style exact match. Optionally add a **financial-table pair** with large
   learnable conventions: TAT-QA as the source, FinQA and OfficeQA as targets. That pair is a real test of "no
   drop on similar targets", because their conventions conflict. Do NOT expect classic benchmarks alone to
   create a content-level gain over a good card. The pilot says that gain is at most about 4 points.
   Feasibility: **medium**. The engineering is easy; whether a measurable transfer effect exists is open, and
   the honest prior is small.

## 2. Candidate table

Licence sources: HF dataset card API (`cardData.license`) and/or the GitHub LICENSE file, both fetched
2026-10-20/21 **[verified]** unless marked. Sizes: **[verified]** = counted in the downloaded training file or
read from the dataset's README `num_examples` metadata; otherwise **[claim]**. "Local" = found by name scan of
/root and /data on both machines (test-labelled paths pruned, `meta/avail_new.txt`); the HF caches on both
machines hold only models (SmolLM2, Qwen2.5-1.5B), no datasets **[verified]**. Harness effort and contamination
are **[estimate]** unless stated. The solver's model-card repo `deepseek-ai/DeepSeek-V4-Flash` was created on HF
on 2026-04-22 (later variants: 0731, V4.1 2026-09-10, V4.1-1017) **[verified]**. The training cutoff is not stated
in the card text I fetched, and which snapshot the PJLAB route serves is unknown. Every benchmark released
before 2026 should therefore be treated as possibly seen in pre-training.

### 2.1 Retrieval / multi-hop QA (current member: SearchQA, BSD-3-Clause [verified])

| Candidate | Licence | Size | Local | Harness effort | Contamination risk | Train split? |
|---|---|---|---|---|---|---|
| HotpotQA (distractor) | CC BY-SA 4.0 (HF); code Apache-2.0 | train 90,447 (hard 15,661: 12,451 bridge + 3,210 comparison), validation 7,405 [verified] | YES: train downloaded, /data/feasibility/E3/data/hotpotqa (332 MB) | trivial (EM/F1; implemented) | high (2018, mirrored everywhere); closed-book probe in section 5 | yes |
| NQ-open | CC BY-SA 3.0 | train 87,925, validation 3,610 [verified] | YES: train downloaded | trivial closed-book; high with passages (needs a retriever + Wikipedia index) | high | yes |
| TriviaQA (rc) | HF "unknown"; GitHub code Apache-2.0 | train 138,384 / val 17,944 / test 17,210 [verified metadata] | no | low (alias EM) | high | yes |
| MuSiQue (answerable) | CC BY 4.0 (GitHub) | train/dev jsonl present on HF (bdsaglam/musique) [verified listing]; train ~19.9k [claim] | no | low (EM/F1, paragraphs supplied) | medium-high | yes |
| 2WikiMultihopQA | Apache-2.0 (GitHub) | train ~167k [claim] | no | low | medium-high | yes |
| FRAMES | Apache-2.0 | test.tsv only [verified listing]; 824 questions [claim] | no | high (needs the linked Wikipedia articles) | medium (Sep 2024) | NO, so target only |
| BrowseComp-Plus | MIT | test 830 queries + fixed corpus [verified metadata/README] | no | high (agentic retrieval loop + index); BrowseComp itself (MIT, simple-evals) ~1,266 encrypted items [claim] | low-medium (Aug 2025) | NO, so far target only |

### 2.2 Document / table QA (current member: OfficeQA, CC BY-SA 4.0, gated "auto" [verified])

| Candidate | Licence | Size | Local | Harness effort | Contamination risk | Train split? |
|---|---|---|---|---|---|---|
| TAT-QA | CC BY 4.0 (HF); code MIT | train 2,207 tables / 13,251 questions (span 5,737, arithmetic 5,553, multi-span 1,656, count 305; 6,792 carry a scale) [verified] | YES: train downloaded | low-medium (scale-aware EM; our approximation exists, not the official script) | medium-high (2021) | yes |
| FinQA | MIT (GitHub); CC BY 4.0 (HF ibm-research) | train 6,251 (3,508 answers with %, 120 yes/no) [verified]; dev 883 / test 1,147 [claim] | YES: train downloaded | low-medium (tolerance + percent convention) | medium-high (2021) | yes |
| ConvFinQA | MIT (GitHub) | ~3.9k conversations [claim] | no | medium (multi-turn) | medium | yes |
| MultiHiertt | licence file NOT FOUND (GitHub API) [verified absence] | ~10k [claim] | no | medium | medium | yes, but licence unclear |
| WikiTableQuestions | CC BY-SA 4.0 (GitHub) / CC BY 4.0 (HF) | train 11,321 / val 2,831 / test 4,344 [verified metadata] | no | low-medium (denotation match) | high (2015) | yes |
| DocVQA (lmms-lab mirror) | Apache-2.0 on the mirror; original RRC terms [claim] | train 39,463 / val 5,349 / test 5,188 [verified metadata] | partial: /root/Evolve-Skill-validation/data/docvqa_id_split on the OLD machine; repo env `skillopt/envs/docvqa` | medium (images: the text-only solver needs OCR text; ANLS metric) | medium | yes |

### 2.3 Math (current member: LiveMath / LiveMathematicianBench, licence NOT FOUND on HF or GitHub [verified absence])

| Candidate | Licence | Size | Local | Harness effort | Contamination risk | Train split? |
|---|---|---|---|---|---|---|
| MATH (Hendrycks) | MIT | train 7,500 (Level 5: 2,304) [verified]; test 5,000 [claim] | YES: train downloaded | trivial (is_equiv; implemented) | very high (2021; train in many SFT corpora such as NuminaMath and MetaMath) | yes |
| MATH-500 | HF licence null; derived from MATH (MIT) [claim] | 500, test only [claim] | no | trivial | very high | NO |
| GSM8K | MIT | train 7,473 / test 1,319 [verified] | YES: train downloaded | trivial | very high | yes |
| AIME 2024/2025 | MIT (Maxwell-Jia) / Apache-2.0 (math-ai) | 30 per year [verified metadata for aime25]; AI-MO aimo-validation-aime 90 [verified] | no | trivial (integer) | high for <= 2025 | NO (too small for 60-100-item panels) |
| MathArena AIME 2026 / HMMT Feb 2026 | CC BY-NC-SA 4.0 (non-commercial) [verified] | ~30 each [claim] | no | trivial | low-unknown (Feb 2026, near or after the cutoff) | NO |
| AQuA-RAT (multiple choice) | Apache-2.0 | train 97,467 / val 254 / test 254 [verified metadata] | no | trivial (letter) | high | yes, the closest multiple-choice relative of LiveMath |
| MMLU-Pro (math subset, 10 options) | MIT | test 12,032 / validation 70 [verified metadata] | no | trivial | high | NO train |
| TheoremQA | MIT | test 800 [verified metadata] | no | low | high | NO |
| GPQA | CC BY 4.0, gated | main 448 / diamond 198 [claim] | no | trivial | medium | NO |

### 2.4 Code (current: none; BigCodeBench and KOR-Bench were used in the earlier F/G line)

| Candidate | Licence | Size | Local | Harness effort | Contamination risk | Train split? |
|---|---|---|---|---|---|---|
| MBPP (full) | CC BY 4.0 | train 374 / test 500 / val 90 / prompt 10 [verified metadata; train verified] | YES: train downloaded; docker python:3.11-slim present | trivial (implemented: docker, no network, 10 s) | very high | yes (374) |
| HumanEval / HumanEval+ | MIT / Apache-2.0 | 164 each [verified metadata] | no | low (evalplus) | very high | NO |
| MBPP+ | Apache-2.0 | 378 [verified metadata] | no | low | very high | NO |
| LiveCodeBench (code_generation_lite) | HF card "cc" (CC variant unspecified); code MIT | release v1 400 -> v5 880 problems (May 2023 - Jan 2025) [verified README] | no | medium-high (stdin/stdout hidden tests, sandbox) | high for the released windows; low only for problems after the cutoff | NO train (date windows can play that role) |
| BigCodeBench (full / hard) | Apache-2.0 | 1,140 / 148 [verified metadata] | YES: both machines hold the v0.1.4 parquet + partition proposal (/root/continual-bcb-prep-20260928/official-v014-b74c0d0); evaluation image loaded on the OLD machine (15.1 GB), only as a 9.3 GB tarball (not loaded) on the NEW one; repo backend exists (`continual_eval` BENCHMARKS) | low (exists) | medium (Jun 2024) | NO official train; the project used its own partition |

### 2.5 Embodied / agent (current member: ALFWorld, MIT [verified])

| Candidate | Licence | Size | Local | Harness effort | Contamination risk | Train split? |
|---|---|---|---|---|---|---|
| ALFWorld (current) | MIT | pools pinned in the v3 manifest; ~3.5k train games [claim] | YES on the NEW machine (/root/continual-alf-prep-20260928/data, /root/.cache/alfworld) [verified]; OLD machine per the migration notes [claim] | exists | medium | yes |
| ScienceWorld | Apache-2.0 | 30 task types x many variations [claim] | no | high (Java simulator, agent loop) | low-medium | yes (variation splits) |
| TextWorld | MIT | generator: unlimited games with known solutions (`tw-make`) [verified README] | no | medium (agent loop); its guaranteed-solvable generation also suits D6 | low (fresh games) | generated |
| WebShop | MIT | 12,087 instructions, 1.18M products [verified README] | no | high (web server with search index) | medium | yes |

### 2.6 Spreadsheets (current member: SpreadsheetBench, CC BY-SA 4.0 on HF; no LICENSE file on GitHub [verified])

| Candidate | Licence | Size | Local | Harness effort | Contamination risk | Train split? |
|---|---|---|---|---|---|---|
| SpreadsheetBench (current) | CC BY-SA 4.0 (HF) | 912 + "Verified" 400 subset (Dec 2025) [verified README] | YES (pinned pools; recalc docker image `evolve-skill-sheet-recalc:20260930-offline` present on both machines [verified]) | exists | medium | project partition |
| SheetCopilot | GPL (GNU GPL LICENSE file) [verified]; version 3 [claim] | 221 tasks on 28 workbooks [verified README] | no | medium-high (workbook-state checks; could reuse the recalc image) | medium | NO (small) |
| InstructExcel | MIT | ~10k Office-Scripts tasks [claim] | no | high (TypeScript Office Scripts; Excel needed) | medium | yes |

### 2.7 Plausible similarity map (what should transfer to what)

[estimate], refined by the neighbor probe of section 4.5 ([measured], 1 run, unscoped replacement of the target's card):

| Evolve on | Similar targets (same answer contract) | Similar by topic only (contract differs) | Dissimilar controls | Measured transfer evidence |
|---|---|---|---|---|
| HotpotQA | SearchQA, 2Wiki, MuSiQue, TriviaQA (all short span + SQuAD EM) | FRAMES, BrowseComp (agentic retrieval) | MATH, MBPP | SearchQA seed on HotpotQA: content +2.5 vs NoSkill (7 up/3 down, n.s.), -3.7 vs card (1/4, n.s.); strict -20.0 vs card because 22/80 replies dropped the tag |
| TAT-QA | FinQA (numeric over financial tables; needs % but no scale words), OfficeQA | WikiTQ, DocVQA | HotpotQA, MBPP | OfficeQA seed on TAT-QA: content 0.0 vs card (6/6); strict -19.4 (scale words lost) |
| FinQA | TAT-QA, OfficeQA, ConvFinQA | WikiTQ | MBPP | OfficeQA seed on FinQA: content -6.2 vs card (0 up/7 down, p = 0.016); strict -41.2 (the % sign dropped) |
| MATH | AIME, MATH-500, GSM8K (free-form numeric) | LiveMath, AQuA, MMLU-Pro (multiple choice) | HotpotQA | LiveMath seed on MATH: content -25.6 vs card (5/28, p < 0.001) |
| MBPP | HumanEval(+), BigCodeBench | SpreadsheetBench (Python + openpyxl I/O) | HotpotQA | SpreadsheetBench seed on MBPP: -54.4 (the model writes openpyxl programs; 45 of 80 items down) |

## 3. Headroom pilot: design

- Candidates (5 core + 2 side probes), all from TRAINING splits, sampled with the fixed seed 20261021 **[verified code]**:
  HotpotQA distractor train at level "hard", 80 items (61 bridge, 19 comparison); TAT-QA train, 80 distinct
  documents with one random question each (26 span, 16 arithmetic+percent, 11 arithmetic+million, 10
  span+thousand, ...); FinQA train, 80 distinct report pages among the 6,085 of 6,251 rows with a clean
  numeric/percent/yes-no answer (42 percentage answers, 3 yes/no); MATH train Level 5, 80 items (19 Intermediate
  Algebra, 18 Geometry, ...); MBPP full train without setup code, 80 items. Side probes, NoSkill only, 1 run:
  GSM8K train 60, NQ-open train 60 (closed book).
- Arms: **noskill** (base + contract only); **card** (GLM-5.3 instruction written once from a public task card
  with `skillopt/coevo5/texts.py` INSTRUCTION_SYSTEM + `instruction_text()`, the same procedure that produced the
  v3 I-ds seeds; the card states the task, the input fields and the scoring rule; 4,268 GLM tokens for five
  cards); **expert** (bullet skills written by the explorer from the task description only, frozen in
  `texts.py` before items were sampled: file mtime 00:07, items 00:16); **neighbor** (the v3 I-ds seed of the
  nearest current benchmark, 1 run, as a transfer probe).
- Cells: 5 x 80 x 3 arms x 2 runs = 2,400 core + 120 side + 400 neighbor = 2,920 scan cells, plus 40 smoke cells
  (run 0, excluded from all tables). Delivered 2,934 of 2,960. Failures: 15 http_429 and 11 length truncations
  (all counted as fails). 431 cells needed 2-4 attempts **[measured]**.
- Scorers (my own implementations, not the official scripts) **[verified code]**:
  - HotpotQA / NQ: strict = SQuAD-normalised exact match of the last `<answer>` tag; lenient also accepts the
    gold span inside a tag at most 3 tokens longer; F1 is recorded.
  - TAT-QA numeric: strict = exactly one number, equal after rounding to the gold's decimals, AND the stated
    scale set equals the gold scale (approximates the official scale-aware EM); lenient = any number within 1%
    of gold x {1, 1e3, 1e6, 1e-3, 1e-6, 100, 1/100}. Spans: normalised EM or containment.
  - FinQA: strict = exactly one number, equal after rounding, with "%" present exactly when the gold has it;
    lenient = within 1% of gold, gold/100, gold x 100 or exe_ans.
  - MATH: strict = Hendrycks `is_equiv` on the tag content (or the last `\boxed` inside the tag); lenient also
    strips `\text`, compares floats, and falls back to a `\boxed` in the last 400 characters when the tag is missing.
  - MBPP: run the code block plus the three asserts in docker python:3.11-slim (no network, 10 s, 512 MB).
  - **content** (added this session): lenient applied to the tag, or to a fallback extraction (last `\boxed` or
    last non-empty line) when the tag is missing. It measures what the model computed, independent of the
    output contract. A missing tag fails both strict and lenient, so lenient is NOT format-free.
- Statistics: per-item mean over runs; paired difference; bootstrap 95% CI (10,000 resamples); two-sided
  sign test on items that moved.

## 4. Results (all [measured]; n = 80 items per candidate, 2 runs unless stated)

### 4.1 Accuracy per arm (per-item mean over 2 runs; neighbor = 1 run)

| Candidate | Metric | NoSkill | Card | Expert | Neighbor |
|---|---|---|---|---|---|
| HotpotQA | strict / content | 0.581 / 0.713 | 0.700 / 0.775 | 0.719 / 0.794 | 0.500 / 0.738 |
| TAT-QA | strict / content | 0.494 / 0.856 | 0.456 / 0.812 | 0.731 / 0.850 | 0.263 / 0.812 |
| FinQA | strict / content | 0.625 / 0.744 | 0.700 / 0.787 | 0.294 / 0.787 | 0.287 / 0.725 |
| MATH L5 | strict / content | 0.356 / 0.756 | 0.719 / 0.806 | 0.669 / 0.769 | 0.550 / 0.550 |
| MBPP | pass (strict = content) | 0.906 | 0.906 | 0.912 | 0.362 |
| GSM8K (60, 1 run) | strict | 0.867 (52/60) | - | - | - |
| NQ-open closed book (60, 1 run) | strict / F1 | 0.183 (11/60) / 0.287 | - | - | - |

HotpotQA run-1 F1: NoSkill 0.690, card 0.849, expert 0.861, neighbor 0.601.

### 4.2 Paired contrasts (mean difference [95% CI], items up/down, sign-test p)

| Candidate | card - NoSkill strict | card - NoSkill content | expert - card strict | expert - card content |
|---|---|---|---|---|
| HotpotQA | +0.119 [+0.062,+0.181] 17/1 p<0.001 | **+0.062 [+0.025,+0.106] 9/0 p=0.004** | +0.019 [-0.013,+0.056] 3/1 p=0.63 | +0.019 [0.000,+0.050] 2/0 p=0.50 |
| TAT-QA | -0.037 [-0.125,+0.050] 7/10 p=0.63 | -0.044 [-0.100,0.000] 1/4 p=0.38 | **+0.275 [+0.175,+0.375] 26/3 p<0.001** | +0.037 [-0.006,+0.087] 6/2 p=0.29 |
| FinQA | +0.075 [+0.019,+0.138] 10/1 p=0.012 | **+0.044 [0.000,+0.094] 8/1 p=0.039** | **-0.406 [-0.519,-0.287] 3/37 p<0.001** | 0.000 [-0.044,+0.044] 3/3 p=1.0 |
| MATH L5 | **+0.362 [+0.263,+0.463] 43/6 p<0.001** | +0.050 [-0.013,+0.113] 13/7 p=0.26 | -0.050 [-0.131,+0.031] 13/19 p=0.38 | -0.037 [-0.100,+0.025] 9/14 p=0.41 |
| MBPP | 0.000 [-0.044,+0.044] 3/3 | same | +0.006 [-0.025,+0.044] 2/2 | same |

### 4.3 Mechanisms (strict passes over both runs, cells)

- TAT-QA: on span answers that carry a scale, NoSkill 0/22, card 0/22, expert 14/22; on arithmetic answers with
  a scale, 34/62, 26/62, 52/62. The GLM-written card contains a self-contradicting line ("scale words in table
  headers usually do NOT need to be restated, but if the reference carries a scale, state it"; the solver never
  sees the reference) and does worse than NoSkill. The procedure that wrote the v3 seeds can garble a scoring
  convention stated in the public card.
- FinQA: percentage answers: NoSkill 63/84, card 67/84, expert **0/84**. Example: gold "35.9%", expert reply
  "35.91" (value right, % dropped). Plain-number answers: 36/70, 39/70, 41/70. Yes/no: 1/6, 6/6, 6/6.
- MATH: NoSkill omits the `<answer>` tag in 40/80 and 43/80 replies (it uses `\boxed` only). Intermediate Algebra
  2/38 -> card 21/38; Algebra 6/22 -> 20/22. All of this is tag compliance.
- HotpotQA: NoSkill omits the tag in 10/80 and 5/80 replies; bridge questions 67/122 -> card 83/122 -> expert
  85/122; comparison 26/38 -> 29/38 -> 30/38.
- Neighbor: on HotpotQA, 22/80 replies under the SearchQA seed were bare answers without a tag (for example
  "Monaco"); plausibly the seed's "minimal entity ... not a full sentence" line [inference, not tested]. On MBPP, the SpreadsheetBench seed made the model write openpyxl load/save programs, which
  crash with ModuleNotFoundError. On MATH, the LiveMath seed (option letters, five choices) lowered content
  accuracy, with replies 20% shorter (841 vs 1,053 completion tokens).

### 4.4 Noise, dead items, power

| Candidate | Strict flips run1 vs run2 (NoSkill / card / expert) | Identical reply text (of 80) | Dead (all 3 arms x 2 runs fail) | Always pass | Movable | Items for a 5-point paired effect (expert - card SD) |
|---|---|---|---|---|---|---|
| HotpotQA | 13 / 2 / 3 | 35 / 15 / 20 | 21 | 38 | 21 (26%) | 68 (SD 0.147) |
| TAT-QA | 5 / 5 / 3 | 34 / 20 / 24 | 15 | 27 | 38 (48%) | 666 (SD 0.460; effect-driven) |
| FinQA | 2 / 4 / 1 | 28 / 19 / 24 | 19 | 17 | 44 (55%) | 905 (SD 0.537; effect-driven) |
| MATH L5 | 17 / 21 / 17 | 3 / 4 / 5 | 7 | 16 | 57 (71%) | 424 (SD 0.367) |
| MBPP | 3 / 1 / 4 | 48 / 59 / 54 | 5 | 67 | 8 (10%) | 69 (SD 0.148) |

Formula: n = ((1.96 + 0.84) x SD / 0.05)^2. For TAT-QA and FinQA the SD is inflated by the large format effect
itself; a near-null rule contrast would have a smaller SD (not measured). For comparison, v3 SearchQA re-runs of
the same text moved 30/194 items (15.5%), and 50.3% of v3 trigger items were dead.

### 4.5 Transfer probe (neighbor arm; 1 run vs 2; unscoped replacement of the target's card)

| Target (source seed) | neighbor - card strict | neighbor - card content | neighbor - NoSkill content |
|---|---|---|---|
| HotpotQA (SearchQA) | -0.200 [-0.294,-0.113] 1/18 p<0.001 | -0.037 [-0.087,+0.013] 1/4 p=0.38 | +0.025 7/3 p=0.34 |
| TAT-QA (OfficeQA) | -0.194 [-0.300,-0.087] 4/21 p=0.001 | 0.000 6/6 | -0.044 4/7 p=0.55 |
| FinQA (OfficeQA) | -0.412 [-0.519,-0.306] 0/35 p<0.001 | -0.062 [-0.113,-0.019] 0/7 p=0.016 | -0.019 4/4 |
| MATH (LiveMath) | -0.169 [-0.281,-0.062] 12/26 p=0.034 | -0.256 [-0.362,-0.150] 5/28 p<0.001 | -0.206 7/24 p=0.003 |
| MBPP (SpreadsheetBench) | -0.544 [-0.656,-0.431] 1/44 p<0.001 | same | -0.544 2/45 |

## 5. Contamination probe [measured]

360 calls (50,721 tokens) on the same sampled TRAINING items: NoSkill layout, deepseek-v4-flash, 1 run, 4 cells
undelivered (excluded from the denominators). Script `scripts/probe_contam.py`. The first process stalled on
route latency (600 s read timeout) and was stopped after 258 cells. It was resumed with
`scripts/probe_contam_resume.py`: identical prompts, read timeout 180 s, 5 workers; existing cells were skipped,
so no cell was run twice.

| Probe | Benchmark | Result |
|---|---|---|
| Closed book (question only, no document) | FinQA | 1/80 strict, 2/80 lenient |
| | TAT-QA | 1/79 strict, 1/79 lenient |
| | HotpotQA | 25/78 strict (32%), 27/78 lenient (with the paragraphs, NoSkill scores 58.1% strict) |
| Verbatim continuation of the first half of the problem text | MATH L5 | 6/40 continue >= 8 words exactly; 1/40 reproduce the whole remainder; ROUGE-L F1 mean 0.42; 4/40 >= 0.8 |
| | GSM8K | 2/40 >= 8 words; 0/40 whole; ROUGE-L 0.37; 2/40 >= 0.8 |
| | MBPP | 1/39 >= 8 words (descriptions are one sentence, so the test is weak); 1/39 whole; ROUGE-L 0.09 |

Reading:
- FinQA and TAT-QA answers cannot be produced without the document (<= 2.5%), so the pilot's scores on them
  are not memorised answers.
- HotpotQA's 32% closed-book is Wikipedia world knowledge, as expected for a 2018 Wikipedia benchmark. About a
  third of items can be answered without reading, which caps how much a reading-strategy rule can matter there.
- MATH shows a verbatim-memorisation signal on 10-15% of level-5 training problems. No control set of
  post-cutoff problems was run, so the chance rate of formulaic overlap is unknown. This is one more reason not
  to use MATH as an evolve source.
- These probes say nothing about whether test splits were seen.

## 6. Interpretation for purpose 2 (evolve on one, evaluate on the rest)

- Where can a learned Skill show a measurable effect? Only where the failures are fixable by text, and on these
  candidates such failures are mostly scorer conventions (MATH tag; TAT-QA scale words; FinQA % sign; HotpotQA
  tag/span granularity). At content level the headroom over a good card is within +/-4 points everywhere. An
  "evolve on HotpotQA" chain can reach at most about 2-4 points of content gain over the card on its own panel.
  Detecting that at 80% power needs about 70-250 paired items with 2 runs.
- Where does an instruction transfer? Only when the target shares the source's output contract. The neighbor
  probe shows "similar topic" pairs with different contracts lose 17-54 points when the source text is applied
  without scoping. In the registered pairs, (searchqa, officeqa) and (officeqa, spreadsheetbench) differ in
  contract (short span vs document numeric vs code), and (officeqa, livemath) differs too (numeric vs option
  letter). The current five benchmarks are therefore a hard setting for positive transfer. A family that shares
  one scorer (multi-hop QA with SQuAD EM) is the friendliest.
- Contamination mostly shrinks headroom (more always-pass items) rather than biasing a paired arm contrast on
  the same items. It matters for claims about absolute ability, less for "rule vs card" deltas.
- Cost: HotpotQA cells cost 1.4-1.8k tokens, TAT-QA 0.6-1.2k, FinQA 1.1-1.9k, MBPP 0.2-0.6k, versus 4.7-7.9k
  (OfficeQA) and 28-106k (ALFWorld) in v3 training cells (`meta/v3_train_stats.json`). The same budget buys
  3-60x more items, which directly attacks v3's power problem (D5, D8).

## 7. Recommendation

1. **Benchmark set for a transfer experiment (purpose 2), best supported by this scan:**
   - Family A (shared contract, small but measurable): evolve on **HotpotQA** (train 90k; card arm flips 2/80;
     68 items per 5-point effect); evaluate on **2WikiMultihopQA** (Apache-2.0) and **MuSiQue** (CC BY 4.0),
     both short-span EM with supplied paragraphs and train splits, plus **SearchQA** (current). Dissimilar
     controls: MATH or MBPP (expect zero change; a drop would be negative transfer).
   - Family B (large learnable conventions, a real "no drop on similar" test): evolve on **TAT-QA**; evaluate on
     **FinQA** and **OfficeQA**. Expected learnable rule: state the scale word or percent sign as the scorer
     wants (+27.5 points strict on TAT-QA when a skill states it). Risk: that same rule transferred to FinQA is
     neutral at best, and the neighbor results predict harm unless it is gated by an applicability condition.
     This is useful as the honest "does it drop on similar targets?" check.
2. **Do not use** as evolve sources: MATH (21-26% run-to-run flips at temperature 0, contamination via SFT
   corpora, content headroom over card -3.7); MBPP (90.6% NoSkill, 8 movable items); GSM8K (86.7%); NQ-open
   closed book (49/60 dead). AIME, MATH-500, HumanEval(+), FRAMES and BrowseComp have no training split:
   targets only, and AIME is too small.
3. **Measurement rule (feeds D12):** transfer = target(card + transferred rules) vs target(card), on the
   target's own scorer, with the same items and 2 or more runs. Never let the source benchmark's text replace
   the target card. Report strict AND content scores, so a format convention is not sold as learned reasoning
   (the project rule "answer repair is not Skill evolution").
4. **Next pilot (<= 4M tokens, prepared but not run):** download the 2Wiki and MuSiQue train splits; one
   evolve-on-HotpotQA step with the v4 machinery (or a hand-written "learned-style" rule as a positive control);
   evaluate card vs card+rule on 100 HotpotQA + 100 2Wiki + 100 MuSiQue + 100 SearchQA training items x 2 runs
   (about 1,600 cells x ~1.8k = ~2.9M tokens).
5. **Card quality matters:** the GLM rewrite of a public card can garble scoring conventions (TAT-QA card below
   NoSkill). Check each seed against its card's scoring rule before using it as the "good instruction" baseline.

## 8. Risks and limitations

- One expert author (me), one GLM card per benchmark, 80 items, 2 runs. The expert results include a
  self-inflicted formatting error (FinQA). "Expert" is not an upper bound.
- My scorers approximate, but are not, the official TAT-QA/FinQA scripts. Strict-score effects depend on these
  conventions. The content score has its own fallback heuristics (last line or last `\boxed`).
- The neighbor arm is 1 run and is the unscoped worst case. A real Skill places rules under "Applies when"
  sections, so these losses overstate what a well-gated learned rule would do.
- Contamination: closed-book FinQA/TAT-QA ~1%, so no memorised answers; MATH shows verbatim recall on 4-6/40
  problems. The probes measure memorisation signals, not test-set membership, and have no post-cutoff control.
- The deepseek route snapshot is unknown (V4-Flash vs later variants); results may shift if the route changes.
- 26 undelivered or truncated cells (0.9%) were counted as fails.

## 9. Cost

Solver cells: 3,378,949 tokens (2,960 cells including 40 smoke). GLM cards: 4,268. Contamination probe: 50,721
(360 cells; at most 4 more in-flight calls were lost when the stalled process was stopped). Earlier
single-call route probes: negligible, no receipts. **Total about 3.43M tokens, within the 4M budget.** Per-cell
costs: see section 6.

## 10. Files

New machine `/data/feasibility/E3/`: `scripts/` (scan.py, texts.py, write_cards.py, download.py,
probe_contam.py, analysis.py, content_rescore.py, find_avail.sh, sizes.py), `items/` (sampled TRAINING items),
`cells/` (2,960 raw replies), `skills/` (cards + the v3 seeds used), `scores.json`, `report.json/.txt`,
`analysis.json/.out`, `content_rescore.json/.txt`, `probe/` + `probe_report.json`, `meta/` (licences,
HF cards, README metadata, availability scans, v3 training-cell stats, DeepSeek card facts),
`data/download_receipts.json`, `chain.log`.
Mac: this report.
