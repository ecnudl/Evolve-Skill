# D13: Proposal quality and the proposer prompt (feasibility report)

Explorer D13, 2026-10-21, 04:42-05:15 HKT. Data: the completed v3 run `/data/coevo5-20261019-v3-run` (read-only, new machine),
frozen v3 code `/data/coevo5-20261019-v3-source-f`. Outputs: `/data/feasibility/D13/run2/` (new machine) and the copies in
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D13/run2/`.
No test or holdout path was opened. The repository was not modified. GLM-5.3 tokens used: 175,147 (limit 300,000).

Labels: **measured** = computed from data/code in this session; **estimated** = derived from measured numbers by a
stated assumption; **claim** = asserted but not verified here. The earlier, unfinished D13 attempt's files in the same
folders (`proposals.json`, `payload_summary.json`, `all_texts.json`, `replies/`, `/data/feasibility/D13/out/`) were
NOT used as evidence: every number below comes from `run2/`, regenerated from the run directory.

## 1. Verdict

Feasibility of a better proposer: **high** (it is a prompt and payload change, it runs, it is cheap).
Evidence that better proposals would have produced an accepted rule in v3: **none**.

* (measured) The v3 analyst's 49 proposals lost 21 at the prepare stage (43%). The causes were mostly mechanical and
  can be fixed: 8 rules voided because ONE of 4-6 cited items carried another code; 8 rules whose code had fewer than 4
  failed check-half items; 3 of 13 analyst calls (187,425 of 749,469 analyst tokens) rejected whole for a field
  4-21 characters over a limit or a missing field; 4 rules stopped by the leakage layer (2 of them are the LiveMath
  meta-option policy conflict). The other 28 rules died on effect size: 13 in selftest, 13 at screen C1, and 2 at confirm.
* (measured, two raters) The proposals mostly re-express the task-card instruction (the I-ds seed). Both raters call only 7
  of 49 "new advice". Both call 8 a restatement of the seed or card (I count 18). Most of the rest narrow a seed
  bullet. About half are global directives (28 of 49 by me, 26 of 49 by GLM; kappa 0.67 for global vs conditional).
  15 of 49 contradict another proposal or the seed. Five of the ten replies hold an internal contradiction, and
  each one traces to the taxonomy's opposite-direction code pairs (too long vs too short, too weak vs too strong).
* (measured, pilot, n small) A per-code proposer with balanced evidence (target-code failures, opposite-code failures,
  always-correct items) and a "When ...: ... Otherwise, ..." template gave conditional rules only: 7 of 7. None had a
  leakage finding (0 of 7). On the same items, the v3 prompt gave 1 global directive in 5 rules, 2 of 5 rules with
  leakage hits, and repeated the silent transfer-slot void. The best pilot condition applies to 14 of 97 check-half
  items; 11 of those 14 are failures, it catches all 5 D1 failures, and it exposes only 3 of the 72 always-correct items.
  The broadest-sounding condition ("the clue says 'this <category>'") applies to 49 of 97, which makes it a global
  directive in disguise. Two of the 7 conditions would fail a judge-based MIN_TRIGGER (0 and 3 failing items) although
  v3's code-based trigger would pass them.
* Bottom line: fix the proposer in v4/v5 (cheap, removes most of the prepare-stage waste and the contradictions,
  shrinks harm exposure), but do not expect it to move the acceptance count. C1 (gain of at least one whole item
  above the placebo range) blocked 14 of 15 screened rules, and that is a noise and headroom problem (D5, D8, D9),
  not a wording problem.

## 2. What I did

1. Traced all 49 proposals (`run2/scripts/trace.py`). It reads `{I-ds,E-ds}/s1..s5/{prepare,selftest,screen,confirm}/unit.json`,
   `prepare/attempt-1/roles.json` (the raw analyst replies, adjudications, usage) and `research.json`. Output:
   `proposals_traced.json`, `stages.json`. Funnel reproduced: 49 -> 28 supported -> 15 screened -> 2 confirmed -> 0 accepted.
   (The context file's "14 screened" is a typo. Its own later line counts 15 screened, which matches: 13 failed
   screen and 2 passed screen.)
2. Re-built all ten v3 analyst payloads with the frozen v3 code (`reconstruct.py`, `evid.py`). The recorded request
   SHA-256 matched in **10 of 10** (measured). This proves the analysis sees exactly what the analyst saw.
3. Measured every raw reply's fields against the stated limits, to explain the 3 rejected replies and the 1 invalid row.
4. Re-ran the frozen v3 mechanical leakage checks on all 49 texts and on every selftest revision (`leak.py`).
5. Evidence analysis of the 8 evidence-invalid rules (`evid.py`).
6. Manual coding of all 49 (cluster, form, restatement, contradiction; `analysis/coding.py`). Independent second
   rating by GLM-5.3, one call per benchmark (`rater.py`, 13,478 tokens). Agreement computed.
7. Verified that the cal-1 arm file's local copy equals the old machine's (md5 `1ea902a73d793b7dd4701096951a2fb9`).
   Its `cand` arm contains the v3 E-ds s1-r1 text, and its `seed-rule` arm is the single seed bullet that the rule
   restates ("Answer with the minimal entity or value requested ...").
8. Drafted the v5 proposer prompt (`v5prompt.py`). Ran the pilot on E-ds s1 (SearchQA) training data, proposal half
   only: D1 twice (stability), D2 once plus a re-ask carrying the validation errors, the v3 prompt on the same D1 items
   (ablation), and a GLM applicability judge over the check half (`pilot.py`, `followup.py`, `check.py`,
   `check_v3abl.py`, `judge.py`, `trig.py`).

## 3. The 49 proposals: where each died (measured)

| Stage of death | n | Detail |
|---|---|---|
| prepare: row invalid | 1 | I-ds s3-r3: `adds` 304 > 300 characters |
| prepare: evidence_invalid | 8 | all `evidence_other_code`; each rule had exactly 1 off-code citation among 4-6 (1 of the 8 off-code items carried the targeted code on another run) |
| prepare: insufficient_support | 8 | trigger 0-3 (< MIN_TRIGGER 4); triggers are defined by the CODE, not the rule |
| prepare: leakage | 4 | mechanical: I-ds s1-r5 `answer_text`, I-ds s3-r1 `option_text` (quotes the meta-option sentence); adjudicated: I-ds s1-r3 (example "Minsk, Monrovia, Manama" gives away an answer), E-ds s3-r1 (meta-option mapping) |
| selftest | 13 | 10 failed after a revision, 3 not revised; E-ds s2-r4's revision was itself dropped: its example number "4.815" equals an OfficeQA training reference (`answer_number`) |
| screen | 13 | all C1 (gains -2 .. +3/4 items) |
| confirm | 2 | I-ds s4-r2 C1 (gain 1/2, margin -3/2); E-ds s1-r1 C2 (rest delta -15/2) |
| accepted | 0 | |

Whole-reply rejections (measured): I-ds s1 attempt 1, `transfer.none` 307 > 300 characters. I-ds s2 attempt 1,
`transfer.none` 321 > 300. I-ds s5 attempt 1, every row lacked `placement` (ALFWorld has no checkable similar
target, and the model dropped the field). Each re-ask re-sent the identical ~140-218 KB request. Cost:
59,792 + 82,001 + 45,632 = 187,425 tokens (25% of all analyst tokens).
Transfer slot: I-ds s2 and E-ds s2 named a rule for transfer whose placement was `local` (recorded `not_a_similar_rule`).
E-ds s3 named its rule 5 (`similar`, the only similar placement of 49), which died at insufficient_support (trigger 2).

## 4. Clusters, form, restatement, contradictions

Coding (coder: D13 explorer, from the full texts). Form: G = global directive; Cq = conditional wording whose
trigger holds on nearly every task of the kind; C = conditional on an observable, restricting trigger.
Restates: card / seed (substantially restates an I-ds seed bullet) / partial (narrows or extends one) / new.
Second rater: GLM-5.3 with the card, the seed bullets and the rules of one benchmark per call.

Agreement (measured, n=49). Form, 3-way: 0.73, kappa 0.55. Global (G or Cq) vs conditional: 0.84, kappa 0.67
(me 28, GLM 26, both 23). Restatement, 4-way: 0.61, kappa 0.41. Restate (seed/card) vs not: me 18, GLM 8,
all 8 of GLM's inside my 18. New advice: me 12, GLM 9, both 7. GLM was more lenient: 9 of my 15 "seed" codes it
called "partial". A lexical-overlap proxy (content-word containment against the best seed bullet) did NOT separate
the classes (mean 0.21 for "seed" vs 0.18 for "new"). Paraphrase defeats it, so it cannot be used as a mechanical
restatement filter.

| Cluster (what the rule asks for) | n | forms | fates |
|---|---|---|---|
| A answer surface form (shorten / strip / copy exact form) | 6 | C3 G3 | 4 screened (C1 x3, confirm C2), 1 leak, 1 selftest |
| B verify the candidate against every clue part | 2 | G2 | screen C1, selftest |
| N identify which element the clue asks for | 2 | G2 | leak (word), screen C1 |
| C locate the right row/column/period/page | 2 | C1 G1 | evidence_invalid, selftest |
| D choose the right statistic / aggregation scope | 2 | C2 | evidence_invalid, screen C1 |
| E precision, arithmetic, units, scale | 3 | G2 Cq1 | evidence_invalid, insufficient, screen C1 |
| F policy when needed data are absent | 2 | G1 C1 | insufficient, evidence_invalid (the two contradict each other) |
| G option strength (weaker / stronger / meta option) | 8 | C4 Cq3 G1 | 2 leak (meta option), invalid, insufficient, selftest, 3 screen C1 |
| H spreadsheet program mechanics | 5 | G3 C1 Cq1 | 3 insufficient, selftest, screen C1 |
| I spreadsheet instruction / example interpretation | 5 | C4 G1 | 2 evidence_invalid, 2 selftest, confirm C1 |
| J ALFWorld search strategy | 3 | G3 | screen C1, 2 selftest |
| K ALFWorld command validity | 3 | C3 | selftest, insufficient, evidence_invalid |
| L ALFWorld goal / object discipline | 4 | G2 C2 | evidence_invalid, 3 selftest |
| M answer tag / single letter | 2 | G2 | screen C1, insufficient (both restate the card) |

Restatement examples (verified texts). I-ds s4-r5 "Write every cell of the required answer range ... including cells
whose expected value is empty" vs. the seed "Ensure every cell in the range is written, including empty strings/None".
I-ds s5-r2 "If the observation ... is 'Nothing happens', do not issue that same action again" vs. the seed
"'Nothing happens' ... adjust rather than repeating it". I-ds s4-r3 "load the workbook twice" vs. the seed "Load twice
(once each way)". E-ds s1-r2 and E-ds s3-r5 restate the cards' fixed answer-tag instruction. For I-ds the seed IS the
parent Skill, so a restatement adds nothing by construction. For E-ds it shows the method re-deriving the task-card
instruction, which is exactly the comparison the owner cares about. cal-1 tests it head-on: arm `cand` (E-ds s1-r1)
vs arm `seed-rule` (the seed bullet it restates).

Contradictions (verified texts; 15 of 49 proposals involved):
* inside one reply (5 of 10 replies): I-ds s1-r1 "surname alone" vs I-ds s1-r5 "mirror the snippets' surface form ...
  formal first name". I-ds s3-r2 "prefer the option without [an unproven clause]" vs I-ds s3-r3 "do not retreat to a
  weaker, safer-looking option". E-ds s1-r1 "no ... category or type words" vs E-ds s1-r4 "give the full specific name
  ... including ... the publication's type word". E-ds s3-r1 "choose the meta-option" vs E-ds s3-r3 "prefer the option
  without the extra claim". E-ds s4-r4 "build each row's formula" vs E-ds s4-r5 "write values, not Excel formulas".
  Each pair targets two taxonomy codes that err in opposite directions. In 4 of the 5 pairs one side died at prepare,
  so the conflict was never tested. In E-ds s1 both sides were screened, separately.
* across chains: I-ds s2-r4 "Never answer 'not determinable' ... read approximate values" vs E-ds s2-r5 "do not invent
  a plausible number: state what is missing".
* against the seed: I-ds s5-r3 ("move ... to") vs the seed's "put A in/on". E-ds s5-r2 "you cannot take a second object
  while already holding one" vs the seed's "you can hold at most two objects" (the taxonomy's D4 sides with the rule,
  so the seed may be wrong here: claim). E-ds s5-r4 vs the seed's put-in-the-appliance procedure.

Cross-chain near-duplicates (same idea from both chains): at least 6 pairs (exact object type, full precision, verify
all clue parts, systematic search, "Nothing happens", meta option). What the analyst proposes is driven by the failure
distribution, largely independent of the parent text.

Screened rules by form (measured, tiny n): C n=5, mean C1 gain 0.50 items. G n=6, mean 0.04 (max 7/4: E-ds s1-r1,
which then failed C2 harm). Cq n=4, mean 0.00. These are not distinguishable at the noise floor
(30 of 194 items move on an identical re-run; context file, verified by the main session).

## 5. The v5 proposer design

1. **Per-code call.** One call per diagnosis code c of the stage. It runs only when c has at least 2 distinct
   proposal-half failed items, and either (v3 code-based trigger) at least 4 check-half failed items with c, or
   (judge-based trigger, v4) the applicability judge decides later. Measured on v3 with the code-based rule:
   27 calls over the 10 stages instead of 10 (I-ds 3/3/3/1/1, E-ds 5/4/3/1/3). The 8 insufficient-support
   proposals would not have been requested.
2. **Balanced evidence.** Up to 12 target-code failures (one run per item, seeded). Up to 6 failures of the code's
   declared opposite (SearchQA D1<->D2, D4<->D5; OfficeQA D2<->D3, D1<->D5; LiveMath D1<->D2, D3<->D4;
   SpreadsheetBench D3<->D4, D2<->D6; ALFWorld D3<->D4, D1<->D2; else the most frequent other code). Up to 6 items
   correct on every run, stratified on a code-relevant surface feature (pilot: reference word count, 3 multi-word
   and 3 single-word). By construction every shown target item carries c, so `evidence_other_code` cannot occur.
   The LiveMath D1 call must see D2 failures (meta option wrongly chosen). That forces a condition instead of
   "choose the meta option" (links to D7).
3. **Conditional template.** Three slots, `when` (one observable test, at most 200 characters), `do` (at most 300) and
   `otherwise` (at most 120), joined by code as "When <when>: <do>. Otherwise, <otherwise>." The join guarantees the
   form and the 600-character limit. The worked example uses a made-up task kind (financial table, thousands vs millions):
   two bad rules (a global restatement; a task fact) and one good rule.
4. **Explicit constraints, enforced by code.** (1) do not repeat card or Skill advice: `covered` quotes it. (2) No
   task facts; examples must be invented placeholders. (3) No 8-word copy, no reference answer or multi-word answer
   phrase, no 3+-significant-digit reference number, no option text. (4) No answer-distribution steering. (5) Support:
   at least 4 failing unseen items (MIN_TRIGGER). (6) Character limits and the Skill's remaining bytes (20,000 - parent).
   (7) Evidence ids only from the shown items. Placement and transfer are removed from the proposer: a separate step
   decides them, which ends the double authority and the silent void.
5. **Validation and re-ask per row.** An invalid row is re-asked with its exact errors (at most 2 re-asks). The other
   rows stand. A reply is never rejected because of one field.

The tested prompt is `run2/scripts/v5prompt.py` (SHA-256 of the system text `16c8b552a2e88dea...`). Changes for
v5.1 suggested by the pilot (NOT tested):
* "Estimate in `share` the fraction of tasks of this kind on which the condition holds. Aim below 0.3. A condition
  that holds on more than half is a global directive and is tested on the whole panel." (pilot: 'this <category>' fired on 49/97)
* "A condition is ONE observable test. If you need two tests, write two rules." (D2's compound condition stayed
  388-489 characters even after the re-ask)
* "A condition may be a property of your own draft answer (for example a word it shares with the question)." (the best
  pilot condition is of this kind)
* Drop the `risks` list (in the first D2 reply, 2 ids were listed as both `spares` and `risks`). Keep `fixes`/`spares` as a consistency check only,
  because the judge agreed with them 19/26 and 17/22.

## 6. Pilot (E-ds s1, SearchQA, training proposal half; GLM-5.3, temperature 0, max_tokens 16384, as v3 roles)

Payloads (measured). D1 call: 95,433 bytes, 12 of 14 D1 items, 4 D2 items (all D2 items not also D1), 6 always-correct
items. D2 call: 74,134 bytes, 5 of 5 D2 items, 6 D1 items, 6 always-correct. Check half: 99 items; D1 on 6 items,
D2 on 7 (code-based trigger for both above 4).

Rules produced (verbatim join of the slots; judge counts over 97 judged check-half items, of which 25 had a failed run
and 72 passed on every run; the D1 rows of the judge's 97 = 5 items):

| Rule | Text (joined) | chars | limits | leak | applies | failing among them | D1 recall | always-correct exposed |
|---|---|---|---|---|---|---|---|---|
| D1 run a r1 | When the clue refers to the answer with 'this' plus a common-noun category, e.g. 'this missile', 'this sport', 'this radar', 'this beverage company', 'this event': answer with the distinctive proper name alone and drop the category noun and any leading article, unless the noun is an inseparable part of the name as it is normally written (test: the name would sound wrong without it). Otherwise, give the full proper name as commonly printed, including any word that is genuinely part of that name. | 499 | ok | none | 49 | 8 | 3/5 | 41 |
| D1 run a r2 | When the clue quotes a word or fragment of the answer in quotation marks or embeds it in the phrasing (...): answer with only the missing word or words, not the whole phrase with the already-given part re-attached; prefer the single head noun that the quoted modifier describes. Otherwise, answer with the complete name of the work or thing being asked for. | 493 | when 238>200 | none | 10 | 8 | 4/5 | 2 |
| D1 run a r3 | When the clue asks for a person ('this man', 'he', 'artist whose', ...): give the name in the form the person is most commonly known by: keep first and last name, but drop middle names, middle initials, 'Jr.'/'Sr.', and honorific or professional titles unless the person is normally called by the fuller form. Otherwise, give the person's name exactly as the context most often prints it. | 407 | ok | none | 27 | 7 | 2/5 | 20 |
| D1 run b r1 | When your candidate answer contains a content word that also appears verbatim in the question itself (e.g. a type word like a sport, device, event, or organization noun the clue already supplies): delete that repeated word from the answer, leaving the distinctive head term only, and verify the shortened form still names the thing asked for. Otherwise, keep the candidate as is, with no additions or deletions of words. | 420 | ok | none | 14 | 11 | 5/5 | 3 |
| D1 run b r2 | When the question quotes only part of a title or name in quotation marks while describing it with other words (...): answer with just the core word that the clue asks for, omitting the quoted portion and any subtitle or place-name continuation of the title. Otherwise, answer with the full name or title as it is normally known. | 369 | ok | none | 3 | 0 | 0/5 | 3 |
| D1 run b r3 | When the answer is a person's name and your candidate includes middle names, middle initials, generational suffixes, or honorifics: reduce to the name the person is most commonly called (typically first and last name), and use that short form in the answer. Otherwise, leave the name exactly as identified, including full names of organizations or works. | 354 | ok | none | 5 | 3 | 2/5 | 2 |
| D2 re-ask r1 | When the question asks to name a species, person, publication, or organization, and the snippets repeatedly present the answer's canonical name in a form that differs from a plain draft (...): find the recurring canonical form ... and copy that exact form ... Otherwise, answer with the plain name as the question itself implies, adding no qualifier, type word, or title beyond what the question uses. | 709 (first reply 917) | when 388>200, otherwise 129>120, joined 709>600 | none | 18 (question part only) | 5 | (D2 1/6) | 13 |

Readings (measured unless marked):
* Form: 7 of 7 final rules (3 + 3 from the two D1 calls, 1 from the D2 call after its re-ask) are conditional with an
  explicit default. 5 of the 7 are within every limit.
  0 of 7 with a mechanical leakage finding (frozen v3 checks against the SearchQA training pool).
* Consistency across the two per-code calls: D1 says drop the words the question already supplies, and D2 says add
  a qualifier only when it is NOT in the question and the snippets repeat it. The pair is consistent; v3's E-ds s1-r1
  vs r4 contradicted. Evidence: one pair only, so this is a weak claim, not a measurement of a rate.
* Stability: run a and run b (same prompt, temperature 0) share the same three themes (category word, quoted fragment,
  person name), but no text is identical. The best condition (b r1) appeared only in run b. A v5 step should sample
  2 replies per code and keep the union.
* Re-ask: one re-ask with the exact errors fixed 2 of 5 listed problems (`adds`, `spares`/`risks` overlap) and shortened
  the rule 917 -> 709 characters, but 3 limits stayed broken. One generic re-ask is not enough; the error message needs
  the fix ("split into two rules").
* MIN_TRIGGER under judge-based triggers (failing check-half items where the condition holds, need 4): 8, 8, 7, 11, 0, 3,
  5. So 5 of 7 pass. b r2 (3 items apply, 0 failing) and b r3 (3 failing) would not be tested, although v3's
  code-based trigger (5-6 items) would test them on items they do not apply to. That shows the mismatch the v4 fix removes.
* Harm exposure: a global "shorten the answer" rule touches all 72 always-correct items (v3's E-ds s1-r1 died on C2,
  rest delta -15/2). b r1 touches 3 of 72. a r1 touches 41 of 72, so it is effectively global.
* Self-labels vs judge: the proposer's `fixes` satisfy its own condition per the judge in 19 of 26; its `spares` are
  outside the condition in 17 of 22. Useful as a cross-check, not as the trigger.
* Caveat: the applicability labels are a single GLM judge pass (question plus the parent's first-run draft, no snippets),
  not ground truth. No solver run tested whether any pilot rule fixes items. The fixable share is bounded: of b r1's 11
  failing items only 5 are D1, and the others are D2-D5 failures that shortening cannot fix (estimated upper bound
  5 items, before the 50% dead-item rate and the noise floor from the context file are applied).

Ablation, the v3 prompt on the same D1/D2/correct items (v3 schema; validated with the frozen v3 validator; 27,367 tokens):
5 rules, all valid per v3. Rule 1 is a global directive ("For clue-style questions, give the shortest natural form of
the answer: a bare last name for a person ..."). Rule 2 has `answer_word` hits ("licorice", "lingual", literal training
answers used as examples). Rule 4 has `answer_text` (a multi-word training answer phrase), and its direction is wrong
for its own D2 evidence ("answer with the name proper (e.g. 'Forbes'), not ... 'Forbes magazine'" while the reference
of that cited item is the longer form). The transfer slot named local rule 3, so `not_a_similar_rule` occurred again.
The per-code payload alone already induced 4 conditional rules out of 5. The template plus the placeholder constraint
removed the global rule, the leaks and the transfer void.

Token use (measured): D1 a 28,653; D1 b 28,347; D2 a 23,857; D2 re-ask 22,319; v3 ablation 27,367; judge 31,126;
second rater 13,478. Total 175,147.

## 7. What a per-code, conditional proposer would have produced in v3 (estimate)

* Removed by construction or by row re-ask: 8 evidence_invalid, 1 invalid row, 3 reply rejections (187k tokens).
  Expected removal: 2 example-based leaks (pilot 0/7 vs ablation 2/5; small n).
  Not removed: the 2 LiveMath meta-option rules. That is a policy conflict between the taxonomy and option-text
  leakage (D7), not wording.
* Not requested: the 8 insufficient-support rules (code-based) or the judge-sized equivalents.
* Prepare-stage survival, estimated: about 37-40 of 49 instead of 28 (the 9 mechanical deaths plus 0-2 example leaks
  recovered). Assumption: the same number of ideas per code.
* After prepare, no change is expected in the C1 outcome: 14 of 15 screened rules failed C1, with gains inside the placebo
  range. Conditional rules reduce C2 exposure (the one C2 death) and focus the panel on applicable items, which raises
  the effective panel above ~29% of nominal (context file, verified by the main session). They cannot create headroom:
  50.3% of v3 trigger items were dead for every arm (context file).

## 8. Risks

* Applicability judging adds a GLM classification layer whose errors move triggers. One pass agreed with the
  proposer's self-labels only ~75%. Use reason-then-label with a 3-vote majority (as planned for v4) and audit 20 items.
* Draft-dependent conditions ("your candidate contains ...") need the parent's draft at judging time. The rule arm's
  draft may differ.
* More calls per stage (27 vs 10 over v3) and more rules per stage mean more multiplicity at screen (D8). Cap rules per
  code (2) and per stage (5) after a cross-code consistency check.
* Per-code calls can still contradict each other across codes. A merge-time pairwise check is needed (the pilot's
  consistent pair is n=1).
* The SearchQA references are sometimes arbitrary truncations ("The Outcasts" for the full story title, in the pilot
  data). No observable condition predicts those. Some D1 failures are label noise, not learnable form errors.
* The restatement coding is subjective (kappa 0.41 four-way). The robust statement is "8 by both raters, 18 by one".

## 9. Cost

Per-code proposals for a v3-sized chain, estimated: 11-16 calls x 25-45k tokens = 0.3-0.7M GLM tokens per chain
(v3: I-ds 476,736, E-ds 272,733 analyst tokens, measured). Applicability judge, estimated: about 31k tokens per
SearchQA code pass (measured once); OfficeQA and SpreadsheetBench conditions need page or workbook context, perhaps
50-150k per pass. Total: about 1-2M GLM tokens per chain, under 2% of the 139M v3 run.

## 10. Recommendation

Adopt into v5: the per-code call; balanced evidence (target / opposite / always-correct); the slot template joined
by code; explicit constraints checked by code; row-level re-ask with the concrete fix; no placement or transfer in the
proposer; 2 samples per code; the v5.1 additions (share estimate, one-test conditions, draft-property conditions).
Before any paid chain: a free step that applies the cal-1 placebo and noise numbers to judge-sized trigger panels
(D5/D8). Also a one-day screen pilot of the 5 limit-passing pilot rules plus v3's E-ds s1-r1 on the E-ds s1 check half
(estimated 6 arms x ~20 items x 4 runs x ~3.4k tokens = about 1.6M deepseek tokens). It would test whether conditional
rules lower C2 harm without losing C1 gain. Do not present proposal-quality gains as method-effect evidence.

## 11. Artifacts

New machine `/data/feasibility/D13/run2/`: `scripts/` (trace, reconstruct copy, leak, evid, coding inputs, v5prompt,
pilot, followup, check, check_v3abl, judge, trig, rater) and `out/` (proposals_traced, stages, leak_findings,
evidence_summary, pilot payloads, all replies, pilot_checked, pilot_judge, pilot_triggers, rater). Mac copies:
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D13/run2/`
(`proposals_traced.json`, `stages.json`, `cards_instructions.json`, `analysis/coding.py`, `analysis/coded.json` with
both raters' codes, `pilot/out/*`, `pilot/scripts/*`).
Code read: `skillopt/coevo5/analyst.py` (ANALYST_SYSTEM, payload, evidence_problem, _transfer, _row), `step.py`
(prepare, _admissible, trigger), `leakage.py`, `protocol.py` (TAXONOMY, limits), `roles.py`, `skill.py`.
