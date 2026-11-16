# typed-v2 readout: chain G (open mode)

Generated 20261113T183849Z UTC from `/data/execskill-20261113-typed-v2`.

> Every acceptance in this run was decided by the practice-side gates (design §2: same-request noise threshold, card/program/no-harm decisions on practice slices). Nothing in this readout picks or recommends a configuration, and no test number fed back into learning. Test-panel numbers are generalization evidence only. Unknown outcomes are never scored as wrong: side L counts them as wrong and side H as right only to bound the accuracy, paired contrasts exclude them, and their counts are listed.

> Open mode: the owner opened the sealed test reads. Practice-side gates decided everything; these numbers are generalization evidence and select nothing.

- base card: historical (sealed `base_card`): every learned arm S1..S5 composes on the historical card C: a learned card is added to C, and a bench whose type learned nothing reads exactly C. The C row is the start of learning, not learned gain (C's own gain over C0 belongs to the hand-written card): typed-v2 starts from C, while the v2.24 SkillOpt / GEPA baselines started from an empty skill (and were read on 2026-11-07/08: cross-run, cross-date).

## Chain state

- status: complete; step: 5; paused: no
- schedule: learn_first; phase: —; current unit: —
- done units: 94
- ledger: cap 150000000, charged 48881121, reported 48149976, sends 21541, missing usage 0, stopped False (—), infra streak 0
- read plan: economy; plan 31882ef1ced9; reads settled 35 of 35 (fresh done 14 of 14 planned, aliases 21, fallbacks 0, voided aliases 0, pending 0, invalid 0)

| part | units | charged tokens | reported tokens |
|---|---|---|---|
| learning_units | 48 | 33232465 | 32734788 |
| read_units | 14 | 15648656 | 15415188 |

- economy: 21 pairs aliased, 0 fallbacks, 0 voided aliases (read tokens: fresh units only)

## Learning steps

### Step 0 (None)
- noise tau: not recorded
- gate decisions: none recorded
- library: empty

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|

### Step 1 (searchqa)
- noise tau: 3.0 points (SE 1.49, 3 runs per item, n 100, mixed items 10, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | True | accepted | 100 | 3 | — | +5.3 | 13/6/81 | — | 1.4907119849998598 | — | — | 3.0 | s1/noise |
| programs[0] | program | False | gain_below_tau | 100 | 3 | 96 | +2.1 | 7/2/87 | +2.0 | 1.4907119849998598 | 1.4731391274719738 | 1.5214515486254616 | 3.0 | s1/card-r1 (selected) |
| programs[1] | program | False | gain_below_tau | 100 | 3 | 96 | -1.4 | 6/6/84 | -1.3 | 1.4907119849998598 | 1.4731391274719738 | 1.5214515486254616 | 3.0 | s1/card-r1 (selected) |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | For quiz-show style clues requiring short canonical answers (1-3 words, e.g., Jeopardy). Use when a trivia clue is given with retrieved snippets; look for archived clue-answer pairs, match every constraint, and give shortest well-known form. Not for open-ended factual questions or tasks needing explanations. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5 | card-t01-s1 | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 300 | 300 | — | 632214 | 0 | 0 | 0 |
| noise | 300 | 300 | — | 458650 | 0 | 0 | 0 |
| outcomes | 100 | 100 | — | 150271 | 0 | 0 | 0 |
| outcomes-card | 100 | 100 | — | 206807 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 300 | 300 | — | 710184 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 7287 | 0 | 0 | 0 |
| program-2 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-2-gate | 300 | 300 | — | 644969 | 0 | 0 | 0 |
| program-2-smoke | 3 | 3 | — | 6527 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 2 (officeqa)
- noise tau: 8.81917103688197 points (SE 4.41, 3 runs per item, n 40, mixed items 14, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 40 | 3 | — | +3.3 | 10/9/21 | — | 3.72677996249965 | — | — | 7.4535599249993 | s2/noharm-t01 |
| cards[1] | card | False | gain_below_tau | 40 | 3 | — | +3.3 | 7/4/29 | — | 3.72677996249965 | — | — | 7.4535599249993 | s2/noharm-t01 |
| programs[0] | program | False | gain_below_tau | 40 | 3 | 25 | -1.3 | 4/5/16 | +2.5 | 3.72677996249965 | 4.618802153517006 | 4.714045207910317 | 7.4535599249993 | s2/noharm-t01 |
| programs[1] | program | False | gain_below_tau | 40 | 3 | 14 | +2.4 | 3/1/10 | +5.0 | 3.72677996249965 | 4.761904761904762 | 6.299407883487121 | 7.4535599249993 | s2/noharm-t01 |
| typing/no_harm[0] | no_harm | True | merged | 40 | 3 | — | -2.5 | 8/9/23 | — | 4.409585518440985 | — | — | 8.81917103688197 | s2/noise |

Shared type: the home type's members are searchqa (source); a candidate that passed the home rule was checked on each (no_regress, on the member's whole gate slice). Related gain is informational: it decides nothing beyond no_regress.
- no candidate of the step reached the member checks

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | For quiz-show style clues requiring short canonical answers (1-3 words, e.g., Jeopardy). Use when a trivia clue is given with retrieved snippets; look for archived clue-answer pairs, match every constraint, and give shortest well-known form. Not for open-ended factual questions or tasks needing explanations. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 120 | 120 | — | 992370 | 0 | 0 | 0 |
| card-r1-learn | 34 | 34 | — | 275473 | 0 | 0 | 0 |
| card-r2 | 120 | 120 | — | 861906 | 0 | 0 | 0 |
| member-searchqa-outcomes | 100 | 100 | — | 205934 | 0 | 0 | 0 |
| noharm-t01 | 120 | 120 | — | 840117 | 0 | 0 | 0 |
| noise | 120 | 120 | — | 812962 | 0 | 0 | 0 |
| outcomes | 34 | 34 | — | 218457 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 120 | 120 | — | 888221 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 17886 | 0 | 0 | 0 |
| program-2 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-2-gate | 120 | 120 | — | 840081 | 0 | 0 | 0 |
| program-2-smoke | 3 | 3 | — | 17648 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 3 (zebralogic)
- noise tau: 7.118052168020874 points (SE 3.56, 3 runs per item, n 100, mixed items 57, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 100 | 3 | — | +5.0 | 31/24/45 | — | 3.559026084010437 | — | — | 7.118052168020874 | s3/noise |
| cards[1] | card | False | gain_below_tau | 100 | 3 | — | +4.7 | 31/20/49 | — | 3.559026084010437 | — | — | 7.118052168020874 | s3/noise |
| programs[0] | program | True | accepted | 100 | 3 | 96 | +9.0 | 35/17/44 | +7.7 | 3.559026084010437 | 3.6416973894796927 | 3.632415786283895 | 7.118052168020874 | s3/noise |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | For quiz-show style clues requiring short canonical answers (1-3 words, e.g., Jeopardy). Use when a trivia clue is given with retrieved snippets; look for archived clue-answer pairs, match every constraint, and give shortest well-known form. Not for open-ended factual questions or tasks needing explanations. |
| prog-t02-s3-a | grid-puzzle-program-s3-a | program | t02 | 3 | — | Solves logic-grid (Einstein/Zebra) puzzles: N houses (2-8) with unique attributes per category, plus numbered clues. Parses clue types (position, adjacency, left/right, distance, same, not) and exhaustively searches for the unique solution, returning a table. Use only for house-based grid puzzles in the exact stated format; not for other logic puzzles, free-text reasoning, or non-unique solutions. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | — |
| t02 | puzzle_template | src-00d0c1e3 | — | prog-t02-s3-a |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 300 | 300 | — | 1593900 | 0 | 0 | 0 |
| card-r1-learn | 73 | 73 | — | 440655 | 0 | 0 | 0 |
| card-r2 | 300 | 300 | — | 1615887 | 0 | 0 | 0 |
| noise | 300 | 300 | — | 1480275 | 0 | 0 | 0 |
| outcomes | 73 | 73 | — | 368624 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 300 | 300 | — | 1193045 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 9976 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 4 (spreadsheetbench)
- noise tau: 8.2192186706253 points (SE 4.11, 3 runs per item, n 50, mixed items 19, model-side unknown runs 2, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 50 | 3 | — | +4.0 | 11/6/33 | — | 4.10960933531265 | — | — | 8.2192186706253 | s4/noise |
| cards[1] | card | False | gain_below_tau | 50 | 3 | — | +6.0 | 13/6/31 | — | 4.10960933531265 | — | — | 8.2192186706253 | s4/noise |
| programs[0] | program | False | smoke_fault | — | — | — | — | —/—/— | — | — | — | — | — | — |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | For quiz-show style clues requiring short canonical answers (1-3 words, e.g., Jeopardy). Use when a trivia clue is given with retrieved snippets; look for archived clue-answer pairs, match every constraint, and give shortest well-known form. Not for open-ended factual questions or tasks needing explanations. |
| prog-t02-s3-a | grid-puzzle-program-s3-a | program | t02 | 3 | — | Solves logic-grid (Einstein/Zebra) puzzles: N houses (2-8) with unique attributes per category, plus numbered clues. Parses clue types (position, adjacency, left/right, distance, same, not) and exhaustively searches for the unique solution, returning a table. Use only for house-based grid puzzles in the exact stated format; not for other logic puzzles, free-text reasoning, or non-unique solutions. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | — |
| t02 | puzzle_template | src-00d0c1e3 | — | prog-t02-s3-a |
| t03 | workbook_preview | src-c9138870 | — | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 150 | 150 | — | 464319 | 2 | 0 | 0 |
| card-r1-learn | 41 | 41 | — | 196228 | 0 | 0 | 0 |
| card-r2 | 150 | 150 | — | 530462 | 0 | 0 | 0 |
| noise | 150 | 150 | — | 507422 | 2 | 0 | 0 |
| outcomes | 41 | 41 | — | 108911 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 5209 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 5 (alfworld)
- noise tau: 3.3333333333333335 points (SE 1.67, 3 runs per item, n 40, mixed items 2, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 40 | 3 | — | -2.5 | 0/3/37 | — | 1.6666666666666667 | — | — | 3.3333333333333335 | s5/noise |
| cards[1] | card | False | gain_below_tau | 40 | 3 | — | -3.3 | 1/4/35 | — | 1.6666666666666667 | — | — | 3.3333333333333335 | s5/noise |
| programs[0] | program | False | never_fired | 40 | 3 | 0 | — | 0/0/0 | -0.8 | 1.6666666666666667 | — | — | 3.3333333333333335 | s5/noise |
| programs[1] | program | False | gain_below_tau | 40 | 3 | 40 | +0.0 | 1/1/38 | +0.0 | 1.6666666666666667 | 1.6666666666666667 | 1.6666666666666667 | 3.3333333333333335 | s5/noise |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | For quiz-show style clues requiring short canonical answers (1-3 words, e.g., Jeopardy). Use when a trivia clue is given with retrieved snippets; look for archived clue-answer pairs, match every constraint, and give shortest well-known form. Not for open-ended factual questions or tasks needing explanations. |
| prog-t02-s3-a | grid-puzzle-program-s3-a | program | t02 | 3 | — | Solves logic-grid (Einstein/Zebra) puzzles: N houses (2-8) with unique attributes per category, plus numbered clues. Parses clue types (position, adjacency, left/right, distance, same, not) and exhaustively searches for the unique solution, returning a table. Use only for house-based grid puzzles in the exact stated format; not for other logic puzzles, free-text reasoning, or non-unique solutions. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | — |
| t02 | puzzle_template | src-00d0c1e3 | — | prog-t02-s3-a |
| t03 | workbook_preview | src-c9138870 | — | — |
| t04 | admissible_commands | src-e2531270 | — | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 120 | 120 | — | 3565956 | 0 | 0 | 0 |
| card-r1-learn | 20 | 20 | — | 692870 | 0 | 0 | 0 |
| card-r2 | 120 | 120 | — | 3501661 | 0 | 0 | 0 |
| noise | 120 | 120 | — | 2127950 | 0 | 0 | 0 |
| outcomes | 20 | 20 | — | 413991 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 120 | 120 | — | 2319291 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 37512 | 0 | 0 | 0 |
| program-2 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-2-gate | 120 | 120 | — | 2296984 | 0 | 0 | 0 |
| program-2-smoke | 3 | 3 | — | 32292 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

## Event grid (accuracy L, unknown = wrong, %)

| event | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|
| C0 | 82.5 | 45.3 | =S2 73.5 u/i/c 0/0/0 | 66.7 | 87.3 |
| C | 82.5 | 50.6 | =S2 73.5 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| S1 | 88.8 | 49.4 | =S2 73.5 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| S2 | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | 73.5 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| S3 | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | =S5 82.0 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| S4 | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | =S5 82.0 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| S5 | 87.2 | 47.7 | 82.0 | 66.2 | 90.3 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667

## Test panels (opened by the owner; generalization evidence only; fresh units only)

### searchqa (common items of the fresh units 400)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 400 | 82.5 | 82.5 | 82.5 | 0 | 0 | 0.0 | 0.0 | 0.0 | 523707 |
| C (base of S1..S5) | 400 | 82.5 | 82.5 | 82.5 | 0 | 0 | 0.0 | 0.0 | 0.0 | 598044 |
| S1 | 400 | 88.8 | 88.8 | 88.8 | 0 | 0 | 93.5 | 93.5 | 0.0 | 823303 |
| S2 | same requests as S5 | =S5 87.2 | =S5 87.2 | =S5 87.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 87.2 | =S5 87.2 | =S5 87.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 87.2 | =S5 87.2 | =S5 87.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 400 | 87.2 | 87.2 | 87.2 | 0 | 0 | 92.2 | 92.2 | 0.0 | 820310 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S1-C0 | different (400 of 400 items) | 400 | 0 | +6.2 | 1.5 | [+3.2, +9.3] | [+3.2, +9.2] | 32/7/361 | 0 |
| S1-C | S1-C | different (374 of 400 items) | 400 | 0 | +6.2 | 1.4 | [+3.6, +8.9] | [+3.8, +9.0] | 28/3/369 | 0 |
| S2-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +4.8 | 1.5 | [+1.7, +7.8] | [+1.8, +7.8] | 29/10/361 | 0 |
| S2-C | S5-C | different (369 of 400 items) | 400 | 0 | +4.8 | 1.4 | [+2.1, +7.4] | [+2.0, +7.5] | 25/6/369 | 0 |
| S2-S1 | S5-S1 | different (5 of 400 items) | 400 | 0 | -1.5 | 0.7 | [-2.9, -0.1] | [-3.0, -0.2] | 1/7/392 | 0 |
| S3-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +4.8 | 1.5 | [+1.7, +7.8] | [+1.8, +7.8] | 29/10/361 | 0 |
| S3-C | S5-C | different (369 of 400 items) | 400 | 0 | +4.8 | 1.4 | [+2.1, +7.4] | [+2.0, +7.5] | 25/6/369 | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +4.8 | 1.5 | [+1.7, +7.8] | [+1.8, +7.8] | 29/10/361 | 0 |
| S4-C | S5-C | different (369 of 400 items) | 400 | 0 | +4.8 | 1.4 | [+2.1, +7.4] | [+2.0, +7.5] | 25/6/369 | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +4.8 | 1.5 | [+1.7, +7.8] | [+1.8, +7.8] | 29/10/361 | 0 |
| S5-C | S5-C | different (369 of 400 items) | 400 | 0 | +4.8 | 1.4 | [+2.1, +7.4] | [+2.0, +7.5] | 25/6/369 | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667
- same-request noise (fresh C vs C0, identical first inputs on 0 of 400 items): no identical requests
- fresh units (time range, returned model ids; R90): C0 2026-11-14T00:03:33..2026-11-14T00:13:20 models glm-5.3 400, C 2026-11-13T23:46:07..2026-11-13T23:54:34 models glm-5.3 400, S1 2026-11-13T23:28:17..2026-11-13T23:39:17 models glm-5.3 400, S5 2026-11-13T19:37:07..2026-11-13T19:44:28 models glm-5.3 400

### officeqa (common items of the fresh units 172)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 172 | 45.3 | 45.3 | 45.3 | 0 | 0 | 0.0 | 0.0 | 0.0 | 1197928 |
| C (base of S1..S5) | 172 | 50.6 | 50.6 | 50.6 | 0 | 0 | 0.0 | 0.0 | 0.0 | 1202959 |
| S1 | 172 | 49.4 | 49.4 | 49.4 | 0 | 0 | 68.0 | 68.0 | 0.0 | 1240607 |
| S2 | same requests as S5 | =S5 47.7 | =S5 47.7 | =S5 47.7 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 47.7 | =S5 47.7 | =S5 47.7 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 47.7 | =S5 47.7 | =S5 47.7 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 172 | 47.7 | 47.7 | 47.7 | 0 | 0 | 94.8 | 94.8 | 0.0 | 1314948 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S1-C0 | different (172 of 172 items) | 172 | 0 | +4.1 | 3.1 | [-2.1, +10.2] | [-2.3, +10.5] | 18/11/143 | 0 |
| S1-C | S1-C | different (117 of 172 items) | 172 | 0 | -1.2 | 2.7 | [-6.6, +4.2] | [-6.4, +4.1] | 10/12/150 | 0 |
| S2-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +2.3 | 3.0 | [-3.5, +8.2] | [-3.5, +8.1] | 15/11/146 | 0 |
| S2-C | S5-C | different (163 of 172 items) | 172 | 0 | -2.9 | 2.9 | [-8.6, +2.8] | [-8.7, +2.9] | 10/15/147 | 0 |
| S2-S1 | S5-S1 | different (56 of 172 items) | 172 | 0 | -1.7 | 3.2 | [-8.1, +4.7] | [-8.1, +4.7] | 14/17/141 | 0 |
| S3-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +2.3 | 3.0 | [-3.5, +8.2] | [-3.5, +8.1] | 15/11/146 | 0 |
| S3-C | S5-C | different (163 of 172 items) | 172 | 0 | -2.9 | 2.9 | [-8.6, +2.8] | [-8.7, +2.9] | 10/15/147 | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +2.3 | 3.0 | [-3.5, +8.2] | [-3.5, +8.1] | 15/11/146 | 0 |
| S4-C | S5-C | different (163 of 172 items) | 172 | 0 | -2.9 | 2.9 | [-8.6, +2.8] | [-8.7, +2.9] | 10/15/147 | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +2.3 | 3.0 | [-3.5, +8.2] | [-3.5, +8.1] | 15/11/146 | 0 |
| S5-C | S5-C | different (163 of 172 items) | 172 | 0 | -2.9 | 2.9 | [-8.6, +2.8] | [-8.7, +2.9] | 10/15/147 | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667
- same-request noise (fresh C vs C0, identical first inputs on 0 of 172 items): no identical requests
- fresh units (time range, returned model ids; R90): C0 2026-11-14T00:03:34..2026-11-14T00:36:15 models glm-5.3 172, C 2026-11-13T23:46:07..2026-11-14T00:03:29 models glm-5.3 172, S1 2026-11-13T23:28:13..2026-11-13T23:46:04 models glm-5.3 172, S5 2026-11-13T19:36:54..2026-11-13T19:56:54 models glm-5.3 172

### zebralogic (common items of the fresh units 200)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | same requests as S2 | =S2 73.5 | =S2 73.5 | =S2 73.5 | u/i/c 0/0/0 | — | — | — | — | — |
| C (base of S1..S5) | same requests as S2 | =S2 73.5 | =S2 73.5 | =S2 73.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S1 | same requests as S2 | =S2 73.5 | =S2 73.5 | =S2 73.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S2 | 200 | 73.5 | 73.5 | 73.5 | 0 | 0 | 0.0 | 0.0 | 0.0 | 1341549 |
| S3 | same requests as S5 | =S5 82.0 | =S5 82.0 | =S5 82.0 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 82.0 | =S5 82.0 | =S5 82.0 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 200 | 82.0 | 82.0 | 82.0 | 0 | 0 | 96.0 | 0.0 | 96.0 | 1077772 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S2-S2 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S1-C | S2-S2 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C0 | S2-S2 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C | S2-S2 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-S1 | S2-S2 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C0 | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S3-C | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S3-S2 | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S4-C0 | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S4-C | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S5-C | S5-S2 | different (192 of 200 items) | 200 | 0 | +8.5 | 3.7 | [+1.1, +15.9] | [+1.5, +16.0] | 37/20/143 | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667
- fresh units (time range, returned model ids; R90): S2 2026-11-13T22:06:32..2026-11-13T23:27:49 models glm-5.3 200, S5 2026-11-13T19:36:57..2026-11-13T20:37:19 models glm-5.3 392

### spreadsheetbench (common items of the fresh units 204)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 204 | 66.7 | 69.1 | 68.3 | 5 | 0 | 0.0 | 0.0 | 0.0 | 447530 |
| C (base of S1..S5) | same requests as S5 | =S5 66.2 | =S5 68.6 | =S5 67.8 | u/i/c 5/0/0 | — | — | — | — | — |
| S1 | same requests as S5 | =S5 66.2 | =S5 68.6 | =S5 67.8 | u/i/c 5/0/0 | — | — | — | — | — |
| S2 | same requests as S5 | =S5 66.2 | =S5 68.6 | =S5 67.8 | u/i/c 5/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 66.2 | =S5 68.6 | =S5 67.8 | u/i/c 5/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 66.2 | =S5 68.6 | =S5 67.8 | u/i/c 5/0/0 | — | — | — | — | — |
| S5 | 204 | 66.2 | 68.6 | 67.8 | 5 | 0 | 93.1 | 0.0 | 0.0 | 670659 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S5-C0 | different (204 of 204 items) | 197 | 7 | -1.0 | 3.3 | [-7.5, +5.5] | [-7.6, +5.6] | 20/22/155 | 0 |
| S1-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C0 | S5-C0 | different (204 of 204 items) | 197 | 7 | -1.0 | 3.3 | [-7.5, +5.5] | [-7.6, +5.6] | 20/22/155 | 0 |
| S2-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-S1 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C0 | S5-C0 | different (204 of 204 items) | 197 | 7 | -1.0 | 3.3 | [-7.5, +5.5] | [-7.6, +5.6] | 20/22/155 | 0 |
| S3-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (204 of 204 items) | 197 | 7 | -1.0 | 3.3 | [-7.5, +5.5] | [-7.6, +5.6] | 20/22/155 | 0 |
| S4-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (204 of 204 items) | 197 | 7 | -1.0 | 3.3 | [-7.5, +5.5] | [-7.6, +5.6] | 20/22/155 | 0 |
| S5-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667
- fresh units (time range, returned model ids; R90): C0 2026-11-14T00:03:35..2026-11-14T02:17:13 models glm-5.3 204, S5 2026-11-13T19:37:03..2026-11-13T21:01:32 models glm-5.3 204

### alfworld (common items of the fresh units 134)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 134 | 87.3 | 87.3 | 87.3 | 0 | 0 | 0.0 | 0.0 | 0.0 | 1741898 |
| C (base of S1..S5) | same requests as S5 | =S5 90.3 | =S5 90.3 | =S5 90.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S1 | same requests as S5 | =S5 90.3 | =S5 90.3 | =S5 90.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S2 | same requests as S5 | =S5 90.3 | =S5 90.3 | =S5 90.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 90.3 | =S5 90.3 | =S5 90.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 90.3 | =S5 90.3 | =S5 90.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 134 | 90.3 | 90.3 | 90.3 | 0 | 0 | 94.0 | 0.0 | 0.0 | 2413974 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S5-C0 | different (134 of 134 items) | 134 | 0 | +3.0 | 2.4 | [-1.7, +7.6] | [-1.5, +7.5] | 7/3/124 | 0 |
| S1-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C0 | S5-C0 | different (134 of 134 items) | 134 | 0 | +3.0 | 2.4 | [-1.7, +7.6] | [-1.5, +7.5] | 7/3/124 | 0 |
| S2-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-S1 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C0 | S5-C0 | different (134 of 134 items) | 134 | 0 | +3.0 | 2.4 | [-1.7, +7.6] | [-1.5, +7.5] | 7/3/124 | 0 |
| S3-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (134 of 134 items) | 134 | 0 | +3.0 | 2.4 | [-1.7, +7.6] | [-1.5, +7.5] | 7/3/124 | 0 |
| S4-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (134 of 134 items) | 134 | 0 | +3.0 | 2.4 | [-1.7, +7.6] | [-1.5, +7.5] | 7/3/124 | 0 |
| S5-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667
- fresh units (time range, returned model ids; R90): C0 2026-11-14T00:55:38..2026-11-14T02:37:34 models glm-5.3 2116, S5 2026-11-13T21:06:26..2026-11-13T22:06:05 models glm-5.3 1971

## Reference block (not same-phase, R89: point difference only; no SE, interval or counts)

No split contrast.

## 5x5 (rows = the bench evolved at step k, columns = the five panels; marks as in the legend)

S<k> - C0, mean paired difference in points (known pairs):

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | +6.2 | +4.1 | - | =S5 -1.0 u/i/c 5/0/0 | =S5 +3.0 u/i/c 0/0/0 |
| 2 | officeqa | =S5 +4.8 u/i/c 0/0/0 | =S5 +2.3 u/i/c 0/0/0 | - | =S5 -1.0 u/i/c 5/0/0 | =S5 +3.0 u/i/c 0/0/0 |
| 3 | zebralogic | =S5 +4.8 u/i/c 0/0/0 | =S5 +2.3 u/i/c 0/0/0 | =S5 +8.5 u/i/c 0/0/0 | =S5 -1.0 u/i/c 5/0/0 | =S5 +3.0 u/i/c 0/0/0 |
| 4 | spreadsheetbench | =S5 +4.8 u/i/c 0/0/0 | =S5 +2.3 u/i/c 0/0/0 | =S5 +8.5 u/i/c 0/0/0 | =S5 -1.0 u/i/c 5/0/0 | =S5 +3.0 u/i/c 0/0/0 |
| 5 | alfworld | +4.8 | +2.3 | +8.5 | -1.0 | +3.0 |
| in-run replicates |  | 0 | 0 | 0 | 0 | 0 |

S<k> - C, mean paired difference in points (known pairs):

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | +6.2 | -1.2 | - | - | - |
| 2 | officeqa | =S5 +4.8 u/i/c 0/0/0 | =S5 -2.9 u/i/c 0/0/0 | - | - | - |
| 3 | zebralogic | =S5 +4.8 u/i/c 0/0/0 | =S5 -2.9 u/i/c 0/0/0 | =S5 +8.5 u/i/c 0/0/0 | - | - |
| 4 | spreadsheetbench | =S5 +4.8 u/i/c 0/0/0 | =S5 -2.9 u/i/c 0/0/0 | =S5 +8.5 u/i/c 0/0/0 | - | - |
| 5 | alfworld | +4.8 | -2.9 | +8.5 | - | - |
| in-run replicates |  | 0 | 0 | 0 | 0 | 0 |

Accuracy of S<k> on L (unknown = wrong), %:

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | 88.8 | 49.4 | =S2 73.5 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 2 | officeqa | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | 73.5 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 3 | zebralogic | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | =S5 82.0 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 4 | spreadsheetbench | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | =S5 82.0 u/i/c 0/0/0 | =S5 66.2 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 5 | alfworld | 87.2 | 47.7 | 82.0 | 66.2 | 90.3 |

Accuracy of S<k> on H (unknown = right), %:

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | 88.8 | 49.4 | =S2 73.5 u/i/c 0/0/0 | =S5 68.6 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 2 | officeqa | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | 73.5 | =S5 68.6 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 3 | zebralogic | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | =S5 82.0 u/i/c 0/0/0 | =S5 68.6 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 4 | spreadsheetbench | =S5 87.2 u/i/c 0/0/0 | =S5 47.7 u/i/c 0/0/0 | =S5 82.0 u/i/c 0/0/0 | =S5 68.6 u/i/c 5/0/0 | =S5 90.3 u/i/c 0/0/0 |
| 5 | alfworld | 87.2 | 47.7 | 82.0 | 68.6 | 90.3 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value
- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667

## Continual-learning metrics (economy: terms through the resolver; S0 := C, the start of learning)

Side L:

| bench | home step | final | n | final % | C0 % | C % | gain vs C0 | gain vs C | forgetting | forgetting after home | backward transfer | forward transfer | plasticity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| searchqa | 1 | S5 | 400 | 87.2 | 82.5 | 82.5 | +4.8 | +4.8 | +1.5 | +1.5 | -1.5 | — | +6.2 |
| officeqa | 2 | S5 | 172 | 47.7 | 45.3 | 50.6 | +2.3 | -2.9 | +1.7 | - (3 by-construction terms) | - | -1.2 | -1.7 |
| zebralogic | 3 | S5 | 200 | 82.0 | =S2 73.5 u/i/c 0/0/0 | =S2 73.5 u/i/c 0/0/0 | +8.5 | +8.5 | - (2 by-construction terms; other classes max -8.5, not above 0) | - (2 by-construction terms) | - | - | +8.5 |
| spreadsheetbench | 4 | S5 | 204 | 66.2 | 66.7 | =S5 66.2 u/i/c 5/0/0 | -0.5 | - | - (4 by-construction terms) | - (1 by-construction term) | - | - | - |
| alfworld | 5 | S5 | 134 | 90.3 | 87.3 | =S5 90.3 u/i/c 0/0/0 | +3.0 | - | - (4 by-construction terms) | — | — | - | - |
| macro (a) |  |  |  | 74.7 (n 5, 0 via representatives) | 71.1 (n 5, 1 via representatives) | 72.6 (n 5, 3 via representatives) | +3.6 (0 of 5 structural) | +2.1 (2 of 5 structural) | +0.6 (3 of 5 structural) | +0.4 (3 of 4 structural) | -0.4 (3 of 4 structural) | -0.3 (3 of 4 structural) | +2.6 (2 of 5 structural) |
| macro (b) |  |  |  | 74.7 (n 5, 0 via representatives) | 71.1 (n 5, 1 via representatives) | 72.6 (n 5, 3 via representatives) | +3.6 (n = 5 of 5) | +3.4 (n = 3 of 5) | +1.6 (n = 2 of 5) | +1.5 (n = 1 of 4) | -1.5 (n = 1 of 4) | -1.2 (n = 1 of 4) | +4.3 (n = 3 of 5) |

Side H:

| bench | home step | final | n | final % | C0 % | C % | gain vs C0 | gain vs C | forgetting | forgetting after home | backward transfer | forward transfer | plasticity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| searchqa | 1 | S5 | 400 | 87.2 | 82.5 | 82.5 | +4.8 | +4.8 | +1.5 | +1.5 | -1.5 | — | +6.2 |
| officeqa | 2 | S5 | 172 | 47.7 | 45.3 | 50.6 | +2.3 | -2.9 | +1.7 | - (3 by-construction terms) | - | -1.2 | -1.7 |
| zebralogic | 3 | S5 | 200 | 82.0 | =S2 73.5 u/i/c 0/0/0 | =S2 73.5 u/i/c 0/0/0 | +8.5 | +8.5 | - (2 by-construction terms; other classes max -8.5, not above 0) | - (2 by-construction terms) | - | - | +8.5 |
| spreadsheetbench | 4 | S5 | 204 | 68.6 | 69.1 | =S5 68.6 u/i/c 5/0/0 | -0.5 | - | - (4 by-construction terms) | - (1 by-construction term) | - | - | - |
| alfworld | 5 | S5 | 134 | 90.3 | 87.3 | =S5 90.3 u/i/c 0/0/0 | +3.0 | - | - (4 by-construction terms) | — | — | - | - |
| macro (a) |  |  |  | 75.2 (n 5, 0 via representatives) | 71.6 (n 5, 1 via representatives) | 73.1 (n 5, 3 via representatives) | +3.6 (0 of 5 structural) | +2.1 (2 of 5 structural) | +0.6 (3 of 5 structural) | +0.4 (3 of 4 structural) | -0.4 (3 of 4 structural) | -0.3 (3 of 4 structural) | +2.6 (2 of 5 structural) |
| macro (b) |  |  |  | 75.2 (n 5, 0 via representatives) | 71.6 (n 5, 1 via representatives) | 73.1 (n 5, 3 via representatives) | +3.6 (n = 5 of 5) | +3.4 (n = 3 of 5) | +1.6 (n = 2 of 5) | +1.5 (n = 1 of 4) | -1.5 (n = 1 of 4) | -1.2 (n = 1 of 4) | +4.3 (n = 3 of 5) |

- terms: as in the module docstring with S0 := C (the start of learning: C under base historical, C0 under format), each term through the resolver
- macro: two pre-registered columns: (a) the mean over the benches where the term is defined, structural zeros and noise samples entered as 0 (k structural, m noise samples); (b) the mean over the measured benches only (n); an incomplete term counts as pending. A macro with a split term prints mixed: k same-phase, m split, no mean. A comparison with a five-bench baseline uses (a); neither is comparable with a full run's maximum over noisy readings
- forgetting: RP4: when an earlier event shares the final event's class (or, a noise sample, its requests), the measured maximum over the other classes if above 0, else - with the count of by-construction terms (JSON value 0, kind structural); without such events the signed measured maximum; split terms and noise samples are listed beside and never enter the maximum; an earlier event without a reading (pending, invalid, void_alias) leaves the maximum undefined (kind incomplete, the missing events and the maximum of the others listed)
- structural: a continual-learning term between two events of one class is a structural 0 (kind structural), never a sample (R70)
- noise sample: a continual-learning term between two same-phase fresh units whose requests are identical on every item (a fallback class, a re-read of a voided alias, a void plan) is a noise sample, not an effect (R67): kind noise_sample, value null, its reading as reference; by construction 0 like a structural term, so it never enters a maximum and a macro counts it apart
- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667

## Generalization view (S<k> minus the previous state; informational, it decides nothing)

- S<k> minus the previous state on every bench (S0 = the base row: C under base historical, C0 under format), from the representatives; home = the bench evolved at step k, same-type = a bench with a source in the home bench's type in s<k>/typemap.json, routed n/N = any other bench n of whose N panel items the fresh unit standing for S<k> (its own or its representative's: same requests) routed into the home type (a bench not learned yet with the home bench's signature, or an earlier bench routed into the type, RP15), other-type = every other bench. Informational: it decides nothing

| step | home bench | previous | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|---|
| S1 | searchqa | C | +6.2 (home) | -1.2 (routed 117/172) | - (other) | - (other) | - (other) |
| S2 | officeqa | S1 | -1.5 (same) | -1.7 (home) | - (other) | - (other) | - (other) |
| S3 | zebralogic | S2 | - (other) | - (other) | +8.5 (home) | - (other) | - (other) |
| S4 | spreadsheetbench | S3 | - (other) | - (other) | - (other) | - (home) | - (other) |
| S5 | alfworld | S4 | - (other) | - (other) | - (other) | - (other) | - (home) |

- (home) the bench evolved at the step; (same) a bench with a source in its type; (routed n/N) n of the bench's N panel items were routed into the home type, so the step's skills reach them; (other) every other bench; - : same requests (the step changed nothing on that panel); split: see the reference block
- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 1.4907119849998598; s2 tau 8.81917103688197 / SE 4.409585518440985; s3 tau 7.118052168020874 / SE 3.559026084010437; s4 tau 8.2192186706253 / SE 4.10960933531265; s5 tau 3.3333333333333335 / SE 1.6666666666666667

## Read classes (economy plan 31882ef1ced9)

| bench | class | members | representative | plan status | fallback reason | settled | post-read check equal/unequal | representative u/i/c |
|---|---|---|---|---|---|---|---|---|
| searchqa | 1 | {C0} | C0 | ok | — | C0 fresh | —/— of — | 0/0/0 |
| searchqa | 2 | {C} | C | ok | — | C fresh | —/— of — | 0/0/0 |
| searchqa | 3 | {S1} | S1 | ok | — | S1 fresh | —/— of — | 0/0/0 |
| searchqa | 4 | {S2, S3, S4, S5} | S5 | ok | — | S2 alias, S3 alias, S4 alias, S5 fresh | 400/0 of 400 | 0/0/0 |
| officeqa | 1 | {C0} | C0 | ok | — | C0 fresh | —/— of — | 0/0/0 |
| officeqa | 2 | {C} | C | ok | — | C fresh | —/— of — | 0/0/0 |
| officeqa | 3 | {S1} | S1 | ok | — | S1 fresh | —/— of — | 0/0/0 |
| officeqa | 4 | {S2, S3, S4, S5} | S5 | ok | — | S2 alias, S3 alias, S4 alias, S5 fresh | 172/0 of 172 | 0/0/0 |
| zebralogic | 1 | {C0, C, S1, S2} | S2 | ok | — | C0 alias, C alias, S1 alias, S2 fresh | 200/0 of 200 | 0/0/0 |
| zebralogic | 2 | {S3, S4, S5} | S5 | ok | — | S3 alias, S4 alias, S5 fresh | 200/0 of 200 | 0/0/0 |
| spreadsheetbench | 1 | {C0} | C0 | ok | — | C0 fresh | —/— of — | 5/0/0 |
| spreadsheetbench | 2 | {C, S1, S2, S3, S4, S5} | S5 | ok | — | C alias, S1 alias, S2 alias, S3 alias, S4 alias, S5 fresh | 204/0 of 204 | 5/0/0 |
| alfworld | 1 | {C0} | C0 | ok | — | C0 fresh | —/— of — | 0/0/0 |
| alfworld | 2 | {C, S1, S2, S3, S4, S5} | S5 | ok | — | C alias, S1 alias, S2 alias, S3 alias, S4 alias, S5 fresh | 134/0 of 134 | 0/0/0 |

## Mount check (F2-style: every read records what it mounted)

- rule: every read records what it mounted, and every mounted skill exists in that step's frozen library (the main-v9 F2 identity defect: a card never mounted went unnoticed)
- scope: fresh units only (R72); alias rows are planned
- all present: True

| read | cells | mount records | present | typed % | card mounted % | skills seen | ids not in the step library |
|---|---|---|---|---|---|---|---|
| C0-searchqa | 400 | 400 | True | 0.0 | 0.0 | — | — |
| C-searchqa | 400 | 400 | True | 0.0 | 0.0 | — | — |
| S1-searchqa | 400 | 400 | True | 93.5 | 93.5 | card-t01-s1 | — |
| S5-searchqa | 400 | 400 | True | 92.2 | 92.2 | card-t01-s1 | — |
| C0-officeqa | 172 | 172 | True | 0.0 | 0.0 | — | — |
| C-officeqa | 172 | 172 | True | 0.0 | 0.0 | — | — |
| S1-officeqa | 172 | 172 | True | 68.0 | 68.0 | card-t01-s1 | — |
| S5-officeqa | 172 | 172 | True | 94.8 | 94.8 | card-t01-s1 | — |
| S2-zebralogic | 200 | 200 | True | 0.0 | 0.0 | — | — |
| S5-zebralogic | 200 | 200 | True | 96.0 | 0.0 | prog-t02-s3-a | — |
| C0-spreadsheetbench | 204 | 204 | True | 0.0 | 0.0 | — | — |
| S5-spreadsheetbench | 204 | 204 | True | 93.1 | 0.0 | — | — |
| C0-alfworld | 134 | 134 | True | 0.0 | 0.0 | — | — |
| S5-alfworld | 134 | 134 | True | 94.0 | 0.0 | — | — |

Alias pairs (planned, from the plan; no cell of their own):

| pair | of | items | typed | unknown | with card | with programs | source |
|---|---|---|---|---|---|---|---|
| C0-zebralogic | S2 | 200 | 0 | 0 | 0 | 0 | planned |
| C-zebralogic | S2 | 200 | 0 | 0 | 0 | 0 | planned |
| C-spreadsheetbench | S5 | 204 | 0 | 0 | 0 | 0 | planned |
| C-alfworld | S5 | 134 | 0 | 0 | 0 | 0 | planned |
| S1-zebralogic | S2 | 200 | 0 | 200 | 0 | 0 | planned |
| S1-spreadsheetbench | S5 | 204 | 0 | 204 | 0 | 0 | planned |
| S1-alfworld | S5 | 134 | 0 | 134 | 0 | 0 | planned |
| S2-searchqa | S5 | 400 | 369 | 31 | 369 | 0 | planned |
| S2-officeqa | S5 | 172 | 163 | 9 | 163 | 0 | planned |
| S2-spreadsheetbench | S5 | 204 | 0 | 204 | 0 | 0 | planned |
| S2-alfworld | S5 | 134 | 0 | 134 | 0 | 0 | planned |
| S3-searchqa | S5 | 400 | 369 | 31 | 369 | 0 | planned |
| S3-officeqa | S5 | 172 | 163 | 9 | 163 | 0 | planned |
| S3-zebralogic | S5 | 200 | 192 | 8 | 0 | 192 | planned |
| S3-spreadsheetbench | S5 | 204 | 0 | 204 | 0 | 0 | planned |
| S3-alfworld | S5 | 134 | 0 | 134 | 0 | 0 | planned |
| S4-searchqa | S5 | 400 | 369 | 31 | 369 | 0 | planned |
| S4-officeqa | S5 | 172 | 163 | 9 | 163 | 0 | planned |
| S4-zebralogic | S5 | 200 | 192 | 8 | 0 | 192 | planned |
| S4-spreadsheetbench | S5 | 204 | 190 | 14 | 0 | 0 | planned |
| S4-alfworld | S5 | 134 | 0 | 134 | 0 | 0 | planned |

---
Practice-side gates decided every acceptance; no configuration was picked from these numbers.
