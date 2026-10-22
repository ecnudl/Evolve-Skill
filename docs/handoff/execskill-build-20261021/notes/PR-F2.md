# PR-F2 notes: ticket fixer-2, the §8.3 short answer (route B, `fivebench-execskill-v1`)

Written by PR-F2 on 2026-10-22. Binding sources: the registrar decision row "fixer-2 short answer"
(`docs/handoff/execskill-registrar-decisions-20261022.md`); its 13:0x addendum (built now, reviewed in the same single
Codex round); registration §6.2 and §8.3; statistics review finding 5; ticket `tickets/fixer-2.md`. This build closes
ticket fixer-2 (the decision plus its implementation).

负责人摘要：测试读取的每组表里加上了“简短回答比例”。简短回答指这样一格：它的回答长度不到本 bench、本组在第一个 15 分钟窗口里中位长度的四分之一。
有三种情况不报比例，写“无”而不写 0：第一个窗口里没有这组的格；中位数是 0；某一格没有 token 记录（这种格单独计数）。

## How the work was done

- No model calls. No network use except SSH to dl. No git writes. No test pool was read and no frozen file was edited.
- I edited only `readout.py`, `tests/test_execskill_readout.py`, my two notes files and my ticket.
- The mutation copy `/tmp/PR-F2-mut` on dl has been deleted.

## The registered definition, and how the code reads it

- **Registered rule:** "A short answer is a cell whose completion tokens are below one quarter of the median
  completion tokens of the same bench and arm in the unit's first time window. The readout reports
  `short_answer_share` per window next to `answer_tag_share` and `mean_completion_tokens`."
- **Unit and first window.** The test read has one evaluation unit per bench (§8.1), and `arm_table(cells)` takes the
  cells of one bench. So the unit's first time window is window 0 of `_windows`: from the first dispatch of any cell in
  the bench's unit, for `TIME_WINDOW_SECONDS` = 900 s (§6.2).
- **Same bench and arm.** Each arm of the table has its own reference: F, C, P_F, T_F and every twin
  `withhold:<p>`. The reference uses the arm's cells that sent requests, the same cells the windows already count. A
  structural-zero shared cell sent nothing, so it stays out, as before.
- **A cell's completion tokens.** This is an implementation reading, because the registration says nothing about cells
  with several calls. The value is the mean visible completion tokens over the cell's logical calls; on a one-call
  cell that is the reply's count.
  - Why: a route-B cell can make several logical calls: `first` + `second` after `<calc>`, `first` + `repair` on
    SpreadsheetBench, one `step` per ALFWorld step, or a restarted episode. With a sum, the number of calls would
    become part of the measure. An ALFWorld episode won in 5 steps would then count as a short answer against a
    median of longer episodes.
  - The per-call mean is also the scale of the existing `mean_completion_tokens`.
  - Test 2 pins it: mutating the mean into a sum makes that test fail.
- **"Below".** The comparison is strict and exact (Fractions): `t < median / 4`. A cell at exactly a quarter is not
  short.
- **Constant.** `SHORT_ANSWER = Fraction(1, 4)` stays in `readout.py` with its citation. It is the registered quarter
  itself, so it is not a `protocol.py` constant (the task allows this). No other constant was added.

## Edge cases (each one is defined here and tested)

1. **No cell with usage of the arm in the unit's first window.** This happens to a twin arm, to an F arm that shares
   most of its cells on the bench, or in a fixture that is not interleaved.
   - The reference is undefined: `status` is `"no_cell_with_usage"`, and `short_answer_share` is None in every window
     of that arm.
   - Nothing stands in for it: neither a constant (such as D11's "≤ 12 tokens") nor a later window. Either one would
     be a different definition from the registered one.
2. **Zero median** (`status` `"zero_median"`).
   - A quarter of 0 marks no cell, so the literal share would be 0.0 in every window. That would falsely read as "no
     short answers" while the reference itself is degenerate (most first-window replies are empty).
   - The share is reported as None, next to the status and the median 0, never as 0.0.
3. **Cells without usage.** A cell has no usage when it made no logical call, or when any of its calls lacks a
   non-negative integer count (a `completion_tokens` entry None, as `evaluation._completion_tokens` returns for a
   receipt without usage).
   - Such a cell is left out of the median and out of the window's share, and is counted as `no_usage` in the window
     and in the reference.
   - A partly counted cell is left out whole, because a partial mean is not the cell's count.
   - A negative count is also treated as no usage.
4. **Shared cells.** Unchanged: they are in no window and are not counted in `no_usage`.

## Output shape (public API)

- `arm_table(cells)[arm]` gains the field `"short_answer_reference"`, with these keys:
  - `"window"`: 0;
  - `"cells"`: n (first-window cells with usage);
  - `"no_usage"`: k;
  - `"median"`: a float, or None;
  - `"status"`: `"defined"`, `"no_cell_with_usage"` or `"zero_median"`.
- Every window gains `"short_answer_share"` (a float or None) and `"no_usage"` (an int). They sit next to the unchanged
  `"cells"`, `"answer_tag_share"` and `"mean_completion_tokens"`. The share's denominator is `cells - no_usage`.
- The sealed `readout(...)` record carries the new fields in `arms[bench][arm]`. All of them are JSON floats or ints;
  the sealed record is checked with `verified` in test 6.
- No new public function. `_reply_tokens`, `_median` and `_reference` are private. `_windows` (private, called only by
  `arm_table`) now returns (reference, windows).

## Files changed

- `skillopt/execskill/readout.py`
  - :34-38 module docstring, the `arm_table` bullet;
  - :70-72 `SHORT_ANSWER`;
  - :420-428 `_reply_tokens`;
  - :431-434 `_median`;
  - :437-448 `_reference`;
  - :451-474 `_windows`;
  - :476-499 `arm_table` (docstring; reference and windows).
- `tests/test_execskill_readout.py`
  - :9 imports `TIME_WINDOW_SECONDS`;
  - :211-299 the helpers `windowed` and `shares` and six tests, `test_fixer_2_*`:
    1. a short answer is below a quarter of its arm's first-window median (per arm; strict);
    2. a multi-call cell counts its mean per call, so an early ALFWorld win is not a short answer;
    3. an arm without a cell with usage in the unit's first window gets no share, and nothing stands in;
    4. a zero median gives None, not 0;
    5. cells without usage are left out and counted, and shared cells stay out;
    6. the sealed readout carries the columns.
- `docs/handoff/execskill-build-20261021/tickets/PR-F2-1.md`, `notes/PR-F2-progress.md` and `notes/PR-F2.md`.

## Tests (dl, `/root/continual-alf-prep-20260928/env/bin/python`)

- `tests/test_execskill_readout.py`: **17 passed**, the 11 existing tests unchanged plus the 6 new ones.
- `tests/test_execskill_integration_b5.py`: **1 passed**.
- `tests/test_execskill_e2e.py`: **11 passed** (321.6 s). Both of these call `readout.readout` on unsealed cells from
  the offline pipeline, so the new code runs on the real cell shape.
- Mutation check on a throwaway copy: there were 7 mutants, and each one was killed by its named test:

  | Mutant | Killed by |
  |---|---|
  | sum instead of the per-call mean | test 2 |
  | `<=` instead of `<` | test 1 |
  | the first non-empty window stands in | test 3 |
  | a zero median gives a share | test 4 |
  | partly counted cells measured | test 5 |
  | negative count accepted | test 5 |
  | shared cells counted | test 5 |
- Not run:
  - the whole suite (left to the integrator);
  - `tests/test_execskill_smoke_rehearsal.py`, which pins the code map. `readout.py` changed, so the integrator has to
    re-pin it.

## Deviations

None from the registered row. The four implementation readings below are stated in the docstrings and here, for the
single Codex round:

1. the per-call mean for cells with several calls;
2. a zero median gives None;
3. an empty first window gives None;
4. a partly counted cell counts as a cell without usage.

## Tickets

- **PR-F2-1 → C7e.** §6.2 also asks for the same series in every acceptance round: per arm and per 15 minutes, the
  short-answer share, the answer-format share and the reply length. `acceptance.decide` reports none of them. They
  are descriptive only and decide nothing. The ticket describes how the round's cell records provide the per-call
  counts.

## Not done / open

- The acceptance-round series (PR-F2-1).
- `mean_completion_tokens` is unchanged. It is a mean per call over integer counts, and it still includes the counted
  calls of a partly counted cell, so its cells can differ slightly from those of the short-answer share. The ticket
  did not ask for a change.
- Should 1/4 move into `protocol.py` with the other registered constants? That is the integrator's call. Decision
  A10-1 / C1-1 moved the constants it listed, and this one was not among them.
- Reporting: in small units, arms with no first-window cell (mostly twin arms) get None by rule. The pilot report
  should show the reference `status` next to each such None.
