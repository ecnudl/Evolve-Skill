# typed-v2 readout: chain D (open mode)

Generated 20261113T130845Z UTC from `/data/execskill-20261113-typed-v2`.

> Every acceptance in this run was decided by the practice-side gates (design §2: same-request noise threshold, card/program/no-harm decisions on practice slices). Nothing in this readout picks or recommends a configuration, and no test number fed back into learning. Test-panel numbers are generalization evidence only. Unknown outcomes are never scored as wrong: side L counts them as wrong and side H as right only to bound the accuracy, paired contrasts exclude them, and their counts are listed.

> Open mode: the owner opened the sealed test reads. Practice-side gates decided everything; these numbers are generalization evidence and select nothing.

- base card: historical (sealed `base_card`): every learned arm S1..S5 composes on the historical card C: a learned card is added to C, and a bench whose type learned nothing reads exactly C. The C row is the start of learning, not learned gain (C's own gain over C0 belongs to the hand-written card): typed-v2 starts from C, while the v2.24 SkillOpt / GEPA baselines started from an empty skill (and were read on 2026-11-07/08: cross-run, cross-date).

## Chain state

- status: complete; step: 5; paused: no
- schedule: learn_first; phase: —; current unit: —
- done units: 96
- ledger: cap 170000000, charged 55743109, reported 55684560, sends 30712, missing usage 1, stopped False (—), infra streak 0
- read plan: economy; plan a1cc0c0c1084; reads settled 35 of 35 (fresh done 14 of 14 planned, aliases 21, fallbacks 0, voided aliases 0, pending 0, invalid 0)

| part | units | charged tokens | reported tokens |
|---|---|---|---|
| learning_units | 51 | 34717753 | 34673039 |
| read_units | 14 | 21025356 | 21011521 |

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
- noise tau: 3.0 points (SE 0.47, 3 runs per item, n 100, mixed items 1, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | True | accepted | 100 | 3 | — | +4.0 | 5/1/94 | — | 0.4714045207910317 | — | — | 3.0 | s1/noise |
| programs[0] | program | True | accepted | 100 | 3 | 10 | +10.0 | 1/0/9 | +1.0 | 0.4714045207910317 | 0.0 | 1.4907119849998598 | 3.0 | s1/card-r1 (selected) |
| programs[1] | program | False | gain_below_tau | 100 | 3 | 1 | +0.0 | 0/0/1 | +0.3 | 0.4714045207910317 | 0.0 | 4.714045207910317 | 3.0 | s1/card-r1 (selected) |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | Answering Jeopardy-style trivia clues supported by retrieved snippets (practice examples show clue + documents). Use for identifying entities from clues/lists/categories, matching quotes or dates, and choosing shortest canonical answer forms. Not for open-ended research, math, or tasks needing explanations rather than a bare entity answer. |
| prog-t01-s1-a | evidence-qa-program-s1-a | program | t01 | 1 | — | Answers short trivia clues (1-6 words, no '?' or ':') by mining multi-document search snippets for proper names that co-occur with all question key terms. Use for Jeopardy-style factoid lookups with snippet context; not for full questions, long queries, or tasks needing computation or synthesis beyond name matching. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5 | card-t01-s1 | prog-t01-s1-a |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 300 | 300 | — | 575929 | 0 | 0 | 0 |
| noise | 300 | 300 | — | 453845 | 0 | 0 | 0 |
| outcomes | 100 | 100 | — | 148648 | 0 | 0 | 0 |
| outcomes-card | 100 | 100 | — | 188484 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 300 | 300 | — | 578447 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 5829 | 0 | 0 | 0 |
| program-2 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-2-gate | 300 | 300 | — | 575931 | 0 | 0 | 0 |
| program-2-smoke | 3 | 3 | — | 5829 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 2 (officeqa)
- noise tau: 5.2704627669473 points (SE 2.64, 3 runs per item, n 40, mixed items 5, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 40 | 3 | — | -4.2 | 5/8/27 | — | 3.3333333333333335 | — | — | 6.666666666666667 | s2/noharm-t01 |
| cards[1] | card | False | gain_below_tau | 40 | 3 | — | -0.8 | 8/8/24 | — | 3.3333333333333335 | — | — | 6.666666666666667 | s2/noharm-t01 |
| programs[0] | program | False | gain_below_tau | 40 | 3 | 11 | -12.1 | 2/4/5 | -4.2 | 3.3333333333333335 | 8.570991287109667 | 6.356417261637283 | 6.666666666666667 | s2/noharm-t01 |
| programs[1] | program | True | accepted | 40 | 3 | 18 | +7.4 | 6/1/11 | +1.7 | 3.3333333333333335 | 5.856069741052555 | 4.969039949999533 | 6.666666666666667 | s2/noharm-t01 |
| typing/no_harm[0] | no_harm | True | merged | 40 | 3 | — | +0.8 | 6/7/27 | — | 2.63523138347365 | — | — | 5.2704627669473 | s2/noise |

Shared type: the home type's members are searchqa (source); a candidate that passed the home rule was checked on each (no_regress, on the member's whole gate slice). Related gain is informational: it decides nothing beyond no_regress.

| decision | accepted | home gain pts | home fired gain pts | member bench | n | R | related gain pts | SE pts | tau | better/worse/tied | no_regress | member baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| programs[1] | True | +1.7 | +7.4 | searchqa (source) | 100 | 3 | -0.7 | 0.0 | 3.0 | 0/2/98 | True | s2/member-searchqa-base |

- home gain and related gain: whole gate slices; a program's gain on its fired items (its home decision) is in "home fired gain pts"

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | Answering Jeopardy-style trivia clues supported by retrieved snippets (practice examples show clue + documents). Use for identifying entities from clues/lists/categories, matching quotes or dates, and choosing shortest canonical answer forms. Not for open-ended research, math, or tasks needing explanations rather than a bare entity answer. |
| prog-t01-s1-a | evidence-qa-program-s1-a | program | t01 | 1 | — | Answers short trivia clues (1-6 words, no '?' or ':') by mining multi-document search snippets for proper names that co-occur with all question key terms. Use for Jeopardy-style factoid lookups with snippet context; not for full questions, long queries, or tasks needing computation or synthesis beyond name matching. |
| prog-t01-s2-a | evidence-qa-program-s2-a | program | t01 | 2 | — | Extracts specific month/year data points from markdown tables in supplied document context when a question references one or more month-year dates (e.g., 'June 1963', '1952-January'). Locates matching rows/columns and returns candidate values with headers. Use for numeric QA over tabular financial documents; not for questions without month-year dates or contexts lacking tables. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | prog-t01-s1-a, prog-t01-s2-a |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 120 | 120 | — | 841273 | 0 | 0 | 0 |
| card-r1-learn | 34 | 34 | — | 218097 | 0 | 0 | 0 |
| card-r2 | 120 | 120 | — | 847493 | 0 | 0 | 0 |
| member-searchqa-base | 300 | 300 | — | 765954 | 0 | 0 | 0 |
| member-searchqa-outcomes | 100 | 100 | — | 249754 | 0 | 0 | 0 |
| noharm-t01 | 120 | 120 | — | 845365 | 0 | 0 | 0 |
| noise | 120 | 120 | — | 677435 | 0 | 0 | 0 |
| outcomes | 34 | 34 | — | 225065 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 120 | 120 | — | 815761 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 18838 | 0 | 0 | 0 |
| program-2 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-2-gate | 120 | 120 | — | 849664 | 0 | 0 | 0 |
| program-2-member-searchqa | 300 | 300 | — | 765885 | 0 | 0 | 0 |
| program-2-smoke | 3 | 3 | — | 18949 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 3 (zebralogic)
- noise tau: 4.0 points (SE 2.00, 3 runs per item, n 100, mixed items 18, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 100 | 3 | — | -45.7 | 1/67/32 | — | 2.0 | — | — | 4.0 | s3/noise |
| cards[1] | card | False | gain_below_tau | 100 | 3 | — | -37.3 | 3/67/30 | — | 2.0 | — | — | 4.0 | s3/noise |
| programs[0] | program | False | gain_below_tau | 100 | 3 | 96 | +0.0 | 11/11/74 | +0.0 | 2.0 | 2.083333333333333 | 2.041241452319315 | 4.0 | s3/noise |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | Answering Jeopardy-style trivia clues supported by retrieved snippets (practice examples show clue + documents). Use for identifying entities from clues/lists/categories, matching quotes or dates, and choosing shortest canonical answer forms. Not for open-ended research, math, or tasks needing explanations rather than a bare entity answer. |
| prog-t01-s1-a | evidence-qa-program-s1-a | program | t01 | 1 | — | Answers short trivia clues (1-6 words, no '?' or ':') by mining multi-document search snippets for proper names that co-occur with all question key terms. Use for Jeopardy-style factoid lookups with snippet context; not for full questions, long queries, or tasks needing computation or synthesis beyond name matching. |
| prog-t01-s2-a | evidence-qa-program-s2-a | program | t01 | 2 | — | Extracts specific month/year data points from markdown tables in supplied document context when a question references one or more month-year dates (e.g., 'June 1963', '1952-January'). Locates matching rows/columns and returns candidate values with headers. Use for numeric QA over tabular financial documents; not for questions without month-year dates or contexts lacking tables. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | prog-t01-s1-a, prog-t01-s2-a |
| t02 | puzzle_template | src-00d0c1e3 | — | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 300 | 300 | — | 948289 | 0 | 0 | 0 |
| card-r1-learn | 73 | 73 | — | 306997 | 0 | 0 | 0 |
| card-r2 | 300 | 300 | — | 1276508 | 0 | 0 | 0 |
| noise | 300 | 300 | — | 1347541 | 0 | 0 | 0 |
| outcomes | 73 | 73 | — | 382777 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 300 | 300 | — | 1161766 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 15059 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 4 (spreadsheetbench)
- noise tau: 6.531972647421807 points (SE 3.27, 3 runs per item, n 50, mixed items 12, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | False | gain_below_tau | 50 | 3 | — | -6.7 | 9/14/27 | — | 3.2659863237109037 | — | — | 6.531972647421807 | s4/noise |
| cards[1] | card | False | gain_below_tau | 50 | 3 | — | -11.3 | 7/16/27 | — | 3.2659863237109037 | — | — | 6.531972647421807 | s4/noise |
| programs[0] | program | False | gain_below_tau | 50 | 3 | 50 | -6.7 | 5/10/35 | -6.7 | 3.2659863237109037 | 3.2659863237109037 | 3.2659863237109037 | 6.531972647421807 | s4/noise |
| programs[1] | program | False | gain_below_tau | 50 | 3 | 50 | -1.3 | 4/8/38 | -1.3 | 3.2659863237109037 | 3.2659863237109037 | 3.2659863237109037 | 6.531972647421807 | s4/noise |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | Answering Jeopardy-style trivia clues supported by retrieved snippets (practice examples show clue + documents). Use for identifying entities from clues/lists/categories, matching quotes or dates, and choosing shortest canonical answer forms. Not for open-ended research, math, or tasks needing explanations rather than a bare entity answer. |
| prog-t01-s1-a | evidence-qa-program-s1-a | program | t01 | 1 | — | Answers short trivia clues (1-6 words, no '?' or ':') by mining multi-document search snippets for proper names that co-occur with all question key terms. Use for Jeopardy-style factoid lookups with snippet context; not for full questions, long queries, or tasks needing computation or synthesis beyond name matching. |
| prog-t01-s2-a | evidence-qa-program-s2-a | program | t01 | 2 | — | Extracts specific month/year data points from markdown tables in supplied document context when a question references one or more month-year dates (e.g., 'June 1963', '1952-January'). Locates matching rows/columns and returns candidate values with headers. Use for numeric QA over tabular financial documents; not for questions without month-year dates or contexts lacking tables. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | prog-t01-s1-a, prog-t01-s2-a |
| t02 | puzzle_template | src-00d0c1e3 | — | — |
| t03 | workbook_preview | src-c9138870 | — | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 150 | 150 | — | 503090 | 0 | 0 | 0 |
| card-r1-learn | 41 | 41 | — | 151937 | 0 | 0 | 0 |
| card-r2 | 150 | 150 | — | 465834 | 0 | 0 | 0 |
| noise | 150 | 150 | — | 364771 | 0 | 0 | 0 |
| outcomes | 41 | 41 | — | 79263 | 0 | 0 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 150 | 150 | — | 339999 | 2 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 5358 | 0 | 0 | 0 |
| program-2 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-2-gate | 150 | 150 | — | 372093 | 0 | 0 | 0 |
| program-2-smoke | 3 | 3 | — | 4789 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

### Step 5 (alfworld)
- noise tau: 7.4535599249993 points (SE 3.73, 3 runs per item, n 40, mixed items 10, model-side unknown runs 0, re-runs 0)

| decision | kind | accepted | reason | n | R | fired n | mean pts | better/worse/tied | whole-slice pts | SE pts | SE fired pts | SE scaled pts | tau | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cards[0] | card | True | accepted | 40 | 3 | — | +12.5 | 11/2/27 | — | 3.72677996249965 | — | — | 7.4535599249993 | s5/noise |
| programs[0] | program | False | gain_below_tau | 40 | 3 | 40 | -0.8 | 5/6/29 | -0.8 | 2.8867513459481287 | 2.8867513459481287 | 2.8867513459481287 | 5.773502691896257 | s5/card-r1 (selected) |

Library after the step:

| skill id | name | kind | home type | origin step | retired | description |
|---|---|---|---|---|---|---|
| card-t01-s1 | evidence-qa-card-s1 | card | t01 | 1 | — | Answering Jeopardy-style trivia clues supported by retrieved snippets (practice examples show clue + documents). Use for identifying entities from clues/lists/categories, matching quotes or dates, and choosing shortest canonical answer forms. Not for open-ended research, math, or tasks needing explanations rather than a bare entity answer. |
| prog-t01-s1-a | evidence-qa-program-s1-a | program | t01 | 1 | — | Answers short trivia clues (1-6 words, no '?' or ':') by mining multi-document search snippets for proper names that co-occur with all question key terms. Use for Jeopardy-style factoid lookups with snippet context; not for full questions, long queries, or tasks needing computation or synthesis beyond name matching. |
| prog-t01-s2-a | evidence-qa-program-s2-a | program | t01 | 2 | — | Extracts specific month/year data points from markdown tables in supplied document context when a question references one or more month-year dates (e.g., 'June 1963', '1952-January'). Locates matching rows/columns and returns candidate values with headers. Use for numeric QA over tabular financial documents; not for questions without month-year dates or contexts lacking tables. |
| card-t04-s5 | household-agent-card-s5 | card | t04 | 5 | — | For TextWorld/ALFRED household tasks: find and move objects (e.g., put-object-on-receptacle goals), and handle clean/heat/cool/look-under-desklamp goals. Use in interactive household environments with admissible commands. Prefers shortcut macros and efficient search. Not for non-embodied or non-ALFRED tasks. |

Type map:

| type | signature | sources | card | programs |
|---|---|---|---|---|
| t01 | question/context | src-676eefb5, src-8290ed2b | card-t01-s1 | prog-t01-s1-a, prog-t01-s2-a |
| t02 | puzzle_template | src-00d0c1e3 | — | — |
| t03 | workbook_preview | src-c9138870 | — | — |
| t04 | admissible_commands | src-e2531270 | card-t04-s5 | — |

| learning unit | cells | expected | stop | tokens | unknown | infra unknown | config errors |
|---|---|---|---|---|---|---|---|
| card-r1 | 120 | 120 | — | 5418771 | 0 | 0 | 0 |
| noise | 120 | 120 | — | 4092229 | 0 | 0 | 0 |
| outcomes | 20 | 20 | — | 455881 | 0 | 0 | 0 |
| outcomes-card | 20 | 20 | — | 680909 | 1 | 1 | 0 |
| program-1 | 0 | — | — | 0 | 0 | 0 | 0 |
| program-1-gate | 120 | 120 | — | 6107822 | 0 | 0 | 0 |
| program-1-smoke | 3 | 3 | — | 40185 | 0 | 0 | 0 |
| programs | 0 | — | — | 0 | 0 | 0 | 0 |
| typing | 0 | — | — | 0 | 0 | 0 | 0 |

## Event grid (accuracy L, unknown = wrong, %)

| event | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|
| C0 | 77.8 | 20.9 | =S5 84.5 u/i/c 0/0/0 | 61.3 | 47.0 |
| C | 81.5 | 29.1 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| S1 | 83.8 | 33.7 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| S2 | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| S3 | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| S4 | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | 67.2 |
| S5 | 84.0 | 34.3 | 84.5 | 57.8 | 76.1 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965

## Test panels (opened by the owner; generalization evidence only; fresh units only)

### searchqa (common items of the fresh units 400)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 400 | 77.8 | 77.8 | 77.8 | 0 | 0 | 0.0 | 0.0 | 0.0 | 517824 |
| C (base of S1..S5) | 400 | 81.5 | 81.5 | 81.5 | 0 | 0 | 0.0 | 0.0 | 0.0 | 592665 |
| S1 | 400 | 83.8 | 83.8 | 83.8 | 0 | 0 | 93.5 | 93.5 | 92.5 | 1001705 |
| S2 | same requests as S5 | =S5 84.0 | =S5 84.0 | =S5 84.0 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 84.0 | =S5 84.0 | =S5 84.0 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 84.0 | =S5 84.0 | =S5 84.0 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 400 | 84.0 | 84.0 | 84.0 | 0 | 0 | 92.2 | 92.2 | 91.8 | 1028468 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S1-C0 | different (400 of 400 items) | 400 | 0 | +6.0 | 1.5 | [+3.1, +8.9] | [+3.2, +9.0] | 30/6/364 | 0 |
| S1-C | S1-C | different (374 of 400 items) | 400 | 0 | +2.2 | 1.3 | [-0.3, +4.8] | [-0.2, +4.8] | 18/9/373 | 0 |
| S2-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +6.2 | 1.5 | [+3.3, +9.2] | [+3.2, +9.2] | 31/6/363 | 0 |
| S2-C | S5-C | different (369 of 400 items) | 400 | 0 | +2.5 | 1.2 | [+0.1, +4.9] | [+0.2, +5.0] | 17/7/376 | 0 |
| S2-S1 | S5-S1 | different (374 of 400 items) | 400 | 0 | +0.2 | 0.6 | [-0.9, +1.4] | [-0.8, +1.5] | 3/2/395 | 0 |
| S3-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +6.2 | 1.5 | [+3.3, +9.2] | [+3.2, +9.2] | 31/6/363 | 0 |
| S3-C | S5-C | different (369 of 400 items) | 400 | 0 | +2.5 | 1.2 | [+0.1, +4.9] | [+0.2, +5.0] | 17/7/376 | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +6.2 | 1.5 | [+3.3, +9.2] | [+3.2, +9.2] | 31/6/363 | 0 |
| S4-C | S5-C | different (369 of 400 items) | 400 | 0 | +2.5 | 1.2 | [+0.1, +4.9] | [+0.2, +5.0] | 17/7/376 | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (400 of 400 items) | 400 | 0 | +6.2 | 1.5 | [+3.3, +9.2] | [+3.2, +9.2] | 31/6/363 | 0 |
| S5-C | S5-C | different (369 of 400 items) | 400 | 0 | +2.5 | 1.2 | [+0.1, +4.9] | [+0.2, +5.0] | 17/7/376 | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965
- same-request noise (fresh C vs C0, identical first inputs on 0 of 400 items): no identical requests
- fresh units (time range, returned model ids; R90): C0 2026-11-13T18:21:08..2026-11-13T18:32:28 models deepseek-v4-flash 400, C 2026-11-13T18:10:28..2026-11-13T18:21:03 models deepseek-v4-flash 400, S1 2026-11-13T17:30:09..2026-11-13T18:10:27 models deepseek-v4-flash 775, S5 2026-11-13T14:24:46..2026-11-13T14:55:34 models deepseek-v4-flash 770

### officeqa (common items of the fresh units 172)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 172 | 20.9 | 20.9 | 20.9 | 0 | 0 | 0.0 | 0.0 | 0.0 | 848284 |
| C (base of S1..S5) | 172 | 29.1 | 29.1 | 29.1 | 0 | 0 | 0.0 | 0.0 | 0.0 | 958801 |
| S1 | 172 | 33.7 | 33.7 | 33.7 | 0 | 0 | 68.0 | 68.0 | 11.6 | 1091708 |
| S2 | same requests as S5 | =S5 34.3 | =S5 34.3 | =S5 34.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 34.3 | =S5 34.3 | =S5 34.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 34.3 | =S5 34.3 | =S5 34.3 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 172 | 34.3 | 34.3 | 34.3 | 0 | 0 | 94.8 | 94.8 | 94.8 | 1185353 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S1-C0 | different (172 of 172 items) | 172 | 0 | +12.8 | 3.2 | [+6.6, +19.0] | [+7.0, +19.2] | 27/5/140 | 0 |
| S1-C | S1-C | different (117 of 172 items) | 172 | 0 | +4.7 | 2.6 | [-0.4, +9.8] | [-0.6, +9.9] | 14/6/152 | 0 |
| S2-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +13.4 | 3.3 | [+6.9, +19.9] | [+7.0, +19.8] | 29/6/137 | 0 |
| S2-C | S5-C | different (163 of 172 items) | 172 | 0 | +5.2 | 3.1 | [-0.9, +11.4] | [-0.6, +11.6] | 19/10/143 | 0 |
| S2-S1 | S5-S1 | different (168 of 172 items) | 172 | 0 | +0.6 | 3.1 | [-5.6, +6.8] | [-5.8, +7.0] | 15/14/143 | 0 |
| S3-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +13.4 | 3.3 | [+6.9, +19.9] | [+7.0, +19.8] | 29/6/137 | 0 |
| S3-C | S5-C | different (163 of 172 items) | 172 | 0 | +5.2 | 3.1 | [-0.9, +11.4] | [-0.6, +11.6] | 19/10/143 | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +13.4 | 3.3 | [+6.9, +19.9] | [+7.0, +19.8] | 29/6/137 | 0 |
| S4-C | S5-C | different (163 of 172 items) | 172 | 0 | +5.2 | 3.1 | [-0.9, +11.4] | [-0.6, +11.6] | 19/10/143 | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (172 of 172 items) | 172 | 0 | +13.4 | 3.3 | [+6.9, +19.9] | [+7.0, +19.8] | 29/6/137 | 0 |
| S5-C | S5-C | different (163 of 172 items) | 172 | 0 | +5.2 | 3.1 | [-0.9, +11.4] | [-0.6, +11.6] | 19/10/143 | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965
- same-request noise (fresh C vs C0, identical first inputs on 0 of 172 items): no identical requests
- fresh units (time range, returned model ids; R90): C0 2026-11-13T18:21:08..2026-11-13T18:27:36 models deepseek-v4-flash 172, C 2026-11-13T18:10:28..2026-11-13T18:17:25 models deepseek-v4-flash 172, S1 2026-11-13T17:30:04..2026-11-13T17:39:48 models deepseek-v4-flash 289, S5 2026-11-13T14:24:32..2026-11-13T14:41:12 models deepseek-v4-flash 335

### zebralogic (common items of the fresh units 200)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | same requests as S5 | =S5 84.5 | =S5 84.5 | =S5 84.5 | u/i/c 0/0/0 | — | — | — | — | — |
| C (base of S1..S5) | same requests as S5 | =S5 84.5 | =S5 84.5 | =S5 84.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S1 | same requests as S5 | =S5 84.5 | =S5 84.5 | =S5 84.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S2 | same requests as S5 | =S5 84.5 | =S5 84.5 | =S5 84.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 84.5 | =S5 84.5 | =S5 84.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 84.5 | =S5 84.5 | =S5 84.5 | u/i/c 0/0/0 | — | — | — | — | — |
| S5 | 200 | 84.5 | 84.5 | 84.5 | 0 | 0 | 96.0 | 0.0 | 0.0 | 983123 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S1-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C0 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-S1 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C0 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965
- fresh units (time range, returned model ids; R90): S5 2026-11-13T14:24:33..2026-11-13T14:48:21 models deepseek-v4-flash 200

### spreadsheetbench (common items of the fresh units 204)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 204 | 61.3 | 63.7 | 62.8 | 5 | 0 | 0.0 | 0.0 | 0.0 | 254060 |
| C (base of S1..S5) | same requests as S5 | =S5 57.8 | =S5 59.8 | =S5 59.0 | u/i/c 4/0/0 | — | — | — | — | — |
| S1 | same requests as S5 | =S5 57.8 | =S5 59.8 | =S5 59.0 | u/i/c 4/0/0 | — | — | — | — | — |
| S2 | same requests as S5 | =S5 57.8 | =S5 59.8 | =S5 59.0 | u/i/c 4/0/0 | — | — | — | — | — |
| S3 | same requests as S5 | =S5 57.8 | =S5 59.8 | =S5 59.0 | u/i/c 4/0/0 | — | — | — | — | — |
| S4 | same requests as S5 | =S5 57.8 | =S5 59.8 | =S5 59.0 | u/i/c 4/0/0 | — | — | — | — | — |
| S5 | 204 | 57.8 | 59.8 | 59.0 | 4 | 0 | 93.1 | 0.0 | 0.0 | 427326 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S5-C0 | different (204 of 204 items) | 198 | 6 | -3.0 | 3.4 | [-9.8, +3.7] | [-9.6, +3.5] | 20/26/152 | 0 |
| S1-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C0 | S5-C0 | different (204 of 204 items) | 198 | 6 | -3.0 | 3.4 | [-9.8, +3.7] | [-9.6, +3.5] | 20/26/152 | 0 |
| S2-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-S1 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C0 | S5-C0 | different (204 of 204 items) | 198 | 6 | -3.0 | 3.4 | [-9.8, +3.7] | [-9.6, +3.5] | 20/26/152 | 0 |
| S3-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-S2 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S5-C0 | different (204 of 204 items) | 198 | 6 | -3.0 | 3.4 | [-9.8, +3.7] | [-9.6, +3.5] | 20/26/152 | 0 |
| S4-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-S3 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (204 of 204 items) | 198 | 6 | -3.0 | 3.4 | [-9.8, +3.7] | [-9.6, +3.5] | 20/26/152 | 0 |
| S5-C | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-S4 | S5-S5 | same requests, not measured | - | - | - | - | - | - | - | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965
- fresh units (time range, returned model ids; R90): C0 2026-11-13T18:21:10..2026-11-13T19:33:08 models deepseek-v4-flash 204, S5 2026-11-13T14:24:41..2026-11-13T15:32:59 models deepseek-v4-flash 204

### alfworld (common items of the fresh units 134)

| event | n | acc L % | acc H % | acc known % | unknown | infra unknown | typed % | card mounted % | programs enabled % | tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 134 | 47.0 | 47.0 | 47.0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 3254005 |
| C (base of S1..S5) | same requests as S4 | =S4 67.2 | =S4 67.2 | =S4 67.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S1 | same requests as S4 | =S4 67.2 | =S4 67.2 | =S4 67.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S2 | same requests as S4 | =S4 67.2 | =S4 67.2 | =S4 67.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S3 | same requests as S4 | =S4 67.2 | =S4 67.2 | =S4 67.2 | u/i/c 0/0/0 | — | — | — | — | — |
| S4 | 134 | 67.2 | 67.2 | 67.2 | 0 | 0 | 0.0 | 0.0 | 0.0 | 3704425 |
| S5 | 134 | 76.1 | 76.1 | 76.1 | 0 | 0 | 94.0 | 94.0 | 0.0 | 5163774 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value

| contrast | of | requests | n (known pairs) | unknown excl. | mean pts | SE pts | t 95% | bootstrap 95% | better/worse/tied | in-run replicates |
|---|---|---|---|---|---|---|---|---|---|---|
| S1-C0 | S4-C0 | different (134 of 134 items) | 134 | 0 | +20.1 | 3.9 | [+12.4, +27.9] | [+12.7, +27.6] | 30/3/101 | 0 |
| S1-C | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-C0 | S4-C0 | different (134 of 134 items) | 134 | 0 | +20.1 | 3.9 | [+12.4, +27.9] | [+12.7, +27.6] | 30/3/101 | 0 |
| S2-C | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S2-S1 | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-C0 | S4-C0 | different (134 of 134 items) | 134 | 0 | +20.1 | 3.9 | [+12.4, +27.9] | [+12.7, +27.6] | 30/3/101 | 0 |
| S3-C | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S3-S2 | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-C0 | S4-C0 | different (134 of 134 items) | 134 | 0 | +20.1 | 3.9 | [+12.4, +27.9] | [+12.7, +27.6] | 30/3/101 | 0 |
| S4-C | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S4-S3 | S4-S4 | same requests, not measured | - | - | - | - | - | - | - | 0 |
| S5-C0 | S5-C0 | different (134 of 134 items) | 134 | 0 | +29.1 | 4.2 | [+20.8, +37.4] | [+20.9, +37.3] | 41/2/91 | 0 |
| S5-C | S5-S4 | different (126 of 134 items) | 134 | 0 | +9.0 | 3.6 | [+1.9, +16.0] | [+2.2, +15.7] | 18/6/110 | 0 |
| S5-S4 | S5-S4 | different (126 of 134 items) | 134 | 0 | +9.0 | 3.6 | [+1.9, +16.0] | [+2.2, +15.7] | 18/6/110 | 0 |

- : same requests, not measured (D10 d)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965
- fresh units (time range, returned model ids; R90): C0 2026-11-13T19:36:31..2026-11-13T21:06:34 models deepseek-v4-flash 4309, S4 2026-11-13T16:30:08..2026-11-13T17:29:40 models deepseek-v4-flash 3114, S5 2026-11-13T15:18:39..2026-11-13T16:24:11 models deepseek-v4-flash 2822

## Reference block (not same-phase, R89: point difference only; no SE, interval or counts)

No split contrast.

## 5x5 (rows = the bench evolved at step k, columns = the five panels; marks as in the legend)

S<k> - C0, mean paired difference in points (known pairs):

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | +6.0 | +12.8 | - | =S5 -3.0 u/i/c 4/0/0 | =S4 +20.1 u/i/c 0/0/0 |
| 2 | officeqa | =S5 +6.2 u/i/c 0/0/0 | =S5 +13.4 u/i/c 0/0/0 | - | =S5 -3.0 u/i/c 4/0/0 | =S4 +20.1 u/i/c 0/0/0 |
| 3 | zebralogic | =S5 +6.2 u/i/c 0/0/0 | =S5 +13.4 u/i/c 0/0/0 | - | =S5 -3.0 u/i/c 4/0/0 | =S4 +20.1 u/i/c 0/0/0 |
| 4 | spreadsheetbench | =S5 +6.2 u/i/c 0/0/0 | =S5 +13.4 u/i/c 0/0/0 | - | =S5 -3.0 u/i/c 4/0/0 | +20.1 |
| 5 | alfworld | +6.2 | +13.4 | - | -3.0 | +29.1 |
| in-run replicates |  | 0 | 0 | 0 | 0 | 0 |

S<k> - C, mean paired difference in points (known pairs):

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | +2.2 | +4.7 | - | - | - |
| 2 | officeqa | =S5 +2.5 u/i/c 0/0/0 | =S5 +5.2 u/i/c 0/0/0 | - | - | - |
| 3 | zebralogic | =S5 +2.5 u/i/c 0/0/0 | =S5 +5.2 u/i/c 0/0/0 | - | - | - |
| 4 | spreadsheetbench | =S5 +2.5 u/i/c 0/0/0 | =S5 +5.2 u/i/c 0/0/0 | - | - | - |
| 5 | alfworld | +2.5 | +5.2 | - | - | +9.0 |
| in-run replicates |  | 0 | 0 | 0 | 0 | 0 |

Accuracy of S<k> on L (unknown = wrong), %:

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | 83.8 | 33.7 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| 2 | officeqa | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| 3 | zebralogic | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| 4 | spreadsheetbench | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 57.8 u/i/c 4/0/0 | 67.2 |
| 5 | alfworld | 84.0 | 34.3 | 84.5 | 57.8 | 76.1 |

Accuracy of S<k> on H (unknown = right), %:

| step | evolved bench | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|
| 1 | searchqa | 83.8 | 33.7 | =S5 84.5 u/i/c 0/0/0 | =S5 59.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| 2 | officeqa | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 59.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| 3 | zebralogic | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 59.8 u/i/c 4/0/0 | =S4 67.2 u/i/c 0/0/0 |
| 4 | spreadsheetbench | =S5 84.0 u/i/c 0/0/0 | =S5 34.3 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | =S5 59.8 u/i/c 4/0/0 | 67.2 |
| 5 | alfworld | 84.0 | 34.3 | 84.5 | 59.8 | 76.1 |

=X v u/i/c: same requests as event X (D10 d: not read again); v is X's own reading shown again, u/i/c = X's unknown / infrastructure / configuration counts; - : same requests, not measured (JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point value in the reference block only; pending / invalid / void_alias: no value
- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965

## Continual-learning metrics (economy: terms through the resolver; S0 := C, the start of learning)

Side L:

| bench | home step | final | n | final % | C0 % | C % | gain vs C0 | gain vs C | forgetting | forgetting after home | backward transfer | forward transfer | plasticity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| searchqa | 1 | S5 | 400 | 84.0 | 77.8 | 81.5 | +6.2 | +2.5 | - (3 by-construction terms; other classes max -0.2, not above 0) | - (3 by-construction terms; other classes max -0.2, not above 0) | +0.2 | — | +2.3 |
| officeqa | 2 | S5 | 172 | 34.3 | 20.9 | 29.1 | +13.4 | +5.2 | - (3 by-construction terms; other classes max -0.6, not above 0) | - (3 by-construction terms) | - | +4.7 | +0.6 |
| zebralogic | 3 | S5 | 200 | 84.5 | =S5 84.5 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | - | - | - (4 by-construction terms) | - (2 by-construction terms) | - | - | - |
| spreadsheetbench | 4 | S5 | 204 | 57.8 | 61.3 | =S5 57.8 u/i/c 4/0/0 | -3.4 | - | - (4 by-construction terms) | - (1 by-construction term) | - | - | - |
| alfworld | 5 | S5 | 134 | 76.1 | 47.0 | =S4 67.2 u/i/c 0/0/0 | +29.1 | +9.0 | -9.0 | — | — | - | +9.0 |
| macro (a) |  |  |  | 67.4 (n 5, 0 via representatives) | 58.3 (n 5, 1 via representatives) | 64.0 (n 5, 3 via representatives) | +9.1 (1 of 5 structural) | +3.3 (2 of 5 structural) | -1.8 (4 of 5 structural) | +0.0 (4 of 4 structural) | +0.1 (3 of 4 structural) | +1.2 (3 of 4 structural) | +2.4 (2 of 5 structural) |
| macro (b) |  |  |  | 67.4 (n 5, 0 via representatives) | 58.3 (n 5, 1 via representatives) | 64.0 (n 5, 3 via representatives) | +11.3 (n = 4 of 5) | +5.6 (n = 3 of 5) | -9.0 (n = 1 of 5) | — (n = 0 of 4) | +0.2 (n = 1 of 4) | +4.7 (n = 1 of 4) | +3.9 (n = 3 of 5) |

Side H:

| bench | home step | final | n | final % | C0 % | C % | gain vs C0 | gain vs C | forgetting | forgetting after home | backward transfer | forward transfer | plasticity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| searchqa | 1 | S5 | 400 | 84.0 | 77.8 | 81.5 | +6.2 | +2.5 | - (3 by-construction terms; other classes max -0.2, not above 0) | - (3 by-construction terms; other classes max -0.2, not above 0) | +0.2 | — | +2.3 |
| officeqa | 2 | S5 | 172 | 34.3 | 20.9 | 29.1 | +13.4 | +5.2 | - (3 by-construction terms; other classes max -0.6, not above 0) | - (3 by-construction terms) | - | +4.7 | +0.6 |
| zebralogic | 3 | S5 | 200 | 84.5 | =S5 84.5 u/i/c 0/0/0 | =S5 84.5 u/i/c 0/0/0 | - | - | - (4 by-construction terms) | - (2 by-construction terms) | - | - | - |
| spreadsheetbench | 4 | S5 | 204 | 59.8 | 63.7 | =S5 59.8 u/i/c 4/0/0 | -3.9 | - | - (4 by-construction terms) | - (1 by-construction term) | - | - | - |
| alfworld | 5 | S5 | 134 | 76.1 | 47.0 | =S4 67.2 u/i/c 0/0/0 | +29.1 | +9.0 | -9.0 | — | — | - | +9.0 |
| macro (a) |  |  |  | 67.7 (n 5, 0 via representatives) | 58.8 (n 5, 1 via representatives) | 64.4 (n 5, 3 via representatives) | +9.0 (1 of 5 structural) | +3.3 (2 of 5 structural) | -1.8 (4 of 5 structural) | +0.0 (4 of 4 structural) | +0.1 (3 of 4 structural) | +1.2 (3 of 4 structural) | +2.4 (2 of 5 structural) |
| macro (b) |  |  |  | 67.7 (n 5, 0 via representatives) | 58.8 (n 5, 1 via representatives) | 64.4 (n 5, 3 via representatives) | +11.2 (n = 4 of 5) | +5.6 (n = 3 of 5) | -9.0 (n = 1 of 5) | — (n = 0 of 4) | +0.2 (n = 1 of 4) | +4.7 (n = 1 of 4) | +3.9 (n = 3 of 5) |

- terms: as in the module docstring with S0 := C (the start of learning: C under base historical, C0 under format), each term through the resolver
- macro: two pre-registered columns: (a) the mean over the benches where the term is defined, structural zeros and noise samples entered as 0 (k structural, m noise samples); (b) the mean over the measured benches only (n); an incomplete term counts as pending. A macro with a split term prints mixed: k same-phase, m split, no mean. A comparison with a five-bench baseline uses (a); neither is comparable with a full run's maximum over noisy readings
- forgetting: RP4: when an earlier event shares the final event's class (or, a noise sample, its requests), the measured maximum over the other classes if above 0, else - with the count of by-construction terms (JSON value 0, kind structural); without such events the signed measured maximum; split terms and noise samples are listed beside and never enter the maximum; an earlier event without a reading (pending, invalid, void_alias) leaves the maximum undefined (kind incomplete, the missing events and the maximum of the others listed)
- structural: a continual-learning term between two events of one class is a structural 0 (kind structural), never a sample (R70)
- noise sample: a continual-learning term between two same-phase fresh units whose requests are identical on every item (a fallback class, a re-read of a voided alias, a void plan) is a noise sample, not an effect (R67): kind noise_sample, value null, its reading as reference; by construction 0 like a structural term, so it never enters a maximum and a macro counts it apart
- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965

## Generalization view (S<k> minus the previous state; informational, it decides nothing)

- S<k> minus the previous state on every bench (S0 = the base row: C under base historical, C0 under format), from the representatives; home = the bench evolved at step k, same-type = a bench with a source in the home bench's type in s<k>/typemap.json, routed n/N = any other bench n of whose N panel items the fresh unit standing for S<k> (its own or its representative's: same requests) routed into the home type (a bench not learned yet with the home bench's signature, or an earlier bench routed into the type, RP15), other-type = every other bench. Informational: it decides nothing

| step | home bench | previous | searchqa | officeqa | zebralogic | spreadsheetbench | alfworld |
|---|---|---|---|---|---|---|---|
| S1 | searchqa | C | +2.2 (home) | +4.7 (routed 117/172) | - (other) | - (other) | - (other) |
| S2 | officeqa | S1 | +0.2 (same) | +0.6 (home) | - (other) | - (other) | - (other) |
| S3 | zebralogic | S2 | - (other) | - (other) | - (home) | - (other) | - (other) |
| S4 | spreadsheetbench | S3 | - (other) | - (other) | - (other) | - (home) | - (other) |
| S5 | alfworld | S4 | - (other) | - (other) | - (other) | - (other) | +9.0 (home) |

- (home) the bench evolved at the step; (same) a bench with a source in its type; (routed n/N) n of the bench's N panel items were routed into the home type, so the step's skills reach them; (other) every other bench; - : same requests (the step changed nothing on that panel); split: see the reference block
- in-run replicates: 0 (searchqa 0, officeqa 0, zebralogic 0, spreadsheetbench 0, alfworld 0)
- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no test-side replicate exists, RP7): s1 tau 3.0 / SE 0.4714045207910317; s2 tau 5.2704627669473 / SE 2.63523138347365; s3 tau 4.0 / SE 2.0; s4 tau 6.531972647421807 / SE 3.2659863237109037; s5 tau 7.4535599249993 / SE 3.72677996249965

## Read classes (economy plan a1cc0c0c1084)

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
| zebralogic | 1 | {C0, C, S1, S2, S3, S4, S5} | S5 | ok | — | C0 alias, C alias, S1 alias, S2 alias, S3 alias, S4 alias, S5 fresh | 200/0 of 200 | 0/0/0 |
| spreadsheetbench | 1 | {C0} | C0 | ok | — | C0 fresh | —/— of — | 5/0/0 |
| spreadsheetbench | 2 | {C, S1, S2, S3, S4, S5} | S5 | ok | — | C alias, S1 alias, S2 alias, S3 alias, S4 alias, S5 fresh | 204/0 of 204 | 4/0/0 |
| alfworld | 1 | {C0} | C0 | ok | — | C0 fresh | —/— of — | 0/0/0 |
| alfworld | 2 | {C, S1, S2, S3, S4} | S4 | ok | — | C alias, S1 alias, S2 alias, S3 alias, S4 fresh | 134/0 of 134 | 0/0/0 |
| alfworld | 3 | {S5} | S5 | ok | — | S5 fresh | —/— of — | 0/0/0 |

## Mount check (F2-style: every read records what it mounted)

- rule: every read records what it mounted, and every mounted skill exists in that step's frozen library (the main-v9 F2 identity defect: a card never mounted went unnoticed)
- scope: fresh units only (R72); alias rows are planned
- all present: True

| read | cells | mount records | present | typed % | card mounted % | skills seen | ids not in the step library |
|---|---|---|---|---|---|---|---|
| C0-searchqa | 400 | 400 | True | 0.0 | 0.0 | — | — |
| C-searchqa | 400 | 400 | True | 0.0 | 0.0 | — | — |
| S1-searchqa | 400 | 400 | True | 93.5 | 93.5 | card-t01-s1, prog-t01-s1-a | — |
| S5-searchqa | 400 | 400 | True | 92.2 | 92.2 | card-t01-s1, prog-t01-s1-a | — |
| C0-officeqa | 172 | 172 | True | 0.0 | 0.0 | — | — |
| C-officeqa | 172 | 172 | True | 0.0 | 0.0 | — | — |
| S1-officeqa | 172 | 172 | True | 68.0 | 68.0 | card-t01-s1, prog-t01-s1-a | — |
| S5-officeqa | 172 | 172 | True | 94.8 | 94.8 | card-t01-s1, prog-t01-s2-a | — |
| S5-zebralogic | 200 | 200 | True | 96.0 | 0.0 | — | — |
| C0-spreadsheetbench | 204 | 204 | True | 0.0 | 0.0 | — | — |
| S5-spreadsheetbench | 204 | 204 | True | 93.1 | 0.0 | — | — |
| C0-alfworld | 134 | 134 | True | 0.0 | 0.0 | — | — |
| S4-alfworld | 134 | 134 | True | 0.0 | 0.0 | — | — |
| S5-alfworld | 134 | 134 | True | 94.0 | 94.0 | card-t04-s5 | — |

Alias pairs (planned, from the plan; no cell of their own):

| pair | of | items | typed | unknown | with card | with programs | source |
|---|---|---|---|---|---|---|---|
| C0-zebralogic | S5 | 200 | 0 | 0 | 0 | 0 | planned |
| C-zebralogic | S5 | 200 | 0 | 0 | 0 | 0 | planned |
| C-spreadsheetbench | S5 | 204 | 0 | 0 | 0 | 0 | planned |
| C-alfworld | S4 | 134 | 0 | 0 | 0 | 0 | planned |
| S1-zebralogic | S5 | 200 | 0 | 200 | 0 | 0 | planned |
| S1-spreadsheetbench | S5 | 204 | 0 | 204 | 0 | 0 | planned |
| S1-alfworld | S4 | 134 | 0 | 134 | 0 | 0 | planned |
| S2-searchqa | S5 | 400 | 369 | 31 | 369 | 369 | planned |
| S2-officeqa | S5 | 172 | 163 | 9 | 163 | 163 | planned |
| S2-zebralogic | S5 | 200 | 0 | 200 | 0 | 0 | planned |
| S2-spreadsheetbench | S5 | 204 | 0 | 204 | 0 | 0 | planned |
| S2-alfworld | S4 | 134 | 0 | 134 | 0 | 0 | planned |
| S3-searchqa | S5 | 400 | 369 | 31 | 369 | 369 | planned |
| S3-officeqa | S5 | 172 | 163 | 9 | 163 | 163 | planned |
| S3-zebralogic | S5 | 200 | 192 | 8 | 0 | 0 | planned |
| S3-spreadsheetbench | S5 | 204 | 0 | 204 | 0 | 0 | planned |
| S3-alfworld | S4 | 134 | 0 | 134 | 0 | 0 | planned |
| S4-searchqa | S5 | 400 | 369 | 31 | 369 | 369 | planned |
| S4-officeqa | S5 | 172 | 163 | 9 | 163 | 163 | planned |
| S4-zebralogic | S5 | 200 | 192 | 8 | 0 | 0 | planned |
| S4-spreadsheetbench | S5 | 204 | 190 | 14 | 0 | 0 | planned |

---
Practice-side gates decided every acceptance; no configuration was picked from these numbers.
