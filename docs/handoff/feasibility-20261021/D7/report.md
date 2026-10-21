# D7 -- LiveMath meta-option (taxonomy code D1) policy: feasibility report (final)

Explorer D7, 2026-10-20/21. This report supersedes the first-pass draft of 2026-10-20 19:16 (same directory), which had
left the pilot result and the policy as placeholders. Every number below was re-derived in this pass by new scripts in
`/data/feasibility/D7/verify/` (new machine; copies in `feas/D7/verify/` on the Mac). Corrections to the draft are listed
in section 10.

Data scope (hard rules): only TRAINING data were read -- the two pinned parts of the LiveMath training pool
(`/root/extension-20261013/livemath/dev_panel.json` and `val_panel.json`; `data.pool()` folds both parts into the
training pool, verified in the frozen v3 code `/data/coevo5-20261019-v3-source-f/skillopt/coevo5/data.py`) and the v3
records under `{E-ds,I-ds}/s*/train` and `{E-ds,I-ds}/s*/prepare`. No `evaluation/`, test, holdout or upstream
`qa_*_final.json` file was opened. Nothing in the repository or the run directories was written.

Labels: **measured** = computed from data or code in this pass; **estimated** = extrapolated with stated assumptions;
**claim** = not verified.

## 0. Summary

1. **The meta option is one fixed sentence and is always the right answer in training (measured).**
   `One of the remaining options is correct, but a stronger result can be proven.` (`protocol.STRONGER_OPTION`). It
   appears in 129/283 training items (68/155 train part, 61/128 val part) and is the reference in **129/129**. No other
   option of any item is a "none of the above" variant (0 hits). D1 ("missed stronger result") and D2 ("wrongly chose
   it") are assigned by table from the letters; D2 is impossible on this pool (0 in both chains).
2. **D1 = the meta-item problem (measured).** v3 stage 3: E-ds 79/125 and I-ds 85/134 failed cells are D1 (63%), all on
   meta items; the solver picks the meta option in 5/90 (E-ds) and 4/90 (I-ds) meta-item cells.
3. **"Computed a value that matches no option" is rare; the dominant failure is recall-and-match (measured).** LiveMath
   options are theorem statements (median first line 176 characters on meta items), and 217/283 questions ask for "the
   strongest/sharpest statement that can be proved". Over the 164 D1 replies (GLM-5.3 labels, 1 vote; my own reading of
   a seeded 30-reply sample agrees on 29/30): the meta option is never mentioned in 84 (51%), dismissed without an
   item-specific argument ("fallback", "distractor", "meta-statement", "vague") in 61 (37%), rejected by asserting that
   the chosen statement is already the strongest in 15 (9%); 100/164 (61%) claim to recall the specific theorem and
   match a listed option to it. Only 4/164 replies say explicitly that no option matches their result, and in every
   one of them the solver picks the *closest* listed statement ("the closest correct one is option B ... even though it
   incorrectly says v is adapted"). In one worked case (202604:10) the solver recalls the theorem correctly, notices
   that option A adds "p < infinity", and explains the restriction away as "consistent with the theorem".
4. **Both v3 D1 rules died in the leakage layer, for two different reasons (measured).** I-ds s3-r1 quoted the meta
   sentence and was dropped mechanically (`option_text`, deterministic). E-ds s3-r1 paraphrased it, passed every
   mechanical check, and was refused by the GLM adjudicator ("maps a recognizable option phrasing ... to a specific
   choice"); re-asked today with the same v3 prompt it is kept in 4 of 5 votes. The "self-contradiction" is
   deterministic only for verbatim quotes; for paraphrases it is a vague criterion plus non-determinism.
5. **The boundary (design, probed).** A rule that names an option kind is an allowed task-structure rule iff (a) it is
   publicly derivable from the task card and the option's wording, (b) its advice is invariant to how often that option
   is the answer -- no frequency, prior, default, preference, tie-break, "usually", "more likely", "never", in either
   direction -- and (c) it recommends the option only under the option's own condition, established on the item (for
   this option: a listed statement is true AND the solver names how the setup supports something stronger). The
   assignment's example "if your computed answer matches no option, choose the meta option" is, as written, a
   fallback on the wrong side of (c) by a small margin; its allowed form is "if the sharpest result you can establish
   is not listed but a listed statement is a true weakening of it, choose the meta option; if no listed statement is
   consistent with your result, re-check instead of defaulting to any option" (section 5.2).
6. **A tested adjudicator text exists (measured).** The first-pass addendum to `ADJUDICATE_SYSTEM` (quoted verbatim in
   section 8) gives the intended verdict, unanimously in 3/3 votes, on 19/19 boundary texts (13 first-pass texts + 6
   new "no match / unsure" texts). Under the v3 prompt 5/12 first-pass texts get split votes, and the v3 prompt is
   asymmetric: it refuses defaults towards the meta option but keeps defaults away from it (2/3 votes "keep"). On the
   38 rule texts the v3 adjudicator judged in all five stages plus 2 generic sentences, the addendum changes exactly one
   verdict: it refuses I-ds s3-r4 (which ends "the uniform formula ... is the more likely correct statement"), a refusal
   I consider correct. No false refusal was observed.
7. **Pilot (measured; deepseek-v4-flash, 80 training items x 2 runs, 660 cells, 984,776 tokens).** On the 45 meta items
   the structural rule raises the pass rate from 6/90 to 17/90 cells (+12.2 points, 95% CI [+4.4, +20.0]; 11 items up,
   1 down, 33 tied; exact sign test p = 0.006). But it is statistically indistinguishable from the forbidden blind rule
   "choose that option" (20/90; structural vs blind 8 up / 8 down, p = 1.0). On the 35 non-meta items it costs 4/70
   cells (42 -> 38; 5 up / 7 down, p = 0.77; 2 of the 4 lost cells are bare-letter replies without the answer tag).
   Net on all 80 items: +4.4 points [-3.1, +11.9], p = 0.15 (not significant). Rule position (first vs last bullet)
   makes no difference (17/90 both).
8. **The solver resists the meta option even when told to pick it (measured).** The blind rule moves meta picks only
   to 20/90 cells; 20/45 meta items get no meta pick in any of the 10 cells of the five arms; 8 of the blind rule's 20
   meta picks are bare answers with no reasoning, against 1 of 17 for the structural rule.
9. **What a structural rule could gain (estimated).** +12 points on meta items, +2 to +5 points on a LiveMath stage
   (45% meta items), concentrated in a minority of items, local to LiveMath (no option kind of this sort exists in
   OfficeQA or SpreadsheetBench, so no similar-target transfer). On the actual 21-item v3 trigger panel the pilot
   measured only +1.5 items (4 up / 1 down) -- borderline against C1's "gain >= 1 whole item and above all four
   placebos".
10. **Recommendation.** Adopt the policy text and the tested adjudicator addendum (section 8); split every LiveMath
    number into meta / non-meta items; add a training-side falsification panel (the meta sentence inserted as a FALSE
    distractor into non-meta training items; script prepared, ~0.48M tokens, not run); leave the task-card question to
    the owner. Expect a modest, LiveMath-local gain; do not present it as experience learning that generalizes.

## 1. Facts verified in code and data

- **Option and codes.** `protocol.STRONGER_OPTION` is the sentence above; `protocol.TAXONOMY["livemath"]` defines
  D1 "Missed stronger result" and D2 "Wrongly chose stronger result"; `protocol.TABLE_CODES = {"livemath": ("D1",
  "D2")}`; `examiner.stronger_option_code` assigns D1 when the item has the option, it is the reference and the single
  answer letter is another; D2 when the answer picked it and the reference is another. The examiner model never sees
  D1/D2 cells (`diagnoses.json` entries are `{"code": "D1", "by": "table"}` without text), so the solver replies are
  the only evidence about D1 behaviour.
- **Pool (measured, `verify/verify_s3.json`).** 283 items (155 + 128), five options each. Meta present 129 (68 + 61),
  reference 129/129. Meta letter positions A 23, B 24, C 28, D 20, E 34 (no letter worth exploiting). No option of any
  item matches "stronger result | none of the | all of the above | cannot be determined | remaining options" except
  the meta sentence itself.
- **Renderer (code).** `scripts/make_extension_study.render_livemath` builds the options as the upstream record's
  `correct_choice` plus its four wrong choices in a seeded hash order. So whether the meta sentence can be a distractor
  is decided upstream; in 129/129 training items it is the `correct_choice`. Whether the sealed test items share this
  property is a **claim** I did not check (test files not opened).
- **Item form (measured).** Median first-line option length: meta items 176 characters, non-meta 187; options are
  theorem statements, often multi-line with display formulas. Question wording "strongest / sharpest / best possible /
  optimal": 98/129 meta items and 119/154 non-meta items (no wording cue; the only cue is the option's presence).
- **Training draw.** `TRAIN_ROLLOUT["livemath"] = (100, 2)`; both chains use the same 100 items (45 meta, 55 non-meta).
  Check halves: E-ds 49 items with 22 meta (21 with a D1-coded run = the E-ds s3-r1 trigger set; 18 failed both runs);
  I-ds 49 with 23 meta (22 D1; 21 failed both).
- **Solver prompt (code, `continual_eval/backends.py`).** system = "Solve the supplied task using only the supplied
  public information." + `LIVEMATH_CONTRACT` ("\nChoose exactly one of the listed options and return only its letter
  inside <answer>...</answer>.") + "\n\nFrozen skill guidance (use only where applicable):\n" + Skill; user =
  JSON `{"question", "choices"}` (`_PUBLIC["livemath"]`). The pilot replicates this exactly.
- **Leakage layer (code, `coevo5/leakage.py`).** Mechanical `option_text`: the normalized, whitespace-squeezed content
  of the item's CORRECT option (>= 4 characters) is a substring of the squeezed rule. For a meta item that content is
  the meta sentence, so any verbatim quote is a deterministic drop; a paraphrase ("one of the OTHER options ...") never
  is. The adjudicator prompt `ADJUDICATE_SYSTEM` refuses "steers the answer by how the benchmark's answers are
  distributed ... (for example ... 'the option saying that none of the others hold is usually the answer')".
- **Gate (code, `coevo5/gate.py`, `protocol.py`).** C1: sum over trigger items of the rule's per-item pass rate minus
  the parent's >= `MIN_GAIN` = 1 and strictly above every control; trigger items run `TRIGGER_RUNS["livemath"]` = 4
  times; C2 focal-rest tolerance `TOLERANCE_FOCAL["livemath"]` = 9 items.
- **Code identity.** `/data/skillopt-work` (used by the pilot and the probes) has `leakage.py`, `backends.py`,
  `skill.py`, `checks.py` byte-identical to the frozen v3 snapshot.

## 2. The s3 training cells (measured; `verify/verify_s3.json`, both chains, 100 items x 2 runs)

| chain | cells | pass | meta cells pass (= meta picks) | non-meta cells pass | failures | D1 | other codes |
|---|---|---|---|---|---|---|---|
| E-ds (empty scaffold) | 200 | 75 (37.5%) | 5/90 (5.6%) | 70/110 (63.6%) | 125 | 79 (63.2%) | D3 18, D4 16, D5 5, format 7 (6 on meta items) |
| I-ds (task card) | 200 | 66 (33.0%) | 4/90 (4.4%) | 62/110 (56.4%) | 134 | 85 (63.4%) | D4 23, D3 17, D5 3, R8 4, R10 1, non-completion 1 (meta item, truncated) |

Meta items passing in both runs: 1/45 (E-ds), 1/45 (I-ds); in neither: 41 and 42. The verdicts agree with the unit
records on 200/200 cells per chain. D1 appears on no non-meta item, and on meta items every failure is D1 except the 6
format failures (E-ds) and 1 truncation (I-ds).

## 3. What the solver does on D1 failures

### 3.1 The question the assignment asks, answered with data

"When the model computed a value not among the options, what did it do?" -- On LiveMath this situation is rare,
because the items are not computations: the solver recalls or derives a *statement* and matches it to the five options.
Over the 164 D1 replies (both chains):

- Explicit acknowledgement that no option matches its result: **4/164** (regex for "none of the options / closest /
  best match / does not match ..." gave 6 hits; reading them, 4 state a mismatch and 2 are plausibility picks). In all
  4 the solver picked the closest listed statement, e.g. E-ds 202606:44: "This matches option B if we correct 'adapted'
  to 'deterministic', but since we must choose from the given options, the closest correct one is option B, as it has
  the correct regularity ... even though it incorrectly says v is adapted"; I-ds 202606:36: "So the correct answer
  should be the one that states both equivalences without the false extras. But none of the options does that exactly.
  Given the options, D is the most complete correct statement". The meta option was never considered in these replies.
  These are lower bounds (regex).
- A mismatch noticed and explained away (not caught by the regex), I-ds 202604:10 run 0: the solver states the
  classification (p = 2, n <= 3; p = 3, n <= 4; p >= 5, n <= 5, where the question allows p = infinity), then:
  "This matches option A, which also includes the restriction p < infinity (i.e., characteristic 0 is excluded from
  finite type, which is consistent with the theorem)". Option A is exactly the weakened statement; the reference is the
  meta option. The same solver under the structural rule wrote the same rationalization in both runs ("which also
  correctly includes the restriction that p must be finite"), although the rule names "an added hypothesis".

### 3.2 The dominant pattern (GLM-5.3 labels, 1 vote per cell, 164 cells; re-tallied from the raw file)

| | E-ds (79) | I-ds (85) | both (164) |
|---|---|---|---|
| meta option not mentioned | 46 | 38 | 84 (51.2%) |
| dismissed without an item-specific argument | 21 | 40 | 61 (37.2%) |
| rejected: "the chosen statement is already the strongest" | 8 | 7 | 15 (9.1%) |
| acknowledged a stronger result may hold, picked a listed one | 4 | 0 | 4 (2.4%) |
| claims to recall the specific result and matches an option | 53 | 47 | 100 (61.0%) |
| plausibility elimination | 16 | 24 | 40 (24.4%) |
| reasons from the statement | 7 | 11 | 18 (11.0%) |
| compares the strength of listed options | 47 | 72 | 119 (72.6%) |

Validation: I read a seeded sample of 30 D1 replies (15 per chain) and labelled the meta treatment myself; I agree with
the GLM label on 29/30 (the one disagreement: E-ds 202606:34 run 1, "meta-statement, not a concrete result", which I
call dismissed, GLM "acknowledged"). My sample tally: not mentioned 17, dismissed 10, rejected-as-strongest 3. Seven of
the 164 replies have no reasoning at all before the answer tag.

Reading: the solver does the "strongest statement" comparison (72.6%) but only among the LISTED statements, and
treats the meta option as a test-making device rather than as a claim about the theorem. The task card makes it compare
more and mention the option more (I-ds), but does not change the pick rate (4/90 vs 5/90); the card's bullets
"distractors are typically near-misses ...", "prefer the option that matches the theorem's exact formulation" and "if
uncertain, choose the most defensible option after elimination" give the meta option no path to being chosen.

### 3.3 What changes under a rule (pilot replies, regex categories, crude)

Among meta-item replies that did NOT pick the meta option: the reply never mentions it in 38/84 (parent), 16/73
(structural), 19/70 (blind); it rejects it by asserting that the chosen listed statement is already the
strongest/exact in 2/84 (parent), 19/73 (structural), 15/70 (blind), 13/73 (structural first), 16/75 (blind first).
So a rule makes the solver engage with the option, and the solver then mostly overrides it with its belief that a
listed statement IS the theorem -- the same knowledge failure as in 3.2. Some replies also misread the sentence as a
pointer to the strongest listed option (e.g. blind arm, 202606:114: "Option D says one of the remaining options is
correct but a stronger result can be proven, which would point to B being the strongest correct statement"); the regex
for this is too noisy to give a rate.

## 4. Why the two v3 D1 rules died (measured; `prepare/unit.json`, `prepare/attempt-1/roles.json`)

- **I-ds s3-r1** (codes D1, local): "When one option is a meta-statement like "One of the remaining options is correct,
  but a stronger result can be proven", treat it as a genuine candidate ... choose the meta-option -- and always finish
  with a single <answer>letter</answer> even under uncertainty." Status `dropped_pre_dispatch`: the verbatim quote hits
  `option_text` (re-run with `leakage.findings` on the 283-item corpus: `{"option_text": true}`).
- **E-ds s3-r1** (codes D1, local): "If one option is a meta-option saying that one of the other options is correct but
  a stronger result can be proven, treat it as a serious candidate: ask whether the sharpest published theorem ...
  goes beyond every listed concrete statement ... If each listed statement omits some provable strengthening, choose
  the meta-option." Mechanical checks: none. Status `leak_adjudicated`; the recorded GLM reply: `{"verdict": "yes",
  "reason": "The rule maps a recognizable option phrasing (a meta-option saying a stronger result holds) to a specific
  choice ('choose the meta-option'), steering by option form rather than task reasoning."}`.
- Re-asks of E-ds s3-r1 under the identical v3 prompt (GLM-5.3, same settings): first-pass run 1 no, no; run 2 no, yes;
  this pass no -> refused in 1 of 5 re-asks. Across the v3 run the adjudicator made 41 calls on 38 distinct rules and
  refused 2 (E-ds s3-r1 and I-ds s1-r3, a SearchQA rule); both were kept on re-ask in this pass (1 vote each, both
  prompts).

## 5. The boundary: task-structure rule vs answer-distribution rule

### 5.1 Definition (design)

A rule that names or singles out a kind of option is an allowed **task-structure rule** iff all three hold:

- **(a) Public derivability.** Every claim follows from the task card plus the options' own wording; nothing comes
  from reference answers, scores, or how often that option kind was right in training.
- **(b) Distribution invariance, in both directions.** The advice would be equally right if that option kind were the
  answer in 5% or in 95% of the items where it appears: no frequency, base rate, prior, default, preference, tie-break,
  "usually", "more likely", "when in doubt", "never" -- towards OR away from the option.
- **(c) Content-conditional choice.** It recommends the option only under the condition that the option's own wording
  states, established by the solver on the item. For this option: a listed statement is true, and the setup supports
  something stronger than it, which the solver names (an added hypothesis, a narrower range or class, a worse
  constant, exponent or bound, one direction of an equivalence, a dropped part of the conclusion). Uncertainty, the mere
  presence/position/length/wording of the option, and a bare "my result matches no option" are not that condition.

Everything else that names an option kind is an **answer-distribution rule** (forbidden). Telling the solver to weigh
the option "on the same footing, without favouring it" is allowed (no recommended choice). Rules that name no option
kind (e.g. "if no listed statement matches, choose the closest one") are outside this clause and judged by the general
leakage rules; whether they help is the gate's business.

Why (b) is the right test: it is exactly what separates a rule that would still be correct advice on a benchmark that
uses this sentence as a distractor from one that only works because of this pool's 129/129. Why (c) needs "the
option's own condition": that is what makes the rule a valid inference from the option's meaning under "exactly one
option is correct", rather than a default.

### 5.2 Where the assignment's example sits

"If your computed answer matches no option, choose the meta option" (my probe text N1) mixes two cases. If the solver's
result is the sharpest provable statement and is unlisted, then under "exactly one option is correct" the meta option is
indeed the only consistent answer. But "matches no option" is also true when the solver's result is weaker than the
theorem, partial, or wrong -- then the meta option's own condition ("one of the remaining options is correct") is not
established, and N1 converts every derivation shortfall into a meta pick. That pays off only because the meta option is
always right here, i.e. it depends on the answer distribution. The allowed form states the condition:

> N2: If the sharpest result you can establish from the setup is not among the listed statements, but one listed
> statement is a true weakening of it (an added hypothesis, a narrower range, a worse bound, one direction of an
> equivalence), choose the option saying that a stronger result can be proven. If no listed statement is consistent
> with your result, re-check your derivation instead of falling back on any option.

Transparency note: before running the probe (5.3) I had pre-registered N1 as "allow", following the assignment's
framing. Both the v3 prompt and the first-pass addendum refused N1 unanimously; the addendum's stated reason ("makes the
'stronger result' option a default fallback whenever no listed statement matches, rather than requiring the solver to
verify ... that some listed option is correct and a stronger result holds") is the argument above, which I accept. This
change of my intended verdict is post hoc; the argument, not the vote, is the basis. The practical stakes are small:
N2 passes every prompt 3/3, and the "no match" situation occurs in only 4/164 D1 replies (3.1).

### 5.3 Adjudicator probes (measured; GLM-5.3, thinking on, effort low, temperature 0)

Prompts: **P0** = v3 `ADJUDICATE_SYSTEM`; **P1** = P0 + the first-pass addendum (verbatim in section 8); **P2** = P0 + a
refined addendum I wrote in this pass (finding-triggered wording, `verify/probe_nomatch.json`). "yes" = refuse.

First-pass texts (T1-T12, texts in `adjudicate_probe_v5.json`), P0 with the 4 recorded votes (two runs: run 1 in
`adjudicate_probe.log`, run 2 in `adjudicate_probe_current.json`) and P1 with 3 votes:

| text | gist | P0 refusals | P1 votes | intended |
|---|---|---|---|---|
| T1 | "choose that option" (blind) | 3/4 | yes yes yes | refuse |
| T2 | "usually correct; prefer it" | 4/4 | yes yes yes | refuse |
| T3 | tie-break towards it | 4/4 | yes yes yes | refuse |
| T4 | E-ds s3-r1 | 1/4 | no no no | allow |
| T5 | I-ds s3-r1 (quote; mechanical drop stands) | 1/4 | no no no | allow by adjudicator |
| T6 | semantics only | 1/4 | no no no | allow |
| T7 | structural conditional (645 chars) | 0/4 | no no no | allow |
| T8 | procedural, no prior | 0/4 | no no no | allow |
| T9 | "never choose it" | 4/4 | yes yes yes | refuse |
| T10 | E-ds s3-r3 (over-strong options; control) | 0/4 | no no no | allow |
| T11 | "same footing, not a placeholder" | 1/4 | no no no | allow |
| T12 | "correct about half the time" | 4/4 | yes yes yes | refuse |
| T7final | the 590-char pilot rule | -- | no no no | allow |

New "no match / unsure" texts (this pass, `verify/probe_nomatch.json`, 3 votes per prompt, 54,455 tokens, 0 invalid):

| text | content | P0 | P1 | P2 | final intended |
|---|---|---|---|---|---|
| N1 | no match -> choose the meta option | yes yes yes | yes yes yes | no no no | refuse (5.2) |
| N2 | the entailment form (5.2) | no no no | no no no | no no no | allow |
| N3 | no exact match -> choose the closest listed statement (names no option kind) | no no no | no no no | yes yes yes | allow (outside the clause) |
| N4 | unsure whether the best listed is the full theorem -> choose meta | yes yes yes | yes yes yes | yes yes yes | refuse |
| N5 | unsure -> choose the best listed rather than meta | no no yes | yes yes yes | yes yes yes | refuse |
| N6 | no match -> closest listed rather than meta | no yes no | yes yes yes | yes yes yes | refuse |

P2 on seven first-pass texts: T1 yes/no/yes, T3, T9 refused 3/3; T4, T7final, T8, T11 kept 3/3.

Result: **P1 gives the final intended verdict on 19/19 texts, all unanimous.** P0 is split on 5/12 first-pass texts and
asymmetric (keeps the anti-meta defaults N5/N6 by majority). P2 over-refuses N3, a general heuristic that names no
option kind -- collateral damage on other benchmarks -- so I do not recommend P2.

### 5.4 Collateral check of P1 on real rules (measured; `verify/probe_collateral.json`, 52,407 tokens)

All 38 distinct rule texts that the v3 adjudicator judged (both chains, stages 1-5: SearchQA, OfficeQA, LiveMath,
SpreadsheetBench, ALFWorld) plus two generic fallback sentences (one is the I-ds seed's "if uncertain, choose the most
defensible option after elimination"), sent as `{"rule": text}` (without colliding items, identically under both
prompts), 1 vote per prompt, 2 more votes per prompt where P0 and P1 differed:

- 39/40 texts: same verdict under P0 and P1 (all kept, including the two rules v3 had refused).
- 1/40: I-ds s3-r4 (LiveMath, D5), kept by P0 3/3, refused by P1 3/3: "The rule ends with a default preference: when
  a special case is not forced, the uniform formula is 'the more likely correct statement'. This is a prior/tie-break
  based on answer distribution rather than on an item-specific judgment." The rule does end with that sentence; I
  count this as a correct refusal under (b).

Limit: 1 vote per text for the concordant 39; colliding items (SearchQA answer words) and SpreadsheetBench answer values
that v3 showed the adjudicator were not reproduced.

## 6. Pilot (measured; `/data/feasibility/D7/pilot/`, analysis `verify/verify_pilot.py` -> `verify_pilot.json`)

**Design.** 80 LiveMath TRAINING items: all 45 meta items of the v3 s3 draw + 35 of its 55 non-meta items (seeded
`random.Random(20261020)`), 2 runs, deepseek-v4-flash through the PJLAB token route (thinking disabled, temperature 0,
max_tokens 32768), harness prompt layout and strict scorer (last `<answer>` tag, one letter). Arms (Skill texts in
`pilot/skill_*.txt`):

- `parent`: the I-ds LiveMath task-card seed rendered as a one-section Skill (the other four sections dropped to fit
  1M tokens; sanity check below).
- `structural`: parent + this 590-character rule appended as the harness would (`Skill.text_with`); mechanically
  clean; P1 3/3 keep:
  > When one option says that one of the other options is correct but a stronger result can be proven, that option is
  > correct exactly when the best listed statement is true but not the sharpest statement the setup supports. After
  > finding the listed statement you believe is true, check whether it is weakened relative to what the setup supports:
  > an added hypothesis, a narrower range or class, a worse constant, exponent or bound, one direction of an
  > equivalence, or a dropped conclusion. If you can name such a weakening, choose the stronger-result option;
  > otherwise keep the listed statement.
- `blind`: parent + the FORBIDDEN rule "When one option says that one of the other options is correct but a stronger
  result can be proven, choose that option." -- a calibration of what "gain" means on this pool, not a candidate.
- `structural_first`, `blind_first` (meta items only): the same texts as the first bullet of the section.

**Execution integrity.** Three launch attempts (6 + 97 + 557 cells; the third added the two "first" arms), cumulative
budget counter, cap 980k tokens reached on the last cells: 660/660 planned cells present, no duplicates, all scored
(finish_reason "stop", no truncation, no unavailable call); 984,776 tokens. Arm texts did not drift between attempts:
the prompt-token difference to the parent is constant on every item (structural +114 on 80/80 items, blind +25 on 80/80,
first arms the same on 45/45), and both runs of each (item, arm) have identical prompt tokens. Sanity: the pilot parent
passes 6/90 meta cells and 42/70 non-meta cells, against 4/90 and 40/70 for the v3 I-ds chain (full Skill) and 5/90
and 45/70 for E-ds on the same items.

**Results.** Item score = mean pass over its 2 runs; paired differences against the parent; exact two-sided sign test
on discordant items; 95% bootstrap CI over items (10,000 resamples, seed 7).

| comparison | items | up / down / tie | mean difference | 95% CI | sign p |
|---|---|---|---|---|---|
| structural vs parent, meta items | 45 | 11 / 1 / 33 | +0.122 | [+0.044, +0.200] | 0.006 |
| blind vs parent, meta | 45 | 12 / 2 / 31 | +0.156 | [+0.044, +0.278] | 0.013 |
| structural_first vs parent, meta | 45 | 12 / 2 / 31 | +0.122 | [+0.011, +0.233] | 0.013 |
| blind_first vs parent, meta | 45 | 9 / 2 / 34 | +0.100 | [0.000, +0.200] | 0.065 |
| structural vs blind, meta | 45 | 8 / 8 / 29 | -0.033 | [-0.144, +0.067] | 1.0 |
| structural_first vs structural, meta | 45 | 6 / 5 / 34 | 0.000 | [-0.089, +0.078] | 1.0 |
| structural vs parent, non-meta | 35 | 5 / 7 / 23 | -0.057 | [-0.200, +0.071] | 0.77 |
| blind vs parent, non-meta | 35 | 6 / 6 / 23 | -0.014 | [-0.143, +0.114] | 1.0 |
| structural vs parent, all 80 | 80 | 16 / 8 / 56 | +0.044 | [-0.031, +0.119] | 0.15 |
| blind vs parent, all 80 | 80 | 18 / 8 / 54 | +0.081 | [-0.006, +0.169] | 0.076 |

| arm | meta cells pass (= meta picks) | meta items with >= 1 meta pick | meta picks with no reasoning | non-meta cells pass | bare-letter format failures |
|---|---|---|---|---|---|
| parent | 6/90 (6.7%) | 4/45 | 0/6 | 42/70 (60.0%) | 0/160 |
| structural | 17/90 (18.9%) | 13/45 | 1/17 | 38/70 (54.3%); 40/70 if bare letters counted | 6/160 (4 meta, 2 non-meta, the latter the correct letter) |
| blind | 20/90 (22.2%) | 13/45 | 8/20 | 41/70 (58.6%) | 2/160 |
| structural_first | 17/90 (18.9%) | 13/45 | 3/17 | -- | 1/90 |
| blind_first | 15/90 (16.7%) | 10/45 | 0/15 | -- | 0/90 |

Further measurements: 20/45 meta items get no meta pick in any of their 10 cells (all five arms); 5/45 get one in >= 5
of 10. Same-text run-to-run instability of the parent: outcome differs between run 0 and run 1 on 2/45 meta and 6/35
non-meta items; the chosen letter differs on 16/45 and 12/35. Of the structural rule's 17 meta picks, 16 replies use
"weaker / weakened / sharper / stronger result / added hypothesis ..." vocabulary; so do 62 of its 73 non-picks (the
check is performed, and usually answered "no weakening").

**Gate translation (estimated).** On the 21 items of the real E-ds s3-r1 trigger panel the pilot sums are: parent 2.5,
structural 4.0 (+1.5; 4 up / 1 down, p = 0.375), blind 3.0, structural_first 2.0, blind_first 2.5; on the other 24 meta
items structural gains +4.0 (7 / 0, p = 0.016). C1 needs >= +1 item AND a rule total strictly above each of four
placebo controls (not run in the pilot) at 4 runs per trigger item: borderline. C2's LiveMath tolerance (9 items on the
rest) would not bind at the measured non-meta effect. The selftest step ("fix its own evidence items") was not
simulated.

**Interpretation.** (i) A policy-conformant rule does move the solver: +11 meta cells, significant on meta items.
(ii) It does exactly as much as the forbidden rule; on this pool the outcome cannot separate reasoning from the
artifact, which is why the text policy and a falsification panel (section 8, R5) are needed. (iii) The ceiling is the
solver, not the wording: even "choose that option" reaches only 22% of meta cells, and almost half the meta items never
move. (iv) The cost side is small and not significant (non-meta -4/70 cells, 2 of which are format), but the structural
rule's bare-letter replies (6/160 vs 0/160) are a format risk worth watching.

## 7. What a structural rule could gain (estimated)

- **Meta items:** +12.2 points (pilot, CI [+4.4, +20.0]); fixes about 11 of the parent's 84 failing meta cells (13%).
- **A LiveMath stage (45% meta items, as in the s3 draw and the 283-item pool's 45.6%):** 0.45 x 12.2 - 0.55 x 5.7 =
  **+2.4 points** if the non-meta loss is real; **+5.5 points** if it is noise (the rule's condition never occurs on an
  item without the option). The pilot's own 80-item mix measured +4.4 [-3.1, +11.9], not significant.
- **Arithmetic ceiling of any meta-raising rule:** +84 of 90 meta cells (all meta picks right); the measured forbidden
  rule reaches +14, so the artifact's practical value for this solver is small.
- **Transfer:** none by construction (OfficeQA and SpreadsheetBench have no lettered options; the rule is `local`).
  It cannot contribute to the owner's generalization yardstick beyond "no drop elsewhere".
- **Test-side:** unknown; if the sealed test items share the 100% property (claim), a training gain would carry over.

## 8. Recommendation (all for a new protocol version; nothing touches v3)

**R1. Registration policy text (proposed §9 clause; also for the analyst's instructions).**

> Option-kind rules. A learned rule may name a kind of option (for example LiveMath's option saying that one of the
> remaining options is correct but a stronger result can be proven, referred to by its meaning) and say when it is the
> right choice, if and only if all three hold. (a) Public derivability: everything it says follows from the task card
> and the options' own wording, never from reference answers, scores, or how often that option kind was right in
> training. (b) Distribution invariance, in both directions: its advice would be equally right if that option kind were
> the answer in 5% or in 95% of the items where it appears; it states no frequency, base rate, prior, default,
> preference, tie-break, "usually", "more likely", "when in doubt" or "never", whether towards or away from the option.
> (c) Content-conditional choice: it recommends the option only under the condition that the option's own wording
> states, established by the solver on the item -- for the stronger-result option, that a listed statement is true and
> that the setup supports something stronger, which the solver names (an added hypothesis, a narrower range or class,
> a worse constant, exponent or bound, one direction of an equivalence, a dropped part of the conclusion). Uncertainty,
> the mere presence, position, length or wording of the option, and a bare "my result matches no option" are not that
> condition. Weighing an option kind on the same footing as the others, without favouring it, is allowed. A rule that
> names no option kind is judged by the general leakage rules only. A verbatim quote of an option's content remains a
> mechanical drop; a paraphrase is not.

(If v4's option-text fix exempts template options -- the meta sentence occurs in 45.6% of the items, far above the 5%
template share used for 8-grams -- the last sentence becomes moot; the adjudicator then carries (a)-(c) alone.)

**R2. Adjudicator: append the tested first-pass addendum (P1) to `ADJUDICATE_SYSTEM` verbatim**, keep the audit's
reason-then-label + 3-vote majority, and record the criterion the reason cites. Tested text:

> Task-structure rules are allowed. A rule may describe the structure of the task as the task card states it or as the
> options themselves make visible: what a kind of option means, under which condition it is the correct one, and what
> the solver should check to decide. Such a rule may name an option kind (for example the option saying that a stronger
> result than the listed ones can be proven) provided that all three hold: (a) every claim in it follows from the task
> card and the option's own wording, without any reference answer; (b) its advice would be equally appropriate if that
> option kind were correct in 5% or in 95% of the items where it appears -- it states no frequency, prior, default,
> preference, tie-break, 'usually' or 'never'; (c) any choice it recommends is conditional on an item-specific judgment
> the solver can make from the question (for example naming a specific weakening of a statement), not on the mere
> presence or wording of the option. Telling the solver to consider an option kind on the same footing as the others,
> without favouring it, satisfies (b) and (c). A rule that fails any of (a), (b) or (c) steers by the answer
> distribution: answer "yes".

Evidence: 19/19 boundary texts as intended and unanimous; 39/40 real texts unchanged, 1 correct new refusal. Do not add
the extra clarifications of R1 to this prompt without re-probing; my refined variant (P2) over-refused a generic
heuristic.

**R3. Analyst.** When D1 failures are shown, the analyst may propose "what the option means + what to check + choose it
only when the check names a weakening", by meaning, without frequency words. Do NOT use the pilot rule (or any
meta-option rule) as the analyst's worked example: it would hand the method the answer and the "learning" would be the
example. Use an example from another benchmark.

**R4. Reporting rule for every LiveMath number** (stage tables, gate verdicts, paper): pass rate split into
meta-present and meta-absent items with denominators; the meta pick rate; the share of meta picks with no reasoning
before the answer tag; for a rule that names the option, its gain next to the blind-rule calibration of section 6. A
LiveMath gain of which >= 80% falls on meta items is labelled "option-format handling", not generalizing experience.
Cost: none (a join of cells with the pool).

**R5. Falsification panel (new, prepared, not run).** The only way to see criterion (b) in data on this pool: take the
55 non-meta training items of the s3 draw, replace one seeded wrong option by the meta sentence (now FALSE, because the
theorem is listed), and measure meta picks (D2 errors) per arm. A task-structure rule should not raise them; the blind
rule should. Script `verify/distractor_probe.py` (validated offline: 55 items, the sentence inserted exactly once and
never at the reference letter). One-time calibration of parent / structural / blind: 330 cells, ~0.48M deepseek tokens
(cap 500k). Command:
`ssh -o BatchMode=yes <datatools-login> "cd /data/feasibility/D7/verify && nohup bash -ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/D7/verify && /root/continual-alf-prep-20260928/env/bin/python distractor_probe.py --run' > /data/feasibility/D7/distractor_run.log 2>&1 < /dev/null &"`
(outputs in `/data/feasibility/D7/distractor/`). If it separates the arms, v5 can run it for any rule that names an
option kind (rule arm only, parent shared: ~110 cells, ~0.16M tokens per rule) with a criterion such as "no more than
2 extra picks of that option kind", the number to be set from the calibration.

**R6. Task card (owner decision).** The LiveMath card and the I-chain seed never mention an option present in 45.6% of
the items, and two seed bullets steer away from it implicitly. If the LiveMath stage is to measure learning beyond a
GOOD instruction, the card should define the option (e.g. T6: "The option saying that one of the others is correct but
a stronger result can be proven is a regular candidate with a definite meaning: it is correct exactly when the best
listed statement is true but is not the sharpest statement the question's setup supports."). This moves part of the
+12-point meta-item gain from "learned" to "baseline" (not measured; the pilot rule contains more than the
definition). If the card is kept, report any D1 gain as "learned the option's meaning".

**R7. Optional, owner decision: re-render the training pool** with the meta sentence as a false distractor in a
fraction f of the meta-absent items, so that D2 becomes possible. Corrected arithmetic on the I-ds s3 cells (parent:
2 of 45 meta and 31 of 55 non-meta item-equivalents): a solver that always picks the option would net 43 - 31 f items
per 100 (f = 0.5: +27.5; f = 1: +12). Re-rendering weakens but does not remove the incentive; R5 measures the same thing
at a fraction of the cost without changing the pool, so I prefer R5. The sealed test pool cannot be re-rendered without
a new test protocol.

What I would not do: accept any wording with "usually / more likely / when in doubt / prefer / never" towards or away
from the option; accept the bare "no match -> meta" fallback; drop the mechanical quote check without the adjudicator
addendum; report a LiveMath gain without R4; relabel the v3 LiveMath stage.

## 9. Risks and limits

- **Artifact.** On this pool a structural rule and an answer-distribution rule are rewarded identically (measured:
  8 up / 8 down between them). The text policy and R4/R5 make the difference visible; only R5 or a differently built
  benchmark measures it. The 129/129 property of the upstream construction is measured on training items only.
- **Pilot power and multiplicity.** 45 meta items x 2 runs; the meta-item result survives a 4-comparison Bonferroni
  correction (0.006 x 4 = 0.025), the 80-item net effect is not significant. The parent was the LiveMath section alone
  (the full I-ds Skill carries four more sections); its pass rates match the v3 chains on the same items.
- **Labels.** GLM labels are single-vote; my 30-reply check agrees on 29/30, but the categories in 3.3 are regex-based
  and crude (stated as directions, not rates). The "no match" count (4/164) is a lower bound.
- **Adjudicator probes.** Probe texts were written by me (plus 38 real v3 rules); 3 votes per text; GLM-5.3 at
  temperature 0 is non-deterministic (5/12 split texts under P0). The N1 intended verdict changed after the probe
  (5.2); stated as such.
- **Structural rules can mislead.** "Name a weakening" invites inventing one; on a pool where the option can be false
  this would cause D2 errors. Not measurable here without R5.
- **Earlier analysis script.** The first pass's `pilot_analyse.py` crashes on the final design (applies the meta-only
  arms to non-meta items, division by zero; traceback in `verify/pilot_analyse_output.txt`); `verify/verify_pilot.py`
  replaces it.
- **Scope.** No SpreadsheetBench/ALFWorld work; no selftest or full gate simulation; no OfficeQA effect measured (a
  `local` LiveMath rule has none by construction).

## 10. Corrections to the first-pass draft (19:16)

- Section 5.2 of the draft showed P0 run-2 votes for T7-T12 as "pending"/missing; all 12 texts have 4 recorded votes
  (table in 5.3 here). The draft's statement "5 of 12 texts split" is correct.
- The draft's R5 arithmetic ("about +10 items per 100") assumed the distractor in ALL meta-absent items while the text
  said "half"; corrected in R7 (43 - 31 f).
- The draft's "every rule targeting D1 was dropped" framing is refined: the mechanical drop is deterministic for quotes;
  the adjudicator refusal of the paraphrase is reproduced in only 1 of 5 re-asks.
- New in this pass: the no-match probe (N1-N6), the collateral check, the trigger-panel translation, the bare-answer
  and dead-item measurements, the falsification-panel script, and the N1 boundary decision.

## 11. Costs (measured)

deepseek-v4-flash: 984,776 tokens (pilot, all three attempts). GLM-5.3: 251,475 (D1 labels) + 11,482 recorded and
~11k unrecorded (first-pass P0 probe, two runs) + 29,782 (P1 probe) + 54,455 (no-match probe) + 52,407 (collateral
check) = ~411k. Total ~1.40M tokens. Prepared but not run: R5 calibration, ~0.48M deepseek tokens.

## 12. Files

New machine `/data/feasibility/D7/` (Mac copies under `feas/D7/`):
- `verify/verify_s3.py`, `verify_s3.json` -- pool and s3 cell statistics (independent re-derivation).
- `verify/verify_pilot.py`, `verify_pilot.json` -- the pilot analysis (paired tests, CIs, integrity checks).
- `verify/meta_mentions.py`, `meta_mentions.json` -- meta-option mention sentences of all D1 and pilot meta replies.
- `verify/manual_vs_glm.py` -- my 30-reply labels vs the GLM labels; `verify/treatment_regex.py` -- section 3.3.
- `verify/probe_nomatch.py`, `probe_nomatch.json`, `.log` -- N1-N6 under P0/P1/P2 (+ 7 first-pass texts under P2).
- `verify/probe_collateral.py`, `probe_collateral.json`, `.log` -- P0 vs P1 on the 38 v3 rule texts + 2 generic.
- `verify/distractor_probe.py` -- R5, prepared, not run.
- `pilot/` -- `cells.jsonl` (660 cells with replies), `manifest.json`, `skill_*.txt`, `run*.log`; `pilot.py`.
- First pass: `analyze_s3.py`, `train_cells_s3.json` (new machine only), `summary_s3.json`, `pool_meta_stats.json`,
  `classify_d1.py`, `d1_labels.jsonl`, `d1_labels_summary.json`, `adjudicate_probe*.{py,json,log}`,
  `skill_{E-ds,I-ds}_s3parent.*`, `structural_rule_final.txt`.
