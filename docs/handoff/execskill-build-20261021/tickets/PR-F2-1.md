# Ticket PR-F2-1 → C7e (owner of `acceptance.py`): the §6.2 per-15-minute series is missing from every acceptance round

From PR-F2, 2026-10-22 14:2x. Statistics review finding 5, its §6.2 part; registration §6.2; registrar decision
2026-10-22 row "fixer-2 short answer". The fixer's notes (statistics row 5) and ticket fixer-2 cover only the §8.3
test-read table, so this part has no owner yet.

§6.2: "每格记派发与完成时间；按组、按 15 分钟报告简短回答比例、答案格式比例、回答长度" -- in every acceptance round, per arm
and per 15 minutes: the short-answer share, the answer-format share and the reply length. `acceptance.decide`
(`acceptance.py:637-720`) reports none of the three; the decision record has `second_call_rates`, `repair_call_rates`
and `worst_delivery_rates` only. Descriptive: it decides nothing, so no J1-J7 reading changes.

The short answer is now defined (registrar decision fixer-2): a cell whose completion tokens are below one quarter of
the median completion tokens of the same bench and arm in the unit's first time window. `readout.py` implements it for
the test read (PR-F2; notes `notes/PR-F2.md`):

- `_reply_tokens(cell)`: the mean visible completion tokens over the cell's logical calls; None ("without usage")
  when the cell made no call or a call has no count. Such cells are excluded and counted (`no_usage`).
- `_reference(first_window_cells)`: the median over the arm's window-0 cells with usage. No such cell, or a zero
  median, means no reference and `short_answer_share` None in every window. No constant and no later window stands in.
- `_windows(rows, start)` -> (reference, windows). It works on rows of the unsealed shape {`shared_with`, `dispatch_ts`,
  `format` (with `tag_present`), `completion_tokens` (one entry per logical call)}.

What `decide` would need: the round's cell records carry `logical_calls` (with `send_indices`), `sends` (with the
receipts), `judge.format` and `dispatch_ts`. The per-call count is `evaluation._completion_tokens(receipt)` of each
logical call's last send's receipt, the same rule `evaluation.sealed_cell` uses. Build those rows per arm (the
accept unit's first dispatch is `start`) and add a `windows` block per arm to the decision record. If you want to reuse
the readout helpers instead of a copy, ask the integrator for a public alias `readout.windows`
(`readout.py` is PR-F2's file in this batch).
