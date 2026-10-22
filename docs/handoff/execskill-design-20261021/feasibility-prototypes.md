# Area map: overnight feasibility prototypes (2026-10-21) that route B builds on

Status: COMPLETE (2026-10-21). Facts F1-F61 in section 2; sections 3-6 follow section 1-final near the end of the file.
Author: read-only subagent. Repo: /Users/dulin/Documents/Paper/SkillOpt (paths below repo-relative unless absolute).
Linux paths are on host `dl` (ssh -o BatchMode=yes dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn).
Convention: [V] = verified by reading the cited file/line; [I] = inferred. `FD` = docs/handoff/feasibility-20261021.
In every FD/<id>/result.json the keys sit on fixed lines: D-series line 5 verdict_cn, 7 evidence, 8 design, 9-14 pilot
(ran/result/command/cost_tokens/blocked_by), 16 risks, 17 cost_estimate, 18 recommendation, 19 references, 20 artifacts;
E-series is shifted by +1 (line 4 = purpose). critic-result.json: 3 verdict, 4 refuted_claims, 5 confirmed_claims, 6 missing,
7 corrected_feasibility, 8 notes_cn. Numbers quoted below come from those lines unless another citation is given.

## 1. Scope and files read (with line counts)
(filled at the end; see list in section 1-final at end of file)

## 2. Facts

### 2.D3 ALFWorld state-tracker tool (+ SpreadsheetBench repair pilot)
Sources: FD/D3/result.json (20 lines; no report.md -- harness refused it, line 20), FD/D3/critic-result.json (8 lines),
dl:/data/feasibility/D3/ (110M) code read in full: r3/lt/tracker_glm.py (147), r3/lt/tracker_ref.py (62), r3/lt_replay.py (78),
r3/lt_induce.py (22), r3/lt_prepare.py (60), r3/lt_diff.py (21), r3/analyze_glm.py (32), r3/pilot_alf_glm.py (352),
r3/pilot-alf-glm/summary.json, r3/lt/usage.json, r3/lt/replay_glm.json, r3/lt/diff_glm_ref.json, r2/pilot-alf-b/summary.json.

- F1 [V] What ran. (a) ONE GLM-5.3 call wrote a Tracker from a registered interface: usage {"prompt_tokens": 2155,
  "completion_tokens": 2831, "total_tokens": 4986} (dl:/data/feasibility/D3/r3/lt/usage.json). Output: 5,087-byte stdlib
  program dl:/data/feasibility/D3/r3/lt/tracker_glm.py, sha256 ed49e788417c35b119f9968a4750d403e530b6cfd890018ab5b6826188254b04
  (FD/D3/result.json:20). (b) Sandboxed replay over 228 v3 stage-5 TRAINING traces / 7,524 steps: 0 exceptions, 0 bad_view,
  0 too_long, p3_checked 4218 p3_fail 0, p4_checked 632 p4_fail 0, p5_fail 0, p6_fail 0, agree_all 7350/7524
  (dl:/data/feasibility/D3/r3/lt/replay_glm.json). Divergences vs hand tracker: glm_only 107, ref_only 67, from
  'examine X' / 'move obj to X' counted as reaching X (dl:.../lt/diff_glm_ref.json). (c) Episodes: 42 paired training games,
  arm T only in r3 (D3_ARMS=T, 6 workers, D3_BUDGET=1600000; FD/D3/result.json:12), compared against pilot B's arms C and
  T-hand that ran 1.5-5 h earlier (FD/D3/result.json:16 risk 4).
- F2 [V] FINAL numbers (run finished 05:38, supersede the 39-game numbers in result.json): T-glm 26/42 pass, 16 fail;
  spent prompt 1,369,286 + completion 28,481 = 1,397,767 deepseek tokens, 1,141 calls, mean 33,280 tokens/episode,
  mean revisits per failing episode 9.4, canonicalised_steps_T 681 (dl:/data/feasibility/D3/r3/pilot-alf-glm/summary.json;
  run.log last line "05:38:16 done"). Critic: T-glm 26/42 vs C 16/42, discordant 11 vs 1, sign p=0.0063, +0.238
  [0.092, 0.385]; T-glm vs T-hand 26 vs 28, 3 vs 5, p=0.73; tokens/call 1,225 vs 873 (FD/D3/critic-result.json:4 item 4).
- F3 [V] Pilot B (r2, earlier round, the C and T-hand reference arms): 57 items listed, 15 per arm not_run (budget stop),
  T 28/42 vs C 16/42, pairs T=pass,C=fail 14 / T=fail,C=pass 2 / both pass 14 / both fail 12; spent 2,594,702 + 57,108 tokens,
  2,581 calls; mean tokens T 32,698 vs C 30,440; mean revisits on failures T 5.4 vs C 19.4
  (dl:/data/feasibility/D3/r2/pilot-alf-b/summary.json). The 42 games are the first 42 in hash order before the budget stop,
  not chosen by outcome (FD/D3/critic-result.json:5). Item ids frozen in dl:/data/feasibility/D3/r3/paired42.json
  (alfworld/train:* and alfworld/val:* ids; val:* are training-pool items per FD/D3/result.json:6).
- F4 [V] Model/settings of episodes: deepseek-v4-flash via `Client(None, "deepseek-v4-flash", proxy=GATEWAY, max_tokens=512,
  read_timeout=600, route="pjlab_token", route_env="/root/.config/weak-solver/pjlab-token.env")`
  (dl:/data/feasibility/D3/r3/pilot_alf_glm.py:282-283); E-ds empty scaffold Skill `SKILL = Skill(scaffold=True).render()`
  asserted `digest(SKILL).startswith("cc516459810a")` (pilot_alf_glm.py:52-53); 50 steps from
  manifest["runtime"]["alfworld"] of /data/coevo5-20261019-v3-run-manifest.json (pilot_alf_glm.py:50-51); code imported from the
  frozen v3 source snapshot `sys.path.insert(0, "/data/coevo5-20261019-v3-source-f")` (pilot_alf_glm.py:36).
- F5 [V] The harness modification = a RE-IMPLEMENTATION of the frozen `_solve_alfworld`, not a patch to backends.py:
  `tracker_episode(public, call, record, use_tracker=True)` (pilot_alf_glm.py:205-255). System prompt
  "Act in the text environment. Return a single action inside <action>...</action>." + TRACKER_SENTENCE (T only) +
  "\nFrozen skill guidance (use only where applicable):\n" + SKILL (lines 207-210). View dict keys
  initial_observation / observation / admissible_commands / recent_history (= history[-5:]) plus "explored" = tracker.view()
  for T (lines 219-222). Env from `backends._new_alfworld(public, RUNTIME)` then env.reset()/env.step([action]) (213-241);
  `tracker.update(action, post)` after each step (243). Win from infos[0]["won"] (246-248).
- F6 [V] CONFOUND 1, text instruction: TRACKER_SENTENCE (pilot_alf_glm.py:56-59) ends "Use it to avoid revisiting places you
  have already checked." -- a behavioural instruction present only in arm T; no sentence-only arm (FD/D3/critic-result.json:4 item 1).
- F7 [V] CONFOUND 2, parser: `parse(text, admissible)` (pilot_alf_glm.py:178-195) returns how in
  {"tag","whole","canonical","earliest_admissible","unchanged"}; `canonical(action, admissible)` (165-175) strips
  "action:"/"action<|>" wrappers and maps case-insensitively to admissible commands. Both arms got it, but the critic recomputed
  rescued steps T-glm 467/1,139 (41.0%), T-hand 438/1,115 (39.3%), C 193/1,462 (13.2%); 25/26 T-glm passes used >=1 rescued
  step; under frozen verbatim parsing 4 of 7 tracker episodes failed with 43-50/50 wrapper actions; under the frozen 32,768
  token cap 2 of 3 logged tracker episodes died of runaway truncated replies => "the tracker hurt in the frozen loop"
  (FD/D3/critic-result.json:4 item 2). max_tokens 512 vs frozen 32,768 is a second loop change (FD/D3/result.json:16 risk 5).
- F8 [V] CONFOUND 3, induction = transcription: dl:/data/feasibility/D3/r3/lt_prepare.py:35-57 builds the prompt with the goal
  (incl. the v3 statistics "about 30-36% ... 'go to' a receptacle it had already reached ... about 20 of 26 receptacles"),
  the interface with "EXACTLY these keys: 'reached' ... 'not_reached_yet' ... 'carrying' ... 'rejected_actions_so_far'",
  environment text facts, and 2 training excerpts (one failing with most revisits, 18 steps; one passing, 12 steps).
  Critic: "GLM transcribed a spec; that explains the 97.7% agreement"; one sample only (FD/D3/critic-result.json:4 item 3).
- F9 [V] CONFOUND 4/5: no placebo arm; one run per arm with 6/42 games flipping between identical v3 runs
  (FD/D3/result.json:16 risks 2-3); only the empty scaffold Skill, task-card Skill not measured (risk 6); about half the looping
  is revisits within the visible 5-step window (444/1,017 E-ds failing-episode revisits = 44%), i.e. a policy failure, not only
  memory (FD/D3/critic-result.json:4 item 5). The tracker module runs IN-PROCESS via importlib during episodes
  (pilot_alf_glm.py:198-201); only replay ran in a container (FD/D3/result.json:12; critic missing item 6).
- F10 [V] Replay verifier contract (reusable): `python -I /input/lt_replay.py <candidate.py> <reference.py> <traces.json>`
  inside `docker run --rm --pull=never --network=none --read-only --user=65534:65534 --cap-drop=ALL --pids-limit=64
  --memory=1024m --cpus=1 --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m ... b8fe4ce3655e` (FD/D3/result.json:12). Prints one
  JSON line {"counts": {...}, "examples": [...]}; property checks p3 (go to/open target must be in reached), p4 (pick-up in
  carrying / moved object not in carrying), p5 (not_reached_yet disjoint from reached and subset of receptacles), p6 (rejected
  count exact) (lt_replay.py:21-38); schema check `set(v) != KEYS` -> bad_view (line 60); `len(s) > 1500` -> too_long (62).
- F11 [V] Trace format for replay (dl:/data/feasibility/D3/r3/lt_prepare.py:8-19): from
  /data/coevo5-20261019-v3-run/{E-ds,I-ds}/s5/train/attempt-1/cells/*.json, benchmark=="alfworld", prediction artifact at
  artifacts/<attempts[-1].prediction.sha256>.json, `pred["trace"]` list of {action, observation, post_observation}; stored as
  {"chain","cell","item","token","initial": tr[0]["observation"], "steps": [[action, post_observation], ...]}. traces.json is
  805,018 bytes on dl.
- F12 [V] SpreadsheetBench side (earlier round, recomputed): repair turn R 14/47 vs plain re-sample S 11/47 on hard-flagged
  failures, discordant 8 vs 5, p=0.58; fence salvage of 91 unclosed-fence 'malformed' failures: 31 pass / 58 fail / 2 unknown;
  v3 stage-4 failure codes D4 'wrong logic' 52/87 (60%) (FD/D3/result.json:7). Critic: inconclusive, not negative; library slot
  never piloted; 213/290 hard flags are trivial 'no_workbook' (FD/D3/critic-result.json:4 item 7).
- F13 [V] Proposed slot design (unbuilt): `alfworld.observer` Tracker(initial_observation); update(action, observation);
  view() -> dict <= 1,500 chars; `alfworld.actuator` map(reply, admissible); `spreadsheetbench.library` module written next to
  input.xlsx; V0 static AST whitelist / V1 replay / V2 selftest / V3 screen+confirm with program placebos / V4 test; identity
  sites that hash only Skill text: cells.py:222, evaluation.py:356/366 (test-eval reuse keyed on text digest), step.py:825,
  chain.py:290 (FD/D3/result.json:8; confirmed FD/D3/critic-result.json:5).
- F14 [V] Costs: tracker induction 4,986 GLM tokens; replay 0 tokens, 2.8 s wall; empty-scaffold ALFWorld episode ~30-31k
  deepseek tokens, 6.2-9.4 worker-minutes; v3 I-ds 3,377 tokens/call vs E-ds 820 because the Skill is re-sent every step
  (FD/D3/result.json:17). Recommended replication 57 games x 2 runs x 4 arms (C, T-hand, T-glm, T-placebo) = 456 episodes
  ~14.4M tokens (FD/D3/result.json:17); critic: the task-card half adds ~45-50M, total ~60-65M, 16-24 h
  (FD/D3/critic-result.json:4 item 6). Critic corrected feasibility: low (FD/D3/critic-result.json:7).

### 2.D14 ALFWorld + SpreadsheetBench failure anatomy under text skills (report never finished)
Sources: FD/D14/report.md (310 lines; NO result.json, NO critic). The report still contains unfilled placeholders
[[BOTTOM_LINE]] (line 7), [[ALF_TABLE]] / [[ALF_FINDINGS]] (after the arm list in 5.1), [[SHEET_TABLE]] / [[SHEET_FINDINGS]],
[[ALF_CONCLUSION]] / [[SHEET_CONCLUSION]] (section 6), [[SPEND]] (section 9). Pilot numbers below were read from
dl:/data/feasibility/D14/out/pilot_all_summary_first12.json, dl:/data/feasibility/D14/pilot-sheet/summary.json and
dl:/data/feasibility/D14/pilot-sheet-x/summary.json (the report's tables are empty). docs/handoff/overnight-report-20261021.md
section 6.4 also lists D14 as "无结论" (no conclusion) and "未审查" (no critic) in 6.5.

- F15 [V] Failure anatomy, v3 stage-5, 57 training games x 2 runs per chain (FD/D14/report.md section 3.2): wins E-ds 46/114
  (40.4%), I-ds 58/114 (50.9%); I-ds minus E-ds +0.105 [+0.026, +0.184], 12 better / 3 worse, p=0.035 -- "the hand-written task
  card is the only text that measurably moved ALFWorld in v3"; same-text run-to-run disagreement 8/57 items per chain; every
  failure is a 50-step timeout (68/68, 56/56); D3 "search loop" diagnosis 43/68 and 45/56; target object never seen in 49/68
  and 46/56 failed episodes; failed episodes visit 6.0 of 26.1 / 6.3 of 25.9 receptacles; revisits are 44.7% / 51.3% of failed
  steps, 60-62% of them within 5 steps (inside the visible window); `close` 12% of failed steps; "Nothing happens" 10-13%.
- F16 [V] "55/57 open surfaces": by the walkthrough metadata of the TRAINING games the object lies on an open surface in 55/57
  games (2 in closable containers); failing agents reached that location in only 16/68 (E-ds) and 10/56 (I-ds) episodes; in won
  episodes the first object came from an open surface in 31/46 and 37/58 (FD/D14/report.md section 3.2). Wins are short: median
  10.5 / 9 steps; expert walkthrough 5.9 steps on average (max 9). Estimated +2..+8 (E-ds) and +10..+14 (I-ds) points from a
  100-step budget at double cost of failing episodes. Stronger solver on the same harness (v1, GLM-5.3 with reasoning): E-glm
  102/114, I-glm 101/114 => "the harness is solvable; the weak, non-reasoning solver is the bottleneck".
- F17 [V] Per-step cost driver: E-ds 807 prompt tokens/step (28.5k/episode, 3.24M per 114 episodes); I-ds 3,364/step
  (105.7k/episode, 12.04M per 114) -- "every 1k characters of ALFWorld guidance costs about 250 tokens x ~35 steps per episode"
  (FD/D14/report.md section 3.2).
- F18 [V] v3 proposal funnel stages 4/5: 20 proposed, 12 supported, 3 selftest passes (all 1-vs-0), 1 screen pass, 0 confirm
  passes; the ALFWorld memory-dependent rule "mental checklist, visit each receptacle once" solved 0 of its 14 trigger items;
  in 3 of 4 gate rounds the best of four placebo controls beat the parent by +1.5 items (FD/D14/report.md section 3.1, 3.4).
- F19 [V] Pilot P1/P3/P3b design (FD/D14/report.md section 5.1): rule R1 (575 chars, state-conditioned "When you do not yet
  hold the object ... go to the open surfaces ... in the listed order ... When you hold it: go to the appliance ..."), R2
  (590 chars = format sentence "Reply exactly <action>COMMAND</action>, COMMAND verbatim from admissible_commands; never write
  'action:'." + shortened R1), F (105 chars, format sentence alone). Skill hashes R1 ab9bb0ad35fc..., R2 f347c4cbfec5...,
  F 22d8287a536c... Arms: V = v3 E-ds s5 records; C = no rule today, frozen loop; T = R1 frozen loop; F; T2 = R2 frozen loop;
  K = R1 in the D3 canonicalising loop; D3C = D3 r2 arm C; K0 = canonicalising loop, no rule, today. Items: 57 training games
  shuffled with Random(20261021), compared on the first 12, one run per arm. EXPLICIT CAVEAT: R1/R2 are in-sample, written from
  aggregate statistics incl. walkthrough object locations => "an upper bound of what one rule of this kind can do".
- F20 [V] Pilot P1/P3 results (dl:/data/feasibility/D14/out/pilot_all_summary_first12.json, "first12_only": true):
  V 9/24 (0.375); C 3/9 (0.333, nonplain_share 0.292, nothing_share 0.367); T(R1) 2/11 (0.182, nonplain 0.645);
  F 0/8 (0.0, nonplain 0.603, mean tokens 44,100); T2(R2) 8/9 (0.889, mean tokens 14,855); K(R1 + canonicaliser) 8/9 (0.889,
  17,431 tokens); K0 0/2; D3C 4/10. Paired: T2 vs C 5 vs 0, sign p=0.0625; T2 vs T 7 vs 0, p=0.0156; K vs KC 5 vs 0, p=0.0625;
  K vs T2 0 vs 0. Reading [I]: in today's frozen loop the provider emits wrapper-form actions (nonplain 29-65%), so the rule
  only works when the action interface is guarded (by a format sentence or the canonicaliser); the format sentence alone (F)
  does nothing; n=8-11 per arm, one run.
- F21 [V] SpreadsheetBench hint ceiling P2 (44 failed E-ds s4 training items): H (item's own GLM hint, <=550 chars, answer
  repair) 25 pass / 18 fail / 1 unknown vs S (plain re-solve) 8/36; pairs H=pass,S=fail 20, H=fail,S=pass 3; GLM 40 calls,
  67,623 + 19,279 tokens (dl:/data/feasibility/D14/pilot-sheet/summary.json). P2x placebo X (another item's hint) 8 pass / 36
  fail (dl:/data/feasibility/D14/pilot-sheet-x/summary.json) -- i.e. the cross-item hint equals a plain re-solve (8/44).
  H "is answer repair by text -- an item-specific ceiling, not a Skill" (FD/D14/report.md section 5.2).
- F22 [V] D14's own ranked protocol advice for ALFWorld (FD/D14/report.md section 7): (1) guard the action interface in the
  frozen loop for EVERY arm (validate against admissible_commands, canonicalise wrappers; "the D3 r2 canonicaliser, about 30
  lines"); (2) give the proposer cross-episode aggregate statistics; (3) ask for state-conditioned rules, forbid memory rules;
  (4) test on all 57 training games x 2 runs; (5) executable state is "stronger and complementary"; (6) more steps last.
  Follow-up estimate: rule vs parent vs two placebos, 57 x 2 = 456 episodes x ~25k = ~11M deepseek tokens, ~4 h at 6 concurrent.
- F23 [V] D14 code on dl (not read line-by-line; names only): analysis a_units.py, b_alf_traces.py, c_alf_locations.py,
  d_items.py, e_sheet_size.py, f_alf_more.py, g_stats.py, h_pilot_alf.py, j_pilot_all.py, k_pilot_sheet.py, n_spend.py; pilots
  p1_alf_rule.py, p3_alf_variants.py, p3b_alf_variants.py, p2_sheet_hint.py, p2x_sheet_cross.py; outputs out/alf_rows.json
  (393,563 B, per-episode v3 metrics), out/alf_locations.json (148,139 B), out/units_s45.json (dl:/data/feasibility/D14/, ls).
  Mac copy: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D14/
  (FD/D14/report.md section 10).

### 2.SUM The two summary documents
- F24 [V] docs/handoff/feasibility-exploration-20261021-cn.md (172 lines) was written at 05:04 and covers only 13 directions
  (D1, D2, D4-D9, E1, E4, E6, E7, E9) (line 5, line 9); its section 5 "unfinished directions" is stale (line 5). Its headline:
  the instrument is the bottleneck; on SearchQA any learned text adds at most 0-3 points over the task card while 200 items
  resolve 3-5 (line 9). Model roles: solver deepseek-v4-flash (no thinking, temperature 0), helper roles GLM-5.3 (line 14);
  13 directions spent ~23M tokens, training items only (line 15).
- F25 [V] docs/handoff/overnight-report-20261021.md (141 lines) section 6.4 (lines 52-66) summarises the 11 late directions,
  section 6.5 (lines 70-98) the critic corrections; critics downgraded E1, E2, E3, E4, E5, E7, E9, E10, D3, D7 to "low" with
  three recurring reasons: the plan uses up the only similar benchmark or non-existent item counts; gains come from format or
  shortcuts; "transcribing a spec into code" was counted as "learning from experience" (line 50). The single first zero-cost
  step: fix the scorer (accept JSON answers, record format errors separately from correctness) (line 50).

### 2.D6 Generated items with program-computed answers (LiveMath-style 52/52)
Sources: FD/D6/result.json (19 lines), FD/D6/critic-result.json (8), FD/D6/report.md (865, skimmed via result fields);
dl:/data/feasibility/D6/ (92M): pilot/sandbox_runner.py (56, read in full), pilot/common.py (187, read lines 1-60 and helpers),
v2/gen_livemath2.py (368, read lines 1-80, 104-260), names of v2/gen_searchqa2.py (627), v2/tiebreak_probe.py (95),
v2/page_scope_check.py (112), v2/officeqa_ops.py, v2/v3_forward_smoke.py.

- F26 [V] What ran: LiveMath-style -- GLM-5.3 writes {definition, code, value, 7 typed claims}; a sandboxed sympy/fractions
  run computes the reference; option texts are rendered from typed claims by template; forms M+ (meta option is the key),
  N (no meta), M- (meta present but wrong). 52 valid of 72 specs over 2 runs; hand audit keys 52/52 (95% CI 0.932-1.000),
  references 51/52 (run-1 #34 had F_2=2, key right by coincidence) (FD/D6/result.json:7). Total pilot 482,281 tokens:
  run 1 217,601; v3 forward smoke 79,229; run-2 LiveMath 103,170; run-2 SearchQA 76,731; tiebreak probe 5,550 (line 17).
- F27 [V] Checks: deepseek yes/no code audit said yes 30/30 incl. the defect (useless); reasoning recompute 9.8% false alarms
  (5/51); an EXECUTABLE program written by deepseek from the item text agreed with 31/31 correct values and gave the true
  value against 4/4 GLM code bugs; GLM's stated value disagreed with its own code in 8/30 run-2 specs (GLM wrong in 6, code in
  1, 1 unevaluated); 2-of-3 tiebreak would lift run-2 yield 22/36 -> 30/36 with 0 wrong (FD/D6/result.json:7).
  Critic: in tiebreak_probe.py the pair (GLM code, GLM stated value) can outvote the independent program; that risky
  configuration occurred 0/16 times, so it is untested; "the independent program must be one of the agreeing pair"
  (FD/D6/critic-result.json:4 item 6).
- F28 [V] Difficulty: solver (contract-first, NO Skill, pilot/common.py `solve`) 14/22 in run 2 (M+ 3/7, N 5/8, M- 6/7);
  pooled M+ 5/21 vs real meta-key cells 1/100; with context SearchQA-style 21/23, blind 8/25; OfficeQA-style forward smoke 14/14
  vs real ~22% (FD/D6/result.json:7). Critic: only run-2 N 5/8 is truly meta-absent, no evidence of difficulty difference there;
  pilot solves used no Skill while real cells carried the parent Skill, so difficulty comparisons are not like-for-like
  (FD/D6/critic-result.json:4 item 2).
- F29 [V] SearchQA-style: run 2 25 valid of 26; explorer 22/25 keys correct at page scope; critic 21/25 under one consistent
  standard (#24 also wrong) and the page-scope check "is not a validated detector" because it defined the defects; deepseek row
  checker agreed 25/25 incl. all wrong keys => two-model agreement is a filter, not a guarantee (FD/D6/result.json:7;
  FD/D6/critic-result.json:4 item 1).
- F30 [V] The frozen v3 forward pathway (research.material + forward.build_panel) ran for the first time: both panels short
  (OfficeQA 7 of 12, LiveMath 3 of 3, minimum 8 => forward_panel_short); 2/7 items state the answer, 3/3 LiveMath-style formulas
  are bare literals keyed "A" (FD/D6/result.json:7). Critic adds "rule echo": topic-chosen material makes the panel echo the
  rule (FD/D6/critic-result.json:6).
- F31 [V] REGISTRATION CONFLICT (critic): registration v6 section 2.2 says a not-yet-reached benchmark's learning history uses
  none of its real items or labels; D6's LiveMath mirror panel (meta sentence verbatim, M+:N = 68:87, meta always the key) is
  derived from LiveMath training labels; the validity study uses forward targets' real training pools; "Each needs an owner
  re-registration or a label-free design" (FD/D6/critic-result.json:4 item 8). Target fact behind it: the meta option
  appears in 68/155 LiveMath dev items and is the key in 68/68 (FD/D6/result.json:7).
- F32 [V] Power/cost corrections: c4_power.py's "non-inferiority" was a point-estimate threshold; a one-sided 95% NI test
  at n=200 x 2 runs passes a harmless rule only 0.45-0.56 of the time; a 3-point margin needs ~550 items x 2 runs; 200 x 2
  supports a 5-point margin (FD/D6/critic-result.json:4 item 3). Per-cell costs under the parent Skill are 2-3x D6's Skill-less
  figures: I-ds stage-entry training cells 3,969 (LiveMath), 4,088 (SearchQA), 7,927 (OfficeQA), 4,273 (SpreadsheetBench)
  tokens; E-ds 1,251 / 1,236 / 4,690 / 2,010 (FD/D6/critic-result.json:4 item 5). Measured per-item generation cost:
  LiveMath GLM 2,585 tokens per valid item (1,895 at tiebreak yield), cross-check 397, solve 811 (FD/D6/result.json:7).
- F33 [V] Reusable code on dl. `pilot/sandbox_runner.py`: "python -I sandbox_runner.py < program.py"; RLIMIT_CPU 40 s,
  RLIMIT_AS 3 GiB, import whitelist ALLOWED = {"sympy","mpmath","math","fractions","itertools","functools","collections",
  "operator","numbers","decimal","string","random","typing","re"} enforced via a `guarded` __import__ for namespace
  "__generated__"; deletes open/input/breakpoint/exit/quit/help; exec/eval/compile stay; reads RESULT and prints
  {"ok": True, "srepr", "str", "type"} or {"ok": False, "error"} (sandbox_runner.py:14-56). It is a host process guard, not a
  container [V: no docker call in the file]; [I] it is not a security boundary (exec/eval kept, builtins reachable).
  `pilot/common.py`: `glm_client(max_tokens=8192)` / `ds_client(max_tokens=8192)` wrap `scripts.weak_solver_probe.Client`
  (lines 33-40); `class Ledger(path, cap)` with `add(model, label, receipt)` writing every call's usage (43-60);
  `ask_json(client, model, ledger, label, system, user, *, last=False, retries=1)`; `solve(ds, ledger, label, bench, view)`
  = SOLVE_SYSTEM "Solve the supplied task using only the supplied public information." + CONTRACT[bench], no Skill;
  `score_searchqa(output, answers)` -> (exact, lenient, tag) using skillopt.envs.searchqa.evaluator.normalize_answer;
  `score_livemath(output, letter)` -> (bool, tag) using skillopt.coevo5.checks.last_answer.
  `v2/gen_livemath2.py`: SEED = 20261021, TOKEN_CAP = 450_000, FORMS = ("M+","N","M-"), CLOSING = " What is the strongest
  statement that can be proved about $Q$?"; `build(raw, form_wanted, k, position, rng)` -> (drop_reason|None, item) with drop
  reasons definition_format / code_format / claims_format / code_error / result_parse / result_not_exact / belief_mismatch /
  value_in_definition / no_form; item id "gen2:livemath:<sha256(question)[:12]>", item shape {"id","benchmark","public":
  {"question","choices"},"private":{"answer"},"spec":{...}}; `run_program_check(ds, ledger, item)` (independent program,
  exact sympy equality); `leaks(definition, q)`; `exact_claim(claim)`; imports `run_code, truth, parse_value, sign, META,
  TOPICS` from pilot/gen_livemath.py.
- F34 [V] Side effect noted by the D6 critic: nine .pyc files were written into the frozen snapshot
  /data/coevo5-20261019-v3-source-f at 2026-10-21 05:01:55 by a Python 3.10 process (not D6) (FD/D6/critic-result.json:6).
  [I] Pilots that `sys.path.insert(0, "/data/coevo5-20261019-v3-source-f")` and run `python -I` without `-B` (e.g. D3
  pilot_alf_glm.py:36 run as `python -I pilot_alf_glm.py`, FD/D3/result.json:12) can write __pycache__ into the frozen snapshot.

### 2.D1 Version-level acceptance on fresh batches (tokens per cell, placebo, interleaving)
Sources: FD/D1/result.json (20), FD/D1/report.md (526; read lines 160-180, 440-460 + grep), no critic;
dl:/data/feasibility/D1/v2/d1v2_pilot.py (159, read in full); repo skillopt/coevo5/step.py:105-160, data.py:173-200.

- F35 [V] What ran: fresh-batch pilot 2026-10-20 23:56:59 -> 2026-10-21 01:43:12, status complete: 130 never-used SearchQA
  training items x 2 runs x 6 arms = 1,560 cells, 0 unknown, 0 truncated, 0 non-200 sends; cost 2,388,219 ledger tokens =
  **1,531 tokens per cell** (FD/D1/report.md:451; FD/D1/result.json:11,14). Total D1 spend ~2.52M incl. a stopped
  attempt 112,525 and smoke 18,549 (FD/D1/report.md:451-453). Solver deepseek-v4-flash.
- F36 [V] Arms (dl:/data/feasibility/D1/v2/d1v2_pilot.py:8-14, 57-68): E (empty scaffold = cal-1 parent:A, sha 717618d4...),
  E+P3 (scaffold + PLACEBOS_SCREEN[2] recipe text = cal-1 control:3, sha c245e31e...), S (scaffold + SearchQA task-card seed =
  cal-1 seed-only, sha f1c48a6d...), S:dup (identical text, separate arm), S+P2 (S + PLACEBOS_SCREEN[1] hex-colour),
  S+P3 (S + recipe). Placebos are attached as `Rule("control-2", PLACEBOS_SCREEN[1], BENCH)` and rendered with
  `seed.text_with(p2)` (lines 60-63) -- i.e. a placebo occupies the rule slot.
- F37 [V] Results (FD/D1/report.md:164-178): S - E +0.162 [+0.104, +0.223], 28/2/100; S:dup - S +0.004 [-0.023, +0.031]
  (6/4/120, SD2 0.159); S+P2 - S 0.000 [-0.035, +0.035]; S+P3 - S -0.023 [-0.062, +0.015]; E+P3 - E -0.081 [-0.142, -0.023]
  (replicates cal-1 -0.098). The good-instruction parent is quieter: 10/130 items discordant (7.7%) vs 15.3% for the scaffold.
  Decision rule replay: accepts S, rejects the duplicate and all placebos; on cal-1 it ALSO accepts placebo control:2
  (+0.036, LB +0.011) on the empty scaffold (FD/D1/result.json:7).
- F38 [V] Fresh-batch construction (d1v2_pilot.py:85-94): `m, setting = manifest.load(MANIFEST)`; pool = setting.pools[BENCH]
  asserted 600 items all part in ("train","val"); used = data.training_items(pool, BENCH, DATA_SEED) (200) and
  reg = data.regression_items(pool, BENCH, DATA_SEED) (60) are excluded; order = data.ranked(fresh, DATA_SEED, TAG) with
  TAG = "d1v2-fresh:searchqa"; first N. The 130 drawn were 92 historical-train + 38 historical-val (FD/D1/report.md:448-449).
- F39 [V] Interleaved multi-arm round machinery reused from the frozen v3 snapshot (d1v2_pilot.py:29-39, 111-144):
  `Budget(out/"shared"/"ledger").declare({scope: cap})`; `Slots(out/"shared"/"slots", name, count)` per SLOTS;
  `dataclasses.replace(setting, root=out, shared=..., budget=..., slots=..., workers=...)`; `tasks = step.pool_tasks(setting,
  [BENCH])`; `schedule = {arm: [[item, runs] for item in items] for arm in arms}`; `solve = solver_endpoint(setting, SOLVER,
  SCOPES)`; `cells = step.run_round(setting, attempt, solve, unit, arms, schedule, tasks, tag="d1v2pilot")`;
  `step.guard(cells, ["E","S"], unit)`; `step.table_of(cells)`; `step.shared_unanswered(cells, items)`; wrapped in
  `run_unit(unit_root, run=..., identity=..., work=work)` with `except Pause`. FORBIDDEN output roots: the v3 run, the cal-1 run
  and /data/skillopt-work (line 42, asserted line 82). Repo signature: `def run_round(setting, attempt, endpoint, unit, arms,
  schedule, tasks, *, tag)` -- arms = {arm: Skill TEXT}; all (arm, item, run) jobs are put in one seeded order
  `_order(list(range(len(jobs))), tag + ":" + unit)` and run by `run_cells(..., workers=setting.workers)`; returns
  {(arm, item): [record per run]} (skillopt/coevo5/step.py:105-121). `guard` pauses when a parent/control arm has
  > MAX_UNKNOWN_SHARE infrastructure-unknown cells (step.py:150-157). `ranked(items, seed, tag)` = sha256 of
  json([seed, tag, task_id]) order (skillopt/coevo5/data.py:173-176).
- F40 [V] Power facts: same-text paired SD 0.326 / 0.222 / 0.144 at k = 1/2/4 runs; every text change incl. placebos adds
  between-item spread tau 0.12-0.28 "More items, not more runs, buy power"; items for 80% power at k=2: delta 0.05 ->
  213-274, 0.03 -> 487-733, 0.02 -> 1,016-1,637; smallest certifiable effect per pool: SearchQA 0.042 (300 x 2), LiveMath
  0.056 (233 x 2), OfficeQA 0.103 (37 x 4), SpreadsheetBench 0.122 (46 x 2), ALFWorld 0.153 (29 x 2); drift: same scaffold same
  items 0.743 on 10/19 vs 0.683 on 10/20 (-0.060 [-0.098, -0.021]) (FD/D1/result.json:7).
- F41 [V] D1 decision rule (design, unbuilt): accept iff one-sided 95% percentile item-bootstrap LB(mean d) > 0 and mean d >=
  0.02; parent duplicate + one length-matched placebo arm in the chain's first round; parent cells never reused across rounds;
  acceptance batch returns to the pool (usage +1), at most 3 steps per stage reuse one batch; "No model role ever sees B_a
  outcomes; at most the accept/reject bit" (FD/D1/result.json:8). Five-stage cost: v3 measured E 13.97M / I 60.22M; D1 two-arm
  12.00M / 34.13M; with duplicate+placebo in each stage's first round 19.85M / 58.75M; ~1.4 h wall for a 1,200-cell SearchQA
  round (FD/D1/result.json:17).

### 2.D9 Headroom over the task card; and where the JSON-answer scoring defect is actually documented
Sources: FD/D9/result.json (20; no report.md), FD/D9/critic-result.json (8); FD/D5/critic-result.json:4; FD/E7/result.json:8.
- F42 [V] D9 evidence section D (cal-1, 200 SearchQA items x 11 texts x 4 runs): totals ids-full (TC) 154.5, seed-only 153.5,
  placebo control:2 143.0, parent:B 137.25, seed-rule 136.5, control:4 136.25, parent:A 135.75, cand 130.5, seed-rule3 129.75,
  control:1 128.75, control:3 116.25; "No text beats the TC"; 25/200 items fail under every text on every run; cross-fitted
  per-item best of 11 texts +2.75 pts [+0.6, +5.5] (FD/D9/result.json:7). Section E: learned v3 rules minus parent on focal
  panels: on TC SearchQA +0.000/+0.004/+0.015, LiveMath -0.022, SpreadsheetBench -0.044/+0.027, ALFWorld -0.140 [-0.254,
  -0.035]; on scaffold only SearchQA s1-r2 +0.055 [+0.018, +0.094] excludes 0 (FD/D9/result.json:7). NOTE: sections D/E of D9 are
  NOT about JSON scoring -- the task brief's "JSON-answer scoring defect, evidence D/E" maps to D5's critic and E7 (next fact).
- F43 [V] JSON-answer scoring defect: "replies wrapped as {\"answer\": ...} score 0 in every arm (0 passes out of 364). In 414
  of 424 JSON replies, the identical answer string also appears inside an <answer> tag on the same item, and in 324 of those
  414 the tagged version passed" (FD/D5/critic-result.json:4). E7: "Untagged replies are mostly JSON such as {\"answer\":
  \"Medina\"}. The registered fallback normalises this to \"answer medina\", which fails exact match"; pass rate when tagged
  0.714-0.776 for every arm (FD/E7/result.json:8). Rescoring JSON as answers: cand -2.6 -> +6.75 [3.0, 10.6], recipe placebo
  -9.8 -> -0.25 (docs/handoff/feasibility-exploration-20261021-cn.md:108). Overnight report: fixing the scorer is "the first
  zero-cost step" (docs/handoff/overnight-report-20261021.md:50).
- F44 [V] D9 pilot (60 SearchQA training items the TC fails, 55 valid hints; 1,292,101 tokens): TC baseline 0.254; TC + oracle
  hint 0.936; oracle hint alone without question 0.891 ("49/55 hints reveal the answer by themselves"); mechanical length hint
  ("the answer has N words") 0.633, +0.386 [+0.264, +0.509], 29 up / 1 down (FD/D9/result.json:11,13). Critic: ~3/4 of the 54
  TC failures are surface-form differences (titles, plurals, accents, hyphens, optional parentheses); true content errors ~6
  points; no "TC + rule" text was among the 11 compared (FD/D9/critic-result.json:8). LiveMath meta option in 129/283 training
  items, the key in all 129; "pick it whenever present" estimated 76% vs TC 33% (FD/D9/result.json:7 section G).

### 2.D11 Reporting standard / occasion audit (zero model calls)
Sources: FD/D11/result.json (20; report.md refused, line 20), FD/D11/critic-result.json (8).
- F45 [V] cal-1 interleaving facts (FD/D11/result.json:7 section A, C): "200 SearchQA training items x 4 runs x 11 arms, all
  interleaved 10-20 16:07-19:52"; 8,800/8,800 cells have verdicts, 15 unknown runs, 8 truncated; same-text single-run
  disagreement parent:A 0.119, parent:B 0.104, ids-full 0.049 (ICC 0.86), placebos 0.074-0.161, cand 0.157; requests are
  byte-identical (9,707 first sends in 1,213 recurring (text, item) pairs, 0 pairs with >1 request SHA-256); "regimes alternate
  in time" (terse share per 15-min bin 5-96%), cause UNKNOWN; same text same 60 OfficeQA items in different windows +22.5
  [+11.5, +33.5] and +24.2 [+12.6, +35.7] points.
- F46 [V] Reusable code (Mac scratchpad, not repo): /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/
  e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D11/scripts/d11stats.py (+ test_d11stats.py "42/42 pass"),
  scripts2/stage_table.py ("the template"), cells_to_long.py, request_identity.py, serving_modes.py, mode_timeline.py
  (FD/D11/result.json:20). Critic kept feasibility high but: "task card halves rerun noise" holds in one window only; detectable
  effect per bench ~5-13 points with co-scheduling and multiplicity, not 3.5-10; each table needs three versions re-run
  co-scheduled, ~2-3x test cost (FD/D11/critic-result.json:8).

### 2.D13 Proposal quality (49 v3 proposals) and a per-code conditional proposer prompt
Sources: FD/D13/result.json (19), FD/D13/critic-result.json (8), FD/D13/report.md (293, not read in full).
- F47 [V] Pilot: GLM-5.3 (temperature 0, max_tokens 16384, v3 role settings), E-ds s1 SearchQA proposal half, 27 GLM calls,
  175,147 tokens; 7 final rules all conditional with a default; 5/7 within limits; 0/7 leakage findings; best rule applies to
  14/97 check-half items, D1 recall 5/5, 3/72 always-correct items exposed; NO solver run, so no score claim
  (FD/D13/result.json:12-13). Critic: the "best rule" executed literally fixes 2 and breaks 3; only 3 of 10 "opposite-direction"
  error pairs are truly opposite; three field caps sum to 641 chars, cannot guarantee 600; pilot used the empty scaffold, not
  the good instruction (FD/D13/critic-result.json:8). Overnight report: 21 of 49 v3 proposals died before formal testing,
  mostly of format/process defects; reviewers judged only 7 genuinely new (docs/handoff/overnight-report-20261021.md:63).

### 2.D8 Statistical acceptance protocol (exact pooled test, Holm, futility, NI margins)
Sources: FD/D8/result.json (19), FD/D8/critic-result.json (8); docs/handoff/feasibility-exploration-20261021-cn.md:70-76.
- F48 [V] Pilot: 2,000/2,000 cells on the same 200 SearchQA training items, 0 unknown, 4 truncated, 333 cells with HTTP 429
  resends, 2,932,691 tokens; a "six-answer spike" (gold answers of 6 items written into the rule) recovered its targets 22/24 vs
  8/24 but raised the 194 non-targets +5.8 pt [+2.0, +9.7] (+16.5 on 68 previously failing items) => not a known-effect control;
  the task-card seed reproduced across sessions (+9.50 vs +8.25 pt) and becomes the standing positive control; session drift
  -1.87 pt (se 1.04); split-half null: registered 1-item C1 false-passes 13.6-17.3%, exact test 0.5-1.8% (FD/D8/result.json:13).
  Proposed NI margins SearchQA/OfficeQA/LiveMath/SpreadsheetBench/ALFWorld 6/10/9/15/25 points
  (docs/handoff/feasibility-exploration-20261021-cn.md:76). Critic: the 14-17% comes from a 2-run simplification; full v3 gate
  false-pass ~0.5%; the seed-toggle control is nearly undetectable on the I chain (~0.1% at 40 items) because items are drawn
  only from parent failures; a whole-version "<= 3 point drop" check needs more items than the pool (FD/D8/critic-result.json:8).

### 2.E1 Verifier-side co-evolution (model-written checks; first run of forward-item machinery); "+13 generated vs 0 real"
Sources: FD/E1/result.json (21), FD/E1/critic-result.json (8), FD/E1/report.md (601, not read in full);
docs/results-and-lessons.md:197 (10/15 17:37 entry).
- F49 [V] Pilot 2: 10 executable reply checks written by GLM-5.3 per seed from training failures, 3 seeds per bench; held-out
  balanced accuracy SearchQA 0.487-0.539, OfficeQA 0.474-0.548 (frozen library 0.512-0.653; v3 text judge 0.546-0.842); 0 of 6
  revisions accepted: "Only form checks transfer to held-out items; content failures stay invisible without the reference"
  (FD/E1/result.json:12). Pilots 3/3b: the protocol's Wikipedia client lost 57 of 69 searches to HTTP 429; with a paced client
  19 of 30 items kept; 23 items solved by S+/S- x 2 runs: 20 saturated, 1 dead, 2 mixed; content discrimination 0 of 23;
  real OfficeQA under the same pair 45 of 70 dead, 3 of 70 fully separating; cost 859,911 tokens (FD/E1/result.json:12-14).
- F50 [V] The "+13 generated vs 0 real" fact (cited by the E1 critic, FD/E1/critic-result.json:4, from
  docs/results-and-lessons.md:197): GLM-5.3, OfficeQA generated 124 items: empty 0.484, zero-shot instruction 0.730, learned
  candidates oq_s1 0.859 / oq_s2 0.847 (candidate - instruction 30 better / 6 worse, p=0.0001, ~+13 pts); OfficeQA real 74 items:
  empty 0.412, instruction 0.601, oq_s1 0.595, oq_s2 0.622 (11 vs 12 and 9 vs 9, p=1.0). Ledger reading: "以生成题为门/迁移测量有
  系统性偏差" (generated items as a gate / transfer measure are systematically biased). deepseek-v4-flash: oq_s2 vs bzero 19/4 on
  generated items (p=0.0026), not measurable on real (FD/E1/critic-result.json:4). Critic corrected feasibility: low.

### 2.E4 / E9 Negative transfer = answer-format conflict
Sources: FD/E4/result.json (20; no report.md), FD/E4/critic-result.json (8); FD/E9/result.json (20), FD/E9/critic-result.json (8),
FD/E9/report.md (562, not read in full); docs/handoff/feasibility-exploration-20261021-cn.md:111-127.
- F51 [V] E4 ran 1,222 of 1,650 planned cells (cap hit 02:07:21), 0 unknown, 14 truncations, 3,676,169 tokens; 3 QA targets
  (SearchQA, OfficeQA, LiveMath) x 5 task cards, 30-41 items per target: H1 registered-similar minus dissimilar +0.1 [-5.6, +5.5];
  answer-channel conflicts hurt on OfficeQA only: ALFWorld card -26.7, SpreadsheetBench card -20.0; same-text cell estimates of
  the two runs correlate -0.50; identical requests within 1 s return reformatted untagged answers (FD/E4/result.json:14).
  Critic: the "+7 generic QA-card gain" is almost all artefact -- SearchQA's gain comes from 7 items where the empty scaffold
  omitted the answer tag; 42-84% of LiveMath gains come from the always-correct meta option (FD/E4/critic-result.json:8).
  Data on dl: /data/feasibility/E4/run-v2/ (cells/, plan.json, pre-registered analysis_plan.json, results.json)
  (FD/E4/result.json:20).
- F52 [V] E9 ran 1,124 cells, 0 unknown, 2,867,869 tokens: 69 generated OfficeQA-style items x 2 runs vs the real 74-item OfficeQA
  training pool x 1 run, same window, 6 texts; generated items saturated (empty scaffold 0.891; 61/69 pass both runs); effects
  keep sign 3/3 but shrink to 0.23-0.54 of the real effect; the generated panel MISSES the real -9.5 harm of the LiveMath seed
  (UB +1.78) while the real pool vetoes it (UB -0.98); it does catch the format-breaking ALFWorld-seed text (-33.3)
  (FD/E9/result.json:13). Mechanism: these texts make the model give short answers on document questions, answer-only replies
  rise from 23% to ~60% (docs/handoff/feasibility-exploration-20261021-cn.md:125). LiveMath seed -> OfficeQA -9.46 here and
  -8.11 in E2's window (FD/E9/result.json:13). Critic: the recommended veto check uses up OfficeQA, the only benchmark similar to
  SearchQA (FD/E9/critic-result.json:8).

### 2.E10 Co-evolution as a game; truth anchors (literature) + generated-item pilot
Sources: FD/E10/result.json (21), FD/E10/critic-result.json (8), FD/E10/report.md (509, not read in full).
- F53 [V] Literature (cited, FD/E10/result.json:8,20): R-Zero pseudo-label accuracy 79.0 -> 69.0 -> 63.0% over 3 iterations,
  collapse after 1-3 iterations; Absolute Zero learnability reward + executor checks; SPIRAL thinking collapse and fixed-opponent
  exploitation (0% -> 62.5%); AutoBencher 5% human-rated label error; POET minimal criterion 50 <= score <= 300; Dynabench
  "cyclical progress, keep old rounds"; Substitution of the Fittest / Hall of Fame. Overnight summary: all need a truth anchor
  neither side can change (docs/handoff/overnight-report-20261021.md:66).
- F54 [V] Pilot: 102 generated SearchQA items (batches B0 30; F1, A1, F2, A2 18 each) x 3 cal-1 arms x 2 runs = 612 cells,
  0 unknown, 1,969,174 tokens (GLM 539,873 + deepseek 1,305,202 in the ledger); on 78 items valid by both judges 0 content
  failures in 468 cells; all 93 content failures on the 24 non-valid items; the difficulty-only reviser invented scorer
  exploitation (answers "never" verbatim) and the GLM reviewer accepted 26/27; panel-vs-full-data Kendall tau 0.714 (30 x 2) ..
  0.864 (200 x 2) (FD/E10/result.json:8,12). Critic: part of the "0 content failures" was re-judged after seeing outcomes;
  OfficeQA has only 74 training items (246 total, 172 test), so the proposed 150+150+200 design is impossible
  (FD/E10/critic-result.json:8).

### 2.D10 Literature boundary (paper positioning)
Sources: FD/D10/result.json (20), FD/D10/critic-result.json (8), FD/D10/report.md (786, not read).
- F55 [V] D10 references (FD/D10/result.json:19): optimizers SkillOpt 2605.23904 v2, GEPA, MIPRO, OPRO, ProTeGi, TextGrad,
  PromptAgent, Promptbreeder; memory agents ACE, AWM, ExpeL, Dynamic Cheatsheet, Reflexion, **Voyager (TMLR 2024)**; skill-learning
  evaluations Zhao et al. 2610.22984, SkillsBench, Liu et al. 2608.02636, SkillBoost, MAGE, RLMOpt, p1, ContinualSkillBench,
  Evo-Memory, StreamBench, "Do Self-Evolving Agents Forget?"; measurement precedents. Executable-skill papers ASI 2504.06821,
  SkillWeaver 2504.07079, AdaPlanner 2305.16653, StateAct 2410.02810 were checked by D3 at abstract level, not by D10
  (FD/D3/result.json:19). [I] design-v0's statement that D10 "did not check the executable-skill-library branch" is roughly
  right for depth (D10 lists Voyager as a memory agent; nobody checked ASI/SkillWeaver beyond abstracts).
- F56 [V] D10 pilot (2,578,134 tokens, 1,160 cells, training items only): SkillOpt's released GPT-5.5 Skills on deepseek-v4-flash:
  SearchQA released - task card -9.05 [-13.45, -4.92], deficit is answer-tag non-compliance (untagged 66/399 vs 4/199), lenient
  -1.76; LiveMath meta items +27.8 [+15.6, +40.0] that vanish without the two meta bullets (+2.2) => construction shortcut
  (FD/D10/result.json:11). Critic: the confirmatory audit would use the project's only held-out test reading; critic's own 80k-token
  probe supports the shortcut reading (FD/D10/critic-result.json:8).

### 2.SQF scripts/make_searchqa_fresh_sample.py and data/searchqa_fresh_20261012
Sources: scripts/make_searchqa_fresh_sample.py (145, read in full); data/searchqa_fresh_20261012/sample_manifest.json (read for
counts/seed only; NO items.json opened -- blocks C/D are sealed hold-out material); docs/handoff/active-evidence-learn-from-b-design-20261012.md:20-30,193,248; docs/current-workflow.md:50; docs/handoff/direction-recommendation-20261021.md:91,152,169.
- F57 [V] Script: `build(dataset, native_dir, output, *, count, blocks, seed, dataset_name, revision)` -> (record, chosen)
  (line 39); SOURCE_SPLIT = "validation" (28); excludes every native train/val/test id and every normalized-duplicate question
  (`normalized(q) = re.sub(r"\W+", " ", q.lower()).strip()`, lines 31-32, 50-81); deterministic order = keys sorted then
  `random.Random(seed).shuffle(order)` (61-62); equal blocks block_a.. (93-99); refuses output inside the repo unless under data/
  and refuses an existing dir (42-47); defaults --dataset lucadiliello/searchqa, --revision c1a979068ba118d85467179b704031d113d689cc,
  --count 4000, --blocks 4, --seed searchqa-fresh-20261012 (114-121); offline HF switches (126-127); prints counts and length
  stats only (138-141).
- F58 [V] Manifest: version searchqa-fresh-sample-v1, source_rows 16,980, count 4000, native_items_excluded 2000, skipped
  {native_id 447, duplicate_question 0, invalid 0}, blocks block_a/b/c/d 1000 items each, sha256 prefixes cc57de4d002128e9 /
  0246bf8d72ce6350 / 9e068b7c34af1eaf / a0a4edcda9ffad27. Roles: A = 10/12 study (A1/A2 halves; later re-cut in file order as
  A01..A10 and Q01..Q40 -- the same 1,000 tasks), B reserved for a follow-up, C and D "stay on the operator's machine, unread,
  for the one-time hold-out read" (docs/handoff/active-evidence-learn-from-b-design-20261012.md:26-30,193,248). The directory
  also holds block_a1, a2, a01-a10, q01-q40, r01-r10, s01-s30 (ls; created 10/12 13:05 - 10/13 11:17; block_s* are listed in
  docs/handoff/prompt-chain-confirmation-blocks-20261013.json). "现有脚本不能排除旧块" -- the script cannot exclude the old blocks
  when drawing again (docs/handoff/direction-recommendation-20261021.md:169). C+D (2,000 items) proposed as the ~1.5-1.9 point
  evaluation target (same file:152).

### 2.CAL cal-1 registration: interleaving, placebos, tokens per cell
Sources: docs/handoff/cal1-registration-20261020.md (152 lines; read 19-48, 91-135, 144).
- F59 [V] Interleaving: comparison unit `cal1/searchqa` = 11 arms x 200 items x 4 runs = 8,800 cells; "All cells of a unit are
  shuffled by the protocol's seeded hash order and dispatched through the same recorder, scorer and decision table as v3
  (16 workers, 12 deepseek slots, temperature 0, max_tokens 32768). Each cell is keyed by (unit, arm, item, run) and sends its
  own request; no response cache exists." (lines 25-28). Items = data.training_items(pool, "searchqa", DATA_SEED=20261017)
  (21-22). Pre-round parent:A alone 2 runs (400 cells) froze eligibility before the comparison round (23-24).
- F60 [V] Arms (36-47): parent:A (Skill(scaffold=True)), parent:B (identical text, separate arm: same-round noise floor),
  ids-full (all five task-card seeds), seed-only, seed-rule (108 chars), seed-rule3 (~420 chars), cand (frozen E-ds s1-r1),
  control:1..4 = scaffold + PLACEBOS_SCREEN[0..3] via `text_with` ("the registered irrelevant-text controls"); frozen arm
  bytes/sha e.g. control:3 779 B c245e31e... (lines 91-105). Placebo results: control:1 -0.035, control:2 +0.036 [+0.006,
  +0.066] (39/16, p 0.003), control:3 -0.098 [-0.136, -0.059], control:4 +0.003 (line 144).
- F61 [V] Tokens per cell: smoke estimate 2,251 (most arms near 1,350) (33-34); attempt 1 paused at the 25,000,000 cap after
  7,205 of 8,800 cells, "Real cost ~3,400 tokens per cell, twice the smoke estimate" (113-117); resume of 1,611 cells cost
  2,613,063 = 1,622 per cell; final ledger 27,481,897 (cap raised to 35,000,000 as a recorded deviation) (119-131). Unknown
  handling: unknown = fail for a judged arm's L, = pass for parent/controls' H; guard pauses above 10% unknown in a parent or
  control arm (29-31).

## 1-final. Files read (line counts)
Repo: docs/handoff/feasibility-20261021/{D1,D3,D6,D8,D9,D10,D11,D13,E1,E4,E9,E10}/result.json (19-21 lines each, long JSON
lines) and their critic-result.json (8 lines each; D1 has none); FD/D5/critic-result.json and FD/E7/result.json (grep only);
FD/D14/report.md (310, full); FD/D1/report.md (526, partial); docs/handoff/feasibility-exploration-20261021-cn.md (172, full);
docs/handoff/overnight-report-20261021.md (141, full); docs/handoff/cal1-registration-20261020.md (152, partial);
scripts/make_searchqa_fresh_sample.py (145, full); data/searchqa_fresh_20261012/sample_manifest.json (counts only);
skillopt/coevo5/step.py:100-160; skillopt/coevo5/data.py:170-200; grep of coevo5 protocol/skill/units/budget/calls/manifest;
docs/results-and-lessons.md:195-197; docs/handoff/active-evidence-learn-from-b-design-20261012.md:20-32.
dl: /data/feasibility/ listing + du; D3/r3/* scripts listed in 2.D3 (906 lines total), summaries; D14 out/*.json summaries;
D6/pilot/sandbox_runner.py (56), common.py (187, partial), v2/gen_livemath2.py (368, partial); D1/v2/d1v2_pilot.py (159).
NOT read: report.md of D6/D8/D10/D13/E1/E9/E10 beyond result/critic fields; dl code of E1/E4/E9/E10/D8/D9/D13/D14 (names only).

## 3. Interfaces an implementer would call or must replace
- ALFWorld environment (used by D3/D14 pilots, frozen snapshot): `backends._new_alfworld(public, RUNTIME)` with
  public = {"game_file": path} and RUNTIME = manifest["runtime"]["alfworld"]; `env.reset()` -> (observations, _, infos);
  `env.step([action])` -> (observations, _, _, dones, infos); `infos[0]["admissible_commands"]`, `infos[0]["won"]`;
  `env.close()` (dl:/data/feasibility/D3/r3/pilot_alf_glm.py:213-255). Frozen loop view = initial_observation, observation,
  admissible_commands, recent_history[-5:] (backends.py:744-746 per FD/D3/critic-result.json:5). Route B's "shell" must REPLACE
  `_solve_alfworld`; D3's `tracker_episode(public, call, record, use_tracker=True)` is the only working template; returns
  {"status": "available", "output": {"won": bool, "steps": int}} or {"status": "fail"|"unknown", "reason": str}.
- Tracker program contract (D3): `class Tracker: __init__(self, initial_observation: str)`; `update(self, action: str,
  observation: str) -> None` (must never raise; GLM version wraps in try/except); `view(self) -> dict` with exactly keys
  reached (dict), not_reached_yet (list), carrying (list), rejected_actions_so_far (int), JSON <= 1500 chars.
- Replay verifier: `python -I /input/lt_replay.py <candidate.py> <reference.py> <traces.json>` -> one JSON line
  {"counts": {...}, "examples": [...]} (or {"load_error": ...}); needs a reference program for agreement counts; trace
  schema {"chain","cell","item","token","initial","steps":[[action, post_observation],...]}.
- Format guardrail for ALFWorld (D3): `parse(text, admissible)` -> (action, how in tag|whole|canonical|earliest_admissible|
  unchanged); `canonical(action, admissible)` -> (action, changed: bool). D14 calls it "about 30 lines".
- Model client: `scripts.weak_solver_probe.Client(<env dir or None>, <model>, proxy=GATEWAY, max_tokens=..., read_timeout=...,
  [route="pjlab_token", route_env="/root/.config/weak-solver/pjlab-token.env"])`, `.call(system, user)` -> receipt dict with
  ok, status, error_type (e.g. finish_length, http_*), usage {prompt_tokens, completion_tokens, total_tokens}, response
  [V usage in pilot_alf_glm.py:79-104, lt_induce.py:8-14, common.py:33-60; full signature not read, I].
- Executable reference sandbox (D6): `python -I sandbox_runner.py < program.py` -> {"ok": true, "srepr", "str", "type"} |
  {"ok": false, "error"}; program must assign RESULT. `run_program_check(ds, ledger, item)` -> {"status": ran|call_failed|
  no_code|code_error|result_parse, "agree": bool, ...}. `build(raw, form_wanted, k, position, rng)` -> (drop|None, item).
- Interleaved acceptance round (D1 template): `step.run_round(setting, attempt, endpoint, unit, arms, schedule, tasks, *, tag)`
  with arms = {arm: Skill text} (skillopt/coevo5/step.py:105); `step.guard(cells, arms, unit)` raises Pause
  ("infrastructure_incomplete"); `step.table_of(cells)`; `step.shared_unanswered(cells, items)`; `run_unit(unit_root, *, run,
  identity, work)` (units.py:126); `solver_endpoint(setting, solver, charged)` (units.py:97); `data.ranked(items, seed, tag)`
  (data.py:173); `Budget(path).declare({scope: cap})`; `Slots(dir, name, count)`; `manifest.load(path, *, verify=True)`
  (manifest.py:116). Placebo arm = `Skill.text_with(Rule("control-k", PLACEBOS_SCREEN[k-1], bench))`.
- Must replace for programs: identity sites hashing only text -- cells.py:222, evaluation.py:356/366, step.py:825,
  chain.py:290 (FD/D3/result.json:8, confirmed FD/D3/critic-result.json:5); run_round's arms type (text only).
- Fresh sample: `build(dataset, native_dir, output, *, count, blocks, seed, dataset_name, revision)` (scripts/make_searchqa_fresh_sample.py:39).

## 4. Reusable unchanged vs must be generalized
Reusable (as code patterns, after copying into a new versioned module; none of it is in the repo):
- R1 D3 replay harness (lt_replay.py + the docker flags of FD/D3/result.json:12) as route B's "回放测试 / 零崩溃" gate: zero solver
  tokens, 2.8 s for 7,524 steps. R2 D3 trace extraction (lt_prepare.py:8-19) from v3 stage cells. R3 tracker_glm.py /
  tracker_ref.py as the first ALFWorld "状态记录" procedure and engineered reference. R4 `canonical`/`parse` as the fixed
  ALFWorld 格式护栏 for ALL arms. R5 D6 executable-reference + independent-program cross-check (52/52 keys, 4/4 bugs caught) for
  LiveMath-style 出题程序. R6 D1's multi-arm interleaved round (one seeded order over all arm x item x run cells) for step 6 验收
  with S', S, task-card-only and placebo arms. R7 D6 common.Ledger per-call token ledger. R8 make_searchqa_fresh_sample.py logic.
Must be generalized (and the baked-in assumption):
- G1 Tracker slot: EXACT four keys, ALFWorld observation regexes ("You arrive at", "On the X, you see"), 1,500-char cap --
  route B procedures need three hook kinds (rewrite context / deterministic compute / veto); veto (防打转) and compute hooks
  were never prototyped; D3's `alfworld.actuator` was proposed only.
- G2 pilot_alf_glm.py: pinned to the v3 snapshot path, asserts the E-ds scaffold digest cc516459810a, max_tokens 512 (vs frozen
  32,768), PAIRED 42 ids, TRACKER_SENTENCE text, in-process importlib of model-written code; and it is a re-implementation, not
  the registered backends path.
- G3 run_round: arms are Skill TEXT; route B arms are (text + procedure package + router); the cell id/identity must hash the
  package (see the four identity sites).
- G4 D6 LiveMath generator: forms and the 68:87 mirror are derived from LiveMath training labels (registration v6 2.2 conflict,
  F31); the 2-of-3 tiebreak lets GLM code + GLM stated value outvote the independent program (F27).
- G5 D6 sandbox_runner: host-process guard with RLIMITs and an import hook; exec/eval/compile kept; route B needs a container
  (D3's docker flags) for any code an "engineer" role writes.
- G6 fresh-sample script excludes only the native split; a new draw must also exclude blocks A-D (S39).

## 5. Gaps and risks for route B in this area
- K1 The only positive executable-skill result (26/42 vs 16/42) is confounded: extra behavioural sentence only in arm T; 41%
  of T steps rescued by the parser vs 13% in C; the tracker HURT in the frozen loop; comparison arms ran 1.5-5 h earlier (no
  co-scheduling); one run; no placebo program; empty scaffold only (F6-F9). design-v0 cites "228 局 7,524 步零错误" correctly
  but not these confounds.
- K2 "Induced by GLM" was transcription of a dictated spec (exact keys + v3 statistics + excerpts), one sample (F8). Route B's
  工程师 claim needs an undictated slot, >= 5 samples, success rate reported, and a statement of who writes the property checks.
- K3 D14's "55/57 open surfaces" comes from walkthrough METADATA of training games (never public to the solver); a procedure
  or detector built from it is in-sample; R1/R2 were written by the explorer with that hindsight (F19). The D14 text-rule pilot
  shows 8/9 vs 3/9 only when the action interface is guarded (F20), on 8-12 items, one run.
- K4 Generated items: saturated or too easy in every measured style (OfficeQA-style 14/14, E9 0.891, E1 0/23 content
  separation, D6 SearchQA-style 21/23 with context); the "20%-80% parent pass" band was never achieved for any style (D6 critic
  missing); predictive validity failed before (+13 generated vs 0 real, F50). Route B's 预测效度 gate has no passing precedent.
- K5 No ALFWorld environment generator, no SpreadsheetBench synthetic-workbook generator, no OfficeQA perturb-and-recompute
  generator was ever run (D6 lists designs only, FD/D6/result.json:8; critic missing). OfficeQA has 74 training items, ALFWorld 57.
- K6 Cost: ALFWorld resends the Skill every step (E-ds 807 vs I-ds 3,364 prompt tokens/step); a 1,500-char view adds roughly
  400 tokens/step [I]; tracker arm 1,225 tokens/call vs 873 (F2). cal-1 real cost ~3,400 tokens/cell at max_tokens 32,768 vs the
  2,251 estimate (F61); D1 1,531/cell (F35).
- K7 Scorer: JSON-wrapped answers score 0 (F43); format guardrails must be fixed per bench and identical across arms; E4/E9 show
  -9.5 to -33 point harms from answer-channel conflicts (F51-F52).
- K8 Serving-regime drift (terse/verbose regimes, 22-24 point swings on OfficeQA; identical requests within 1 s reformatted)
  => every comparison must be co-scheduled in one interleaved round (F45, F51).
- K9 Frozen-snapshot hygiene: pilots import /data/coevo5-20261019-v3-source-f without -B; .pyc files appeared in it (F34).
- K10 Literature: ASI / SkillWeaver / Voyager / AdaPlanner / StateAct only checked at abstract level by D3 (F55).
- K11 Evidence status: everything here is training-side feasibility evidence; none is an end-to-end route B run; D14 has no
  conclusion and no critic.

## 6. Open questions for the designer
- Q1 Was analyze_glm.py re-run on the final 42 episodes and stored? Only the critic's recomputation (26/42, p=0.0063) and
  summary.json exist; no stored analysis output was found in dl:/data/feasibility/D3/r3/.
- Q2 Which loop is route B's baseline: the frozen `_solve_alfworld` (verbatim actions, 32,768 cap) or a new protocol loop with
  the canonicaliser and a truncation policy for every arm? D3/D14 show the answer changes the sign of the tracker effect.
- Q3 May LiveMath-style generators use regularities learned from LiveMath training labels (meta option always key)? Owner
  decision per D6 critic (F31).
- Q4 Can ALFWorld "sample new environments in the simulator" use the ~2,435 ALFWorld train folders outside the 57-game pool
  (D6 critic notes 365 of 2,435 are pick_and_place_with_movable_recep)? Not verified; no prototype did it.
- Q5 New solver interface deepseek-v4.1-flash-1017: all prototypes used deepseek-v4-flash via route="pjlab_token"; whether the
  new interface shows the same wrapper-form action drift (C nonplain 29% in D14) is unknown.
- Q6 Roles of the fresh-sample sub-blocks r01-r10 and s01-s30 (re-cuts of which block?) -- only q/a re-cuts of block A are
  documented; I did not open any items to check.
- Q7 Who writes the replay property checks and detectors' acceptance thresholds in route B (D3 critic missing item 3)?
