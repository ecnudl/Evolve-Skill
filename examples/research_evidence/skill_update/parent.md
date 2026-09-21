## When

Apply this Skill when repairing a small Python artifact (e.g., `logic.py`) under a strict delivery contract: only declared files may change, the entry module/function must stay intact, inputs must never be mutated, and the response must contain file sections with no stray commentary. The evidence comes from paired closed-trajectory feedback where each task has a generation stage and a revision stage, plus private probe executions.

## Procedure

1. **Read the prompt as the specification, not the existing code.** In both observed tasks the seeded code was subtly wrong relative to the prompt (inclusive instead of exclusive prefix products; `<=` instead of `<` for a strictly increasing run). Diff the prompt's stated semantics against the current implementation before editing:
   - "ONLY values strictly BEFORE that index" → append the running product *before* multiplying; first element is the identity (1).
   - "STRICTLY increasing" → use `previous < x`, not `<=`; equal neighbors reset the run; empty input yields 0.
2. **Preserve the declared output shape and audits.** Return exactly the required keys (here: `result`, `input_count`, `input_sum`), with `input_count = len(values)` and `input_sum = sum(values)` computed from the *original* input. Do not add, rename, or drop keys.
3. **Never mutate input data.** Iterate or copy; do not sort, reverse, or assign into `data` or its lists. The harness fingerprints inputs before/after and fails mutation.
4. **Honor unused parameters.** If the prompt says a field (e.g., `k`) is unused, do not let it affect logic — but still read it only if safe; ignoring it entirely is fine.
5. **Deliver only file sections.** A response consisting of anything outside the file-section format (even a short JSON action like `{"action":"keep"}`) triggers `delivery_contract` failure: "unexpected commentary outside file sections". If a stage asks for no change, emit the files in the required section format (or an empty valid delivery per the contract), never free-form text or JSON.
6. **Verify against public cases, then reason about boundaries.** Check the two public cases by hand, then test edge conditions implied by the prompt: empty input, all-equal values, zeros, negatives, maximum length. Negative values are legitimate inputs, not errors.
7. **Interpret feedback by category:**
   - `delivery_failure` with no observations: a protocol mistake; fix the response format, the code was never judged.
   - `semantic_pass` on all cases including private ones: the mechanism is consistent with the spec, but this is not proof of generality — keep the reasoning, not just the code.
   - Probe outcomes (`not_detected`) are unexecuted-or-nondetecting checks, not confirmations of correctness.
8. **When a stage fails on delivery but the revision passes semantically**, the delivery guard retains the valid artifact; the lesson is about formatting, not about the algorithm.

## Avoid

- Emitting any text outside the file-section delivery format, including JSON action objects, notes, or explanations.
- Assuming the seeded code is correct because public cases pass; the seeded bugs were off-by-one/inclusion errors invisible without reading the prompt.
- Treating a passing public case as proof, or a `not_detected` probe as a failure (or as a pass).
- Mutating inputs, changing non-editable files (e.g., `api.py`), or altering the entry function signature.
- Turning this task's conventions (specific key names, the `k` parameter, exact audit fields) into rules for other tasks; re-read each task's own contract.
- Claiming the Skill caused an improvement when anchor and current artifacts are identical; only executed receipts count as evidence.
