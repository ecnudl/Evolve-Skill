# Critique of spec-measurement.md -- LENS 1: evidence and statistics

Critic: adversarial reviewer (evidence/statistics lens), 2026-10-21, started 19:20 CST. Read-only.
Target: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/spec-measurement.md
Status: COMPLETE (28 findings: 0 fatal at protocol level, 1 fatal for a headline claim (F5), 14 major, 13 minor; see index).

Conventions: every number is marked "measured (source path:line)" or "estimate (assumptions)".
Severity: fatal / major / minor. Implementer-facing text in English; owner-facing summary at the end in plain Chinese.

## Findings

### F1 [MAJOR] LiveMath acceptance is gameable by the "stronger statement" label artefact; the ban covers generators only

- Attacked text: §6.2 "L labels: ... Banned: training-label regularities (LiveMath generated items contain no 'stronger
  statement' meta option at all ...)" -- the ban is scoped to *generators*. §4.4 (engineer checks) has only
  `leakage.mechanical` + "AST literal/regex/dict-key extraction against the R references"; nothing forbids a *procedure*
  from conditioning on the meta option. §2.2 even records "129 contain the 'stronger statement' meta option, always the key".
- Evidence: meta option in 129/283 LiveMath training items and the key in all 129; "pick it whenever present" is
  estimated at 76% vs task card 33% -- measured (feasibility-prototypes.md:304-305, citing FD/D9/result.json:7 section G).
  E4 critic: "42-84% of LiveMath gains come from the always-correct meta option" -- measured
  (feasibility-prototypes.md:367-368). The v3 examiner taxonomy itself names the code "missed/wrongly chose stronger
  result" (coevo5-method.md:192-193), so the engineer's diagnosis inputs point straight at it.
- Why it breaks the measurement: R (83 items) and A (200 items) are cut from the SAME 283-item pool, so the artefact is
  present in ~45% of both. A context note "if an option says a stronger result can be proven, prefer it" (or a veto-style
  note) is not a literal reference and passes every §4.4 check, then passes the IUT on A by tens of points (D9's own
  estimate is +43 points POOLED, 76% vs 33%; on the ~45% of items carrying the option the gain is larger still --
  estimate, assuming the card's accuracy on the other items is unchanged). That is a training-label
  regularity, not a skill, and it would also be counted as "home gain" at test if the LiveMath test shares the artefact
  -- and DR §5 step 3 already asks the LiveMath TEST readout to be split by presence of the option, "去掉后约剩 68 道"
  (direction-recommendation-20261021.md:80), i.e. roughly 57 of the 125 test items carry it (estimate, 125 - 68). DR §4 停
  is explicit: "不去'学'LiveMath 的'更强结论'选项 ... 学到它不算学习" (direction-recommendation-20261021.md:35).
  The LiveMath step therefore cannot distinguish skill from artefact exploitation, in acceptance or at test.
- Fix: (a) extend the §6.2 L-ban to procedures, predicates, notes and detectors: a static check rejects any source or
  note containing the `STRONGER_OPTION` text (protocol.py:222), its normalised substrings, or option-position logic;
  (b) register the LiveMath decision contrast on the meta-free stratum (items whose choices do not contain
  STRONGER_OPTION; ~154 of 283 pool items, measured count derived from 283-129), with the full-pool contrast reported
  only descriptively; (c) report S'-S separately by stratum in every LiveMath table; (d) state in the owner summary
  that pre-existing LiveMath "gains" were mostly this artefact (E4 critic).

### F2 [MAJOR] ALFWorld run and acceptance slices share scenes/task folders; acceptance rewards seen-scene memorisation that the valid_unseen test cannot reward

- Attacked text: §2.3 "R and A are cut from one order over these 657" and "The selector of §6.2 draws only from the
  remaining ~2,914 train games, so generated (selected) games never overlap R or A."
- Evidence: `json_2.1.1/train` holds 3,553 games in 2,435 task folders -- measured (data-and-pools.md:204-211), i.e.
  ~1.46 trials per task folder (several trials of the SAME task in the SAME room with different initial placements).
  Measured by this critic (read-only `ls` of dl:/root/continual-alf-prep-20260928/data/json_2.1.1/train, 2026-10-21,
  names only): the 2,435 task folders span only **108 distinct rooms** (trailing scene number of the folder name), and
  there are 7 task-type prefixes, including 365 `pick_and_place_with_movable_recep` folders, which is not one of
  ALFWorld's six types -- the registration must say whether D_alf's "100 per task type" excludes them.
  The test is very probably `valid_unseen` (data-and-pools.md:218), which in ALFWorld uses rooms not present in train
  (domain knowledge; to be confirmed by S-T1).
- Why it is a problem: "never overlap" is true by game id only. A random 657-game draw puts trials of the same task
  folder, and certainly of the same room, into both R and A: with 108 rooms and R = 100 games, ~61% of A games share
  their room with at least one R game (estimate, uniform-room approximation). A procedure keyed on the room's receptacle list
  ("in this layout, search countertop 2 then cabinet 4 first") learned from R trajectories is legitimate under §4.4 and
  will help on A (same rooms) and on the selector's games (same rooms), but not on unseen-room test games. The
  acceptance batch then certifies an in-distribution memorisation effect, and the readout calls it a learned skill.
  D14 already showed in-sample hindsight from walkthrough metadata ("55/57 open surfaces", feasibility-prototypes.md:115-120).
- Fix: register a GROUPED split: parse the room/scene id from the game path (the trailing scene number of the task
  folder) and assign whole rooms to R, A and the selector pool (disjoint room sets); cluster the item bootstrap and the
  detector bootstrap by room; add a static check that no predicate/procedure contains a receptacle-numbered literal
  ("cabinet 4") unless it comes from the current view. Report the R/A room overlap count in the registration.

### F3 [MAJOR] OfficeQA documents are shared between train and test (40 bulletins); procedures can memorise document facts and the home-bench test gain would partly be memorisation

- Attacked text: §4.4 step 2 (leakage = literal extraction "against the R references and test-free corpora") and §7.2 Q1
  "F - C on b's test set".
- Evidence: "The split is not document-disjoint: train and test share 40 bulletins" -- measured
  (data-and-pools.md:185, citing current-workflow.md:56).
- Why: an engineer that sees R trajectories with references can write a procedure "if the question mentions the
  <month year> bulletin and 'public debt', the figure is in table FD-1 / page n" -- not a reference literal, so it passes
  §4.4; it helps on A when A shares bulletins with R and on the 172 test items that share the 40 bulletins. Q1 would then
  report document memorisation as a home gain.
- Fix: static rule: procedures/notes may not contain bulletin identifiers (issue dates, page numbers, table ids) taken
  from R items (AST literal check against the R items' `source_files`); register the OfficeQA Q1 readout split into
  "bulletin seen in route-B R items" vs "not seen" (a test-side bulletin list is already needed for generators,
  data-and-pools.md:411-412, so compute it inside evaluation with TestAccess); the headline OfficeQA effect is the
  not-seen stratum.

### F4 [MAJOR] The MDE table overstates the power of the registered decision; its low ends are not supported by the measured anchors, and every noise input comes from the old solver

- Attacked text: owner summary item 3 (spec line 19) "量得出的最小差别（80% 把握）：SearchQA 1,000 题约 2–3.4 分 ... OfficeQA
  50题×4次约 6.5–11.6 分；SpreadsheetBench 60题×2次约 8–13 分"; §2.4 table (lines 279-283); §5.6 (line 498) "Power at the
  §2.4 MDE ≈ 0.8 for S' − S alone".
- (a) The decision is an intersection-union rule (S'>S AND S'>P, line 467). With two one-sided 0.05 tests sharing the S'
  arm, joint power at the single-contrast MDE is 0.67-0.71 for correlation 0.3-0.7, and 80% joint power needs the MDE
  x1.11-1.15 -- estimate (bivariate normal, equal effect vs S and P, i.e. an inert placebo; computed inline by this
  critic). The owner is told "80%" for a rule that has ~70%. If the placebo helps (cal-1: one placebo +3.6 [+0.6, +6.6],
  sign p 0.003, measured, docs/handoff/cal1-registration-20261020.md:144), joint power is lower still.
- (b) Scaling the measured D1 anchors (feasibility-prototypes.md:272-276) by sqrt(n) at the same runs per item gives
  OfficeQA 50x4 -> 8.9 and SpreadsheetBench 60x2 -> 10.7 points; D1's own parameters (paired SD 0.326 at k=1, tau 0.19
  implied by 0.042 at 300x2) give SearchQA 1,000x1 -> 3.0 and ALFWorld 200x1 -> 7.5, 150x1 -> 8.6 -- estimates derived
  from measured inputs. The spec's low ends (OQ 6.5, SB 8.1, SQ 2.0) are below every measured anchor. Its SearchQA low
  end uses s^2 = 0.049 (ids-full card, cal-1), but S' and P carry procedures, and cal-1 measured 0.074-0.161 for placebo
  texts and 0.157 for the candidate (feasibility-prototypes.md:309-313); DR §2 item 4 says same-text reruns still flip 8-10%
  of items (docs/handoff/direction-recommendation-20261021.md:17). The OQ/LM/SB s^2 values are "assumed so that 1-run
  discordance matches DP F17's implied pi" (spec line 273-274), and DP's pi were themselves "computed by me, not measured"
  (data-and-pools.md:363-369): a twice-derived assumption presented next to measured anchors.
- (c) Every s^2 and tau comes from the v3/feasibility solver (deepseek-v4-flash via the PJLAB route, feasibility-prototypes.md:43).
  The registered solver is a different model behind a different gateway. No smoke check measures its run-to-run
  disagreement (S-E1..S-E6, S-F1 are single-run checks, spec §9); the first measurement is G5's duplicate at step 1, after
  A_1 is consumed.
- Combined honest decision MDEs (80% joint power, D1-anchored, old-solver noise) -- estimate: SB ~12, OQ ~10, SQ ~3.4,
  ALF ~8.4 (200 games) / ~9.7 (150 games) points.
- Fix: (1) register decision MDEs for the IUT (joint power), with the D1-anchored value as the point estimate and the
  assumption-based range as sensitivity only; (2) add a paid smoke S-N1 "same-text duplicate" of the C arm, interleaved,
  on tail items: SearchQA 150 items x 2 arms (0.5-1.0M, estimate from §8.1 anchors) and ALFWorld 20 games x 2 arms
  (1.4-1.8M); re-register the MDEs (not the slice sizes, which are supply-bound) and the Δ_NI before the pilot if the new
  model's disagreement differs by >25% from the old; (3) owner summary: replace "80% 把握" with the joint figure.

### F5 [MAJOR; fatal for headline claim (1) as worded] Predictive validity, as registered, cannot test anything and gates nothing

- Attacked text: §6.3 (lines 576-584) "Registered contrast order: (S'−S), (S'−P), (S'−C), (S−C), (P−S), (P−C)" ... "`admitted`
  → `validated` after ≥ 2 AGREE and 0 OPPOSE"; §4.5(c) (line 409-411); §10.1 headline claim "(1) the examiner's
  predictive-validity gate".
- (a) Duplicate counting. At step 1, S ≡ C (K3, byte-identical requests). Then S'−S and S'−C estimate the same quantity
  (sharing the S' cells), P−S and P−C likewise, and S−C is a pure null. "≥ 2 AGREE" can be met by ONE underlying
  comparison counted twice; "two consecutive non-AGREE" retirement can be triggered the same way. The six contrasts are
  not six comparisons; at step 1 there are at most two distinct ones (S' vs parent, P vs parent).
- (b) In-sample bias. G_b is made FROM R items (SB perturbs R items, OQ re-computes R questions, LM varies R items, §6.2),
  and S' was written from R failures. On G the candidate is evaluated on near-copies of its own training items, so
  sign(S'−S) on G is biased positive regardless of whether G predicts fresh items. This is exactly the measured E1 pattern:
  learned candidates +13 on 124 generated OfficeQA items (30 better / 6 worse, p=0.0001) vs p=1.0 on the 74 real items
  (feasibility-prototypes.md:353-358). AGREE then mostly measures overfitting, not generator validity.
- (c) Sensitivity. AGREE needs a one-sided 90% bound on G (120 items x 1 run) to exclude 0: roughly 7.5 points on G
  (estimate: 2.12 x sqrt(0.15/120)). E9 measured that effects on generated items shrink to 0.23-0.54 of the real effect
  (feasibility-prototypes.md:371-376), so AGREE requires real effects of ~14-33 points (estimate) -- above any plausible
  accepted effect. E9 also MISSED a real −9.5 harm (UB +1.78): SILENT, which the rule treats as harmless.
- (d) Consequence-free. §4.5(c) is the only place a `validated` status is used, and it requires the current bench's
  generator to be validated at sieve time. Each bench is visited once, so a generator can only become validated after its
  own step's acceptance round: (c) can never fire in the pilot (the spec admits this, line 411) NOR in the full chain.
  A "gate" whose outcome is never consumed is a descriptive metric.
- (e) Admission is near-impossible anyway: D band [0.20, 0.80] was never reached by any generated style (E9 0.891; D6
  OfficeQA-style 14/14; spec line 564 itself). The only generator likely to pass, the ALFWorld *selector*, picks real
  train games, so its "predictive validity" is agreement between two real samples, not generator validity.
- (f) Targeting makes it worse: §6.4 has the generator aim at R's top failure category, i.e. at exactly what the
  engineer's procedure was written to fix; the D6 critic called this "rule echo" (topic-chosen material makes the panel
  echo the rule, feasibility-prototypes.md:200-201).
- Fix: (1) count distinct contrasts only: at step 1 merge S and C, drop S−C as a contrast and use it as a NEGATIVE CONTROL
  (a generator whose G shows a "significant" S−C difference is flagged unreliable); register S'−S as the single primary
  PV contrast; (2) break the in-sample link: generate from a generator-source slice the engineer never sees (LiveMath:
  cut ~30 items from the order for sources only; ALFWorld: select from rooms disjoint from R, see F2; SB/OQ: no supply ->
  register PV there as "not testable"); (3) state in §10.1 that headline claim (1) is pre-registered as "not measurable in
  the pilot", or add a second step per bench so a generator meets two real batches; (4) rename "gate" to "metric" unless
  a validated status changes something registered (e.g. a validated G replaces R-replay in the next step's sieve on the
  same bench).

### F6 [MAJOR] The test sets become a validation set through the pilot -> full-chain continuation

- Attacked text: §0 (line 103-104) "test scores are sealed until the chain ends"; §2.5 (line 294) "scores sealed until the
  chain (pilot) completes"; ST5 (line 520-522) "The remaining steps run only after an owner decision taken on the pilot
  report"; owner decision 9 "试点即正式链的前两步".
- Why: the pilot reads all five test sets once (§7), the scores are unsealed at pilot end, the owner decides on that
  report whether (and how) to continue the SAME chain, and the full chain's end read (§8.4 "test read once at the end")
  re-reads the same five test sets. A decision informed by test scores, followed by a re-read, is test-set reuse: the
  final read is no longer held out. DR §4 留: "测试集只在方法冻结后、经你同意读一次"
  (docs/handoff/direction-recommendation-20261021.md:40). The spec's own §0 rule is violated by its §2.5/ST5.
- Fix: register ONE of: (a) the pilot test read stays sealed until the whole chain ends, and ST5's continuation rule uses
  learning-side evidence only (as its default already does: ">= 1 package accepted with all guards intact"); or (b) the
  pilot read IS the study's only test read and steps 3-5, if run, are reported without a test read (learning-side only).
  Tell the owner in plain words that looking at pilot test scores before continuing spends the single test read.

### F7 [MAJOR] The non-inferiority margin is reverse-engineered from power and silently loosens the owner-approved 4-5 points to 6-10

- Attacked text: §7.2 Q3 (lines 612-616) "Δ_NI registered as the margin giving 80% power at a true difference of 0 ...
  pilot SB→OQ ... Δ_NI = 10 points".
- Evidence: owner-approved design-v0 §三 "不相似 bench 用合并的不劣检验，允许下降约 4 到 5 分"
  (scratchpad/execskill/design-v0.md:44); v6 Q3 margin was −2 points on the pooled mean
  (docs/handoff/coevo5-registration-v6-20261017.md:611); DR §5 step 3 "可测的允许下降约 4–5 分"
  (direction-recommendation-20261021.md:80). The spec changes an owner-approved parameter without a contradiction
  paragraph or an owner decision entry.
- Why it matters: a margin derived from the sample size makes "non-inferior" mean "we could not see a drop smaller than
  what we can see": under Δ_NI = 10 a 9-point ALFWorld drop passes. At the owner's 5-point margin the default pilot's
  power at a true zero is ~0.37 (estimate: SE = sqrt(0.195/134) = 3.8 points from mde.py's own pi) -- an honest and
  informative number the owner should see, and an argument for the alternative pilot.
- Second problem: in the default pilot an SB/OQ package will very likely enable nothing on ALFWorld (no table, no
  numbers). Then F and P_F on ALFWorld send byte-identical requests to C (by construction; S-Q1 checks it for QA), and Q3 is a duplicate-null
  test that "passes" by construction.
- Fix: register the owner's margin (5 points; a smaller one only by owner decision) and the resulting power; report the
  one-sided lower bound itself as the headline ("a drop larger than x points is excluded"); when the router enables 0
  test items on a bench, report "no procedure fired -> no change by construction (uninformative)" instead of an NI pass.
  See F12 for the cost consequence.

### F8 [MAJOR] The text twin T_F is not a fair code-vs-text comparator: it is unconditional, so it measures format leakage, not form

- Attacked text: §7.1 (line 600-601) "T_F (text twin: card + the procedures' descriptions as one `shell_notes` block on
  every item, no code executed)"; §7.4 "If T_F ≥ F outside the home bench, the report states 'text form transferred at
  least as well'".
- Evidence: E9/E4 measured that other benches' guidance text, even in its own section, costs OfficeQA −8.1/−9.5 points
  and format-breaking text −33.3 / −26.7 (feasibility-prototypes.md:363-376); DR §4 改: "文字写在别的数据集的小节里照样会渗"
  (direction-recommendation-20261021.md:48).
- Why: F applies a procedure only where its predicate fires; T_F injects ALL descriptions on EVERY item of every bench. Off
  the home bench, T_F therefore adds unrelated text where F adds nothing (F ≡ C there), so F − T_F > 0 is expected from the
  E9 leakage mechanism alone. The pre-stated Break-It-Down check (§7.4) is biased toward "code transfers better".
- Fix: route T_F through the same router: the description of procedure j is shown exactly where j's predicate fires, in
  the same slot, padded to the same byte budget; then F − T_F isolates execution vs description. Keep an unconditional
  "text dump" arm only as an optional owner-approved replication of Break It Down.

### F9 [MAJOR] The placebo does not control the procedure's constant instruction text (D3 confound 1), so acceptance cannot tell an executable skill from a text rule wrapped in a predicate

- Attacked text: §1.6 (lines 208-219): context placebo = "note of identical byte length, text drawn ... from a frozen
  irrelevant corpus"; compute placebo = "`computed` is replaced by the fixed string `\"[value withheld]\"`".
- Evidence: D3's tracker result was confounded because its TRACKER_SENTENCE "Use it to avoid revisiting places you have
  already checked" was a behavioural instruction present only in the treated arm, with no sentence-only arm
  (feasibility-prototypes.md:56-57).
- Why: a context procedure's note typically mixes a constant instruction ("avoid revisiting; check open surfaces first")
  with variable computed content (the visited list). P replaces both with irrelevant text, so S' − P measures
  "instruction + content" vs "irrelevant text". A procedure whose note is a fixed advice sentence (zero executed content)
  passes the IUT exactly like a text rule would -- so "executable procedures help" is unfalsifiable at acceptance.
  The compute placebo's "[value withheld]" is not neutral either: it tells the solver something was withheld and invites
  self-recomputation or refusals, so P can be harmed below S, which inflates S' − P without loosening the S' − S contrast
  (the IUT bound is safe) but corrupts the R2/R3 interpretation (spec §10.2).
- Fix: (1) context procedures return `{"instruction": <constant, statically identical for all views>, "content": <variable>}`;
  the placebo keeps `instruction` verbatim and replaces only `content` by same-length filler; then S' − P tests executed
  content; (2) compute placebo returns the solver's own expression unevaluated ("computed": "<EXPR as written>"), which
  adds no information and no "withheld" signal; (3) register a placebo-inertness readout P − S (two-sided) with the rule:
  if P < S significantly, the report says the placebo was harmful and S' > P does not isolate content.

### F10 [MAJOR] Per-procedure "general" labels have no multiplicity control; headline claim (3) will produce false "general" procedures at a high rate

- Attacked text: §7.3 (line 624) "**general** = 95% LB > 0 on ≥ 1 non-home bench and no bench with 95% UB < 0".
- Why: each procedure is tested on up to four non-home benches, each at a two-sided 95% interval (2.5% per side). Under a
  global null the chance that one procedure gets LB > 0 somewhere is ~1 − 0.975^4 ≈ 9.6% (estimate, independence); with
  six procedures in F (two steps x <= 3), the chance that at least one is falsely labelled "general" is ~45% (estimate).
  The "no bench with UB < 0" clause does not help (it is rarely triggered at per-procedure MDEs of 10-19 points, spec
  line 626-627). Holm is applied to Q1 (|L| = 2) but not to the much larger per-procedure family that carries novelty
  claim (3).
- Fix: register the (procedure x non-home bench) family and apply Holm (or BH at q = 0.10, labelled as such); or register
  ONE primary non-home bench per procedure before the test read (the bench where its predicate fires most often on public
  views -- known from the router dry-run, no outcomes needed); require "general" to also pass DR §4 改's measured
  format-preservation check (answer-format shares within the registered tolerance on that bench).

### F11 [MAJOR] Inherited procedures fire on each new bench untested, cannot be retired there, and their causal forward effect is never measured during learning

- Attacked text: §4.4 (line 401) "Δ = surviving new procedures (+ registered retirements, only of procedures whose home
  bench is b)"; §5.3 (line 472) "S' − C is reported, not tested for the decision"; §4.4 step 4 (line 399-400) guard only
  forbids answer tags / action tags / code fences in notes.
- Why: from step 2 on, the parent S carries procedures from earlier benches; any "cross" procedure whose predicate fires
  on bench b changes bench b's behaviour in S, S', P alike. The acceptance tests only Δ. If an inherited procedure harms b
  (E9: other benches' text costs OfficeQA −8.1/−9.5 via shorter answers, feasibility-prototypes.md:371-376 -- a mechanism
  the tag/fence guard does not catch), nothing in the loop can remove it at step b (retirement is restricted to home-b
  procedures), so it propagates into F. DR §4 改 requires that "通用" rules pass a measured "does not change answer format"
  check (direction-recommendation-20261021.md:48); the spec's static `scope: cross` label is unmeasured.
- Fix: (1) run the run slice R_b with BOTH S and C (one extra arm on training items; estimate SB +0.13-0.22M, OQ
  +0.20-0.30M from §8.1 anchors), so the engineer sees on TRAINING data where inherited procedures hurt, and allow Δ to
  include "scope narrowing" of inherited procedures (a predicate conjunct `bench != b`), tested as part of the package
  decision on A_b; (2) in the acceptance round add withholding twins for INHERITED procedures that fire on A_b
  (S ∖ {j}, same rule as §5.5): this gives a causal per-procedure FORWARD-transfer estimate on fresh real items without
  touching the test sets -- the strongest available evidence for novelty claim (3); (3) register S − C on A_b as a
  two-sided descriptive forward-transfer readout in every step report.

### F12 [MAJOR] The decision tests -- and pays for -- byte-identical arms on items where nothing new fires, diluting power and wasting budget

- Attacked text: §5.3 (per-item d_i over all items of A_b); §5.1 (all four arms on every item); §7.1 (all arms on every
  test item of every bench).
- Why: enablement is a pre-treatment covariate known before dispatch and identical across arms (§1.5: "every enable
  decision known before dispatch"). On an item where no procedure of Δ (and no retired procedure) fires, S', S and P send
  byte-identical requests (by the shell's construction; testable like S-Q1), so the true per-item effect is exactly 0 and d_i is pure run noise. The
  spec's own planning assumption is that new procedures fire on only ~60% of items (line 494). Testing on all items adds
  ~40% noise-only items; restricting the test to the "differing set" D is valid (the effect outside D is 0 by
  construction) and more powerful: bench-level MDE about 0.84x at f = 0.6 for SpreadsheetBench 60x2 (estimate: tau^2 0.04,
  s^2 0.13, k = 2), with ~20% fewer acceptance cells (S' and P dispatched only on D).
- At test the effect is larger: in the default pilot an SB/OQ package probably fires on few or no ALFWorld games; F, P_F
  (and a routed T_F, F8) are then byte-identical to C there, yet ALFWorld is 55-64% of the 38-66M test read (spec §8).
  Running only C on items where nothing fires would save up to ~19-30M (estimate) per read in that case.
- Fix: register D_b = items where any Δ-added or retired procedure fires (from the router log, before dispatch); dispatch
  S' and P on D_b only, S and C on all items; decision statistic on D_b; report the bench-level effect as
  (|D_b| / |A_b|) x effect on D_b. Same rule at test per bench (F, P_F, T_F only where some procedure of F fires).
  Keep a registered minimum |D_b| (e.g. 20 items) below which the step is "not decidable".

### F13 [MAJOR] Detector acceptance is satisfiable by failure *symptoms*, so "the examiner evolved" is cheap and nearly tautological

- Attacked text: §6.1 (line 540-542) "Accept iff |F| ≥ 10 cells from ≥ 6 items, and the one-sided 90% item-cluster-bootstrap
  lower bound of (p − b) ≥ 0.10, and r ≥ 0.15"; §6.4 "The examiner side 'evolved' in a step iff a detector was accepted or a
  generator was validated".
- Evidence: every v3 ALFWorld failure is a 50-step timeout (68/68 and 56/56), revisits are 44.7-51.3% of failed steps
  (feasibility-prototypes.md:109-114). Base fail rate b ≈ 0.5 under the card (same source).
- Why: a predicate such as "the agent visited >= 12 receptacles" or "the trajectory has >= 30 steps" is a consequence of
  failing, has precision ~1 and lift ~0.5 >> 0.10, and passes on V trivially -- it is a re-statement of the outcome, not a
  diagnosis. The mechanical category `step_budget_exhausted` is excluded from "examiner evolution", but its paraphrases are
  not. On QA benches "reply contains no digit" plays the same role for OfficeQA. Since generators cannot be validated
  (F5), "both sides evolve" (an owner-fixed requirement) would in practice rest on such detectors. E1 is the measured
  precedent for model-written checks being near chance on content (balanced accuracy 0.47-0.55,
  feasibility-prototypes.md:344-349); the symptom route is the easy way around that bar.
- Fix: (1) QA/Sheet incremental-lift rule: precision lift is computed on V cells where NO mechanical category fires, and
  must meet the threshold there; (2) ALFWorld (where every failure is a budget exhaustion, so rule (1) would be vacuous):
  detectors see only the first 10 steps of a trajectory -- an early-warning predicate is a diagnosis, a terminal one is a
  symptom; QA detectors may not read the final answer tag content; (3) "examiner evolved"
  additionally requires USE: the detector's category was targeted by an engineer procedure in that step (report
  "accepted, unused" otherwise); (4) the category NAME the examiner writes is unvalidated model text -- pass the engineer
  the predicate source and counts, mark the name "unvalidated".

### F14 [MAJOR] Freshness leak: LiveMath has no "tail" for the smoke, and the consumption registry is per root

- Attacked text: §9 (line 710-711) "Items: SearchQA/LiveMath/ALFWorld from the tail of each order (beyond every registered
  slice)"; §2.3 (line 259) LiveMath "83 × 2 | 200 × 2 | ... | 0 (283 used)"; §2.1 (line 229) "refuses an item already
  present (also across chains of the same root). Smoke and pilot use separate roots".
- Why: LiveMath's registered slices use all 283 items, so the smoke's LiveMath items (S-F1: 20 items) must come from R or
  A. Because the smoke runs in a separate root and the registry only refuses re-use within a root, the full run would
  silently re-dispatch smoke-used items inside A_LiveMath: a freshness violation the registry was built to prevent.
- Fix: one global, append-only registry shared by smoke, pilot and full run (or a registered import of the smoke
  registry before the first pilot cell); remove the LiveMath smoke items from the supply before slicing, as already done
  for SB/OQ (e.g. R = 63, A = 200), or run the LiveMath format check on generated items only.

### F28 [MAJOR] Unequal resource paths break the same-session guarantee for ALFWorld: procedure arms queue for 3 sandbox slots, card arms do not

- Attacked text: §1.5 (spec lines 197-198) "one worker per ALFWorld episode ... Worker slots: `execskill-sandbox` = 3"
  with 6 ALFWorld episode slots; §5.2 (line 454) "Recorded per cell: dispatch and finish time" (recorded, not guarded).
- Why: S', P and the twins need a sandbox worker for their whole episode (predicates and procedures run in it); C (and S
  at step 1) need none. With 6 episode slots and only 3 worker slots, card-arm episodes start whenever an episode slot
  frees, while procedure-arm episodes wait for a worker: a seeded dispatch ORDER does not give equal execution TIMES.
  The serving regime alternates in time (terse share 5-96% per 15-min bin, cause unknown; feasibility-prototypes.md:
  312-313), so arm and time become confounded -- the exact failure interleaving exists to prevent. QA/Sheet worker
  pools are smaller-scale versions of the same asymmetry.
- Fix: (1) strict head-of-line dispatch: a cell starts only when every resource it needs is free AND every earlier cell
  in the seeded order has started (no skipping ahead); or give every arm, including C, the same worker path (a no-op
  worker), so resource needs are identical; (2) register a balance guard: per-arm start-time distributions compared
  (e.g. median start-time difference between any two arms <= 5% of the round's wall time, or a two-sample KS p > 0.01)
  -> otherwise pause, decision withheld; (3) the smoke (S-A1/S-X3) measures the queueing with 6 episodes and 3 workers.

### F15 [MINOR] The truncation rule and the `over_nominal` row contradict each other; resolution must precede the pilot

- Attacked text: §3.1 (lines 317-320) "`completion_tokens − (reasoning_tokens or 0) ≥ max_tokens` ... → truncated
  (completion-aware fail); `max_tokens < completion ≤ COMPLETION_BOUND` → flag `over_nominal`, counted, delivered".
- Evidence: probe-2 log, read-only grep by this critic: `reasoning_effort_none 200 deepseek-v4.1-flash-1017 stop 1 None 0
  '391'` and `max_tokens_2 200 deepseek-v4.1-flash-1017 stop 21 19 63 '391'` (dl:/data/execskill-ops/probe-20261021-2.log).
  The visible answer fits in 2 tokens, so neither A4 ("cap not enforced") nor K1 ("cap applies to content") is
  established; K1's S-E4 is the right test.
- Why: a reply with 10,000 content tokens at max_tokens 8,192 satisfies both rows. If "truncated" wins and the cap is
  not enforced, complete long replies are scored as failures -- differentially, because procedure notes can lengthen
  replies (arms S', P vs S, C).
- Fix: register precedence now: if S-E4 shows the cap is NOT enforced, truncation = `finish_reason == "length"` or
  structural incompleteness (unclosed answer/action tag), never token count; if it IS enforced, the count rule applies and
  any `over_nominal` reply is an `AssumptionBroken`. Report truncation counts per arm.

### F16 [MINOR] The 600 s read timeout cannot deliver replies the ledger registers as deliverable; the throughput figure is invented

- Attacked text: §3.1 (line 311-312) "read timeout 600 s (... 600 s exceeds 1.8× the time of a 16k-token reply at ≥ 50
  tok/s — E)".
- Why: no measurement supports 50 tok/s (the probe replies were 1-21 tokens in ~3 s, i.e. latency, not throughput). At
  50 tok/s a SpreadsheetBench reply at COMPLETION_BOUND = 32,768 tokens needs ~655 s (estimate) > 600 s, so a reply the
  ledger treats as `over_nominal`/deliverable becomes an infrastructure unknown; if procedure arms are longer, the
  unknowns are differential (L/H bounds then penalise S').
- Fix: paid smoke S-E7: 5 long-answer requests (>= 4k tokens) to measure tokens/s; set the timeout >= 1.2 x bound /
  throughput or lower SpreadsheetBench max_tokens; report read timeouts per arm.

### F17 [MINOR] Several cost multipliers are unanchored, and the twin cost model contradicts §7.1

- Attacked text: §8.1 (line 666) "Procedure arms (S', P, twins) × 1.25 (low) / × 1.6 (high)"; line 494 "(E: 0.6)";
  specB-calc/testread.py `twins = 1.0 if b in home else 0.3` and `tt = (1.15, 1.35)`.
- Why: only the ALFWorld state block is anchored (1,225 vs 873 tokens per call = 1.40x, feasibility-prototypes.md:35-36).
  A compute round trip costs >= 2x on the cells where it fires (the second prompt repeats the first prompt plus the first
  reply), so x1.6 is exceeded when compute fires on more than ~50% of cells (estimate: second call ~1.1x the first) -- the expected case for
  OfficeQA/LiveMath. §7.1 allows up to 3 twins per item, but the model charges 1 per item on home benches: up to +8M
  (default pilot) and ~+23M (SB->ALF, ALFWorld home) per read (estimate), which brings the SB->ALF read (63M high,
  spec §8.4) to ~86M = the registered read cap.
- Fix: model compute arms as 1 + f_c x (1 + r) with r (first reply / prompt) measured in S-E6; cap twins at one random j
  per item (or cost three); re-register caps from the worst case, not the mid case.

### F18 [MINOR] SearchQA block N: "ids only" contradicts "normalized-question dedupe"

- Attacked text: §2.2 (line 247) "exclusion by id of test 400 ∪ reserve 1,000 ∪ blocks A-D ∪ pool, plus normalized-question
  dedupe ... ids only".
- Why: de-duplicating by normalized question against the test 400 reads test question text (the existing script does
  exactly this, data-and-pools.md:403). Fix: say so; run it inside the evaluation code holding TestAccess; emit only
  counts and the excluded ids.

### F19 [MINOR] "V outcomes are never shown to any role" is false as written

- Attacked text: §6.1 (line 535-536) vs §3.2 (line 329) the engineer receives "up to 40 failing and 10 passing R
  trajectories ... with pass/fail bit" drawn from all of R (W ∪ V).
- Why: harmless for detector validity (the examiner, not the engineer, writes detectors), but the registered sentence is
  wrong. Fix: draw the engineer's examples from W only, or correct the sentence.

### F20 [MINOR] The OfficeQA run slice violates the spec's own sizing rule

- Attacked text: §2.3 (line 266) "the acceptance slice gets the larger share wherever the run slice still yields ≥ ~30
  failing cells". OfficeQA R = 19 x 2 at card pass 0.25-0.29 (DR §5) gives ~27-28 failing cells from ~14-15 distinct
  items (estimate). Fix: state it, or move to R = 24 / A = 45 (decision MDE x1.05, estimate sqrt(50/45)).

### F21 [MINOR] The pre-set minimum effect of design-v0 was dropped, and accepted estimates are not labelled as selection-inflated

- Attacked text: §5.3 "ACCEPT S' iff p(S' > S) ≤ 0.05 and p(S' > P) ≤ 0.05 and G1-G5" vs design-v0 step 6 "最小效果按
  bench 事先定" (design-v0.md:32) and D1's rule "mean d >= 0.02" (feasibility-prototypes.md:277-278). DR: winning effects
  are over-estimated 1.3-1.5x (direction-recommendation-20261021.md:77).
- Fix: either add a δ_min clause (e.g. observed mean >= 0.5 x decision MDE) or list its removal as an owner decision; label
  every accepted step's estimate "conditional on acceptance (inflated)"; the test read is the effect estimate.

### F22 [MINOR] OfficeQA is read in one serving window without regime strata, against DR §5 step 3

- Attacked text: §7.1/§7.2 (single interleaved read) and §5.6 "interleaving protects the contrast".
- Evidence: DR §5 step 3 asks OfficeQA to be read in two windows, stratified by answer regime, with a pre-specified
  primary regime (direction-recommendation-20261021.md:80); same text, same 60 OfficeQA items moved +22.5/+24.2 points
  between windows, terse share 5-96% per 15-min bin (feasibility-prototypes.md:309-314).
- Why: interleaving protects a contrast only without an arm x regime interaction; E9's mechanism (texts that shorten
  answers) is such an interaction. Fix: register regime strata (terse share per bin, defined from the C arm only), report
  F − C per stratum and the interaction; optional second OfficeQA window (~5-10M, spec §8.3 OQ column).

### F23 [MINOR] The sieve reuses frozen generated panels across steps and half of the self-test spend buys nothing in the pilot

- Attacked text: §4.5 "All four arms (S', S, C, P) on G_b × 1 run (needed for §6.3), plus S' and S on each earlier bench's
  frozen G".
- Evidence: DR §4 停: no generated items "当门或当证据"; veto-only checks on other data = "变相验证集"
  (direction-recommendation-20261021.md:31, 33).
- Why/fix: only (a) faults and (b) format share can fire ((c) is dead, F5). Keep (a)/(b) as mechanical checks, delete (c),
  register the earlier-bench G panels as a "reused diagnostic panel, never evidence". Make the P and C arms on G optional
  (they exist only for an untestable PV in the pilot): saves roughly half of the 1.4-6.3M per-step self-test (estimate,
  spec §8.2).

### F24 [MINOR] Gains from teaching the scorer's surface form are not separated from content gains

- Evidence: ~3/4 of the card's SearchQA failures are surface-form differences (feasibility-prototypes.md:302-304); the
  "+7 generic QA-card gain" was "almost all artefact" (feasibility-prototypes.md:366-368). A note can teach surface form
  without any tag, so §4.4 step 4 does not stop it, and it is not "answer repair" either.
- Fix: per accepted procedure, report S' − S under the recorded `lenient` score next to v2; a gain that vanishes under
  lenient is labelled "format", not "content", in every readout.

### F25 [MINOR] The 57 ALFWorld pool games carry D14 hindsight and sit inside R/A

- Evidence: "55/57 open surfaces" came from the walkthrough metadata of these games (feasibility-prototypes.md:115-120)
  and is design-v0's own motivating example for an ALFWorld procedure (design-v0.md:16); spec §2.3 cuts R and A from
  57 + 600 games, so ~17 A games (estimate: 200 x 57/657) are in-sample for a procedure motivated by that hindsight.
- Fix: exclude the 57 pool games from R and A (supply 3,514 is ample; zero cost).

### F26 [MINOR] ALFWorld "generated" games are real train games: they must be registered as consumed, and the type stratification is under-specified

- Attacked text: §2.3 "The selector of §6.2 draws only from the remaining ~2,914 train games"; §6.2 ALFWorld "a selector ...
  that picks unused train games".
- Why: the selector's 40 games are real items solved by four arms before the acceptance round. They must enter the
  consumption registry (the spec registers only R and A), otherwise a later chain or the full run can reuse them; and the
  readout must call them "examiner-selected real games", not generated items (their "predictive validity" is agreement
  between two real samples, F5e). The train folder has 7 task-type prefixes (measured, F2) while the spec stratifies by
  "the 6 task types"; register the exclusion of `pick_and_place_with_movable_recep` (or its inclusion) explicitly.

### F27 [MINOR] The frozen hook-API text given to the engineer must not contain example procedures or failure statistics

- Attacked text: §3.2 input "shell/hook API spec (frozen text)".
- Evidence: D3 confound 3, "induction = transcription": the tracker prompt carried the v3 revisit statistics and an exact
  key list, and the critic concluded "GLM transcribed a spec; that explains the 97.7% agreement"
  (feasibility-prototypes.md:65-70).
- Fix: register the API text's sha256 and a rule that it contains signatures and contracts only -- no example procedure,
  no benchmark statistics, no failure taxonomy beyond the mechanical category names; otherwise an accepted procedure is
  evidence about the prompt writer, not about learning.

## Index (for the synthesis)

| # | severity | one line |
|---|---|---|
| F1 | major | LiveMath 'stronger statement' artefact exploitable by procedures (pool and test) |
| F2 | major | ALFWorld R/A share rooms (108 train rooms, ~61% of A); test rooms unseen -> group split by room |
| F3 | major | OfficeQA train/test share 40 bulletins -> document memorisation counted as home gain |
| F4 | major | MDEs: IUT joint power ~0.7 not 0.8; low ends below measured D1 anchors; old-solver noise; add S-N1 |
| F5 | fatal for claim (1) | predictive validity: duplicate contrasts, in-sample G, insensitive, consumed by nothing |
| F6 | major | pilot test read unsealed before continuation -> final read not held out |
| F7 | major | NI margin 6-10 reverse-engineered from power vs owner-approved 4-5; null-by-construction on ALFWorld |
| F8 | major | text twin T_F unconditional -> measures format leakage, biased toward code |
| F9 | major | placebo replaces the procedure's constant instruction too (D3 confound 1); '[value withheld]' not neutral |
| F10 | major | 'general' labels without multiplicity control (~45% chance of >= 1 false 'general') |
| F11 | major | inherited procedures untested and unretirable on new benches; add inherited-procedure twins |
| F12 | major | test and pay only where something fires: ~0.84x MDE, ~20% fewer acceptance cells, ~19-30M test saving |
| F13 | major | detectors pass on failure symptoms; 'examiner evolved' cheap |
| F14 | major | LiveMath smoke has no tail; per-root registry -> silent reuse |
| F28 | major | ALFWorld procedure arms wait for 3 sandbox slots, card arms do not -> arm/time confound; add balance guard |
| F15-F27 | minor | truncation precedence; timeout vs bound; unanchored multipliers; ids-only; V shown; OQ run slice; delta_min dropped; OQ regimes; sieve reuse; format vs content; 57 pool games; ALFWorld selector registry; API-text transcription |

## Best ideas worth keeping in the synthesis

1. One seeded order per bench cut into consecutive slices, plus an append-only consumption registry written and fsynced
   before the first cell of an item is dispatched (§2.1); independent tags forbidden because they overlap by chance
   (29/18/60 items, measured, DP F6). Extend it to one global registry across roots (F14).
2. K3: at step 1 the parent equals the card arm, and the spec turns this into a free same-text duplicate null (G5,
   p < 0.01 two-sided -> pause). Keep; also use it as the negative control for predictive validity (F5).
3. The intersection-union decision (S' > S AND S' > P, each one-sided 0.05) with the correct statement that no Holm is
   needed and false accept <= 5% per step; L/H bounding of unknowns in d_i (conservative); "accepted only through the
   placebo-free contrast -> reject" (R2). Fix the power statement (F4).
4. The shell has no reply-writing path, and with zero enabled procedures it must reproduce frozen `backends.solve`
   request hashes byte for byte (S-Q1). This makes C a faithful v3 baseline AND makes the restricted test of F12 valid.
5. The router decides enablement once, on the public view, before dispatch -- the precondition for causal withholding
   twins (§5.5, §7.3) and for testing only on the differing set (F12).
6. The compute placebo mirrors call counts so "a second look" is controlled (§1.6); keep it with the echo fix (F9).
7. K1 + S-E4: refusing to rely on finish_reason, checking reasoning-off as `reasoning_tokens in (None, 0)` AND empty
   reasoning content (None is the observed value), and logging every attempt's usage (the frozen ledger keeps only the
   last attempt's, a lower bound).
8. Detector acceptance on a held-out half V that the examiner never sees, with an item-cluster bootstrap and an explicit
   "not decidable at |V| = n" outcome (K6). Keep with the incremental-lift and early-warning fixes (F13).
9. Generator admission gates T/D/S/L with per-reason drop counts, the D6 critic fix (the independent program is always in
   the agreeing pair), and the explicit ban on training-label regularities -- extend the ban to procedures (F1).
10. §7.4: the code-transfers-worse-than-text risk is pre-stated with a pre-committed reporting sentence. Keep, with a
    routed text twin (F8).
11. ST4 (no test read when nothing was accepted: the arms would be identical, and the one-time consent is not spent) and
    ST6 (a step whose slice exceeds the unconsumed supply is skipped, items never reused).
12. K5/K7 honesty: design-v0's minimum effects declared unreachable; pool items called "route-B-fresh", never "unseen";
    absolute accuracies labelled "this serving window only"; the §10.2 failure-mode table with a reporting rule per row and
    the list of claims never made.
13. Fail-open procedure faults (P1/P2) kept out of infrastructure unknowns, with a 2% fault cap (G1) and a separate
    sandbox-infrastructure row (P4).
14. Per-15-minute bin reporting of terse share, answer-format share and reply length for every arm (D11 lesson).

## 给负责人的白话摘要（本节写给负责人）

这份审查只看"数字和判定规则站不站得住"。结论：**需要修改后才能登记**，没有发现推翻整个方案的问题，但有几处会让结果"看起来有效、其实不算数"。

1. **几处题目其实不够"新"。** LiveMath（数学选择题）里有 129/283 道题带一个"能证明更强结论"的选项，而它总是正确答案；
   现在只禁止出题程序利用它，没有禁止工程师（写过程的 GLM 角色）写的过程利用它——利用了也能在验收里大幅"胜出"，但那不是学到本事。
   ALFWorld（文字家务游戏）的训练局只有 108 个房间，跑题段和验收段约六成局同房间，而测试集是没见过的房间；OfficeQA（财政公报问答）
   训练题和测试题共用 40 期公报。三处都要在登记里堵上（禁止相关写法、按房间分段、按"公报是否见过"分开报）。
2. **"能分辨的最小提高"写乐观了。** 要同时赢旧包和安慰剂（不给有用信息、只占位置的替身过程）才收下，这种"两条都要成立"的规则
   实际把握约 70%，不是 80%；按实测噪声算，SpreadsheetBench（表格题）约 12 分、OfficeQA 约 10 分才认得出。而且噪声都是旧做题模型测的，
   新模型要先花约 200–300 万 token 测一次再定。
3. **考官一侧"出题程序预测得准"这条主打创新，按现写法测不出来、还可能"假通过"。** 生成题由跑题段改出来，候选过程又是照着跑题段写的，
   天然占便宜；第一步里"新包比旧包"和"新包比任务卡"其实是同一个比较，被数了两次。建议改成只数一次、加一个"本应无差别"的对照，
   并在登记里写明试点里大概率"无法检验"。
4. **测试集可能被用两次。** 试点读完测试集就解封，您看完再决定是否接着跑整条链，链尾还要再读同一批测试集——第二次就不算"没见过"了。
   要么试点的测试分封存到整条链结束，要么试点那次就是唯一一次。
5. **"不相似的 bench 不掉分"的门槛被放宽了。** 您认可的设计稿写的是允许下降约 4–5 分，这份稿子按题量反推成 6–10 分；
   默认试点里 10 分以内的下降都算"不掉分"。建议保留 4–5 分并如实写出把握（默认试点约 37%）。
6. **安慰剂不够公平。** 过程的提示里常带一句固定的建议（如"别重复去查过的地方"），安慰剂把这句也换成了无关文字，
   所以"赢安慰剂"分不清是程序算出的信息起作用，还是那句建议起作用；"只有文字说明"那组又把所有说明塞进每一道题，等于故意制造格式冲突。
7. **能省钱也能提把握的一处：** 某道题上如果没有任何新过程启用，新包和旧包发出的请求一模一样，比较它们只是在比噪声。
   只在"有过程启用"的题上派发和比较，验收约少两成调用、把握更高；测试时 ALFWorld 若没有过程启用，可省约 2,000–3,000 万 token。
8. **"同一时段"在 ALFWorld 上可能做不到。** 带过程的组每局要占一个沙盒（隔离运行程序的容器），沙盒只有 3 个，
   而游戏局可以同时跑 6 局；只有任务卡的组不用沙盒，会先跑完。这样不同组实际在不同时间段做题，而服务状态随时间变化，
   比较就不干净了。要么严格按顺序放行，要么各组走同样的路径，并登记一条"各组开跑时间是否均衡"的检查。

术语：SB = SpreadsheetBench，OQ = OfficeQA，ALF = ALFWorld，SQ = SearchQA；S′ = 候选包，S = 上一步的包，P = 安慰剂组，C = 只有任务卡的组；
"跑题段" = 给工程师和考官看失败的那批题，"验收段" = 只做一次收不收决定的那批题。

Status: COMPLETE (19:45 CST, 2026-10-21). Verdict: needs_revision.
