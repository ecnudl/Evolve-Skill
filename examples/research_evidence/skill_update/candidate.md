## Mechanism

When a task supplies a natural-language specification plus one or a few public assertions, the assertions are samples, not the spec. An implementation can satisfy every public assertion while violating the stated semantics on inputs the examples do not cover (e.g., a "z not at start/end of the word" check implemented as `text[1:-1]` passes a single-word example but is wrong for multi-word or punctuation-adjacent inputs). The Skill therefore treats the prompt text as the authority and uses public assertions only as sanity checks, constructing additional boundary cases from the prompt's own wording before finalizing code.

## When
Apply when implementing or repairing a small Python artifact under a delivery contract (declared files only, entry function intact, no input mutation, file-section response format) where the task provides a prose specification and at least one public example. Also apply when interpreting paired feedback: a public case passing is not evidence of general correctness, and paired pass/pass or pass/fail outcomes with different code do not by themselves establish what caused any outcome.

## Procedure
1. **Read the prompt as the specification, not the existing code.** Diff the stated semantics against the current implementation before editing. Seeded or drafted code may be subtly wrong in ways a single public example cannot reveal.
2. **Derive boundary cases from the prose, not just the examples.** After the public assertions pass by hand, construct 2–4 additional inputs implied by the wording (empty/short inputs, multi-word inputs, punctuation, duplicates, negatives, all-equal values) and trace the implementation on them. If the prose mentions structure the example lacks (words, ordering, strictness), test that structure explicitly.
3. **Preserve the declared output shape.** Return exactly the required keys, names, and types; compute any audit values from the original, unmodified input.
4. **Never mutate inputs.** Iterate or copy; do not sort, reverse, or assign into caller-owned data.
5. **Deliver only file sections.** No text, JSON, or commentary outside the required format, even when no change is needed.
6. **Interpret feedback by category:**
   - `delivery_failure` with no observations: a protocol mistake; fix the format, the code was not judged.
   - Public-case pass: sanity only; do not treat it as proof the mechanism is general.
   - Unknown or unexecuted checks are neither passes nor failures.
   - Identical artifacts across roles, or divergent outcomes with equivalent code, show environment or evaluation variance, not a Skill effect; do not infer causality from such pairs.
7. **When a stage fails on delivery but revision passes semantically**, the lesson is about formatting, not the algorithm.

## Avoid
- Emitting anything outside the file-section delivery format.
- Assuming code is correct because the public example passes; single-example tasks especially under-constrain word-boundary, ordering, and strictness semantics.
- Treating a `not_detected` probe as a pass or a failure.
- Mutating inputs, editing non-editable files, or changing the entry function signature.
- Carrying one task's key names, parameter conventions, or audit fields into other tasks; re-read each contract.
- Claiming a Skill caused an improvement from paired outcomes alone; only executed, attributable evidence counts.
