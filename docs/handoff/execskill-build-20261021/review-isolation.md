# Review: test isolation and leakage (route B, protocol fivebench-execskill-v1)

Date: 2026-10-22. Lens: test isolation and leakage. Reviewer: adversarial code review, read-only.

## What I looked at

- **Code reviewed:** `dl:/data/execskill-dev`, which is git 010d453 plus the untracked route-B files. I read it through the SSHFS mirror at `/Users/dulin/remote/dl`.
- **Against:**
  - `docs/handoff/execskill-registration-v1-20261021.md` (§3.1, §3.4, §3.5, §4.2–4.4, §5.2–5.4, §7.1–7.2, §8.1, §10 S0)
  - `docs/handoff/execskill-implementation-plan-v1-20261021.md`
  - the frozen modules in `/Users/dulin/Documents/Paper/SkillOpt`
- **Modules read:** `exclusion`, `evaluation`, `cells`, `units`, `chain`, `trajectories`, `engineer`, `detectors`, `replay`, `research`, `supply`, `solver`, `precheck`, `judge`, `qualify`, `acceptance`, `donors`, `placebo`, `describer`, `generators/*`, `sandbox/client`, `policy`, `registry`, `readout`, `smoke`, `protocol`, `scripts/run_execskill.py`.
- **Tests run on dl** (`python -B -m pytest -q -p no:cacheprovider`): the `exclusion`, `evaluation`, `trajectories`, `research`, `engineer` and `placebo` test files. 43 passed.
- **Probes:** four zero-call probes on dl, run in `/tmp` through stdin. No file in the tree was edited. Outputs are in the appendix.
- **Rules kept:** no paid call, no test pool opened, no key or `.env` printed.

## Checked and found sound (as far as the code goes)

- **Sandbox mounts.** The sandbox mounts only `/runner` (the worker and `policy.json`) and an optional `/input`. Both are read-only. It runs with `--network=none`, a read-only root and only the registered environment variables. No ledger, consent file or `.env` is mounted (`sandbox/client.py:97-112`, `:351-358`).
- **Replay hides the token and judge.** Replay never passes a trajectory's `token`, judge or reference into the sandbox. Hooks get only views, notes, reports, events and their own state (`replay.py:335-400`). Negative tests and the fix claim use the token on the host side only.
- **Sealed test cells.** A sealed cell holds only hashes, tokens, flags and fault kinds. It holds no message, reason text or reply (`evaluation.py:189-214`). `_counts` holds no pass or fail counts.
- **Training trajectories.** The ALFWorld views and events in training trajectories carry no `infos.extra`, game file or expert plan (`solver.py:660-765`; T-SOLVER-8; mutation 12). `whitelisted` refuses the hidden keys.
- **SearchQA tail.** The tail builder writes nothing. It never keeps the content of blocks C and D (`del drawn`). It drops tail items that duplicate a block question (`supply.py:105-165`).
- **Write-once and versioned records:**
  - The consumption registry, research archive, trajectories, enable log and seals are write-once or append-only `protocol.record` lines, and they are verified on read.
  - The exclusion records hold counts and hashes only.
- **Exact-key consent checks.** `evaluation.consent` and `exclusion.exclusion_consent` check the exact key sets that §8.1 registers. Findings 13 and 14 cover the gaps.

## Findings

Summary: 3 BLOCKER, 9 MAJOR, 9 MINOR. Each finding gives its severity, where it is, why it matters and the fix.

### 1. BLOCKER — The role-isolation boundary is not implemented

**Where:**
- `skillopt/execskill/step.py` and `skillopt/execskill/examiner.py` do not exist, although the plan's §1 rows list them.
- `scripts/run_execskill.py:53-55` and `:148-166`: `ENTRY` names `step.run_unit_spec`, `evaluation.run_unit_spec` and `readout.report`, and none of them exists. `chain.run` and `chain.terminate` take `setting`, so `_delegated` refuses them.
- `tests/test_execskill_e2e.py` does not exist.

**Why:**
- Every visibility rule in the registration is enforced by whatever code builds the role inputs. That code would have to:
  - show the engineer run-slice trajectories only, never acceptance trajectories;
  - give references only for QA and table failures of this bench, never ALFWorld plans or paths;
  - give the examiner the write half only;
  - build the leakage corpora from run-slice references, plus the researcher's corpus;
  - build G_acc on the A\* public views after the engineer step;
  - create test access only inside the copied evaluation unit (§3.5, §4.2, §4.3, §5.3, §7.2, §8.1).
- That code does not exist.
- The modules that do exist take all of these as caller arguments and do not check where they came from (finding 5, probe 2).
- The CLI subcommands `run`, `step-unit`, `evaluate-unit`, `terminate` and `report` all raise `ConfigurationError`. So no chain step, acceptance round or test read can run, and none of the isolation claims has been exercised end to end. As built, they cannot be verified.

**Fix:**
- Make `step.py` and `examiner.py` the only builders of role payloads, with the provenance checks of findings 5, 6, 8 and 9.
- Add the `run_unit_spec` and `report` adapters.
- Add the e2e fixture-chain test. It must assert that the stored payloads hold no acceptance or test item id, no forbidden reference kind, no expert plan and no game path.
- Do not launch the pilot until this exists and passes.

### 2. BLOCKER — The ALFWorld test read cannot run, and the obvious fix would leave test observations on disk

**Where:**
- `evaluation.py:162-181`: `test_plan` calls `solver.routing_view` for every test item (line 169).
- `solver.py:159-167` and `:170-182`: on ALFWorld, `require(registered is not None, ...)` at line 180.
- `continual_eval/datasets.py:27-35`: a frozen ALFWorld task's public data is exactly `{"game_file"}`.

**Why:**
- On the first test game, `test_plan` raises "An ALFWorld item carries its registered routing view". It does this whether or not F has an ALFWorld procedure, so the ALFWorld unit always pauses as `configuration`.
- Routing views exist only for the 422 sliced training games, through `supply.prereset` (S0). The registration does not say how test games get one.
- Pre-resetting the test games the way `supply.prereset` does would write their initial observations and admissible commands into an items file. That file would sit outside `<attempt>/transient/`, outside the canary scan, and stay forever.

**Fix:**
- Register how test routing views are made: inside the evaluation unit, from the live first reset that the solver already hash-checks, kept only in memory or in the transient store, and covered by the scan.
- Add an ALFWorld test-read test whose test panel is frozen-shaped (public data `{game_file}` only).

### 3. BLOCKER — Every SpreadsheetBench test cell is scored `unknown`, and the obvious fix would keep the test answer workbooks

**Where:**
- `evaluation.py:239-240`: `EvaluationStore.scorer_dir` is `<attempt>/transient/scorer_artifacts/<position>`.
- `cells.py:265-276`: `_score` passes that directory to the scorer as `artifact_dir`.
- Frozen `continual_eval/sheet_numeric_adapter.py:89` calls `sheet_recalc_adapter.py:73-75`, which requires the directory's grandparent to be named `host_only`.

**Why:**
- Probe 1 on dl:
  - The frozen `_context` refuses this path with "Private evidence must use host-only scorer storage".
  - `backends.score` returns `{"status": "unknown", "reason": "native_scoring_input_error:ValueError"}`.
- The evaluation tests use a fake scorer, so the suite is green while the registered v7 scorer can never score a test cell. Because of `INFRA_UNKNOWN_MAX`, the SB unit would pause as `infrastructure_incomplete`.
- The naive repair, `<attempt>/host_only/scorer_artifacts/...`, would be worse:
  - The v7 scorer writes recalculation receipts that carry `output_base64` of the recalculated reference workbook (`sheet_recalc.py:579-593`). That is the test answer workbook.
  - These receipts would then survive the transient deletion.

**Fix:**
- Use `scorer_dir = <attempt>/transient/host_only/scorer_artifacts/<position>`. This passes the frozen guard and is still deleted.
- Add a test that calls the real `sheet_recalc_adapter._context` on `EvaluationStore.scorer_dir` and asserts that no receipt remains after `finish()`.

### 4. MAJOR — The two test-exclusion runs are not wired, not persisted, and do not stop on failure

**Where:**
- `exclusion.py:59-75` and `:97-115`: `disjoint` is returned at line 112 and never enforced.
- `scripts/run_execskill.py`: there is no `exclude-tests` subcommand (docstring at lines 6-29).
- `smoke.py:43-44` and `:125-129`: S0 has no exclusion row.
- `manifest.py` binds neither exclusion record.
- `tests/test_execskill_exclusion.py:110-111` asserts that an overlapping game only yields `disjoint is False`.

**Why:**
- §10 S0 registers: "ALFWorld 测试集全在 valid_unseen 且与题源不相交 | 通过，否则停" (all ALFWorld test games are in valid_unseen and share none with the supply; pass, otherwise stop).
- §8.1 says the exclusion code prints only counts and the exclusion hash.
- Nothing calls `exclude_tests` or `alfworld_test_identity`, and their records exist only in memory.
- `apply_exclusion` needs a record that no code writes.
- An overlap between test games and new games is recorded, not refused, so a contaminated supply can pass S0.

**Fix:**
- Add the `exclude-tests` CLI. Build `TestAccess` only there, behind `exclusion_consent(<root>/shared/exclusion-consent.json)`.
- Write both records once under `shared/` and print only counts and hashes.
- Raise when `disjoint` is false: stop and report.
- Bind both record hashes into the manifest, and make `write_supply` and `apply_exclusion` require them.
- Add an S0 row for them.

### 5. MAJOR — The engineer payload accepts acceptance trajectories and arbitrary references and "previous" data (verified)

**Where:**
- `engineer.py:148-168`: `Context` takes trajectories, references, `previous` and `detectors`, and shows them as given.
- `engineer.py:177-186`: `shown` filters only on bench, `arm_kind == "parent"` and token.
- `engineer.py:189-196`: `_shown_view` attaches `references[task_id]` without any check.
- `engineer.py:206-212` (`payload`).
- `engineer.py:394-403`: `_scope` replays every trajectory in the context.
- `engineer.py:461-479`: `fix` sends the engineer check details that come from those replays.

**Why:**
- Probe 2 showed three leaks into `payload()`:
  - A resealed trajectory from the acceptance unit `G/s1-searchqa/accept-r1` with `arm_kind` "parent" is shown.
  - A reference `{"expert_plan": [...], "gamefile": ...}` reaches the payload.
  - `previous={"acceptance_item_scores": {...}}` passes through verbatim.
- Acceptance-round S cells are also stamped `arm_kind` "parent" (`acceptance.py:68-69`), and `trajectories.load_run` loads any completed unit. So the natural caller code can leak the acceptance slice.
- §4.2 lists what the engineer is never given: expert routes and game paths, anything from the acceptance slice, other benches' references, and anything from the test set. It also says the previous step's acceptance result is reported only as "accepted / not accepted" plus fault and format statistics. The code enforces none of this.

**Fix:**
- In `Context.__post_init__`:
  - require every trajectory to belong to a run unit of this chain, with the unit kind recorded in the trajectory;
  - refuse references on ALFWorld, and for items that are not among this bench's run-slice failures;
  - require references to have the frozen answer shape;
  - check `previous` against the fixed schema `{decision: accepted|not_accepted, faults, format}`;
  - allow `detectors` to carry counts only.
- Add a test for each refusal.

### 6. MAJOR — `detectors.diagnosis` can show the examiner hold-half failure labels, and it uses full-episode categories

**Where:** `detectors.py:281-293` (`diagnosis` runs on whatever trajectories it is given; its docstring says "What the engineer and the examiner are shown"), `:297-320` (`split`) and `:331-339` (`seal_candidates`).

**Why:**
- §4.3: the examiner sees only the write half's masked trajectories and their right/wrong bits.
- §5.2: candidate detectors are sealed before the hold half is touched.
- `diagnosis` returns, for every failed cell id it is given, the categories that fired. Called on the whole run slice, it tells the examiner which hold-half cells failed, and how, before `seal_candidates` runs.
- It computes the categories on whole trajectories (for example ALFWorld's `step_budget_exhausted` over all 50 steps), not on the masked view that the residual uses.

**Fix:**
- Take the split record and use only `split["write"]`, and assert that no hold cell id appears.
- For the examiner, compute the categories on the masked view (`mechanical_masked`).
- Add a test.

### 7. MAJOR — The masked QA view does not hide the answer, so the examiner can read the reference of passed items

**Where:** `trajectories.py:198-212` and `:249-250`.
- `mask_answers` masks only answer tags, JSON "answer" values and SearchQA's last line.
- For the examiner, the view adds `passed`.

**Why:**
- Replies usually state the answer in the free text before the tag, for example "so the answer is X", "option C", or the computed number. When `passed` is true, that text is the reference answer.
- §4.3 says the examiner never sees reference answers, and FE-F2 says detector views hide answer content. For such replies, neither holds.
- No real trajectory exists yet, so how often this happens is unknown.

**Fix:**
- Mask every occurrence of the extracted final answer, normalized, across the whole reply; on LiveMath, also mask the chosen option's letter and text.
- Measure, on the S2 trajectories, the share of passed masked replies that still contain the reference, and register a limit. Otherwise drop the `passed` bit for QA replies.

### 8. MAJOR — The researcher's pre-dispatch leakage screen skips parameter names (verified)

**Where:**
- `research.py:839-842`: `parameter_choice` screens `[question, topic]` but passes `names` on as `subject`.
- `research.py:810-824` (`_send`).
- `research.py:677-690`: `subject` goes into `base`, which every researcher call shows.
- Names have no bound on count or length when they come in.

**Why:**
- Probe 3: an item text that is on its own a `shared_8gram` hit was passed as a parameter name. The request was dispatched (2 researcher calls) and the text reached the researcher.
- §4.3 and §7.2: the researcher never sees a bench item, and every request is screened before dispatch.

**Fix:**
- Screen every string the researcher will see: the question, topic, rule and each name.
- Bound names to `MAX_PARAMETERS` × `MAX_PARAMETER_CHARS` when they come in.
- Add the test.

### 9. MAJOR — The sandbox input mount is unchecked, and a procedure can read any workbook in it

**Where:**
- `sandbox/client.py:276-287`: `start` accepts any absolute directory.
- `replay.py:408-421` and `engineer.py:168`: `inputs_dirs` comes from the caller.
- `acceptance.py:89-97`: `workers(package, item)` comes from the caller.
- `policy.py:71-75` and `:93-99`: `pandas` can be imported, and `ExcelFile` is not forbidden.

**Why:**
- In the frozen SpreadsheetBench layout, `*_answer.xlsx` and `*_golden.xlsx` sit next to `*_input.xlsx` in the same directory (`datasets.import_spreadsheetbench`).
- Only `solver._inputs_dir` (`solver.py:583-589`) builds a clean directory. Replay and acceptance mount whatever directory the missing step code passes, and the natural choice is the item's own folder.
- Probe 4: `pd.ExcelFile("/input/1_1_answer.xlsx").parse(0)` passes `policy.check` with 0 violations. A procedure could therefore read reference workbooks during C6/C7 replays or acceptance routing.

**Fix:**
- `Worker.start` should require that `inputs_dir` holds exactly one regular file, `input.xlsx`.
- Build every `/input` directory through `solver._inputs_dir`.
- Forbid `ExcelFile` and other constructors that read files.
- Add tests.

### 10. MAJOR — The canary scan misses most of the unit's artifacts, never runs on paused attempts, and the registered canaries have no creator

**Where:**
- `evaluation.py`:
  - `:304-322`: the scan covers `attempt_dir` only.
  - `:480-491`: the pause and exception paths do not scan.
  - `:494-497`: the infrastructure pause comes before the scan.
  - `:338-342` and `:410-416`: `_diagnose` prints full tracebacks into the file of `contained()`.
  - `:114-137`: the test-side SB qualification is kept under `shared/test/...`.
  - `:262-277`: no code writes `shared/test-canaries.json`.
- `chain.py:113-127`: the child's stdout and stderr go to `shared/host_only/diagnostics/child-*.log`.
- `qualify.py:54-66`: scores and `host_only/scorer_artifacts`, whose recalculation receipts hold test answer workbooks.

**Why:**
- §8.1 requires a scan of every artifact of the unit before sealing.
- These artifacts sit outside the attempt directory and are never scanned:
  - the diagnostics logs (the frozen code itself says a warning may quote test content);
  - the chain's child logs;
  - the test-panel registry `shared/test/<bench>.json`, which holds test ids;
  - the test-side SB qualification, which keeps the recalculated test answer workbooks permanently.
- Paused attempts are never scanned.
- No code selects and writes the registered canaries. Making them requires reading the test sets with a `TestAccess` outside the evaluation unit, which §3.5 does not provide for.

**Fix:**
- On every exit (complete, pause, exception), scan the unit root, its diagnostics and child logs, and `shared/test`.
- Either make the test-side qualification transient (deleted after the last read) or register it as an explicit exception in §8.1.
- Implement canary-making inside a consented unit, with its selection rule registered and its record hash bound into the manifest.

### 11. MAJOR — A transient store left by a crash or SIGKILL is never deleted or scanned

**Where:**
- `evaluation.py:217-258`: `finish()` runs only inside the process.
- `evaluation.py:480-491`.
- Recovery starts a new attempt (`_next_attempt`) and leaves the old one as it is.

**Why:**
- If the evaluation child is killed (OOM kill, reboot, SIGKILL), `<attempt>/transient/` stays behind with full test predictions, receipts and requests, including the test question text.
- Recovery starts attempt N+1, and nothing removes or records the old transient store.
- The pause path deletes the store but writes no `transient-deleted.json`.

**Fix:**
- Before any new attempt starts, and in `recover`:
  - delete every earlier attempt's `transient/` with a deletion manifest;
  - scan the old attempt;
  - record both.
- Write the deletion record on the pause path too.

### 12. MAJOR — Unseal accepts a self-declared addendum and can unseal one chain while the other is still running

**Where:**
- `evaluation.py:540-548`: `_addendum` checks only the format of `{sha256, written_at}`.
- `evaluation.py:555-559`: `_case` trusts `written_at`.
- `evaluation.py:529-537`: there is one continuation file per root.
- `evaluation.py:605-630`: `unseal` requires only this chain to have ended.

**Why:**
- §8.1 requires the complete formal-chain addendum to be written and hash-sealed before the unseal.
- The code never checks that `sha256` belongs to an existing document, or when that document was written. Any well-formed JSON with a past timestamp earns the "confirmatory" label.
- Chain G can be unsealed while chain D is still running. The owner would then know G's test scores while still making D's recover and terminate decisions, and the single continuation decision may come before D's learning report.

**Fix:**
- Read the addendum document from a fixed path and compare its sha256 with the record.
- Take the write time from a write-once `record()` made when the addendum is written.
- Require every chain of the root to be complete or terminated before any unseal, or label reads unsealed early as `repeated_test_development`.

### 13. MINOR — The exclusion consent is not bound to the run root, and `TestAccess` can be built anywhere

**Where:** `exclusion.py:36-48`, where only `path.parts[-2:]` is checked, and `:51-56`; the frozen `coevo5/data.py` `TestAccess`.

**Why:**
- Any directory named `shared` works.
- `TestAccess` is a plain class, so "only the evaluation unit creates test access" (§3.5) holds by convention only.

**Fix:**
- Take the run root as the argument and build the path inside the function.
- Allow `TestAccess(` only in the exclusion CLI and in evaluation, with an AST check in the S0 pytest.

### 14. MINOR — Owner files are checked loosely, and the recovery file is self-stamped

**Where:**
- `evaluation.py:87-98`: the consent `date` may be blank.
- `evaluation.py:529-537`: the continuation `date` and `note` may be blank.
- `scripts/run_execskill.py:169-175`: `recover` writes `"by": "owner"` for whoever runs it, with no version or `record_sha256`.

**Why:**
- §8.1 requires the owner's own note.
- The recovery decision belongs to the owner, yet an agent running the CLI produces an owner-stamped file.

**Fix:**
- Require a non-blank date and note.
- Make `recover` refuse unless an owner-written decision file exists, or stamp the record `"by": "operator"`.
- Seal the record with `record()`.

### 15. MINOR — The unit diagnostics file is not write-once

**Where:** `units.py:163`.

**Why:** `write_text` overwrites the file. It holds the full traceback text and is not versioned.

**Fix:** Write it once, recording only the exception type and the stack, or route it through `contained()`.

### 16. MINOR — Hidden-data refusal checks key names only

**Where:** `trajectories.py:48` and `:172-195`.

**Why:**
- A value that carries a game path or plan text under an allowed key, such as an observation or a fault message, passes.
- `HIDDEN` lacks `private`, `answers`, `test_files` and `game_metadata`.

**Fix:**
- Add a scan of values for `json_2.1.1/`, `.tw-pddl` and `traj_data.json`.
- Add the missing keys to `HIDDEN`.

### 17. MINOR — Two registered isolation mutations are missing, and the key isolation paths have no test

**Where:** `tests/test_execskill_mutations.py:23-135`. Mutation (21), placebo built from acceptance items or after dispatch, and mutation (27), research accepting a non-frozen host or a changed archive file, are both absent.

**Why:**
- The mutation suite is the evidence that the guard tests actually catch a broken guard.
- No test covers findings 3, 5, 6, 8 or 9.

**Fix:** Add both mutations, plus tests for the payload refusals, the write-half diagnosis, the research names, the input mount and the scorer directory.

### 18. MINOR — ALFWorld new-game ids are unsalted hashes of public paths

**Where:** `supply.py:199` (`xs_id` of the relative game path). Trajectories carry `task_id` (`TOP`).

**Why:**
- Anyone with the public dataset can map `alfworld-xs:<sha16>` back to its game path and that game's `traj_data.json`.
- LLM roles cannot enumerate the dataset, so the risk is low. Still, the mapping is not confined to the registrar's file as §3.1 states.

**Fix:** Salt the hash with a registrar secret, or keep task ids out of role payloads.

### 19. MINOR — Sealing of test scores is procedural only

**Where:** `evaluation.py:242-246`. `cells/<id>.json` holds `final.token` and the judge tokens in clear.

**Why:** Any process or operator can read per-cell pass/fail before the unseal, and nothing records such a read.

**Fix:**
- Keep the tokens in a restricted or encrypted store until the unseal.
- At minimum, document that `cells/` must not be read, and make the operator CLIs refuse to read it.

### 20. MINOR — The sandbox escape probe has no code

**Where:** `smoke.py:43-44`. `escape_probe` is a boolean that the operator supplies.

**Why:**
- §10 S0 requires that the sandbox sees no `*.env`, key, ledger or consent file, runs as uid 65534 and has only the registered environment variables.
- The mounts look right, but no code checks what the pinned image contains.

**Fix:**
- Ship a fixture probe procedure that lists `/`, `/runner` and `/input`, reads the environment, tries the network, and asserts the expected results.
- Make S0 consume the probe's record.

### 21. MINOR — Design note for `examiner.py`: drop counts reveal properties of source references

**Where:** `generators/sheet.py:12-25` (`literal_answer` and `edit_target_invalid` depend on the source item's reference workbook) and `generators/__init__.py:86-97` (drop counts).

**Why:** If drop counts per source item reach the examiner, they leak bits of the reference workbook.

**Fix:** Show only drop counts aggregated across items.

## Appendix: zero-call probes on dl

All four probes ran in `/data/execskill-dev` with `python -B -` reading the script from stdin. They used `/tmp` only and made no model or network call.

1. **SpreadsheetBench scorer directory (finding 3).**
   - `EvaluationStore("/tmp/.../attempt-1").scorer_dir(p)` = `/tmp/.../attempt-1/transient/scorer_artifacts/<p>`.
   - `sheet_recalc_adapter._context` raised "ValueError Private evidence must use host-only scorer storage".
   - `backends.score(..., spreadsheet_scorer="qualified_lo_recalc_v7_v1")` returned `{'status': 'unknown', ..., 'reason': 'native_scoring_input_error:ValueError'}`.
2. **Engineer payload (finding 5).** With an acceptance-unit trajectory (resealed, `arm_kind` "parent"), the reference `{"expert_plan", "gamefile"}` and `previous={"acceptance_item_scores": ...}`, the output was:
   - "acceptance-unit trajectory shown: True"
   - "expert_plan/gamefile reached the payload: True True"
   - "previous passed through verbatim: {...}"
3. **Research names (finding 8).** `leakage.mechanical(item_text)` = `shared_8gram`. `parameter_choice(names=[item_text])` dispatched 2 researcher calls, and "item text reached the researcher: True". The run then stopped on "No scripted reply left", the fake GLM's end of script.
4. **Policy (finding 9).** For `pd.ExcelFile("/input/1_1_answer.xlsx").parse(0)`, `policy.check` returned `[]`.

Targeted suite: the `exclusion`, `evaluation`, `trajectories`, `research`, `engineer` and `placebo` test files, 43 passed in 7.8 s.
