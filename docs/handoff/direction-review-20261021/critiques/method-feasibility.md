# Feasibility / cost / protocol critique of the "method first" proposal

- **Proposal:** scratchpad/direction/proposals/method.md (lens 方法优先: what the co-evolution mechanism itself should become)
- **Critic:** feasibility / cost / protocol, adversarial
- **Verdict:** needs_revision
- **Scope:** read-only. No API call, no SSH, no test pool opened.

**Source keys** follow the proposal (docs/ prefix):
- `Xr` = docs/handoff/feasibility-20261021/X/result.json; `Xc` = the critic-result.json beside it
- CAL = docs/handoff/cal1-registration-20261020.md; RL = docs/results-and-lessons.md; PS = docs/project-status.md
- V6 = docs/handoff/coevo5-registration-v6-20261017.md; CW = docs/current-workflow.md; OV = docs/handoff/overnight-report-20261021.md
- SPEC = docs/handoff/v4-plans-20261021/spec.md; G4v2 = docs/handoff/v4-plans-20261021/G4.v2.md
- E3rep = docs/handoff/feasibility-20261021/E3/report.md; D14rep = docs/handoff/feasibility-20261021/D14/report.md
- PORT and LIM = the owner's memory notes new-benchmark-port-map.md and workflow-limit-restart-behaviour.md, under ~/.claude/projects/-Users-dulin-Documents-Paper-SkillOpt/memory/

**Evidence labels:**
- [run]: real model run on training items
- [replay]: re-analysis of archived cells
- [pilot]: exploratory run
- [claim]: from papers or READMEs, unchecked
- [calc]: my own arithmetic from the cited inputs. It uses a normal approximation, a one-sided 97.5% bound and 80% power, so MDE = 2.8 × SD / √n.
- "Receipts" are API usage tokens. "Ledger" is the coevo5 formal ledger, the unit of v3's 139M and cal-1's 27.48M.

---

## 0. Bottom line

The diagnosis and the stop list largely hold. So does the central idea: replace per-rule C1-gated chains with **one** powered, placebo-controlled acceptance test per version, on a source pool large enough to resolve 2–3 points.

The plan as written does not deliver what its numbers promise:

1. **Cost comparisons use the wrong comparator and mixed units.**
   - The "1.16B v4 chain" is a GLM-5.3 ceiling, not a cost. v3's whole run cost 139.0M deepseek plus 7.8M GLM (ledger).
   - M1 is about 3–7× cheaper than a v3-like run, not 20–50×.
   - In matching units, the whole plan costs about 1.7–2.3× v3, not "close to v3".
2. **M1's resolution is optimistic.**
   - The stated 1.9 / 3 points come from the most favourable SD on file: E3's lenient content score for card vs NoSkill, on 80 items.
   - They also count only the "LB > 0" half of a two-part GO rule. At a true +2, the GO rule fires about 50% of the time (content SD) or about 22% (strict SD).
   - The fired share of 0.4 is assumed, not measured.
3. **The source bench's metric does not exist in the needed form.**
   - FinQA's official script scores executed programs, not answer strings.
   - 3,508 of 6,251 answers carry "%". The still-undecided percent rule therefore settles about half the items.
4. **E0 is underestimated by roughly an order of magnitude.** "About 3 h" is the estimate for a different, already planned job.
5. **M3's decision rule is ill-posed.** It is either trivially met or it saturates in round 1. It also reuses one score half for three rounds.
6. **M4's no-drop rule is ambiguous.** Read as a bound, it is unreachable. The similar-bench half of objective 2 is designed out.
7. **Several citations are wrong in ways that matter:** the resend claim, "card + rule never run", "lenient", and "code conditions need no judge".

All of this is repairable, so the verdict is needs_revision, not rejected. A cheaper first step is suggested in §6, item 14.

---

## 1. Per-experiment checks (a) items, (b) cost, (c) protocol, (d) duplication, (e) time, (f) decision rules

### E0 — instrument build

**(a) Items.** "Items: none solved" conflicts with two other parts of E0: "official metric with the card checked against it", and the pivot "if the FinQA card fails its scorer check twice, port TAT-QA".
- **If the check uses E3's archived 80 × 2 cells:** they come from a different harness. E3 used its own prompt and max_tokens 12,288 (E3r design; E3rep L161–190). Such a check does not validate the registered harness.
- **If new cells are solved:** "0 solver tokens" is wrong, although the amount is small (about 0.3M receipts for 100 × 2 cells [calc]). The AGENTS.md first-response check then applies.
- **Undefined criterion:** "fails its scorer check" is never defined.

The usable FinQA pool is also smaller than stated:
- **Clean rows:** 6,085 of the 6,251 rows have a clean answer (E3rep L164).
- **Shared pages:** rows share report pages; E3 deliberately drew 80 distinct pages (E3rep L164). No file I read records how many distinct pages there are.
- **Fit:** the pinned draw needs 300 + 5 × 1,000 = 5,300 rows. That fits by rows. Whether it fits page-disjointly is unknown.
- **TAT-QA pivot:** 13,251 questions sit on only 2,207 documents, about 6 per document (E3c C6). Its effective n is far below its row count.

**(b) Cost.** "0 solver tokens, about 3 h agent [S38], 1–2 days scorer".
- **The 3 h is for another job:** PS L179 gives it for implementing the six **prepared** v4 plans (G1–G6.v2).
- **Most of E0 has no plan:** see refuted claim 11.

**(c) Protocol.**
- **Outside the v4 spec:** v4-min plus fresh-batch acceptance plus gating is outside the reviewed v4 spec. SPEC L177 lists "fresh-batch version-level acceptance" as "explicitly NOT to implement". This must be registered as a new protocol version with its own review. Calling it "v4-min" invites confusion with the v4 spec, which has 12 reviews, 127 comments and 18 blockers (OV L6).
- **Per-bench gated cards change the I-ds parent:** the parent is currently the five-seed card ("ids-full", 12,681 bytes). Under per-bench cards, K1's yardstick must be re-measured. Own card vs five-seed card differ a lot on OfficeQA: +13.5 / +17.6 against +4.7 (E9c R4).
- **"Predicate safety" is undefined:** if it runs predicates on other benches' training items to see how often they fire, it selects on target items. D12 said plainly: "不要拿下一个基准的训练题筛规则（等于验证集）". Restrict the check to public input schemas and task cards, as the answer-contract check already does.
- **The scorer version changes gate outcomes:** CH4 is pending owner decision (d) (PS L344). With JSON-aware scoring, E-ds's cand screen goes from +0.75 to +13.75 items (OV L94).
  - It must be frozen before any M1 manifest is sealed.
  - Every hashed-source edit changes every manifest identity, so all E0 code must land in one snapshot (PORT).

**(d) Duplication.** Gated injection is new; it is listed as untested in D4c missing #2 and D13c missing #4. This is not a duplicate.

**(e) Time.** See refuted claim 11: 3–5 overnight sessions, not "week 1 / 3 h".

**(f) Decision rule.** "If fewer than half the conditions compile to input-only predicates, drop A2" tests compilability, not fidelity.
- **What D4 measured:** hand-written regex predicates agree with a careful reader at a median Cohen kappa of 0.27 over 29 pairs; GLM-written predicates reach 0.66 (D4r evidence (7)).
- **Fix:** require fidelity against independent labels on source items, with a threshold fixed before M1.

### M1 — decisive mechanism test

**(a) Items.**
- **Pool:** 1,300 FinQA training rows fit the pool (but see the page issue above).
- **Fired share:** the share of 0.4 is unmeasured for FinQA predicates. On v3's rules, D4r (1) found 6 of 49 conditions holding on 86–98% of items ("always in disguise"). In D13, one trigger held on 14 of 97.

**(b) Cost [calc].**
- **Cells:** 600 + 9,000 + 1,600 = 11,200. The proposal's count is correct.
- **Receipts:** 11,200 × 1.1–1.9k (E3r cost fields), plus 7,600 text-carrying cells (A1, P1, P2, A2, Pg) × 0.75k, gives 18.0–27.0M. The proposal's 17–26M is fine.
- **Ledger:** cal-1's ledger ran at about 1.96× its receipts: 27,481,897 against 14.0M (CAL L128–131; E7c refuted #8; D8c R5 says "about 1.9×"). That puts M1 at 35–53M ledger.
- **Cap:** the proposed 55M ledger cap leaves only about 4% headroom at the high end.
- **Precedent for a cap hit:** E3's per-cell figures are from E3's harness. cal-1's pre-launch estimate was 2× too low, and the run paused on its registered cap (CAL L113–117). Pre-register what happens if the cap binds.
- **Wall clock:** at cal-1's pace of about 57 cells per minute (7,205 cells in 126 min, CAL L113–115), M1 takes about 3.3 h, i.e. one night.

**(c) Protocol.**
- **Harvest and acceptance run in different serving regimes:** harvest is a single-arm round, acceptance is interleaved. In v3, untagged replies were 1.0% at harvest but 6.5–10.1% at gating (E6c R2). Harvest interleaved with a duplicate arm, or at least tag the regime per cell (CH4 promises tags).
- **One session means one regime:** regimes alternate (E8c R1), and the same text on the same 74 OfficeQA items moved +20.3 points across windows (E9c R4). Split the 1,000 acceptance items across **two windows of 500**, interleaved within each, at no extra cost. Pre-register a per-window report.
- **The extension is optional stopping:** it runs "only if a point estimate reaches +2 / +3", so the sample size depends on the outcome. Nothing controls alpha across Ha, Hg and the extension; D8c recommends Holm. Pre-register how the extended test is combined.
- **The bootstrap must be clustered by report page:** FinQA rows share pages, and single-item resampling is anti-conservative (D11c R4(c)).
- **Page-disjointness is unstated:** a rule written from page P's failures and tested on another question from page P carries page-specific content into acceptance.

**(d) Duplication.** The core question is whether a learned text beats a good instruction on fresh, interleaved items. It already has several null answers:
- the 10/13 07:05 study: 975 SearchQA items, 20 interleaved arms, `lz` − bzero +0.001 [−0.016, +0.018], 19,500 solves, 37.39M tokens (RL L222);
- v11 fg17: +0.029 [−0.011, +0.072] (RL L139);
- v3's I-ds card + rule arms: −0.107 to +0.005 on never-shown halves (D1r replay);
- on FinQA itself, E3's expert − card: 0.000 [−0.044, +0.044] on 80 items (E3r).

What is new in M1: a content-heavy bench, a 5-rule package, gating, and placebo-relative acceptance. So M1 is not a pure duplicate, but its prior is low, as risk 6 concedes.

**(e) Time.** The run fits one night. Building it does not (see E0).

**(f) Decision rules.** The thresholds are fixed in advance, but reachability depends on an SD that has never been measured.

Power table [calc] (n = 1,000 items, 400 fired, k = 2 runs, one-sided 97.5%):

| SD of the paired item difference | where it comes from | SE / MDE, all items (pts) | Ha GO power at true +2 / +3 | P(NULL) given true 0: all-items part / fired part | Hg GO power at a fired-item gain of +5 / +6 |
|---|---|---|---|---|---|
| 0.213 | back-computed from E3c R2 "FinQA 142 items per 5 points" (card − NoSkill, content level, lenient scorer, 80 items) | 0.67 / 1.9 | 0.50 / 0.93 | 0.84 / 1.00 | 0.50 / 0.83 |
| 0.344 | D1r real-effect SD (SearchQA, k = 2) | 1.09 / 3.0 | 0.45 / 0.79 | 0.45 / 0.83 | 0.50 / 0.72 |
| 0.537 | E3r strict FinQA score ("905 items per 5 points") | 1.70 / 4.8 | 0.22 / 0.42 | 0.22 / 0.46 | 0.46 / 0.61 |

How to read the table:
- The proposal's "1.9 points / 3 points" are row 1's MDEs for the "LB > 0" condition alone.
- The added condition "estimate ≥ +2" (or share × gain ≥ +2) cuts power at the threshold to about 0.5, the same effect E1c R1 found for E1's two-part rule.
- The package-vs-card SD under the not-yet-built FinQA scorer is unknown. It could fall anywhere between rows 1 and 3.

Hg (gated package) has a narrow window:
- **The bar rises as the share falls:** share × (A2 − A0) ≥ +2 points means a fired-item gain of at least +5 at share 0.4, +10 at 0.2 and +20 at 0.1.
- **At share near 1, gating is just always-on.**
- **Prior:** in D4r (4), v3 rules moved 19.4% of items in scope against 18.9% out of scope (p = 0.60). A large effect concentrated on fired items has a low prior.

The NULL rule needs both UB95(A1 − A0) < +2 and UB95(A2 − A0) < +5.
- **Content SD:** under a true zero, NULL is reached about 84% of the time.
- **Strict SD:** at most about 22% of the time (the all-items part alone reaches 0.22; the fired part 0.46).
- **Otherwise:** the result is "no detectable gain", which does not trigger the stop.

The placebo comparator is itself noisy:
- **A placebo still moves scores:** even with JSON answers accepted, one cal-1 placebo still moved SearchQA by +3.6 points (OV L94). The −9.8 placebo shrinks to −0.25 under JSON scoring.
- **Two placebos are too few:** with only two, the between-placebo variance cannot be estimated. LB(A1 − mean(P1, P2)) silently treats the placebo mean as fixed.

Unspecified cases:
- **Too few rules:** what happens if fewer than 5 rules, or none, pass admission?
- **Regime dependence:** risk 4 promises a "regime-stratified read", but nothing says what a regime-dependent result changes.

**Fallback (LiveMath).** The pool is about 99 non-meta items outside v3's draw (D9c: 154 non-meta minus 55 inside the draw).
- **SD:** about 0.336, back-computed from D1's certifiable 0.056 on 283 items.
- **MDE:** about 9.5 points on all items and 14.9 on about 40 fired items.
- **P(NULL) given a true zero:** about 0.09 (all-items part) and 0.15 (fired part) [calc].
- **Consequence:** the fallback can almost never reach NULL, so it cannot trigger the stop. It is a pilot, not a substitute for M1.
- **Mislabelled failure rate:** "card fails 48/110 such runs" describes the 55 non-meta items **inside** v3's draw (D9c), not the 99 outside it.

### M3 — verifier evolution on ground truth

**(a) Items.** About 2,600 cells plus about 300 variants per round is adequate for recall estimates.

**(b) Cost.** GLM 0.6–1.5M is plausible (E1r 859,911; E6r 1,324,475).
- **"0 solver tokens" holds only if the checks judge item validity.** If they judge replies, the variants would have to be solved.
- **New code is needed:** a FinQA program executor and a seeded-variant generator. E3c M3 confirms the programs are executable.

**(c) Protocol.** The same score half is reused for three rounds while the proposer sees its outcome. E10c missing #7 calls this a verifier-side validation set. Use a fresh score half per round.

**(d) Duplication.** M3 follows the same line as the September V2–V18 Verifier Gate: executable checks calibrated against independent labels, which produced 0 verifier promotions in V4 and 0 new natural detections in V16 (E10c missing #2; CW L388).
- **What is new:** seeded ground-truth variants in the Code-as-Task style (E1c missing #4). They answer V4's lesson that "calibration material ran short".
- **What they do not show:** recall on seeded defects says nothing about natural-defect detection, the thing V16 failed at.

**(e) Time.** 1–2 sessions of new code [estimate].

**(f) Decision rule.** "Admitted in ≥2 of 3 rounds" is ill-posed because the checks' inputs are unspecified.
- **Gold-reading checks saturate round 1:** a check that re-executes the gold program and compares it with the key catches all three seeding operators (swapped key, removed referent, changed table value). Recall is about 1 with 0 false rejects, so recall cannot rise in rounds 2–3. Depending on how coverage starts, the rule then either fails by saturation or passes trivially.
- **The rule contradicts risk 7:** the proposal's own risk 7 says gold-derived checks do not count, but the decision rule does not exclude them.
- **Fix:**
  - checks may not read the gold program or answer;
  - hold out one defect operator never shown in the write half, and score recall only on it;
  - add a natural-defect readout;
  - state the "fixed precision" level.

### M4 — one-source chain plus one transfer read

**(a) Items.**
- **Batches:** three 1,000-row batches.
- **Sealed FinQA test:** the official test has 1,147 items, an unchecked count from E3rep L100.
- **Registered tests:** 400 / 172 / 125 / 279 / 134 (V6 L84–88). SpreadsheetBench has only about 177 judgeable of its 279 (E5c R4).

**(b) Cost [calc].**
- **Per version:** 10,600 cells × 1.1–1.9k plus 7,600 × 0.75k = 17.4–25.8M receipts. The proposal's 11–21M leaves out the package and placebo text.
- **Test read, card arm, without FinQA:** about 20.2M. Per-cell costs come from D6c R5 and D14rep L87:
  - SearchQA: 400 × 4,088
  - OfficeQA: 172 × 7,927 × 2 windows
  - LiveMath: 125 × 3,969
  - SpreadsheetBench: 279 × 4,273
  - ALFWorld: 134 × 105.7k, about 14.2M
- **Test read, total:** adding FinQA (about 1.3–2.2M) gives about 22M, which matches the proposal. The fired arms add about 14M.
- **Uncosted Ha-only branch:** if only the always-on package passes, the package and its placebo must run on every test item. That is about 2 × 22M = 44M instead of about 14M, an extra **≈30M**.

**(c) Protocol.** A single consented test read after freeze is registered (PS L118). Reading OfficeQA in two windows is good. sim(FinQA) = {OfficeQA} adds an entry to the similarity map fixed before launch (V6 §1.1), which needs an owner decision; the proposal says so.

**(e) Time.** At least 3 more sessions.

**(f) Decision rules.**
- **Source-test replication ("LB95 > 0"):** suppose M1's fired-item estimate sits at the +5 bar and the true effect is shrunk by the winner's curse of 1.34–1.51× (D1r). On about 458 fired FinQA test items with 1 run, replication power is about 0.65–0.76 at the content SD and about 0.15–0.18 at the strict SD [calc]. "Stop if the CI includes 0" may therefore discard a real effect. Pre-register this power.
- **"Each dissimilar bench must drop by at most 3 points":** the estimator is undefined.
  - *As a bound (LB95 ≥ −3):* the chance that all four dissimilar benches pass under a true zero is about 4% at fired share 0.3 [calc]. The test MDEs at 1 run are 4–5 / 10–11 / 7–7.7 / 9–10 points (D5c missing #4); with Holm they are 4.6–12.9 (D11c). D8c R4 also found a 3-point non-inferiority test infeasible within the pools.
  - *As a point estimate:* the chance that at least one of four benches shows −3 from noise alone is about 15–35% (fired share 0.3–0.5, per-item SD 0.40–0.45) [calc].
  - *In either reading:* no action is defined for a failure.
- **Similar bench:** the readout is "descriptive only" (OfficeQA MDE 6.6–7.7; D5c). The owner's "similar benches improve somewhat" therefore cannot be established by this plan, and the owner should be told this up front.

### Last resort — ALFWorld state-gated procedures

- **Cost:** uncosted. At 28.5k (E-ds) to 105.7k (I-ds) tokens per episode (D14rep L87), 200 episodes × 9 arm-runs come to about 51–190M receipts [calc].
- **Basis:** D3c found that the ALFWorld pilot gain depended on a modified harness, with format errors auto-corrected in 41% of steps. Replicating it with the card costs about 45–50M.
- **Protocol:** an "expanded public training block" would be a new protocol version.

---

## 2. Cost table (recomputed)

| Item | Proposal says | Receipts, recomputed | Ledger (×≈1.96) |
|---|---|---|---|
| M1 | 17–26M receipts, cap 55M | 18.0–27.0M | 35–53M |
| M1 extension (conditional) | not stated separately | 17.4–25.8M | 34–51M |
| M4, per version | 11–21M | 17.4–25.8M | 34–51M |
| M4, 3 versions | (33–63M) | 52–77M | 102–152M |
| Test read | ≈22M + ≈14M | ≈36M | ≈71M |
| Ha-only branch, extra | not costed | ≈+30M | ≈+59M |
| Whole plan, no extension | — | 106–140M | 208–275M |
| Whole plan, with extension | "≈160M, close to v3's 139M" | 123–166M | 242–326M |
| Added: positive control (NoSkill × 1 run, 1,000 items) | — | 1.0–1.6M | 2–3M |
| Added: second package (× 2 runs) | — | 3.7–5.3M | 7–10M |
| Comparator: v3 actual | "v4 chain cap 1.16–1.17B" | — | 139.0M deepseek + 7.8M GLM (RL L142) |

**The comparator.**
- **What 1.16B is:** OVERALL_CEILING = 1,160M is the GLM-5.3 ceiling (G4v2 L1841–1845, L2048–2051). It equals v3's 1,170M GLM ceiling minus v3's actual GLM spend of 9.24M. It covers role calls and the capped GLM-solver chains (E-glm 572M, I-glm 837M).
- **Expected use:** G4v2's own expected use is "2–6M of roles per step (v3: 7.8M for ten steps)". v3's deepseek cap was 430M (RL L142).
- **Realistic v4 cost:** a v3-like v4 run would cost roughly 150–250M ledger. This is my estimate: v3's 147M, with role calls about tripled by three-vote judging (PS L344 (a); OV L130 item 1).
- **Ratio:** M1 is therefore about 3–7× cheaper than a v4 run, not about 20–50×.

**Matching units against v3.** v3's 139M is a ledger figure. cal-1, on the same ledger, recorded about 1.56× its charged and about 1.96× its receipt tokens.
- **Plan in ledger:** the plan's 242–326M is about 1.7–2.3× v3.
- **Plan in receipts:** 123–166M receipts compares with v3's roughly 71–89M receipts, if v3's ledger carried the same factor.

---

## 3. Refuted or corrected claims

1. **"v4 chain (cap 1.16–1.17B)"; "settles the question for 20–50M instead of a 1.16B chain"** (ST1, risk 6, S28)
   - 1.16B is the GLM-5.3 OVERALL_CEILING, not an expected cost.
   - v3's real run cost 139.0M deepseek plus 7.8M GLM (ledger).
   - M1, at 35–53M ledger, is about 3–7× cheaper than a v3- or v4-like run.
   - Sources: G4v2 L1841–1845, L2048–2051; RL L142; OV L135.
2. **"Whole-plan worst case ≈160M, close to v3's 139M"**
   - The figure mixes receipts with v3's ledger unit.
   - Recomputed: 123–166M receipts, or 242–326M ledger, about 1.7–2.3× v3.
   - M4 per version is 17.4–25.8M, not 11–21M.
   - The Ha-only branch adds about 30M.
   - Sources: RL L142; CAL L128–131; E7c refuted #8; D6c R5; D14rep L87; [calc].
3. **summary_cn "M1 约花 1,700–2,600 万 token"**
   - This counts receipts only. In the unit used for v3 (1.39亿) and cal-1 (2,748万), M1 is about 3,500–5,300万.
   - The per-cell inputs come from E3's own harness, and cal-1's estimate was 2× too low.
   - Sources: CAL L113–117, L128–131; E3r design; E7c #8.
4. **"Resolves about 1.9 points (all) and about 3 points (fired), scaled from 142 items per 5 points"**
   - The 142 comes from the content-level card − NoSkill contrast on 80 items, scored leniently (within 1%, or gold ×100, or gold /100, or exe_ans, with fallback extraction).
   - Strict scoring needs 905 items per 5 points, which means an MDE of 4.8 at 1,000 items.
   - The package-vs-card SD has never been measured.
   - The GO rule's power at a true +2 is about 0.50, or about 0.22 under strict SD.
   - Sources: E3c R2; E3r evidence; E3rep L177–190 and L244; E1c R1; [calc].
5. **Hg "resolves about 3 points (fired)" at share 0.4**
   - The bar requires a fired-item gain of at least +5 at share 0.4 and at least +20 at share 0.1.
   - The share is unmeasured.
   - Rule movement is the same in scope and out of scope (19.4% vs 18.9%).
   - Power at the bar is about 0.5.
   - Sources: D4r evidence (1) and (4); [calc].
6. **CH6 "FinQA qualifies ... a numbers-only metric"; K6 "official binary metrics"**
   - The official evaluate.py compares executed program results (5 decimals) and never reads the answer string; it parses "5%" as 0.05.
   - The .787 is a lenient score.
   - 3,508 of 6,251 answers carry "%".
   - Only 6,085 rows are clean.
   - Whether the metric is "dominated by surface form" is decided by a scorer choice not yet made.
   - Sources: E3c R4; E3rep L164, L177–190; E3c C6.
7. **CH1 "Code conditions need no judge: 97/97"**
   - That condition is word overlap between the final answer and the question. It reads the reply, so it cannot gate before solving.
   - For input-only predicates, regex vs reader agreement is a median kappa of 0.27, against 0.66 for GLM-written predicates.
   - Sources: D13c confirmed_claims; D4r evidence (7).
8. **Diagnosis 5 "Card + learned rule versus card was never run"**
   - Every v3 I-ds screen arm was card + rule against card. All seven landed between −0.107 and +0.005, as diagnosis 1 itself cites [S8].
   - E7c's "missing" item says only that E7 did not run it.
   - Sources: D1r replay; E7c missing.
9. **K3 "resends caused 5 of the card's 6–8 'gains'"; S55 "no flips at ≥2 minutes" (cited as E4c R5)**
   - The claim holds only for the SearchQA scaffold arm.
   - Card arms flip more when lagged: 11/106 against 6/94.
   - In v3, 138 pairs sent ≥120 s apart had 5 flips.
   - The send gap is confounded with the launch period.
   - E4c R5 is about a different topic.
   - Source: E4c refuted_claims R2, R5.
10. **ST3 "Lenient scoring gives s1-r1 +0.068"**
    - That number is em_rob. Under lenient scoring, s1-r1 fails the screen (+0.75 < 1).
    - CH4's JSON-aware scoring is itself a relaxation that flips gates, moving E-ds cand's screen from +0.75 to +13.75 items. A boundary between CH4 and ST3 must be stated.
    - Sources: E6c R1; proposal S21; OV L94.
11. **E0 "about 3 h agent work [S38]", "week 1"**
    - The 3 h is for implementing the prepared v4 plans. E0's list is mostly unplanned:
      - fresh-batch acceptance, out of v4's scope (SPEC L177);
      - the predicate compiler and gated renderer, which change the Skill format;
      - dropping P1, which invalidates parts of G1–G6.v2;
      - the admission checks and the item ledger;
      - the FinQA protocol version: about 15 code sites plus builders, tests and identity, split and closure traps (PORT; E3c M6);
      - the scorer version, still pending owner decision (d);
      - M3's executor.
    - The 3 h v4 job itself was never started across two nights, because 5-hour limits restarted agents from scratch (LIM).
    - Realistic estimate: 3–5 overnight sessions.
    - Of B1–B17, B10, B11, B14, B15 and B16 serve only the stopped chain or SpreadsheetBench qualification (SPEC L31–117).
    - Sources: PS L179, L344; SPEC L177; PORT; LIM.
12. **E0 fallback "≈99 non-meta LiveMath items ... (card fails 48/110 such runs), pre-registered as low-powered"**
    - MDE is about 9.5 points.
    - P(NULL) given a true zero is about 0.09 / 0.15, so the stop branch is unreachable.
    - The 48/110 failure rate refers to items inside v3's draw.
    - Sources: D1r; D9c; [calc].
13. **M1 pivot "NULL → stop text-rule learning for this solver class"**
    - The test has one analyst draw, one bench, one scorer, one session, and no in-session positive control (E6c R3: none exists for the card + rule regime).
    - A NULL cannot separate "packages do not help" from "this package, regime or instrument".
    - Source: E6c R3.
14. **M3 "the verifier evolves iff ≥1 check is admitted in ≥2 of 3 rounds"**
    - Gold-reading checks saturate round 1.
    - The score half is reused for three rounds.
    - The same design line produced 0 promotions and 0 natural detections in September.
    - Sources: proposal risk 7; E10c missing #2 and #7; CW L388.
15. **M4 "each dissimilar bench must drop by at most 3 points"**
    - Read as a bound, it is unreachable (about 4%).
    - Read as a point estimate, there is a 15–35% chance of a false "drop" somewhere.
    - No action is defined for a failure.
    - Sources: D5c missing #4; D11c; D8c R4; [calc].
16. **Last resort "state-gated ALFWorld procedures (105.7k tokens per episode)"**
    - Uncosted at 51–190M.
    - It rests on a pilot whose gain came from a modified harness.
    - Sources: D14rep L87; D3c notes_cn.

## 4. Confirmed claims (checked against the cited files)

- **cal-1** [run]:
  - card +0.0938 [0.0505, 0.137];
  - bridges +0.004 / −0.030 / −0.026;
  - C1 passage 75.8% against 0 / 0 / 7.7%;
  - 27,481,897 ledger tokens for 8,800 cells.
  - Sources: CAL L128–146.
- **v3:** 0 rules accepted; 139,024,462 deepseek tokens (I-ds 106.6M, E-ds 27.4M, NoSkill 5.1M) and 7,804,250 GLM tokens (RL L142).
- **No registered pool reaches 1,000 training items:** 600 / 74 / 283 / 120 (91 qualified) / 57 (V6 L84–88; PS L179).
- **SearchQA:** 59 of 600 items are unused (E5c missing #7).
- **LiveMath:** about 99 non-meta items lie outside v3's draw (D9c: 154 − 55).
- **FinQA:**
  - 6,251 training rows, 3,508 with "%";
  - licence MIT / CC BY 4.0;
  - E3 cells cost 1.1–1.9k tokens;
  - card strict / content scores .700 / .787 [pilot];
  - closed-book contamination 1/80.
  - Sources: E3r; E3c C6; E3rep L100.
- **142 FinQA items per 5 points** on the content-level card − NoSkill contrast (E3c R2).
- **M1 cell arithmetic** (11,200) and the about-2× ledger factor (E7c #8).
- **The test read's card arm** costs about 22M, including about 14M for ALFWorld (D6c R5; D14rep L87; [calc]).
- **Certifiable effects** of 4.2 / 5.6 / 10.3 / 12.2 / 15.3 points (D1r).
- **D1's acceptance rule** (LB95 > 0 and mean ≥ 0.02): in the pilot the card was accepted and the placebos rejected; the replay accepted control:2 (D1r).
- **OfficeQA test MDE** is 6.6–7.7 points at 1 run (D5c missing #4).
- **Instrument drift:**
  - serving regimes alternate (E8c R1);
  - +20.3 across windows (E9c R4);
  - untagged replies 1.0 / 9.0 / 6.5 / 10.1% (E6c R2).
- **Model-written checks** reach a balanced accuracy of 0.474–0.548, with 0 of 6 revisions accepted (E1r).
- **The generated panel** saturates at 0.891 and missed the −9.46 harm (E9r).
- **September V-series:** 0 promotions in V4 and 0 natural detections in V16 (E10c missing #2; CW L388).
- **Gated injection** is untested (D4c missing #2; D13c missing #4), so the gating idea is new.
- **Owner's rules:** no held-out validation partition (V6 L124); mimic-train generation counts as a fake validation set; the rubric should combine text and code (PS).

## 5. Feasibility issues (summary)

1. **E0 time:** E0 needs 3–5 overnight sessions, not 3 h or one week. The whole plan cannot fit 1–3 sessions. The M1 run alone (about 3.3 h) fits one night.
2. **FinQA scorer:** there is none yet. It must be frozen in the same snapshot as all other E0 code, before any manifest is sealed. The percent rule decides about half the items, and owner decision (d) is pending.
3. **M1 power:** it depends on an unmeasured SD. Under strict SD, MDE is 4.8 points and NULL is reached only about 22% of the time under a true zero.
4. **Fired share:** it is unknown, so Hg can only succeed in a narrow window.
5. **Clustering:** the bootstrap is unclustered, the page-disjoint draw is unspecified, and the number of distinct pages is unknown.
6. **Ledger cap:** the 55M cap has about 4% headroom at the high end, and the per-cell costs come from a non-registered harness.
7. **Regimes:** harvest and acceptance run in different regimes, and a single session sees one regime. Two windows would fix this for free.
8. **Fallback:** the LiveMath fallback cannot reach a decision.
9. **M3 rule:** ill-posed. It needs gold-free inputs, a held-out defect operator and fresh score halves.
10. **M4 rules:**
    - the no-drop rule is ambiguous, and unreachable as a bound;
    - the similar-bench half of objective 2 cannot be tested;
    - replication power is 0.65–0.76 at best.
11. **Uncosted branches:** the Ha-only branch (about +30M) and the ALFWorld last resort (51–190M) carry no cost in the plan.
12. **Protocol:**
    - "predicate safety" must not run on target items;
    - the plan needs a new protocol version number, not "v4-min";
    - per-bench cards change the parent, so the card yardstick must be re-measured.
13. **Multiplicity:** the conditional extension and the two GO tests need pre-registered alpha control.
14. **Admission shortfall:** no rule covers zero or too few admitted rules.
15. **Agent limits:** E0 must be cut into agent tasks under 45 minutes that write intermediate files, because 5-hour limits restart agents from scratch (LIM).

## 6. Corrections for the synthesizer (plain Chinese, apply verbatim)

1. 把"v4 链（上限 11.6–11.7 亿 token）""用 2,000–5,000 万代替 11.6 亿的链"改为：v4（第 4 版协议，规格写好但没实现）里的 11.6 亿是方法角色所用模型 GLM-5.3 的总封顶额度，不是预计花费；第 3 版协议 v3 实际跑完一整轮花了 1.39 亿 deepseek token（正式账本）加 780 万 GLM token。v4 照 v3 的方式跑一轮，估计约 1.5–2.5 亿。所以 M1（关键试验）比它便宜约 3–7 倍，不是 20–50 倍。
2. 给负责人的 M1 花费改成与 v3、cal-1（10/20 的校准实验，记账 2,748 万）同一口径：按正式账本约 3,500–5,300 万 token（接口实际计数约 1,800–2,700 万），另有 GLM 约 20–50 万。全计划最坏情况改为：接口计数约 1.2–1.7 亿、正式账本约 2.4–3.3 亿，大约是 v3 一整轮的 1.7–2.3 倍，不是"和 v3 差不多"。"只有始终开启的规则包过关"这一支还要另加约 3,000 万（在 ALFWorld 家务模拟上每个臂约 1,400 万），原文没算。M4 每个版本约 1,700–2,600 万，不是 1,100–2,100 万（原文漏了规则包和安慰剂文字本身的长度）。
3. 删掉"能分辨约 1.9 / 3 个百分点"，改为：这两个数借用的是 E3 试点（80 道 FinQA 财报计算题、宽松评分，差 1% 以内或差 100 倍都算对）里"任务卡对无说明"的差异波动；按严格评分要 905 道题才能分辨 5 分，1,000 道题只能分辨约 4.8 分；"规则包对任务卡"的波动从没测过。按预先写定的"置信下界大于 0 并且估计值至少 +2 分"这条规则，真实效果正好 +2 分时过关的机会只有约一半（严格评分下约两成），真实 +3 分时约九成（严格评分下约四成）。
4. 在 Hg（只在条件成立的题上加规则）过关条件旁写明：触发比例 0.4 是假设、没测过；触发比例 0.4 时，被触发的题上要涨至少 5 分，比例 0.1 时要涨 20 分，实际够不着；比例接近 1 时就等于始终开启。D4 探索（检验规则条件的那次）发现 v3 规则在条件成立和不成立的题上变动几乎一样（19.4% 对 18.9%），所以这一支先验很低。
5. M1 加两个臂：（一）阳性对照"无说明对任务卡"（E3 测到内容分约 +4.4 分），1,000 道题跑 1 次约 100–160 万 token，用来证明这次实验本身看得见真实效果；（二）第二个独立写出的规则包（让分析模型再写一次），跑 2 次约 370–530 万 token。没有这两个臂，"无效就停掉整条文字规则路线"站不住，只能写"这一个规则包在 FinQA 上没测出 2 分以上的提升"。
6. 把 1,000 道验收题分成两个时段各 500 道（每个时段内仍然各臂交错），预先写好两个时段分别报告。原因：E8、E9 两个夜间探索方向发现模型服务会在"简短/啰嗦"两种状态间切换，同一份说明在 OfficeQA 上不同时段能差 20 分；而且收集错题的那一轮是单臂跑的，和交错验收时的状态不同（v3 里漏写答案标签的比例 1.0% 对 6.5–10.1%），收集错题也要交错跑或至少给每次求解标上状态。
7. FinQA 题要按报告页抽：同一页最多一道题，或者收集错题用的题和验收题来自不同的页；置信区间按页聚类重抽样。E0（建工具阶段）先数清 6,085 道可用题里有多少个不同的页。可用题是 6,085 道，不是 6,251 道。
8. 评分规则先定死再开跑：FinQA 官方脚本比的是执行标准程序得到的数（保留 5 位小数），根本不读答案文字，"5%" 当 0.05；E3 的 .787 是自己写的宽松分。6,251 道题里 3,508 道答案带百分号，百分号怎么判直接决定一半题的对错。要在看任何 M1 结果之前写死评分规则，并写清它和"停用宽松评分"（ST3）的界线：认 JSON 包着的答案可以，"包含就算对"不行。这一项等负责人对 (d)（零成本评分修复要不要并入）表态。
9. 删去"代码条件不需要评判"的证据句：那个 97/97 一致的条件看的是模型的最终答案（答案和问题有没有重复的词），做题之前根本算不出来，不能拿来证明"做题前用代码判断要不要加规则"可行。D4 测过：用正则写的条件和人工判读的一致度只有 kappa 0.27（kappa 为 1 表示完全一致、0 表示和瞎猜一样；GLM 写的条件为 0.66）。E0 里"过半条件能编译成代码"这个检查要换成"代码条件和独立人工标注的一致度不低于事先定的值"。
10. "任务卡 + 学到的规则对比任务卡从没跑过"改为：在 cal-1 和这次探索里没跑过；但 v3 主链 I-ds（从五份任务卡出发的那条链）的 7 条规则本身就是"卡 + 规则对比卡"，在没见过的检查题上全部落在 −10.7 到 +0.5 分之间（D1：夜间探索里检验“版本级一次验收”的方向，对 v3 存档结果的回放）。
11. K3 里"重发导致任务卡 6–8 道增益里的 5 道、隔 2 分钟以上就不翻转"删掉：E4（夜间探索里测“通用问答说明”效果的方向）的审查员复核发现这只在 SearchQA 空白模板一个臂上成立，任务卡臂隔开发送反而翻得更多（11/106 对 6/94），v3 里隔 2 分钟以上的 138 对有 5 对翻转。间隔发送可以保留（无害），但降不了 8–10% 的同文本翻转底噪。出处改为 E4 审查 R2（原文写的 R5 讲的是别的事）。
12. ST3 里"宽松评分让 s1-r1 得 +0.068"改为：格式鲁棒的精确匹配（em_rob）让 E-ds 链第 1 步第 1 条规则 s1-r1 得 +0.068；按宽松评分它连初筛都过不了（E6：夜间探索里用不同评分方式重放 v3 过门过程的方向，审查第 1 条）。另外写明：CH4 说的"认 JSON 答案"本身也是一种放宽，会让 E-ds 那条被拒规则的初筛从 +0.75 道变成 +13.75 道。
13. E0 的工作量改成实话："约 3 小时代理工作"只是已有方案的 v4 六组实现的估计；E0 里的版本验收（v4 规格明写不做）、规则包渲染、代码条件编译、准入检查、条目台账、FinQA 新协议版本（以前接入新题库约改 15 处代码，外加构建器、测试和若干坑）、评分器新版本、M3 的埋错生成和 FinQA 程序执行器都没有方案。按每个代理 45 分钟以内、5 小时用量限额会让代理从头重来的经验，E0 现实需要 3–5 个通宵；M1 本身（约 11,200 次求解，按 cal-1 的速度约 3.3 小时）一夜能跑完。整个计划 1–3 个通宵做不完。v4 的 17 个修复里 B10、B11、B14、B15、B16 只服务被停掉的逐条过门链或电子表格资格审查，可以不做。新东西要登记成新的协议版本号（例如 v5），不要叫"v4-min"，并单独过一轮 Codex（外部代码评审工具）评审。
14. 建议在 E0 之前先做一个"M1 简版"：在 E3 已经搭好的 FinQA 试点程序上（只用训练题、按页抽、评分规则事先写死），只测始终开启的规则包对任务卡，加两个安慰剂、无说明阳性对照和第二个规则包，分两个时段，一夜跑完，接口计数约 2,000–3,000 万。如果为零，就不必花 3–5 个通宵建 E0；如果过关，再在正式协议里重做。试点程序不是正式求解提示，它的结论只能当"去/不去"的判断，不能写进论文结果。
15. LiveMath 退路（约 99 道没有"更强结论"选项的题）要写明：最小可测效果约 9.5 分（被触发的约 40 道题上约 15 分），在真实效果为零时判出"无效"的机会只有 1–9%，所以它判不出"停"，不能当 M1 的替代，只能当低把握试点。原文"任务卡在 110 次中错 48 次"说的是 v3 抽到的 55 道题，不是这 99 道。
16. ALFWorld 最后一招要标价：每局 2.85–10.57 万 token，200 局 × 9 个臂次约 0.5–1.9 亿；而且 D3（ALFWorld 记事工具试点）的审查发现那次 ALFWorld 提升依赖改过的评测程序（41% 的动作格式错误被自动纠正）。没有新证据前不要列为退路。
17. M3（验证端进化）判定规则改为：（一）写明检查程序能读什么——不能读标准答案和标准程序，否则"重算一遍标准程序"第一轮就 100% 抓到三种埋错，后两轮无从提高；（二）留出一种写检查时没见过的埋错类型，只在它上面算召回率；（三）每轮换新的打分题，否则三轮反复用同一半就是验证端自己的"验证集"（E10（验证端自动出题的探索方向）审查第 7 条）；（四）另报一次对真实坏题的检出。并注明九月 V 系列（V4 零次晋升、V16 零次新发现真实错误）是同一思路的前例。
18. M4 的"不相似题库掉分不超过 3 分"写清是点估计还是置信下界：按置信下界，四个不相似题库在真实无影响时同时过关的机会只有约 4%，根本达不到；按点估计，四个里至少一个因噪声被判"掉分"的机会约 15–35%。还要写明判了"掉分"以后怎么办。并向负责人说清：相似题库只有 OfficeQA（测试集 172 题，一次运行只能分辨 6.6–7.7 分），按设计只能描述、不能确认，所以"在相似题库上也涨"这半个目标这个计划证明不了。另外，M1 效果刚过线时，在 FinQA 测试集上复现成功的机会约 0.65–0.76（严格评分下约 0.15–0.18），"复现不了就停"可能丢掉真实效果，要事先写出这个把握。
19. "条件安全"检查只能用别的题库公开的输入格式说明（任务卡），不能在别的题库的训练题上跑条件、看触发多少——那等于拿别的题库的题筛规则，就是变相验证集（D12 探索方向的结论）。
20. M1 的"估计值够线才加 1,000 题"是看了中间结果再加样本，要事先写好合并检验办法（例如加的部分单独检验，或按 Holm 校正，D8（改进过门统计方法的探索方向）的建议）；Ha（始终开启的规则包）和 Hg（只在条件成立时加）两个过关检验也要一起控制误判率。准入后剩不到 5 条或一条规则都没有时怎么办也要事先写（例如重新调用分析模型一次，仍为零就记为"没有可验收的规则包"，不算阴性结果）。55M 的记账上限在高端只剩约 4% 余量，要事先写好碰到上限时怎么办（cal-1 就碰过一次）。

## 7. What survives (plain Chinese)

诊断部分基本成立：v3 两条链十步都没收下一条规则；cal-1 显示单条规则大小的文字在 SearchQA 上的效果约为零、过不了门；量尺会漂移、有 8–10% 的同文本翻转；模型写的判卷程序接近瞎猜；生成题太容易。停止清单也成立：不再跑逐条过门的链（含 v4 正式运行，但理由改成"花费约为 v3 级别、而单条规则测不出"，不是"11.6 亿"）、不拿生成题当门或迁移证据、不拿别的题库的题当门（那是变相验证集）、不再用 SearchQA 当源题库、先不学 LiveMath 的"更强结论"选项。保留项里"任务卡当起点和标尺""五个环节的流程不动""同一时段交错、配重复臂和安慰剂""D1 式的版本验收（新题、一次、下界大于 0 且至少 +2 分）""一次经同意的测试读取"都站得住。

核心改法也站得住，但要按上面的修正落地：把"一条一条过门"换成"整包在源题库没见过的新题上一次验收、同时和任务卡与安慰剂比"，放在题量足够分辨 2–3 分、错误以内容为主的源题库上。FinQA 是一个可信但未获批准、先验偏低的候选（FinQA 上手写的专家说明对任务卡是 0.0），而且它的评分规则还没定。验证端改为"用标准答案或人为埋错来打分的检查程序、不拿做题分数当奖励"的方向也成立，但判定规则要重写。

站不住或要降级的：花费对比（M1 不是便宜 20–50 倍而是 3–7 倍；全计划约为 v3 的 1.7–2.3 倍）、M1"能分辨 1.9 分"的说法、Hg 的可达性、LiveMath 退路的"决定性"、M3 的判定规则、M4 的"不掉 3 分"规则，以及"在相似题库上也涨"这半个目标——这个计划按设计证明不了它。最划算的下一步是先用 E3 现成的试点程序做一夜的"M1 简版"（约 2,000–3,000 万接口计数），结果为零就不必花 3–5 个通宵建全套工具。
