# Design contract (2026-10-11, early morning): one KOR-Bench matched-scalar study with the repaired package

Extends `active-evidence-reference-study-design-20261010.md` (study v2) and the evidence-delivery repairs of
`active-evidence-screen-design-20261011.md`. No code change to the package or the stage tool; one new zero-call
reading script. Frozen before the stage is launched and before any of its outcomes exists.

## 1. Why

Tonight's SearchQA studies with the repaired diagnosis package (rep1, big1d, rep3; more queued) all put the
diagnosis branch a few points above the pass/fail branch, each interval containing 0. The owner's yardstick is one
frozen optimizer that works across datasets. BigCodeBench has a queued study with the same package (brep1).
KOR-Bench has none: its only v11 run (m1, 10/10, method mode) predates every repair -- in particular the case view
then truncated long rules, and judged verdicts were discarded ("prefer no change"). This run asks the same question
there with the same frozen settings; nothing is tuned for KOR.

## 2. The run (settings frozen here)

`korbench-active-krep1`: snapshot `20261011-g` (repairs R1-R3, summary v3, passed-case controls), arms
`diagnosis_research / matched_scalar_branch`, `update_mode = native`, parent none, seed 20261006, no named
reference (the parent reference always runs), `G_SKIP_TEST=1`, no test read. Every limit at its default: the study
holdout is `min(242, eligible pool)` = the WHOLE eligible pool here, 200 tasks = 20 rule families x 10 tasks, all
of them rules outside the 30 step families (so each contrast is measured on rules the step never saw); coverage
requirement 90% of 200 = 180 jointly known. Step rows: 90 (30 rules x 3), the same seeded subset as m1.

Not screened: a KOR screen would add up to 11 arms x 90 slow positions (about eight more hours).
Expected cost: about six hours behind the shared lock (holdout 3 x 200 positions at about 29 s per position with 8
workers, diagnosis about one hour), 4-5M tokens. It is launched last and will still be running when the morning
report is written; it is reported as running, never as a result.

## 3. Reading (fixed now; revision 2 after the reviewer's four must-fix items)

Tasks inside one rule are not independent, so the study record's task-level class and Tango interval are
DESCRIPTIVE here (they ignore clustering and are too narrow). Primary, per contrast, from the sealed positions with
[active-evidence-family-summary-20261011.py](active-evidence-family-summary-20261011.py) (zero-call):

* the mean over families of the within-family difference of pass rates on jointly known positions (every family
  weighted equally), with an approximate t interval over families -- families assumed independent, conditional on
  this realized pair of Skills;
* improving / regressing / tied families and the exact two-sided sign test over non-tied families (a test of
  directional balance, not of the mean effect).

Missing data, fixed now: positions with either side unknown are dropped inside a family and the per-family
jointly-known counts are printed. A family with NO jointly known position is missing: it is listed and never
counted as a tie; the estimate is then labelled an available-family estimate with its own degrees of freedom
(families - 1); with more than a tenth of the families missing (more than 2 of 20 -- the study's 90% coverage rule
applied to families) no primary estimate is reported for that contrast. Independently, EVERY contrast (the
branch-minus-parent ones included) needs ceil(0.9 x positions) = 180 of 200 jointly known positions; below that no
primary estimate is reported for it either (revision 3).

Eligibility, read from the sealed study record before any number is interpreted: identical Skill texts (a
same-Skill replicate), a branch not recorded as a Skill that differs from the parent, a diagnosis package that was
not delivered, a missing holdout or a missing reference record make the affected contrasts diagnostic only or
unavailable, and the script says which.

Contrasts, named separately: treatment (diagnosis branch) minus comparator (pass/fail branch) -- the package
question; each branch minus the parent reference (no Skill) -- does ONE unselected step help on unseen rules at
all. Expectation, not a guarantee: m1's 96-position panel gave a family-level interval of about +-0.11 for
candidate minus parent, so with 200 positions in 20 families power is limited to effects of roughly eight points
and more. A wide interval leaves the effect unresolved; a sufficiently narrow interval can exclude worthwhile
gains; a negative result can indicate harm. All contrasts are exploratory.

Scope: one unselected update step from one learning history on rules the step never saw. It does not measure the
optimizer's reliability across histories, nor the deployed decision policy (decision v2 is not exercised in a
study). Packages differ across tonight's runs (rep1 / sel1 / bsel1: snapshot c; rep2-rep4 / refine / brep1: e-f;
ctl1 / cov1 / this run: g = e plus passed-case controls); the per-run table carries the package identity and no
cross-run difference is attributed to a package change.

Disclosures to be written with the result: the 200 pool tasks are the reserved development pool that m1's fresh
panel drew 96 tasks from on 10/10 (m1's candidate was parked; no Skill was chosen by those outcomes); F evaluated
every development task earlier under other Skills; the design follows tonight's SearchQA results, so this is
reused, adaptive development evidence, one learning history, one seed. The parent reference runs after the two
branches (not interleaved). A difference between this run and m1 is not attributable to the repairs (different
package, different draw, different day).

## 4. Addendum (2026-10-11, evening; frozen before any replication outcome exists): three more histories

Why: krep1 (seed 20261006) gave pass/fail branch minus no Skill = +0.070 [-0.013, +0.153] over 20 unseen rules
(9 / 2 / 9 families, sign p 0.065) and diagnosis minus pass/fail = -0.015 [-0.050, +0.020]. One history cannot say
whether a one-step update helps on rules its step never used; the owner's yardstick is a procedure that works on
more than one dataset, and SearchQA is so far the only domain where a one-step gain over the EMPTY Skill has shown
up consistently (adaptive development evidence).

Runs (one at a time on the shared lock, behind the pilot stage ksh08): krep1 with the seed changed -- arms
`diagnosis_research / matched_scalar_branch`, native update, parent none, defaults for every limit,
`G_SKIP_TEST=1`, no test read -- seeds 20261009 / 20261010 / 20261011 (KOR seeds not used by any earlier stage:
06 = m1 and krep1, 07 = the cancelled ksm07, 08 = ksh08). Each seed draws its own 30 step rules and leaves the
other 20 of the 50 training-partition rules as the holdout, so holdouts overlap between seeds.

Amended the same evening, before any of these stages had begun: the three stages were first prepared as
`korbench-active-krep2` / `krep3` / `krep4` under snapshot `20261011-g` with no named reference; they are NOT
launched (prepared, unused records). They run instead as `korbench-active-krepg2` / `krepg3` / `krepg4` under
snapshot `20261011-j` with one evaluation-only named reference, the fixed generic instruction of
[active-evidence-generic-control-design-20261011.md](active-evidence-generic-control-design-20261011.md) (about 45
more minutes each). Same seeds, arms and limits. Snapshot j's package is snapshot i's; it differs from g's in the
BigCodeBench probe parser and the optional train panel of the challenge arm, neither on a KOR matched study's path
(read from the diff, not verified by execution). So these are NOT "krep1 with only the seed changed": besides the
seed, the named reference changes the manifest (hence the seeded evaluation order) and the reserved call capacity,
and adds a fourth block of holdout solves after the parent reference; the branches' own settings are krep1's.

Reading, fixed now:

* every history exactly as section 3 (the same script, the same eligibility and missing-data rules);
* across krep1-krep4, per contrast, with
  [active-evidence-kor-pooled-20261011.py](active-evidence-kor-pooled-20261011.py) (zero-call): the rule-clustered
  mean (each rule's within-rule difference averaged over the histories in which it was a holdout rule; equal-weight
  mean over rules, t interval over rules, sign test over non-tied rules) and the list of per-history family means
  with the number that are positive. The contrast read first is pass/fail branch minus no Skill; then diagnosis
  branch minus no Skill; then diagnosis minus pass/fail.
* The same pooled reading on the three new histories ONLY (`--also-without krep1`) is the sensitivity reading that leaves out
  the history whose outcome was known when this addendum was written.
* All four histories are reported whatever they show, including any that stop or are ineligible. krep1 is part of
  the first pooled reading although its outcome is known (disclosed: it motivated the replication); that pooling is
  adaptive and exploratory.

What it can and cannot show (revised after the direction check, before any outcome): the estimand is the
equal-weight mean, over the observed eligible holdout rules, of the realized one-step updates' within-rule effect
on reused development data -- not an equal-history average and not the reliability of the procedure. Rules and
histories are crossed (one Skill serves the 20 holdout rules of its history; step rules overlap between seeds), so
the t interval and the sign p-value are working-independence summaries that understate the uncertainty by an
unknown amount; they are not calibrated procedure-level inference and are not used to exclude gains. Neither
pooled reading is a confirmation and neither attaches a deployment decision. They do inform research planning:
whether KOR-Bench enters the prospective hold-out read with a pass/fail one-step arm is judged from the new
histories TOGETHER with the generic-instruction contrasts (a learned Skill that does not beat the generic text is
a different case from one that does), and such a read would keep the generic-instruction control. Nothing here
establishes cross-dataset generalization or validates a decision rule. Expectation, not a
criterion: per-history intervals will each contain 0; the pooled pass/fail-minus-no-Skill mean lies between 0 and
+0.07.
