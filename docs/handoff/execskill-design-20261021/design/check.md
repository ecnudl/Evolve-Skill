# Final consistency check: registration-draft.md + implementation-plan.md (fivebench-execskill-v1)

Checker: final consistency checker (read-only). Date: 2026-10-21.
Scope: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/registration-draft.md (RD) and
/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/implementation-plan.md (IP),
against design-v0.md (owner sketch), understand/map.md + 7 reader maps, critique-*.md (6 files), A1-A15 working assumptions.
Citations: path:line. RD = registration-draft.md, IP = implementation-plan.md, DV0 = design-v0.md, MAP = understand/map.md.
Severity: FATAL / MAJOR / MINOR. Numbers marked "measured (source)" or "estimate (assumptions)".

Status: COMPLETE (see end); file appended during the check.

## Progress log
- 20:2x read DV0, MAP (all), RD (901 lines), IP (399 lines); finding index of all six critiques (94 fatal/major rows
  confirmed: FE 10, FA 18, ME 15, MA 22, EE 13, EA 16; every one has a row in RD §15).
- Code facts re-checked in the local repo (byte-identical to dl snapshot f for skillopt/ scripts/): outcomes classes
  (outcomes.py:95-112), budget.reserve wait/stop semantics (budget.py:283-316), ledger breach rule (ledger.py:62-72),
  Endpoint.send/_record (calls.py:136-221), cells STOP_KINDS/_solve/_replay (cells.py:45-46, 122-148), backends contract
  constants and _native argv (backends.py:35, 53-56, 169-178, 381-382), ALFWorld loop (backends.py:715-785),
  Client._receipt/body/__init__ (weak_solver_probe.py:220-300), data.ranked (data.py:173-176), PLACEBOS (protocol.py:105-124),
  STRONGER_OPTION (protocol.py:222), TEST_SIZES (protocol.py:65), forward MAX_EXPONENT/MAX_BITS (forward.py:37-40),
  step primitives (step.py:71-160), CONSENT_FIELDS (evaluation.py:43), qualify.load (qualify.py:134-138),
  SearchQA sampler seed (scripts/make_searchqa_fresh_sample.py:62, :121), native image base = Python 3.11
  (runtime/Dockerfile:2-5; so `-P` is supported).

- 20:3x dl (BatchMode ssh, ls/cat/grep/head only): /data/execskill-dev exists (created 19:20; .git/HEAD =
  refs/heads/research/exec-skill-coevolution; has skillopt/coevo5, scripts/run_coevo5.py, scripts/weak_solver_probe.py; no
  skillopt/execskill yet; no .env in it); /data/skillopt-work is NOT a git repo and holds a mode-600 .env; nproc 7, 15 GiB;
  /root/continual-alf-prep-20260928/env/bin/python, /data/coevo5-20261019-v3-source-f, texts.json (version
  "fivebench-coevolution-v3-texts-import"), /data/feasibility/D3/r3/lt/traces.json, v3 sheet training qualification all
  present; /root/.config/weak-solver/elucid.env present (mode 600, NOT read). probe-20261021-2.log (15 lines, read without
  credentials): reasoning_effort_none -> completion 1, reasoning_tokens missing, 0 reasoning chars; max_tokens_2 -> 21 =
  19 reasoning + 2 visible (reasoning ON, so non-enforcement is NOT shown); concurrency 8/8 in 3.50-4.25 s (reasoning on).
  These confirm RD 4.1 (RD:261, :264, :267) and C-A4 (RD:845-846).
- Health of the inputs the owner asked about ("设计稿和攻击人是否正常"): the three specs exist; all six critiques carry a
  COMPLETE/DONE status line (critique-engineering-adversarial.md:7, -evidence.md:6, fidelity-adversarial.md:9,
  fidelity-evidence.md:6, measurement-adversarial.md:5, measurement-evidence.md:6); finding indices match RD §15 counts.

## Verdict

ok = false. Five MAJOR corrections (C1-C5), thirteen MINOR corrections (C6-C18), thirteen omissions (O1-O13).
No FATAL. Everything else checked (identity/import rule, A1-A15 mapping, fixed owner decisions, numeric sums of §9.2/§9.3,
MDE/power arithmetic for SB/OQ/ALF/SQ, positioning vs FlowEvo/CoEvoSkills/GRASP/Break It Down, frozen-code line facts)
is consistent; details in "Verified as consistent" at the end.

## Corrections

### C1 [MAJOR] Build location contradicts the owner's relayed instruction; the real dev tree on dl is not registered
- Quote: IP:337 "Each batch ends with its unit tests green on the Mac (offline)"; IP:367 "1. **Snapshot.** On the Mac:
  sha256 list of `skillopt/ scripts/ tests/` -> rsync to `dl:/data/execskill-20261021-source`"; RD:47 lists dl directories
  but not /data/execskill-dev.
- Problem: the owner's request relayed for this run says "实现的时候请你在我的新的linux开发机上实现". The plan builds and
  tests on the Mac and ships a snapshot from the Mac. On dl a working copy already exists: /data/execskill-dev,
  git HEAD = research/exec-skill-coevolution, created 19:20, no skillopt/execskill yet (measured, ls/cat on dl). Neither RD
  nor IP names it. /data/skillopt-work is not a git repo and holds a .env (measured), so it must never be an rsync source.
- Fix: register /data/execskill-dev as the build tree (13 agents edit there; unit tests run there with
  `/root/continual-alf-prep-20260928/env/bin/python -B -m pytest -p no:cacheprovider`). Make the snapshot a dl-local copy:
  /data/execskill-dev -> /data/execskill-20261021-source, sha256 list plus `cmp`, with `.env*` excluded and checked absent.
  The Mac copy and the Codex review read a pulled mirror. Add the path to RD §1 and to the manifest `provenance`, and
  change the IP:337/:357/:359 wording ("on the Mac", "clean clone") to dl.

### C2 [MAJOR] The detector residual rule makes ALFWorld detectors unacceptable by construction; RD §11 claims the opposite
- Quote: RD:318-319 mechanical categories for ALFWorld include `step_budget_exhausted`; RD:449 "残差格 = 没有任何机械类别、也没有
  已收检测器报警的格"; RD:446-448 "ALFWorld 失败局全部跑满 50 步，124/124"; RD:616 "ALF 有机会判定（验的一半约 30 局；只看前 10 步）".
- Problem: every scored ALFWorld failure exhausts the 50-step budget. backends.py:768-770 stops early only on won/done,
  measured 124/124 [FP]. So `step_budget_exhausted` fires on every failed cell. The residual set therefore holds no
  failures. Precision minus the residual base is then 0 and residual recall is undefined, so no ALFWorld detector can
  pass RD:449-451. RD:320 also says the examiner writes detectors only for failures that no mechanical category covers,
  so on ALFWorld it writes none.
  - On SB and OQ, detectors are "无法判定" (RD:452).
  - Predictive validity is "无法评估" (RD:476).
  - ALFWorld selection is excluded from the examiner claim (RD:464-465).
  So with RD as written, the examiner side of BOTH pilots cannot succeed by construction. Yet RD:616, a row of the
  owner's pilot comparison, implies that the recommended pilot gives it a chance. This bears on owner decision #1.
- Fix: define the residual with mechanical categories evaluated on the SAME masked view the detector sees (ALFWorld:
  prefix of 10 steps; so `step_budget_exhausted` and full-episode loop counts are excluded from the residual definition),
  and add a unit test: with all failures at 50 steps, a prefix-only detector can still be accepted. Otherwise delete
  RD:616's claim and state in §0 item 6 / §11 that the examiner side cannot evolve in either pilot.

### C3 [MAJOR] Slot-wait timeouts mapped to P4 turn ordinary ALFWorld queueing into unit pauses
- Quote: IP:238-240 "Every route-B wait has a timeout (sandbox 600 s, native 1,800 s, episode 3,600 s) -> P4"; IP:251
  "Threads: 16 per unit"; RD §15 MA-M7 (RD:765) "waits time out to P4".
- Problem: the slot pool polls at random every 0.5 s with no FIFO (calls.py:78-90). With 16 threads and 6
  `alfworld-episode` slots, about 10 threads wait at any time. Episode durations: median 290-348 s, p90 1,929 s
  (measured [LO F36]).
  - Per wait (estimate; assumes mean episode ~600 s, i.e. ~36 slot releases per hour, and each release won uniformly by
    one of ~10 waiters): P(no slot within 3,600 s) ≈ 0.9^36 ≈ 0.02.
  - Per round (estimate): an ALFWorld acceptance round has ~600-700 episodes, so several timeouts are expected.
  - Consequence: each timeout raises SandboxUnavailable, which pauses the one-shot acceptance unit (RD:299 P4).
  - The same risk exists for native waits (1,800 s, 3 slots, 13 waiters) whenever programs run near their 300 s limit.
- Fix:
  - Run ALFWorld units with workers = episode slots (6), or use the frozen untimed wait for the episode pool.
  - Map a slot timeout to a retry or a logged wait, not to P4. The registered lock order already prevents deadlock.
  - Keep timeouts only for the short-hold sandbox pool.
  - Add a unit test with 16 workers, 6 slots, heavy-tailed durations and no P4.

### C4 [MAJOR] Budget ceilings do not add up against the registration's own estimates and rules
- (a) Smoke. IP:388-389 says the smoke total is "within the 5M smoke cap". Its own items sum to 2.7-5.2M (S1 ≤ 0.2 +
  S2 1.0-2.5 + S-N1 1.0-2.0 + S4 0.5), so the high end already exceeds 5M. RD:604 puts S-N1 at "约 2–3M", against IP's
  1.0-2.0M. Recount S2 with RD:603's arm list (C, X, P, twins) and the ×1.25/×1.6 procedure multipliers of RD:538:
  - ALFWorld: 6 × 4 arms × 2 runs = 48 episodes, about 1.7-3.1M;
  - SearchQA 20 items plus 60 fixtures: about 1.0-4.5M (the high end assumes fixtures as large as real items; estimate);
  - so S2 is about 2.7-7.6M and the smoke total about 3.9-11M (estimate).
  By RD:577 a smoke BudgetStop means no pilot, plus a v1.1 re-registration.
  Fix: smoke solver cap ≈ 10M, or cut S2 ALFWorld to 1 run and 3 arms; reconcile S-N1.
- (b) Test read. RD:548 says 12–37M (default) and 25–60M (recommended), and RD:901 says this arithmetic was "未写入任何文件".
  Recomputed with RD's own §9.1 anchors, the fired shares in the RD:541 header, and F/P_F/T_F on fired items at ×1.25/×1.6:
  - default: 11.8-43.4M without twins; 12.6-54.4M with 0.5-1.0 twin cells per fired item;
  - recommended: 20.7-54.1M and 23.0-68.7M (estimates).
  The default test-read cap of 45M (RD:563) is below 1.3 × the registered high estimate (1.3 × 37 = 48.1M), which the
  start rule RD:570 itself requires. The recommended cap of 70M is below 1.3 × 60 = 78M.
  Fix: save the calculation, then either raise the test-read caps (≈ 65M default / ≈ 100M recommended, estimate; this
  pushes the overall caps to ≈ 110M / ≈ 200M) or trim test arms (P_F and T_F only on L ∪ similar; twins only on L).
- (c) Step caps sit at about 1.2× the high estimates: SB accept 5 vs 4.1, OQ accept 16 vs 13.6, ALF accept 55 vs 44.6
  (RD:545-546 vs :562). Yet RD:566-567 says the ledger counts 1.5-2× actual (cal-1), and S-E6 accepts a ledger/actual
  ratio up to 1.5 (RD:605). At the high anchor × 1.5 these scopes BudgetStop mid-round, and this does not trip the
  "> 25% above the high anchor" re-registration rule (RD:539). The mid-round stop then forces `raise_cap`, a recorded
  deviation, on a one-shot batch.
  Fix: make the S-E6 check compare (measured per-cell × measured ledger ratio × planned cells) with every scope cap
  before the pilot, or set each cap = high × 1.5.

### C5 [MAJOR] Changes to the owner-approved design-v0 are explained but not listed as owner decisions
- Quote: §14 (RD:666-705) lists only two of the design changes: the pilot order (#1) and the canonicaliser (#16).
- Problem: the task rule is that nothing in design-v0 may be changed except as a listed owner decision. The RD changes,
  in its owner-facing text but without a §14 item:
  - (1) The self-test no longer blocks on accuracy regression. DV0:31 said "查有没有倒退"; RD:343-347 changes it.
  - (2) Predictive validity changes from a gate ("连续两次不一致的出题程序作废", DV0:29) to a metric with an 8-pair
    slope test (RD:470-477). In English this appears only in §16 C-A8. It is the examiner's headline mechanism.
  - (3) The labels "通用/仅本 bench" (DV0:33) move from freeze time to after the test read. Scope defaults to "all"
    (RD:351-354).
  - (4) The format guard. DV0:17 has "最后由格式护栏输出答案"; RD makes it an instruction only and forbids output rewriting
    (RD:101-104). The reason (answer repair) is sound, but the owner must be told that it differs from DV0.
  - (5) The task cards. DV0:10 says "人写的说明"; RD:96 uses the five GLM-written I-ds instructions. MAP §4 item 9 flags
    this and A5 fixes it, but no owner-facing deviation note exists.
  - (6) Detector acceptance targets pass/fail, not the "目标失败类别" of DV0:28.
  - (7) The SearchQA examiner's "答案归一化检查" and paraphrase probes (DV0:29) are dropped (RD:322).
  - (8) The DV0 minimum effects (SB 7, LM 5; DV0:32) are replaced by MDEs of 12 and 9-10.
- Fix: add a §14 block "相对设计稿 v0 的改动" with items (1)-(8), each with a default, a one-line reason and the effect.
  Keep (2) explicitly as the owner's call, since it changes novelty claim 1.

### C6 [MINOR] Bench names and numbers are in mismatched order
- Quote: RD:224 "SearchQA、SpreadsheetBench、OfficeQA 以 D1 的实测下限换算（10.7 / 8.9 / 3.0 分".
- Fix: write SpreadsheetBench 10.7, OfficeQA 8.9, SearchQA 3.0. Check: 0.122 × √(46/60) = 0.107 and 0.103 × √(37/50) = 0.089.

### C7 [MINOR] Acceptance probabilities mix single-contrast and IUT numbers
- Quote: RD:25 "被收下的机会只有约 13%–41%"; RD:438 "两步都不收的概率约 0.71".
- Problem: 13% is the critic's IUT acceptance for SB; 41% is RD's single-contrast power for OQ. By RD's own table
  with the 0.85-0.9 joint factor, acceptance at +5 is ≈ 0.27-0.29 (SB) and 0.35-0.37 (OQ), so P(none) ≈ 0.45-0.47.
  The critic's bench-specific noise gives 0.13 / 0.18 and 0.71.
- Fix: write "约 13%–37%" and "约 0.45–0.71（取决于噪声来源）".

### C8 [MINOR] LiveMath power row describes an unregistered design
- Quote: RD:435 "LiveMath 200 × 2（若全用…）| 0.30 | 0.59 | 0.98".
- Problem: RD:220 registers 100 meta-absent items × 2 (MDE 9-10). A power of 0.59 at +5 implies an MDE of ≈ 7.5. By the
  same method, 100 × 2 gives ≈ 0.41-0.47 at +5 (estimate).

### C9 [MINOR] "C10" is referenced but never defined
- Quote: RD:606 and IP:56, :352 refer to "C1–C10"; RD §5.4 (RD:326-340) defines only C1-C9.
- Fix: define C10, or write C1–C9.

### C10 [MINOR] The empty-package equivalence test contradicts the always-on level-1 canonicaliser (EA-E18 unresolved)
- Quote: RD:122 and IP:300, :357 ("must pass ... on all five benches") vs RD:105 "所有组都开".
- Problem: with a reply such as "Action: go to X", the frozen loop executes the raw text (backends.py:752-762), while
  route B executes the canonical command. The predictions differ, and so do all later request hashes.
- Fix: for ALFWorld, test equivalence only on exact admissible replies (how = tag_exact), add a separate test that
  isolates the canonicaliser, and state in RD that route-B ALFWorld numbers are not comparable with v3's.

### C11 [MINOR] The reasoning-leak path is overstated
- Quote: RD:262 "回执里有推理 → ... 走冻结的重发路径"; RD:301 P6.
- Problem: if a leaked reply's completion exceeds B, `_record` latches the breach and raises AssumptionBroken before the
  Recorder can resend (calls.py:209-221, ledger.py:67). That is a global halt, not P6. For ALFWorld, B = 2,048 under
  branch E, so a typical leak would halt. RD §15 marks EA-E7 as P, but the Chinese text does not say this.
- Fix: say so in §4.1 and §14 #4.

### C12 [MINOR] The refutation rule for predictive validity is ambiguous
- Quote: RD:475 "两组以上配对上…超过 2 个合并标准误 → '效度被否定'".
- Problem: this can be read as firing with only 2 pairs. IP:59 and T-VAL-1 (IP:313) return not_evaluable below 8
  informative pairs.
- Fix: state that refutation also needs ≥ 8 pairs, or pre-state that the pilot can refute.

### C13 [MINOR] Owner-facing readability
- The decision criteria "D1–D7" (RD:401-410, e.g. "D3 故障") collide with the feasibility studies D1/D3/D6/D11/D14,
  which the same sections cite (RD:224 "D1 的实测下限", RD:337 "D3 的手写记录器").
  Fix: rename the criteria (e.g. 判据 J1–J7).
- Glossary §17 lacks these codes:
  - chain and study names: I-ds, E-ds, cal-1, E1/E4/E9/E10, the D-numbers;
  - arm and set names: G_acc, G_self, P_F, T_F, F∖p, τ;
  - outcome tokens: over_nominal, procedure_fault/unknown_fault, thinking_mismatch;
  - v1.1, and "[审查 …]" tags.
- RD:35 says the smoke has "四段", but §10 has S0, S1, S2, S-N1, S-E6, S3, S4.

### C14 [MINOR] The ALFWorld high anchor is not the I-ds measurement
- Quote: RD:530/:536 "高（以 I-ds 实测为锚）… ALFWorld 每局 45,000".
- Problem: the measured I-ds episode was 105.7k tokens with the five-card render [FP F17]. 45k is an adjusted estimate
  (single card, about 37 steps × ~1.2k).
- Fix: label it "估计" with its assumptions.

### C15 [MINOR] S1 probes can halt the smoke ledger
- Quote: RD:602 S1-b ("M ∈ {16, 64, 256}，各 10 次长文请求") and S1-e (reasoning on); IP:376 "cap 0.5M".
- Problem: if these probes use B = 2M or 4M, a non-enforcing gateway or a reasoning reply gives completion > B. That is
  a global smoke-ledger halt.
- Fix: register B_probe (e.g. 32,768) for S1-b and S1-e, or run S1 on its own ledger root. Keep S1-d's 8 concurrent
  reservations under the 0.5M cap (small M).

### C16 [MINOR] Raw-reply score is described wrongly
- Quote: RD:290 "原始回答得分（本协议不改写输出，所以等于 v2）".
- Fix: the raw-reply score equals the guarded-answer score, because there is no transformation. v2 differs from the
  official score by JSON extraction.

### C17 [MINOR] Deviation from A10 is not flagged
- Problem: A10 says "a failed computation falls back to the parent reply". RD:136 still sends the second call with
  "not evaluated" and falls back only if that call fails.
- Fix: add this to §16 (C-A10 covers only the call count).

### C18 [MINOR] One §15 status is optimistic
- Problem: EE-F5 is marked R (RD:785), but the SearchQA-derived noise used for the SB and OQ MDEs is only disclosed
  (power brackets), not replaced. S-N1 measures only SearchQA and ALFWorld.
- Fix: mark it P/D.

## Omissions

- O1. The G_acc size per bench is not registered (RD:471; IP:58), although its cost sits in the examiner caps.
- O2. The withholding-twin cost is not stated separately (A11 and related-work consequence (ii) ask for size AND cost).
  It is lumped into "验收含孪生" (RD:545) and the test read.
- O3. Runs per item for the test read are not registered (RD §8.1). Only RD:503 implies 1.
- O4. The S0 test-exclusion runs need their own consent record. These are the ALFWorld valid_unseen identity check and
  the SearchQA exclusion (RD:599). They hold TestAccess before the pilot consent exists. The key
  `alfworld_test_identity_check` sits in the test-read consent (RD:494), and frozen consent() requires
  test_evaluation = true (evaluation.py:152-159). Register a separate exclusion-consent record (EA-E27).
- O5. The §9.2 and §6.6 arithmetic is not saved (RD:901), so it cannot be verified. Save the script and its output under design/.
- O6. The ALFWorld MDE (RD:219) has no room-cluster design effect. Register the number of acceptance rooms and a
  games-per-room cap.
- O7. LiveMath D7 (RD:409) has no item source. All 129 meta items are in the run slice (RD:220), so a probe on them
  would reuse consumed items and hit ConsumptionConflict. Formal chain only.
- O8. The new ALFWorld id namespace required by A9 is not stated in RD §3.1.
- O9. When |A*| < 15 (RD:233), the step's decision label and the handling of S' (archived, S passes on) are not stated.
- O10. The zero-call ALFWorld pre-reset for routing views (RD:118; IP:49) would cover ~3,514 games, and its time is not
  estimated. Reset only the cut slices.
- O11. S-N1 does not measure noise for the default pilot's benches (SB, OQ). OQ step 2 has no same-text duplicate
  unless S = C. Owner #22 covers the option, but the re-registration trigger (RD:226) then rests on SearchQA noise.
- O12. Memory is not budgeted. Up to 16 per-cell containers (768m limit each, IP:217), the 3 native 4 GiB containers
  and the ALFWorld workers share 15 GiB (EA-E34). State the cap on simultaneously live sandbox containers.
- O13. Optional: RW §8 item 10 also names Self-Challenging and DGM for direct contrast. RD §12 covers the three
  required works plus Break It Down.

## Verified as consistent (no action)
- Identity:
  - the closed-set copy and the one exception set (outcomes.py:95-112; cells.py:45-46);
  - leakage/roles/calls/stats/checks imports are protocol-free except calls' MAX_RESENDS/RESEND_COOLDOWN (calls.py:32);
  - IMPORTABLE string = qualify.load's check (qualify.py:134-138);
  - texts.json version = IP:258 "fivebench-coevolution-v3-texts-import" (dl, measured).
- Endpoint:
  - Endpoint built with B and the body sending M works as registered (calls.py:136-221; ledger.py:62-72);
  - `rooted` needs deepseek-prefixed solver scopes, and IP uses `deepseek:xs:*` (budget.py:59-64);
  - parent `_receipt` checks reasoning only when thinking == "disabled" (weak_solver_probe.py:295-296), so an override
    is needed, as planned.
- Frozen-code facts:
  - Frozen `_native` argv (backends.py:169-178) matches RD:142-143.
  - The sandbox's `-s -B -P` runs on the Python 3.11 image (runtime/Dockerfile:2-5).
  - Contract sentences match backends.py:35, 53-56, 381-382, 730.
- Data:
  - The data.ranked signature (data.py:173-176) and the SearchQA sampler seed (make_searchqa_fresh_sample.py:62, :121)
    match RD:199, :207.
  - Smoke real items add up: 280 = 20 + 200 + 60, and 12 ALFWorld games.
  - Pilot slices use the whole pools: SB 31 + 60 = 91; OQ 24 + 50 = 74; LM 54 + 129 + 100 = 283.
- Statistics and budget arithmetic:
  - MDE → power arithmetic for SB/OQ/ALF/SQ reproduces RD:432-436 (σ = MDE / (1.135 × 2.487)).
  - §9.2 sums are right: 2.6 + 7.4 = 10; 6.9 + 19.2 = 26.1; 22-63; 60-131.
  - Cap sums are right: default steps + test = 77.1M ≤ 100M; recommended 160.1M ≤ 180M (RD:847-848).
- Coverage of the brief:
  - All 94 fatal/major critique findings have §15 rows (counts verified against the six critique indices).
  - The A1-A15 mapping is complete (RD:813-829).
  - The fixed owner decisions are kept: both sides evolve, no validation set, five benches, the default order, the solver
    and gateway, GLM roles, the new identity, smoke then pilot.
  - Positioning claims match related-work §2 and §8. The forbidden "first ..." claims are excluded (RD:641).

## 给负责人的白话摘要

1. 结论：登记稿和实现计划总体扎实，但有 5 处"重大"问题要先改，才能进入建设。没有"推翻方案"的致命问题。
   - "登记稿"指事先写定、开跑后不许改的规则文件。
   - "实现计划"指写给编程代理的建设说明。
2. 第一处，建设地点和您的要求不一致。
   - 计划写的是先在 Mac 上写代码、跑测试，再拷到开发机。
   - 您要求直接在新 Linux 开发机上实现。开发机上已经有准备好的工作目录 /data/execskill-dev，在新分支上，还没有新代码。
   - 要改成在开发机这个目录里建设，并把它写进登记稿。
3. 第二处，ALFWorld（文字家务游戏）上考官写的"失败检测器"按现在的规则永远收不下。
   - 原因：失败的局都会走满 50 步，而"走满 50 步"本身就被算作固定类别，剩下可检验的格子里没有失败局。
   - 稿子却说"ALF 有机会判定"。要么改规则，让固定类别也只看前 10 步；要么删掉这句话，并写明两个试点方案里考官一侧都不可能成功。
4. 第三处，排队等"局锁"超过 1 小时就判"隔离箱不可用"并暂停。
   - "局锁"是同时最多跑 6 局的名额；"隔离箱"是运行模型所写代码的封闭环境。
   - 按 16 个线程抢 6 个名额估算，ALFWorld 一轮验收里几乎一定会因为正常排队而误停。
   - 要么把线程数设成 6，要么排队超时不算故障。
5. 第四处，预算上限和自己的估算对不上。
   - 冒烟（试点前的小规模检查）按稿子自己的组数估算约 390–1,100 万 token（估计），上限只有 500 万。
   - 最后一次读测试集按稿子自己的假设可能到 4,300–5,400 万（估计），上限 4,500 万，还低于它自己"开始前要留 1.3 倍余量"的规则。
   - 各步上限只比高估计多约两成，而账本记数可能比实际高 1.5 倍。
6. 第五处，稿子改动了您认可的设计稿 v0 的几处做法，原因都写了，但没有列进"需要您拍板的事"。这几处是：
   - 自测不再按准确率拦截；
   - "预测效度"从淘汰关卡改成只报告的指标。预测效度指生成题上谁好谁坏是否和真题一致；
   - "通用 / 仅本 bench"标签改到读测试集之后才给；
   - 格式护栏只当指令，不再改写输出；
   - 任务卡用 GLM 写的版本，而不是人写的；
   - 检测器只看对错，不看失败类别；
   - SearchQA 的答案归一化检查被去掉；
   - 最小效果改成按题量算出的数字。
   建议在第 14 节加一组，逐条给默认值，请您确认。
7. 另有 13 处小问题（数字标错顺序、个别概率口径混用、术语表缺代号等）和 13 处遗漏，都在上面逐条写了出处和改法。
8. 您问的"设计稿和审查人是否正常"：三份设计、六份反方审查都已完成（文件里都写着 COMPLETE/DONE），登记稿逐条回应了全部 94 个致命和重大意见。开发机通过 aTrust 可以连上，我只做了只读查看。

Status: COMPLETE (20:4x).
