# Ticket fixer-2 → owner / registrar: §8.3 "short-answer share" has no registered definition

From the fixer (2026-10-22). Statistics review finding 5; registration §8.3.

§8.3 lists a "short-answer share" per time window in the per-arm table. The registration does not say what a short
answer is: it gives no token threshold, no character threshold and no reference to the reasoning trace.

What the code does now (`readout.arm_table`, `_windows`): for each window of `TIME_WINDOW_SECONDS` it reports
- `answer_tag_share`: the share of cells whose reply carried the registered answer carrier; and
- `mean_completion_tokens`: the mean completion tokens of the cells, read from the receipt.

The output labels these two measures under their own names. The code does not claim to compute the registered
"short-answer share".

Request: define the short answer, e.g. "completion tokens < X", or "an answer carrier with no reasoning text before
it". Then the readout can add that share next to the two measures above. Until then, §8.3's short-answer column is
open.
