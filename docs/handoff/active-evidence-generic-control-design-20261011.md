# Design contract (2026-10-11, evening): a fixed, hand-written "generic instruction" as an evaluation-only control

Extends `active-evidence-reference-study-design-20261010.md` (study v2: named evaluation-only reference Skills on
the study holdout) and section 4 of `active-evidence-kor-study-design-20261011.md`. Snapshot `20261011-j` = `i`
plus one change to the stage tool. Frozen before any stage with such a reference is launched.

## 1. Why

Every v11 comparison so far is against the EMPTY Skill. Two zero-call readings of sealed records (ledger, 10/11
14:45 and 19:10) suggest that what the learned one-step Skills add may be largely generic:

* SearchQA: with no Skill 21-25% of all holdout tasks fail exact match although answer and reference contain one
  another; after one step 8-12%. The kept Skills consist largely of answer-form rules ("output only the entity").
* KOR-Bench (krep1): 11 of the 14 net tasks gained by the pass/fail branch are in the logic category (19 -> 30 of
  40), where the solver's mean reasoning tokens per task rise from 133 to 761 and the median visible answer from
  20 to 211 characters. At low effort the solver hardly reasons on SearchQA and BigCodeBench (2-5 reasoning tokens
  per task without a Skill).

If a three-line instruction that anyone would write obtains a similar gain, the claims and the planned hold-out
read have to be framed against that baseline and not only against the empty Skill. This is the missing control.
(The SearchQA gains referred to here are adaptive development gains against the EMPTY Skill.)

## 2. What is added

Tool only (`scripts/run_fivebench_g_stage.py`, `reference_skill`): `--reference name=f:<text file>` -- a FIXED
text supplied by the operator, solved on the study holdout exactly like the other named references (own rollout
key, evaluation-only, never a parent, never shown to a diagnoser, analyst or Research). The stage record seals the
file path, byte length and sha256 with `action: fixed_text`; the manifest carries the text. Nothing in the
`active_evidence` package changes; the report tool exports the byte length. Package of snapshot j = snapshot i;
its differences from g (krep1's snapshot) are the BigCodeBench probe parser (`checks.py`, the probe record in
`diagnosis.py`) and the optional train panel of the challenge arm -- none on the path of a KOR-Bench or SearchQA
matched study (read from the diff, not verified by execution).

The three texts (same for every dataset; `docs/handoff/active-evidence-generic-control-texts-20261011/`):

* `generic` (416 B, sha256 724d5870...): (1) think the task through step by step and check the result against
  every stated condition; (2) follow the task's rules, definitions and conventions exactly, even where they differ
  from everyday knowledge; (3) give the final answer in exactly the form the task asks for, as short as that form
  allows, with nothing around it.
* `generic_reason` (264 B, 908f0a34...): bullets (1) and (2) only.
* `generic_form` (173 B, 73c67465...): bullet (3) only.

Authorship disclosure: written by the operating assistant on 10/11 after it had read one kept SearchQA Skill and
the two readings above. They are deliberately INFORMED trivial baselines: the strongest three lines one would
write knowing what the learned Skills turned out to say, but naming no dataset, no answer format and no rule.
They were not tried on any task before being frozen and will not be edited after an outcome.

## 3. Runs (queue t1; matched-scalar study v2, `diagnosis_research / matched_scalar_branch`, native update, parent
none, defaults for every limit, `G_SKIP_TEST=1`, no test read)

In this order (short stages first; one at a time on the shared lock):

1. `searchqa-active-gen17`, seed 20261017, references `generic`, `generic_form`, `generic_reason` (about 15 min).
2. `searchqa-active-gen18`, seed 20261018, the same three references.
3. `bigcodebench-active-bgen12`, seed 20261012, the same three references (about 50 min).
4. `korbench-active-krepg2` / `krepg3` / `krepg4`, seeds 20261009 / 20261010 / 20261011, reference `generic` only
   (each named reference costs 200 slow positions there). These REPLACE the three stages krep2-krep4 of the KOR
   memo's section 4, which were prepared under snapshot g and never begun (their directories stay as prepared,
   unused records): same seeds, same arms, same reading, plus the one reference.

Seeds are new for their domain (SearchQA 06-16 and BigCodeBench 06-11 are used; KOR 06-08).

## 4. Reading (fixed now; revised after the review, before any outcome)

Per study, on its own holdout, from the sealed study record (study v2 computes, for every named reference, the
paired difference with a Tango interval for reference minus parent and for each branch minus the reference). Read
in this order, the same in every domain (it matches the KOR memo's order, with the generic contrasts appended):

1. pass/fail branch minus no Skill, diagnosis branch minus no Skill, diagnosis minus pass/fail -- the study's own
   contrasts, as before;
2. **Q-A, generic minus no Skill** -- does this fixed hand-written instruction give a gain on this holdout?
3. **Q-B, pass/fail branch minus generic** -- the Skill LEARNED FROM THE EMPTY parent against the generic text. It
   is a comparison of two alternatives, NOT a measurement of what learning adds on top of the generic instruction
   (no branch here starts from the generic text; that would be a different study);
4. diagnosis branch minus generic; the same three for `generic_form` and `generic_reason` where they ran;
   `generic` minus `generic_form` and minus `generic_reason` from the sealed positions (zero-call) as a descriptive
   split of the generic text's own effect.

KOR-Bench: the family-level reading of the KOR memo, per history and pooled over the histories that evaluated the
reference, with the pooled script extended to the contrasts that name `generic` (same working-independence
caveats; task-level intervals are descriptive there). Descriptive, per arm, everywhere: mean reasoning tokens,
visible answer length and reported tokens (a generic "think step by step" may buy accuracy with inference cost).

Interpretation, fixed before any outcome (each statement keeps its interval; no equivalence margin is frozen, so
no equivalence is claimed in either direction):

* Q-A about as large as "learned minus no Skill" and Q-B's interval centred near zero: on that holdout the
  observed gain is also obtained without a new automated learning run, by an informed hand-written text. It does
  not establish equivalence, and it does not show that learning is useless elsewhere -- one text, written with
  knowledge of the learned Skills, on reused development pools -- but every later claim then has to be made
  against a generic-instruction baseline and not only against the empty Skill.
* Q-B's interval clearly above zero: the learned text does something this generic text does not (on that domain
  and holdout); it does not show that this something is more than dataset-specific answer conventions.
* Q-A's interval containing zero: no gain from this particular text is established there; that is not evidence
  that it does nothing and says nothing about the learned Skill's mechanism.
* One generic text on KOR-Bench tests that one competitor, not generic instructions in general and not the
  reasoning mechanism as such.
* All of it is adaptive development evidence; no deployment decision is attached. It does inform research
  planning: a prospective hold-out read would carry a generic-instruction arm whatever these runs show.

Expectations, not criteria: SearchQA Q-A positive (+0.04 to +0.10), Q-B small (0 to +0.06); BigCodeBench all
within noise; KOR-Bench Q-A positive on logic rules, Q-B near 0.

Disclosures: reused development pools; the references run in blocks after the two branches and the parent (not
interleaved or counterbalanced with them), so a service drift during a stage can bias a reference contrast -- an
explicit limitation of tonight's runs, shared by the study's parent contrasts; KOR histories share rules; the
`f:` path trusts the supplied text (it cannot certify what its author had seen -- that is this memo's disclosure).
Later, not tonight: interleaved / counterbalanced arms, a zero-shot analyst-written Skill with declared
information access as a further arm, and a cost-matched comparison.

## 5. Execution notes (appended; sections 1-4 are unchanged)

* 2026-10-11 21:42 -- `gen18` ended `pending` 67 seconds after it began, reason
  `treatment_package_not_delivered:diagnosis_no_hypotheses`: the diagnoser's reply and its one repair were both
  rejected by the all-or-nothing validation of the hypothesis list (the third hypothesis named no case). By the
  study's own rule a stage stops before any updater call when the treatment package is not delivered, so no
  candidate, no holdout draw and no outcome exist (130 calls: 128 step solves and 2 diagnoser calls). It is not
  resumed and stays as a stopped record. Replacement: `searchqa-active-gen19`, seed 20261019, the same settings,
  references and snapshot j, queued on its own (queue t3). The replacement was decided after gen17's outcome had
  been read; gen18 has no holdout outcome that could have influenced the decision.
* The same early stop can hit any stage of this design: of the 24 diagnosis runs of v11 so far, 9 needed the repair
  call and 2 ended without hypotheses even after it (one of those two, on 10/11 at night, had a cause that was
  fixed afterwards). A KOR-Bench stage that stops this way is reported as a lost history; whether it is replaced
  is decided and disclosed then. Making the validation drop an invalid hypothesis instead of the whole reply is a
  package change for a later version, not made tonight (all control stages keep the package of snapshot i).
