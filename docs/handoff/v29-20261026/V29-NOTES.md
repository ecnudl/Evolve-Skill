# Route B v2.9 implementation notes

2026-10-26. Writer implementation of [BRIEF-v29-writer.md](BRIEF-v29-writer.md), extending the
[v2.8 structure](../v28-20261026/V28-NOTES.md) and [v2.8 writer brief](../v28-20261026/BRIEF-v28-writer.md).
All execution here used authored engineering fixtures and fake transports/judges. Experiment model calls,
API charges, network requests, remote launches, commits and pushes: **zero**. No `dl` or absolute `/data`
path was accessed. Registered future `/data` paths are strings only. The three protected living documents
were not edited; their starting bytes are recorded in [INITIAL-SHA256.json](INITIAL-SHA256.json).
This is implementation/fixture evidence, not an experiment or evidence that audits improve model outcomes.

## Configuration and identity

| Configuration | Parent | Future root | Namespaces | Evidence |
| --- | --- | --- | --- | --- |
| `zebra-pc-v7` | `zebra-pc-v6` | `/data/execskill-20261027-zebra-pc-v7` | `G-zpc7`, `D-zpc7` | `zebra_pc_v7_real_run` |
| `alfworld-v4` | `alfworld-v3` | `/data/execskill-20261027-alfworld-v4` | `G-alf4`, `D-alf4` | `alfworld_v4_real_run` |

Manifest paths append `-manifest.json`. G is registered; only D launches. Both have feature family `v2.9`,
record kinds `engineer-v2-9` / `manifest-v2-9` / `procedure-v2-9`, and the separate immutable sandbox policy
`fivebench-execskill-v2-9-policy`. Source limit: 24,000 UTF-8 bytes. Sandbox restrictions and fixed seed zero
are inherited. `is_v23` through `is_v28` include the new family; `is_v29` selects only these two configurations.
Six training rounds, patience two, ordinary `TRAIN_FIXES=3`, inherited slices and practical-v2-2 acceptance
remain. J1 requires at least five whole-batch percentage points; J3 remains information.

Acceptance freshness is
`zebra_split_v1_slices_reused_accept_used_four_times_plus_ub_probe` and
`alfworld_split_v1_slices_reused_acceptance_used_once`. Confirmation freshness is
`zebra_split_v1_confirm_spare_probe_smoke_first_use` and
`alfworld_split_v1_confirm_spare_rooms_first_use`.

Every older configuration retains its registered behavior and pins. The original fourteen fingerprints
remain unchanged; the two new frozen v2.8 fingerprints were captured before implementation:

- `zebra-pc-v6`: `42053c423a0a0ec6b2abc6d8e52460a51e090bc20c7f31d6b4388e75ba208fe1`
- `alfworld-v3`: `7a19d347420679d6a880ff5ab160557d7c5573d7d909327409acb2a5763eb18a`

## Prompts and policy pins

[V29-PROMPTS.json](V29-PROMPTS.json) contains the final literal policy, both audit systems, final-audit
contradiction addition, response schemas, format retry, audit-fix request components, task cards/hook
semantics, all four engineer configurations/modes and their fix/retry/audit-fix suffixes, and northgate
probe prompts. Each string has its raw UTF-8 SHA-256; the task-card/hook-semantics maps use the existing
canonical-JSON digest. Actual audit requests also seal `system`, `user`, combined `prompt_text`, its raw
SHA-256, label, both raw replies, parsed verdicts, retry prompts/labels, availability and usage.
Engineer request hashes and unit records pin the selected v2.9 text; no old prompt was rewritten.

- Exact policy text SHA-256: `5e86651b3421993bbfaeb10cfbfb57eaa3c6424096bf48095482fd320ee2b697`.
  Its bytes were compared with the brief's POLICY block.
- Policy JSON SHA-256: `ab2ee7cba15cf810830fae7c133d61c2bbd11464bb5849a9e2e73590c33cf8dd`.
- v2.9 runtime-screen identity: `b1591410c48ba8b6987c64ba78643cca66ed44e3920124894432e43cf9c5c81d`.
- Prompt archive SHA-256: `29ee760491eb21730bab0d72e4bb96e47f1e4177ddfab59316a06e3ffd1532d8`.

New engineer prompts derive from v2.8, remove its sentence-removal instruction, and add optional applies,
P1–P6 including the task-requirement exception, the one audit-fix cycle/final audit, and count-only
held-out confirmation. Numerical bounds remain generated from registered constants.

## Runtime behavior

`package.default_applies` inspects the actual top-level source functions. Missing `applies` means true
without a worker call; derived declarations remain truthful to the source. Router, C6, training and
confirmation routes, live cells/trajectories, donor routing, enable logs and sealed evaluation cells retain
`applies: "default_true"`. Helper-only procedures remain inert. An explicitly defined predicate still runs.

The shared v2.9 screen delivers lexical/imperative-hit sentences unchanged. `sentence_elements` is also
the auditor's sentence/list-element splitter. Each hit sentence records its UTF-8 SHA-256 and a count of
lexicon plus imperative matches; cells aggregate these, including explicit zero-hit card cells and reused
cells. Live, replay, donor and placebo use this same mechanism. C8 answer-channel markers, field/cell
caps, invalid-output suppression and v2.8 fault handling remain active. A late interactive fault cannot
retract a note already sent; audit2 uses actual delivered text and source/step attribution.

Chain D's start and bound route are B; v2.9 refuses route switches. The transport request model is
`client.NORTHGATE_MODEL` (`deepseek-v4-flash`), with `NORTHGATE_RESPONSE_MODEL_IDS`; the historical internal
chain-D model key still identifies its shared slot pool. Every v2.9 cell records route and returned model(s).
Parent nominal solver output caps/read timeouts remain unchanged. J-D copies those provider/client
settings but sets its own output/reservation cap to 8,192.

## Audit sampling, agreement and consequences

J-G uses a fresh GLM-5.3 request through the engineer provider; J-D uses northgate. Both get identical
systems/user prompts, 8,192 maximum output tokens and their clients' existing deterministic settings.
They have separate `:role:audit_g` / `:role:audit_d` ledger scopes. Neither receives an engineer conversation,
reference/gold answer, solver reply, score, judge label, acceptance item or sealed test item.

Part A mechanically extracts source-order string literals of at least eight characters containing a
letter, f-string templates with `{...}` substitutions, percent-format templates and `.format` templates.
It deduplicates and retains at most 60, prioritizing lexicon/imperative hits and marking them “always check
P2.” F-string literal fragments are represented in their complete f-string template; independent literals
inside computed expressions are extracted. Total, truncated and truncated-priority counts are sealed and
shown. The over-60 priority conflict is discussed below.

Part B's deterministic RNG seed is the canonical SHA-256 of configuration, step, round, change ID and
raw source SHA-256 (a canonical list of source hashes for a multi-procedure audit). Only non-empty-note
situations qualify. Zebra selects up to 12 items; ALF selects up to eight episodes, step zero when present
plus two random later non-empty steps (still at most two later steps if zero has no note). Smaller sets are
used in full. Up to four additional marked situations are selected in stable order. Batches contain at
most four Zebra or six ALF situations. Views are constructed from a whitelist: Zebra question/columns;
ALF task/initial/current observation, last five public action/observation steps and at most 60 admissible
commands. Notes receive system-assigned S/N IDs. Description and C6 item/fired/non-empty/fault counts
accompany the batches.

Agreement is an intersection of flagged units, not a majority of policy labels:

- Same procedure/template ID: confirmed even if P codes differ.
- Same procedure/situation/note: confirmed when both flag false or P2–P5, even if the fault kinds differ.
- `other`: same procedure, function and P code required.
- Program P6: each judge's P6 in any batch suffices; their batches need not coincide.
- Final contradictions: the same unordered note pair; remove the later-ordered procedure.

One-sided findings remain advisory. `unverifiable` alone is never a fault. Missing/malformed verdicts get
one format-only retry; still unusable makes that judge unavailable for the audit. No finding can then be
confirmed, the change continues subject to other checks, and `audit_incomplete` is sealed and counted in
the step summary. Identical requests are cached within a unit. Final Part A additionally reuses identical
prior template requests with source-unit provenance; final situation prompts remain fresh.

Audit1 runs after v2.8 checks for each non-inert, non-deferred coded new/revised change. It uses only that
change's C6 forward replay of run-slice trajectories. Confirmed findings produce one engineer audit-fix
request, with matching run-note evidence where available and explicit absence of such evidence otherwise;
no unrelated or invented example is substituted. Advisories are optional. The generic reader and one
format retry handle the fix. Checks run once more; fatal failure drops with `audit_fix_failed_checks`,
without restarting behavior fixes. A second audit with any confirmed finding drops with `audit_confirmed`.
Audit fixes count against engineer call caps, never against `TRAIN_FIXES`. Next-round lint contains only
audit1 decisions/advisories and run-slice evidence. Deletions/narrowings are not audited.

Audit2 runs in `audit-final` before self-test/acceptance, only when the package edits its parent. Only added
or revised procedures get source/P6 judgments; all final procedures' descriptions and delivered notes are
shown together for contradiction checks. Candidate-arm training/confirmation trajectories must contain
the final procedure's source identity. Confirmation situations are preferred, audit1 situation keys are
excluded, and the same sample/batch limits apply. Audit2 can take three later ALF steps when no eligible
step-zero situation remains. Confirmed findings remove procedures; there is no
engineer fix or disclosure of this audit. An unchanged result releases `audit_emptied`, with no self-test,
acceptance or test read. A deletion/narrowing-only final package records `not_applicable` and proceeds.

## Second-slice confirmation

Zebra confirmation is exactly the three spare IDs, all 27 `EXCLUDED_IDS` probe IDs and ten smoke IDs,
in the registered 5–6-house domain: forty distinct IDs, disjoint from run/accept. ALF confirmation uses
forty games from spare rooms in the existing seeded order, taking whole room queues capped at
`MAX_GAMES_PER_ROOM=5`. A deterministic first exact subset of those queues totals forty; an impossible
exact total fails preparation rather than silently truncating a room. The manifest seals actual IDs,
ID hash, source-group/room provenance and freshness; loading verifies these against the pinned pool.
No real pool was opened during this work, so its actual ALF room cardinalities remain unverified here.

A training-adopted, pruned candidate then runs `confirm-rN`, S' versus incumbent S, once per differently
routed confirm item. Exact-request-equivalent pairs are skipped and contribute no fixes/breaks. Incumbent
cells are reused across rounds only while their exact package SHA-256 matches; a promoted candidate's
cells can become incumbent cells. Verdict: `fixed > broken`, at least one differently routed item, and
S' format-violating cells minus S's at most `max(2, ceil(.02 * S' logical cells))`. Equivalent pairs remain
in that format denominator. Failure changes adoption to false with `confirm:<rule>` and consumes ordinary
candidate patience. The engineer receives only counts; confirm IDs, views, notes and replies stay sealed.
Each round/unit records items/evaluated, fixed/broken/net, format counts/margin, passed/reason, reuse and
actual new input/output/total tokens.

## Smoke and cap formulas

Lean S1/S2/S3a/S3b/SE6 remain. S1 confirms northgate's first response and measures three sequential long
fixture replies, persisting their longest completion and the branch-N ledger bound
`max(4*M, ceil(1.5*longest))`. A clean, non-empty `finish_length` reply with the correct model and
no reasoning is a valid length measurement, necessary with ALF's 1,024-token cap; it is not counted as a
successful task answer. S2/S3 and the real manifest inherit that measured bound. Authored S3a has
one true note and the known-false “all parsed”/“all visited” statement. It calls both real judge backends
in production and passes on parsed replies plus the recorded agreement/decision; detecting the specific
false statement is informational. Offline tests replace those backends with fake judges. S3b runs the
ordinary engineer/audit1 path. S3a also runs two confirm fixtures in explicit exercise mode; they clone
run-fixture content under distinct IDs/rooms and are **not independence or method-effect evidence**.
SE6 includes both judges, all engineer calls and leakage rechecks, and confirm cells. Its procedure-cell
estimate is at least the larger of the inherited 1.6× S2 estimate and S3 confirmation's measured settled
cost per cell. Repeated nested audit records are deduplicated within a unit; genuine identical sends in
separate S3 units are both counted.

[V29-CAPS.json](V29-CAPS.json) contains every final numerical cap and constant. Let
`R(b,m)=4*(b+512+m)`, `I=220000` registered input bytes, `T=6` rounds, `C=3` changes,
`P=24` maximum package procedures, `J=8192`, one format retry, and two audit1 passes.

- Prompts per judge/pass: `qZ=1+ceil((12+4)/4)=5`; `qA=1+ceil((8*3+4)/6)=6`.
- Per-step calls per judge: `N=(T*C*2+P)*q*2`: **600 Zebra / 720 ALF**. Counting all 24 final procedures
  is deliberately conservative relative to the final edit budget; request reuse only lowers actual cost.
- Per-judge cap: `(N+1)*R(I,J)`: **549,804,416 / 659,582,336** ledger tokens. `R(I,J)=914,816`.
- Engineer unit caps: **16 single / 26 train**, parent 13/23 plus `MAX_CHANGES` audit fixes. SE6 engineer
  calls: `6*(26+4)=180`; leakage calls: parent 72 plus `6*3=18`, total **90**.
- Shared engineer-scope increment: `T*C*(R(I,32768)+R(I,16384))=35,292,672`, reserving the audit-fix
  requests and their possible C4 adjudications. Final engineer scope: **55,292,672**.
- Method-total increment: that engineer increment plus both judge caps. Final totals:
  **1,252,501,504 Zebra / 1,472,057,344 ALF**. Existing examiner scopes remain inherited.
- Confirm maximum: `T*2*40=480` logical solver cells. Confirm cap is
  `round_up_100000(3*(480*high_anchor*1.6 + MAIN_RESERVATIONS*READ_RESERVATION))`, giving
  **37,200,000 Zebra / 128,700,000 ALF**. The solver total adds this cap and any increase in the
  maximum whole-scope redo reserve. Final solver caps: **272,200,000 / 1,013,700,000**.

These are conservative ledger envelopes, not measured bills. A normal single audit costs 10 judge calls
on Zebra or 12 on ALF; allowing every format retry doubles that, and an audit-fix re-audit can double it
again. At the full registered input allowance and an illustrative four UTF-8 bytes/input-token estimate,
each judge's one-pass envelope is 275,000 input + at most 40,960 output tokens on Zebra, or 330,000 input
+ at most 49,152 output tokens on ALF. If `Gi,Go,Di,Do` are the respective provider prices per million
input/output tokens, paired one-pass costs are approximately
`0.275*(Gi+Di)+0.040960*(Go+Do)` and `0.330*(Gi+Di)+0.049152*(Go+Do)`.
This is an input-size planning estimate, not a tokenizer measurement or current price quote. Cash prices
were not fetched under the offline constraint. SE6 must replace estimates with real S3 usage; unusually
large public views still face the ordinary ledger reservation guard. Per-audit/unit/step records retain
each judge's actual input, output and charged ledger tokens, excluding reused requests.

## Files and functions

- `audit.py`: policy/prompt pins; `templates`, `sample_situations`, `public_view`, `parse_verdict`,
  `agreement`, `run_audit`, `audit1`, `audit_fix_prompt`, `situations_from_cells`, `removed_procedures`.
- `engineer_v29.py`: generated systems/suffix pins and count-only/audit feedback validators.
  `engineer.py` and `engineer_v28.py`: configuration-scoped dispatch, C6 capture, audit-fix loop and records.
- `confirm.py`: exact slice identity/provenance, confirmation verdict, counts-only boundary and token totals.
  `step.py`: confirm routing/reuse/units, post-confirm adoption/patience, `_audit_final`, `_audit_summary`,
  `audit_emptied`, and step records before self-test/acceptance.
- `profiles.py`, `protocol.py`, `v29_limits.py`: identities, predicates, caps, freshness and record vocabulary.
  `policy.py`, `sandbox/policy-v2-9.json`, `sandbox/client.py`, `package.py`: immutable policy, source cap,
  seed, source-derived optional applies and package roundtrip.
- `notes.py`, `router.py`, `replay.py`, `solver.py`, `donors.py`, `placebo.py`: shared log-only screen,
  no-worker default applies, fault handling and exact delivered-note attribution.
- `cells.py`, `trajectories.py`, `evaluation.py`: per-cell zero/nonzero hit metadata, applies/route/model
  records and preservation in structural reuse and sealed reads.
- `budgets.py`, `units.py`, `manifest.py`, `routes.py`, `chain.py`: separate judge scopes/endpoints,
  manifest prompt/model/confirm pins, northgate start/binding and first-call confirmation.
- `v29_route_probe.py`, `v29_smoke.py`, `zebra_smoke.py`, `alf_smoke.py`, `smoke.py`: northgate measurements,
  authored/real audit smoke, confirm exercise and measured projection. `scripts/run_execskill.py`: new choices.
- Seven `tests/test_execskill_v29_*.py` modules cover audit/agreement, engineer fixes, confirmation/final
  audit, runtime/route parity, profiles/caps/manifests/smoke and the two added frozen fingerprints.
  The existing v28 roster assertion excludes the newly inherited v29 family; historical expected values/hashes
  were not changed. [V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json) binds all 41 changed/new source/test files.

## Validation

Final consolidated commands, counts, log hashes and baseline comparisons are recorded in
[V29-VALIDATION.json](V29-VALIDATION.json). All test evidence is authored engineering fixtures, with
no experiment model or model-accuracy denominator. The offline harness blocks sockets, real Docker,
external network commands and `/data`/`dl` filesystem operations; Linux worker/listener skips are not
passed isolation tests. Temporary test material stays in the working copy or authorized `/private/tmp`
scratch; receipts/logs stay here. No production check or test expectation was weakened for path fixtures.

| Selection | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Final targeted, including **105 new v29 cases** and all **16 frozen configurations** | **143** | 0 | 0 | 0 |
| v24–v29, Zebra and ALF | **1,050** | 4 | 0 | 0 |
| Registered execskill + weak-solver suite | **2,809** | 22 | 174 | 118 |
| Entire repository, continuing past collection errors | **15,235** | 1,061 | 280 | 147 test skips |

Receipts/logs: [targeted](final-delivery-validation.json), [focused](selected-delivered-validation.json),
[registered](registered-checked-validation.json), [repository](repository-delivered-validation.json).
The repository's pytest terminal summary reports **148 skips**, including a collection skip; the receipt's
147 counts runtime skips. Its 280 errors include two collection errors for missing upstream task assets in
`test_coevolution_v4_tasks.py` and `test_validator_pilot_tasks.py`; nothing was downloaded. It collected
16,721 tests. Failures/errors are test infrastructure outcomes, not model-accuracy denominators.

The registered suite retains **all 192 baseline failure/error IDs, zero removals**, plus exactly the four
known ALF `card`, `views`, `pool_pin` and `alias` path fixtures. Its **196 distinct failure/error IDs** are
therefore the expected baseline plus those fixtures. Earlier scratch-only attempts added two SearchQA
setup errors and then one authored-Docker guard error. The final harness permits only authored fixture
executables inside this session's explicit authorized private-tmp basetemp; real Docker remains blocked.
The three affected cases pass in [harness-validation.json](harness-validation.json). No runtime validation
or historical assertion was relaxed.

The full repository has **1,341 distinct failure/error IDs**: all 192 registered baseline IDs plus 1,149
others. Compared with the archived v28 full-repository receipt, one ID was added
(`test_sleep_engine.py::TestCodexBackend::test_codex_attempt_with_tools_windows`) and three were removed
(two now explicitly skipped Linux-worker tests and the authored-Docker fixture). That comparison uses
different historical harnesses and does not establish every non-execskill failure as pre-existing. No v29
test failed. **The registered and full repository suites are not clean passes.**

The broad selections collected immediately before two final isolated corrections: accepting clean
length-capped northgate probe measurements, and retaining at most two later ALF steps in audit1 when
step zero has no note (audit2 may use three later steps). Each has an added regression. The final
**143/143** targeted run covers those delivered corrections, all 105 new cases, affected audit/smoke/profile
behavior and frozen fingerprints. Earlier integration
snapshots and zero-test/failed launches remain archived and are not substituted for the final results.
Source hashes, exact commands, baseline comparisons and these timing limits are consolidated above.
Relative handoff links, protected-file byte comparisons and `git diff --check` were checked.

## Deviations and coordinator decisions

1. The brief simultaneously caps extraction at 60 and says every marked template is always included.
   More than 60 distinct marked templates cannot satisfy both. Implementation preserves the hard cap,
   prioritizes marked templates and seals/shows `always_check_truncated`; the coordinator must decide
   whether a future protocol should expand/batch the cap or refuse this case. No silent overflow occurs.
2. ALF whole-room selection uses the first deterministic exact subset in seeded room order. If the real
   pinned spare queues cannot total forty without partially taking a room, preparation refuses. The real
   room counts were not read here.
3. Real northgate/GLM availability, judge quality/agreement, response-token behavior, runtime overhead,
   prices, Linux isolation and method effects remain unmeasured. Production smoke must exercise the real
   judges and confirmation cells before launch. The registered large caps are capacity, not authorization
   to spend or claims of expected cost.

4. Both registered configurations require step 1 from an empty parent; inherited/nonempty starting
   packages are rejected before units run. In a future generalized nonempty-parent profile, removing a later
   unchanged procedure for a contradiction could turn three edits into four and hit the inherited edit cap.
   A zero-call review reproduced that generic case and verified it is unreachable in these configurations.
   Such a future profile needs an explicit deletion/selection budget decision; this implementation does not
   silently extend the current scope.

## Fixes v29-1

Implemented all six findings in [FIX-BRIEF-v29-1.md](FIX-BRIEF-v29-1.md). This section supersedes the
original delivery's package-only confirm reuse, confirm-first audit sampling and repository-scratch behavior
described above. Historical validation receipts remain unchanged.

| Finding | Change | Regression evidence |
| --- | --- | --- |
| 1. Missing ALF confirm views | New `alf_confirm_views.prepare` and `alf-confirm-views` CLI use `supply.prereset`/`supply.alfworld_reset` for exactly forty confirm games. Original supply, pool export, game hashes and views runtime must match the main preparation before reset. S0 requires the sealed record; S0 and manifest embed it by value. `_alfworld_views` attaches validated copies, including when `_slices` reloads saved IDs. | `test_execskill_v29_confirm_views.py`: 13 cases covering exact forty resets and closes, write-once publication, unchanged historical files, runtime/root/game mismatch before reset, missing or altered IDs/view/runtime/supply/slice hash, by-value manifest validation and slice reload. |
| 2. Partial-package audit evidence | Candidate trajectories retain package SHA and procedure-source hashes. Final sampling prefers the exact final package, then packages containing every final added/revised source, then fallback; confirm precedes train only within each tier. Audit1 situations remain excluded. | Two-round fixture retains the newly added procedure in every sampled final-package situation; source revisions, fallback, exclusion and ALF later-step priority are covered. `_audit_final` integration asserts the final SHA and source map. |
| 3. Unsafe incumbent reuse | `_confirm_identities`, `_confirm_cell_reusable` and `_confirm_cached` require matching saved/current identities plus a complete, fault-free cell. Zebra uses the S-arm request signature; ALF binds package SHA, game ID, pinned view SHA, runtime digest and card SHA. Missing identities never match; promoted candidates use their saved S' identity. | Changed Zebra signatures rerun all forty incumbent cells. Faulted/incomplete/missing-identity cells rerun; unchanged valid cells and promoted candidates reuse. ALF game/view/runtime/card mutations and actual completed pass/fail verdict shapes are covered. |
| 4. Informational hits counted as faults | `audit.c6_counts` excludes informational events from `faults` and reports `keyword_hits` separately to the judges. | Healthy replay with keyword hits reports zero faults; adding a real crash reports one. |
| 5. Noncanonical judge replies | `parse_verdict` validates the complete decoded value with finite JSON numbers and canonical UTF-8 serialization before acceptance. Invalid replies consume one format retry, then mark the judge unavailable. Literal invalid Unicode is archived escaped with an explicit encoding marker. | NaN, Infinity, negative Infinity, numeric overflow, escaped and literal lone surrogates all retry once and persist an incomplete audit without confirmed findings or a crash. |
| 6. Incorrect adopted fates | `_line` handles `audit_confirmed` and `audit_fix_failed_checks` before ordinary fates. | Both audit-dropped changes retain their reason when a surviving sibling makes the round adopted. |

The coordinator must run this **zero-model-call preparation on Linux before v2.9 ALF S0**. Set
`MAIN_V22_PREPARATION` to the existing main-v2-2 manifest, `ALFWORLD_DATA` to its exact
`runtime.alfworld.alfworld_data` path, and choose new `ALF_V29_CONFIRM_VIEWS` and `ALF_V29_S0` output paths.
`ALF_V29_SNAPSHOT` is the verified code snapshot used for S0. The pinned pool's adjacent `pools.json`
must retain `source.alfworld` references to the original supply and pre-reset views. Those source seals,
the pool pin and original views runtime digest are verified; the runtime is imported directly from the
preparation. Only the selected forty game files are read and reset. Exporting `ALFWORLD_DATA` is required
by the existing production environment loader.

```sh
export ALFWORLD_DATA
python scripts/run_execskill.py alf-confirm-views \
  --configuration alfworld-v4 --preparation "$MAIN_V22_PREPARATION" \
  --data-root "$ALFWORLD_DATA" --out "$ALF_V29_CONFIRM_VIEWS"
python scripts/run_execskill.py alf-s0 \
  --configuration alfworld-v4 --preparation "$MAIN_V22_PREPARATION" \
  --confirm-views "$ALF_V29_CONFIRM_VIEWS" --out "$ALF_V29_S0" \
  --snapshot "$ALF_V29_SNAPSHOT"
```

The new record seals ordered IDs, each view and its SHA-256, runtime digest, supply SHA-256, confirm-slice
ID hash, preparation and pool provenance. Its original output file is no longer required after S0 embeds
it. Neither historical preparation nor pool files are rewritten. This Linux preparation was not run here;
tests use authored temporary games and fake environments.

The offline harness now places tempfile, pytest basetemp and cache scratch under `/tmp` or `TMPDIR`,
refuses repository basetemp, and final commands disable cacheprovider. All five workspace scratch
directories (`.v29-confirm-final-tmp`, `.v29-confirm-integration-tmp`, `.v29-confirm-review-tmp`,
`.v29-confirm-tmp`, `.v29-fixtures`) were deleted. The three protected documents still match
[FIX-v29-1-INITIAL-SHA256.json](FIX-v29-1-INITIAL-SHA256.json).

[V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json) now binds 44 source/test/harness files, including the new
preparation module and tests; [FIX-v29-1-SOURCE-BEFORE.json](FIX-v29-1-SOURCE-BEFORE.json) preserves the
preceding source-hash map. Literal prompt/policy hashes, sampling limits, agreement rules, cap formulas
and cost estimates are unchanged. Actual network requests, model calls, paid experiments and commits
remain zero. No new protocol deviation or decision was introduced; the original open decisions remain.

Final validation after all fixes and regressions:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| All v29 tests (146, including the two v28 configuration fingerprints) plus fourteen earlier frozen fingerprints | **160** | **0 / 0 / 0** |
| v24–v29, Zebra and ALF selections | **1,097** | **0 / 0 / 0** |

All **sixteen frozen fingerprints pass**. Moving scratch outside the repository also resolves the four
previous ALF path-fixture failures without changing their assertions. These are offline engineering
tests, not Linux runtime or model-effect evidence. The registered and entire-repository suites were not
rerun for this fix; their historical outcomes above are not replaced by these selection results.

Both commands used this prefix:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest
```

Targeted arguments: `tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q
--offline-receipt docs/handoff/v29-20261026/fix-v29-1-final-targeted-validation.json`.
Broad arguments: `tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py
tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py
tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q
--offline-receipt docs/handoff/v29-20261026/fix-v29-1-selected-validation.json`.

Receipts and exact commands/hashes: [fix validation](FIX-v29-1-VALIDATION.json),
[targeted receipt](fix-v29-1-final-targeted-validation.json) / [log](fix-v29-1-final-targeted-validation.log),
[selection receipt](fix-v29-1-selected-validation.json) / [log](fix-v29-1-selected-validation.log).
Final source hashes, protected-document hashes, handoff links, absence of `.v29-*` scratch and
`git diff --check` were verified.

## Coordinator fix before commit (2026-10-26 23:3x)

The Linux pre-commit run (787ecd2 + v29.diff in a scratch worktree, `tests/test_execskill_mutations.py` plus the
Zebra, v2.4–v2.9 and ALF selections) gave **1,234 passed, 2 failed**. Both failures were stale mutation-catalogue
anchors, not behaviour changes. v2.9 adds a `configuration` keyword (v2.9 only) to two protected calls, so
mutation `56-step-unit-starts-without-a-confirmed-first-call` (`step.py`, `confirmation(...)`) and
`109-route-switches-under-a-running-process` (`manifest.py`, `routes.check_bound(...)`) no longer found their
old text. The coordinator updated only those two catalogue entries in `tests/test_execskill_mutations.py` to the
new line text. The mutants are still "skip the call", and the named tests are unchanged. No source file changed.
The Mac cannot run this module (its unmutated-copy baseline has one Mac-environment failure), so verification is
the Linux rerun of the whole selection.

## Fixes v29-2

Implemented [FIX-BRIEF-v29-2.md](FIX-BRIEF-v29-2.md), including its focused-review addendum,
following the coordinator-reported S3a failure.
The supplied failure is reproduced with authored replies: D's optional Part A `other` row contains P6,
while both judges validly flag T2, “All clues were parsed.” D now remains usable, that optional row is
recorded and ignored, T2 is confirmed, and the offline S3a fixture passes. This applies to both v2.9
configurations. No real smoke, Linux environment or model request was run for this fix.

`audit.parse_verdict` now distinguishes unusable reply shapes from invalid units/fields. Invalid JSON,
nonfinite numbers, invalid Unicode, unusable nesting and missing/wrong required containers follow the
one-retry path. Canonical JSON cloning also keeps valid deeply nested diagnostic data safe through
request caching and persistence. Extra top-level keys and invalid optional rows are recorded in
`ignored` with their path, reason and raw value. Missing `other` is empty; missing/invalid final
`contradictions` records an optional abstention. P6 remains valid only as a Part B program verdict.
Part A optional function references must belong to the source shown in that request.

The focused review found that a malformed duplicate situation could abstain notes already judged by a
valid fragment, while their findings remained usable. The addendum corrects that inconsistency:
`audit._parse_verdict` validates each fragment before its local `resolve` helper decides coverage.
Unknown/invalid IDs, non-object fragments, malformed situation `notes` containers and invalid known-unit
rows go into `ignored`, with path, reason and raw fragment. They never remove coverage supplied by a
valid fragment. A required unit abstains only if no fully valid, non-conflicting judgment remains;
known-unit field problems retain their exact paths in abstention/retry diagnostics when no valid
fragment survives. Malformed fragments with no identifiable required unit produce no phantom abstention.

A note is retained and used only when its truth, evidence, policy and text reason are all valid and its
valid duplicates do not conflict. A false judgment requires non-empty evidence. Invalid truth or policy
therefore abstains the **whole note** when no valid duplicate remains; complementary malformed fragments
are never merged. This replaces the initial v29-2 behavior that used the surviving field of a partial
note. Identical valid duplicates collapse; conflicting valid template/note judgments abstain the unit.
Malformed duplicates are set aside before that conflict check, irrespective of their order. Templates
and the program verdict also contribute judgments only when covered.

`audit._request` retries once only for an unusable shape or a missing/invalid requested unit. The retry
lists exact paths and problems. It selects the usable attempt covering more **complete required units**
(one template, one note with both judgments valid, or one program); ties keep the first attempt, and
attempts are never merged. Request-level `covered`, `abstained` and `ignored` describe that selected
attempt; `attempts` retains every attempt's diagnostics and `selected_attempt` is zero-based. Optional
contradiction coverage does not enter retry scoring. Both attempted sends still enter token accounting.

`audit.findings` explicitly checks required-unit coverage before emitting any template, note or program
finding, in addition to the parser omitting uncovered units. Valid optional `other` rows and covered
optional contradiction judgments retain their existing rules. Coverage, abstention, findings and
retry selection thus describe the same usable judgments. `audit.agreement` preserves the same-template,
same-note, same-function/code, any-batch P6 and unordered-contradiction-pair rules. One unavailable request no
longer disables unrelated agreements. `incomplete_units` retains missing coverage by request, procedure,
unit and judge, including batch-specific program gaps; `audit_incomplete` reflects those gaps or any
unavailable request. `available` still reports whether every request was usable for each judge.

`v29_smoke._proposal` retains `all(available.values())` as its S3a pass rule and keeps
`false_template_confirmed`. Its new `judge_counts` sums selected-attempt complete coverage, distinct
abstained units per request, and ignored entries per judge. `_audit_measurements` counts only framework
request records and their retries, so request-shaped objects inside ignored replies cannot corrupt
measurements. `audit._tokens` continues counting all sends, including format retries.

Files changed: `audit.py`, `v29_smoke.py`, the existing v29 audit/smoke test modules, the new
`test_execskill_v29_reply_parts.py`, and the offline harness. The old unknown-template test now asserts
ignored unknown fragments and abstention only for missing required templates; v29-1's canonical and
persistence regressions remain. The harness additionally redirects the historical v28 neutral-directory fixture into OS scratch
without modifying its test source. All test scratch is under `/tmp` or `TMPDIR`; no `.v29-*` directories
remain in the working copy. The focused-review addendum changes only `audit.py`, the v29 audit test
and reply-part test modules, plus handoff notes, hashes and validation evidence.

The coordinator's complete `tests/test_execskill_mutations.py` file, including both updated anchors,
matches its starting hash. The three protected documents, `V29-PROMPTS.json`, policy bytes and both
configurations' generated prompt/policy pins are unchanged, verified against
[FIX-v29-2-ADDENDUM-INITIAL-SHA256.json](FIX-v29-2-ADDENDUM-INITIAL-SHA256.json) and
[FIX-v29-2-PROMPT-PINS-BEFORE.json](FIX-v29-2-PROMPT-PINS-BEFORE.json).
[V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json) now pins 46 source/test/harness files, including the
preserved mutation catalogue; [FIX-v29-2-SOURCE-BEFORE.json](FIX-v29-2-SOURCE-BEFORE.json) preserves the
prior map and [FIX-v29-2-ADDENDUM-SOURCE-BEFORE.json](FIX-v29-2-ADDENDUM-SOURCE-BEFORE.json)
preserves the map before the focused-review addendum. No prompt/schema/policy literal, sampling bound,
agreement matching rule or cost/cap formula changed.
Network requests, experiment model calls, paid usage and commits remain zero. No new owner decision or
protocol deviation is pending; earlier open decisions remain.

Final offline validation on the delivered files:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| All v29 tests (348 cases) plus fourteen earlier frozen fingerprints | **362** | **0 / 0 / 0** |
| v24–v29, Zebra and ALF selections | **1,299** | **0 / 0 / 0** |

All sixteen frozen fingerprints remain unchanged. The reply-part module now contributes 198 cases across
both configurations, 64 more than before the addendum. These cover valid S1 plus a malformed duplicate,
retaining both shared flags without an unnecessary retry; a separately forced worse retry preserving
the first attempt; repeated malformed duplicates never confirming an abstained note; whole-note
abstention; valid/malformed duplicate order; complementary invalid fragments; consistent coverage and
retry selection; and explicit findings coverage gates. Four smoke/counting cases cover the complete
S3a failure reproduction and record measurements. The v29-1 regression cases pass. Registered/full-repository and Linux mutation suites were
not rerun; the coordinator's mutation changes were preserved by byte comparison.

Exact final commands (logs share each receipt's basename):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/fix-v29-2-addendum-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/fix-v29-2-addendum-selected-validation.json
```

Evidence: [addendum validation and hashes](FIX-v29-2-ADDENDUM-VALIDATION.json),
[targeted receipt](fix-v29-2-addendum-targeted-validation.json) /
[log](fix-v29-2-addendum-targeted-validation.log),
[broad receipt](fix-v29-2-addendum-selected-validation.json) /
[log](fix-v29-2-addendum-selected-validation.log).
Earlier receipts remain archived. The pre-addendum `fix-v29-2-delivered-*` runs passed 298 targeted
and 1,235 broad tests; [their validation](FIX-v29-2-VALIDATION.json) describes the superseded partial-note
semantics, not the delivered addendum behavior. The intermediate `fix-v29-2-final-*` runs collected an earlier
deep-nesting test assumption and reported two failures; the portable test now checks safe retry/cache
and persistence without requiring rejection of JSON that the active decoder can serialize. Those runs
are superseded by the delivered selections above. Final hash/anchor comparisons, handoff links,
`git diff --check` and absence of repository `.v29-*` scratch were checked.

## v2.9.1

Implemented [BRIEF-v291-fault-feedback.md](BRIEF-v291-fault-feedback.md) as two new configurations,
`zebra-pc-v8` and `alfworld-v5`, with feature family `v2.9`. The rules were written in
[V291-PREREG.md](V291-PREREG.md) before the offline fixtures and before any v2.9.1 model run.
No experiment, model call, network access, remote access or paid usage was performed. The reported real
v2.9 failures are motivation supplied by the coordinator; the checks below are engineering evidence only.

Implementation files changed in this increment:

| Files | Functions and behavior |
| --- | --- |
| `skillopt/execskill/replay.py`, new `fault_feedback.py` | Opt-in C6 capture in `_Run.call`, `fault`, `render`, `show`, `replay` and `zero_crash`; `CapturePredicate`/`predicate_capture` retain C6b arguments; `summarize` groups distinct-item evidence and `lint_details_ok` validates next-round diagnostics. |
| `skillopt/execskill/engineer.py`, `engineer_v28.py`, new `engineer_v291.py` | `check` and `_routing_checks` enable captures only for the children; `_ask` selects new prompts; `run` invokes `repair` after fatal fixes and before audit1; `advisory_feedback` enriches C6 lint. Context validators accept only the new bounded fields for v2.9.1. |
| `skillopt/execskill/step.py` | `_feedback`, `_procedure_fault_feedback`, `_format_example`, `_format_feedback` expose fault/format evidence; `_line` uses the kept attempt and adds verdict counts; `_train` uses per-configuration patience. |
| `skillopt/execskill/profiles.py`, `protocol.py`, `v29_limits.py` | Child identities, tables, evidence/record labels, `is_v291`, `train_patience`, call budgets and six-round reservations. |
| `skillopt/execskill/manifest.py`, `confirm.py`, `evaluation.py`, `smoke.py`, `v29_smoke.py`, `scripts/run_execskill.py` | New prompt/feature/ALF registration pins, confirm freshness, final evaluation fields, measured role projection and request floor, cached S3c, CLI choices. Generic prelaunch, routes and ALF confirm-view implementations already support these feature-family children; tests exercise them without modifying those files. |
| Five new `tests/test_execskill_v291_{faults,engineer,feedback,profile,smoke}.py` modules | 92 cases covering the new rules and both configurations. Two existing v29 profile/manifest-smoke tests now account for new family members and the child ALF registration key while retaining parent assertions. |

Handoff additions are the pre-registration, [exact prompts and hashes](V291-PROMPTS.json),
[initial preservation hashes](V291-INITIAL-SHA256.json), [parent snapshot](V291-PARENTS-BEFORE.json),
[previous source map](V291-SOURCE-BEFORE.json), validation receipts/logs and this section.
[V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json) now pins 53 source/test/harness files. The coordinator's
mutation catalogue is unchanged: all 139 protected anchors still occur exactly once, including the
two previously corrected anchors. The three protected living documents were not edited.

The exact repair rule is:

1. After the fatal-check fix loop, a coded change is eligible iff its selected attempt passes every fatal
   check and is not deferred. Inert-by-fault changes are eligible. `fired` is the union of task IDs with
   `applies == True` or default application across both C6 passes and C6b. `faulted` is the union of those
   fired IDs with a non-informational fault in any of those observations. A predicate fault counts when
   that item applied in another observation; a predicate that never applies does not manufacture firing.
2. Trigger iff `faulted >= max(1, ceil(fired / 10))`. Make at most two calls per change, labeled
   `fault-repair/<n>/<k>`, without consuming `TRAIN_FIXES`. The request includes entry/source and the
   captured evidence. Parsed replies are checked by the normal `e.check()` path. The existing one
   format-only retry is available for an unusable repair reply and is separately budgeted.
3. Keep a repair iff all fatal checks pass, it is not deferred, and its distinct faulted-item count is
   **strictly lower** than the best version's. Continue only while the trigger still holds, the preceding
   repair was kept, and the two-call/budget limits permit another call. A tie, worse repair, failed check,
   deferred result or unusable reply retains the best version. Its inert/deferred/lint state and audit
   replay evidence are retained too; discarded checks cannot overwrite the evidence audit1 will see.
4. Per-change `fault_repair` records initial and final trigger numbers, requests/call IDs, parsed and
   checked flags, fatal-check/deferred result, `faulted_after`, `kept`, `kept_index` and stop reason.
   Index zero is the original; later indices number repair calls. `kept_attempt` locates the selected
   report among all check attempts. Stop reasons are `not_triggered`, `fixed`, `no_improvement`,
   `failed_checks`, `unparseable`, `no_calls_left` and `limit`. Ineligible coded changes are marked
   `eligible: false`, with no repair calls. Unit totals include `fault_repair_calls`.

Evidence groups up to five signatures by `(hook, kind, exc_type, message[:300], line)`, ordered by
distinct faulted-item count with deterministic ties. Each includes item count, first numeric step, up to
two task IDs, source line/context ±2 where available, and cap measurements plus declared and bench caps.
Per-hook counts also deduplicate task IDs. One call from the most frequent signature supplies actual
pre-execution arguments; small JSON values are exact, including ALF `state: null`. Larger values use an
explicitly labeled JSON-prefix wrapper whose entire serialization stays within 4,000 view characters
and 1,000 state characters. Cap drops include field dimensions/limits as well as measured text length.

C6 lint adds `fired_items`, `faulted_items`, top-three signatures and `dropped_notes` with event count and
top-three reasons, excluding retained `audit_keyword` hits. Training fault summaries union cell and
trajectory-shell faults and deduplicate cells per procedure/signature; they use
`(hook, kind, exc_type, message[:200])`, top-three counts and a seeded run-only example task ID. Aggregate
counts include measured generated cells; a generated-only signature gets no disclosed task ID.
Informational drops are not fault cells. Format feedback copies verdict `S`, `S'`, margin and blocked
state, plus at most two seeded run-only items with a candidate format violation and no incumbent-cell
violation. Examples contain recorded diagnostic text (or the serialized recorded format mapping,
never a new judgment), first 300 characters, actual delivered notes up to 600 characters and the last
600 characters of the actual candidate reply. ALF uses the actual reply, not an episode outcome summary.
Validators bind these examples to the corresponding candidate trajectory. History adds
`own_fault_cells` and `format_cells`; unevaluated rounds report zeros.

Patience is four for the children and remains two for all older configurations. Six rounds, the
candidate-only counting rule, adoption reset, confirm/adoption/format rules, audits, solver route and
splits are unchanged. Freshness labels, root strings and namespaces are the exact values in
[V291-PREREG.md](V291-PREREG.md); neither new nor old `/data` roots were accessed.

Cap formulas, in ledger token units rather than a monetary forecast:

- Both unit call budgets add `MAX_CHANGES * (2 * FAULT_REPAIRS + 1) = 3 * 5 = 15`: six fault-repair
  calls, six possible repair-format retries, and three audit-fix format retries. Single-mode rises
  `16 → 31`; training rises `26 → 41`. The extra nine format reservations beyond the mandated six
  repair calls close otherwise reachable budget exhaustion; `TRAIN_FIXES = 3` is unchanged.
- Let `R(b,m) = 4 * (b + 512 + m)`. Full engineer payload plus system allowance gives
  `R_e = R(220000 + 16000, 32768) = 1,077,120`; ordinary roles use
  `R_o = R(220000, 16384) = 947,584`. Six rounds reserve `6*(41+4) = 270` engineer/analyst calls,
  `6*3*(1+3+2+1) = 126` leakage adjudications, and `min(24,6*3) = 18` describer calls.
  Engineer scope is `270*R_e + (126+18)*R_o + R_e = 428,351,616`, including a next-call reserve.
  Each child's total role cap is its parent's plus `373,058,944`.
- ALF self-test scope covers `6*2*(60*1+40) + 2*2*40 = 1,360` cells: six training rounds and the
  conservative two final self-test passes. Its cap is
  `ceil_to_100000(3*(1360*45000*(8/5) + 16*392192)) = 312,600,000`.
  Both self-test and redo reserve rise by `103,600,000`, making the solver cap
  `1,013,700,000 + 2*103,600,000 = 1,220,900,000`. Zebra already covers 720 training cells;
  its self-test, redo and solver caps remain unchanged.
- Confirm remains `6*2*40 = 480` cells per configuration. Judge call maxima remain 600 per judge
  for Zebra and 720 for ALF. `v29_limits.identity`, measured S-E6 role projection and manifest features
  bind the new child formulas; parent ledgers and prompts retain their original values.

| Child | Single / train calls | Engineer role | Total role cap | Self-test / redo | Confirm | Solver cap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `zebra-pc-v8` | 31 / 41 | 428,351,616 | 1,625,560,448 | 43,300,000 | 37,200,000 | 272,200,000 |
| `alfworld-v5` | 31 / 41 | 428,351,616 | 1,845,116,288 | 312,600,000 | 128,700,000 | 1,220,900,000 |

Exact new prompt additions (full generated systems and raw UTF-8 hashes are in `V291-PROMPTS.json`):

> `state` is None at step 0 and stays None until your `alf_after_step` returns a value. The first fault
> of a procedure (exception, timeout, note over a cap, oversized state) disables it for the rest of that episode.

> Faults (exceptions, timeouts, notes over `max_note_chars` or the bench cap, oversized state) suppress
> that item's notes. They are reported back with exception type, message, source line and an example
> input; a change that faults on at least 10% of the items where it fires gets up to 2 fault-repair calls.

> Fix these faults so the procedure runs without raising and its notes fit the caps; keep its intended
> behaviour; return the corrected change in the usual format.

The first addition is ALF-only; the second applies to both benches. The third is the repair instruction
and system suffix. Training systems say `Up to 6 training rounds, patience 4`; single-mode systems add
`Training, when used, has patience 4 over at most 6 rounds.` Configuration/version text names the child
and v2.9.1. Parent `V29-PROMPTS.json`, generated prompt maps and policy bytes remain unchanged.

S3c authors Zebra's `view["question"].splitlines()[999]` or ALF's `state.get(...)` at step zero, checks
the change with real C6 mechanics, and makes exactly one fault-repair engineer request with format retry
disabled for this substage. Passing requires the triggered all-item fault, exception type/message/line,
source/context and example arguments (ALF state null), plus a measured engineer call whose reply was
parsed and checked. Neither fatal-check success nor a lower repaired fault count is a pass condition;
the latter is recorded as information. S3c is independently cached and included in S3's pass/measurement
aggregation. Tests use authored fake endpoint replies; no real S3c was run.

Final offline validation:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| All v29/v291 tests plus fourteen earlier frozen tests | **454** | **0 / 0 / 0** |
| v24–v29/v291, Zebra and ALF selections | **1,391** | **0 / 0 / 0** |

The targeted selection includes 92 new v2.9.1 cases, all sixteen historical frozen fingerprints,
and explicit unchanged v7/v4 parent registration/prompt/budget comparisons. New test counts by module:
faults 23, engineer 23, feedback 18, profile 13, smoke 15. Full repository and Linux mutation suites
were not run; all 139 mutation anchors were checked without changing the catalogue. Test scratch is
under `/tmp` or `TMPDIR`, and no `.v29-*` directory remains in this working copy.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v291-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v291-selected-validation.json
```

Evidence: [validation summary and hashes](V291-VALIDATION.json),
[targeted receipt](v291-targeted-validation.json) / [log](v291-targeted-validation.log),
[broad receipt](v291-selected-validation.json) / [log](v291-selected-validation.log).
Initial focused feedback fixtures had six test failures (missing ALF-qualified fixture IDs and missing
fixture reference inputs); the corrected focused run passed all 18, and final selections supersede it.
No new owner decision or protocol deviation is pending. The implementation choices above make explicit
the predicate denominator, truncation representation, generated-cell counts with run-only examples,
and conservative format/role/self-test reservations. Earlier open decisions remain; real-run effects
and real S3c completion remain unmeasured.


### Fixes after review

Implemented items 1–3 of the [focused-review addendum](BRIEF-v291-fault-feedback.md).
The source/context duplication that could push next-round lint beyond the payload ceiling is
now bounded in `fault_feedback.summarize` and `bound_diagnostics`; counts and repair decisions
still use every captured observation. Each `source_line` and context `text` is at most 200
characters, including the visible `... [truncated]` marker. Context line numbers already shown
by an earlier signature are omitted from later signatures.

`serialized_bytes` measures the actual `json.dumps(..., ensure_ascii=False, sort_keys=True)`
UTF-8 output, including default separator spaces and JSON escapes. The C6 lint extension
projected by `lint_extension` (`signatures`, `dropped_notes`, and optional `truncated`) is capped
at 4,000 bytes per change; the complete repair `evidence` is capped at 16,000 bytes. To fit,
remove lower-ranked signatures from the tail, retain the most frequent one if possible, then
remove context lines, then shorten the largest example arguments with a byte-aware JSON-prefix
wrapper. Small values and null state stay exact. A defensive fallback omits remaining oversized
signature/reason/identifier/example metadata rather than inventing shortened task IDs; pathological
hook metadata can also be omitted. Fired/faulted counts and trigger decisions are preserved.
Truncation or omission is explicitly recorded with `truncated: true`, including source clipping,
context deduplication, signature limits and already-truncated captured arguments. View/state
serialized-character limits remain 4,000/1,000 in addition to the aggregate byte cap.

`engineer_v28.advisory_feedback` propagates the bounded extension and truncation flag;
`engineer._lint_entry` and `fault_feedback.lint_details_ok` accept that flag only on the v2.9.1
C6 extension and reject oversized extensions or source/context text. Training-feedback fault
messages remain capped at 200 characters; format detail/notes/reply tail remain at 300/600/600.
Repair thresholds, strict keep rules, patience, role/cell caps and S3c criteria are unchanged.

`engineer_v291.note_caps_rule` generates one sentence from all relevant `notes.FIELD_TYPES`
values, the binding-key list and `profiles.MAX_NOTE_CHARS[bench]`. Both child train/single
systems include it; separate `<configuration>/note_caps` pins are added to the full prompt map.
The exact generated sentences are:

`zebra-pc-v8`:

> Note caps: facts/warnings items ≤ 200 characters each, candidates ≤ 120 characters each, table ≤ 20 rows × 12 columns with cells ≤ 40 characters, bindings name/quote/value ≤ 200 characters each; a field over its cap is dropped whole and counts as a fault; rendered notes must also fit `max_note_chars` and the ZebraLogic bench cap of 4,000 characters per request.

`alfworld-v5`:

> Note caps: facts/warnings items ≤ 200 characters each, candidates ≤ 120 characters each, table ≤ 20 rows × 12 columns with cells ≤ 40 characters, bindings name/quote/value ≤ 200 characters each; a field over its cap is dropped whole and counts as a fault; rendered notes must also fit `max_note_chars` and the ALFWorld bench cap of 1,500 characters per step.

Refreshed [V291-PROMPTS.json](V291-PROMPTS.json), [V291-PREREG.md](V291-PREREG.md) and
[V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json), now 55 source/test/harness entries. Production
changes are limited to `fault_feedback.py`, `engineer_v28.py`, `engineer.py` and `engineer_v291.py`.
Two new regression modules add 27 cases: `test_execskill_v291_diagnostic_bounds.py` (17) and
`test_execskill_v291_note_caps.py` (10). The latter tests altered live constants as well as the
registered values, including differing facts/warnings caps, so the sentence cannot silently drift.

Stress tests use three coded changes, each with exactly 24,000 UTF-8 source bytes and five fault
signatures, across both configurations and ASCII, four-byte Unicode and quote/backslash text.
They exercise real checks, `advisory_feedback`, next-round `Context`/`payload`, and the actual
`repair`/`_ask` request path with authored fake replies. The existing 64,000-byte package cap permits
two retained 24,000-byte sources, while next-round lint contains all three proposed changes—matching
the review failure. Payloads fit the 220,000-byte user ceiling without raising; each repair request
including its system fits the existing 236,000-byte allowance. Additional tests cover trimming
priority, deterministic counts, nonmutation, source/context bounds and exact small arguments.
No allowance or ledger-cap increase was needed.

Final offline selections after the review fixes:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Targeted v29/v291 plus earlier frozen tests | **481** | **0 / 0 / 0** |
| Broad v24–v29/v291, Zebra and ALF | **1,418** | **0 / 0 / 0** |

All sixteen frozen fingerprints and the v7/v4 parent registration/prompt/budget snapshots remain
unchanged. The three protected living documents, `V29-PROMPTS.json`, policy bytes and the complete
mutation catalogue are unchanged; all 139 anchors still match. Scratch stays under `/tmp` or
`TMPDIR`, with no `.v29-*` directory left in the working copy. No network, model/paid call, remote
access, commit or `dl`/absolute `/data` access was performed. These are offline engineering fixtures;
no real S3c or method-effect result is claimed. No new owner decision or deviation is pending.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v291-fix-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v291-fix-selected-validation.json
```

Evidence: [review-fix validation and hashes](V291-FIX-VALIDATION.json),
[targeted receipt](v291-fix-targeted-validation.json) / [log](v291-fix-targeted-validation.log),
[broad receipt](v291-fix-selected-validation.json) / [log](v291-fix-selected-validation.log).
[V291-FIX-INITIAL-SHA256.json](V291-FIX-INITIAL-SHA256.json) and
[V291-FIX-SOURCE-BEFORE.json](V291-FIX-SOURCE-BEFORE.json) preserve this increment's starting hashes;
[V291-FIX-PROMPTS-BEFORE.json](V291-FIX-PROMPTS-BEFORE.json) preserves the earlier child prompt archive.
The preceding 454/1,391 receipts remain historical pre-fix evidence, superseded by these selections.

### Coordinator fix before commit (2026-10-27 04:0x)

The first dl pre-test of the v2.9.1 diff (sha256 prefix `27afaf88`, 2026-10-27 03:46–03:56) passed 1,528 tests and
failed 2: `test_parent_registrations_prompts_budgets_remain_byte_identical[zebra-pc-v7]` and `[alfworld-v4]` raised
`FileNotFoundError` on `docs/handoff/v29-20261026/V291-PARENTS-BEFORE.json`, because handoff files are not part of the
diff or the dl commit. The coordinator copied that file byte for byte to
`tests/fixtures/execskill/v291_parents_before.json` (sha256 prefix `9265fd7317e4c659`, same as the handoff copy) and
changed both readers (`tests/test_execskill_v291_profile.py`, `tests/test_execskill_v291_note_caps.py`) to resolve it
relative to the test file. No product code changed. Both modules pass locally from the repository root (23 tests) and
from another working directory. The new diff (sha256 prefix `f4a4c106`, 25 files, hash list `2dc7f11d`) also carries
the review-fix round; it is the one committed on dl.

## v2.9.2 — reader tolerance (2026-10-27)

Implemented [BRIEF-v292-reader-tolerance.md](BRIEF-v292-reader-tolerance.md) on
the supplied v2.9.1 working-copy contents, preserving the real reply fixture.
[V292-PREREG.md](V292-PREREG.md) records the rules before any v2.9.2 real run;
no such run was performed. The new configurations are `zebra-pc-v9` and
`alfworld-v6`; both retain all v2.9/v2.9.1 behaviour except the specified opt-ins.
`is_v292` is true only for those two children.

### Files and implementation

- `engineer_reader.py`: `_inline_source` selects non-empty `source`, then `code`,
  removes `code` before normalization, and strips only one complete enclosing
  fence. It logs `inline_code_alias`, `inline_source_unfenced`, and conflicting
  `source` precedence as `inline_source_precedence`. Partial or multiple blocks
  and unfenced text remain unchanged. Child result rows retain the written
  manifest entry in `original`; raw model IDs remain available for selection,
  while actual new procedure IDs continue to be assigned by the host.
- `engineer_reader._selected_entry`, `_source_owners`,
  `_large_retry_source_owner`, and `engineer_v28._retry/read_call`: retry requests
  include the original `change_count`, index, and first string `id`/`revises`
  as `change_id`. Counts survive parseable-envelope errors; genuinely unreadable
  manifests use a null count. Select a single reply entry, otherwise a unique raw
  `id`/`revises` match, otherwise the original position when counts match.
  Non-unique ID matches may still use that positional fallback. Validate only
  the selected entry and its source; sibling schema errors do not reject it.
  Events record `selected_by` and `reply_change_count`, including selected-entry
  failures. Ordinary proposals retain the three-change limit. Oversized retry
  envelopes use bounded source selection rather than the exponential matcher;
  their discarded siblings do not increase proposals or calls.
- New `engineer_v292.py`, plus `engineer._ask` and `engineer_v28.run`: new system,
  retry text, prompt pins and `engineer-v2-9-2` record hash. System text is exactly
  the parent's text with `(v2.9.1)` replaced by `(v2.9.2)`, including the parent
  configuration name in the prose, as the brief requires. Actual configuration,
  manifest and record identities belong to the child.
- `donors.py` and `solver.py`: the live shell and donor checker share return-shape
  types and hook/extra mappings; `expected_shape` generates the explanation from
  those same rules. Prior return values and fault records are unchanged.
- `fault_feedback.py`, `engineer_v291.py`, `engineer_v28.advisory_feedback`,
  `step._procedure_fault_feedback`, and the `engineer.py` lint/training validators:
  only child `output_shape` signatures gain `expected` and `returned`. The same
  explanation reaches lint, repair requests and next-round training feedback.
  Validators require exact generated descriptions and the recorded returned type,
  reject the fields on other faults/older configurations, and enforce prior bounds.
- `v29_smoke.py`: only the child ALF fault fixture returns nested `fields` while
  still faulting on null step-zero state. Zebra content is unchanged. Child S3c
  uses recipe `v292-fault-repair-v1`; parent fixture hashes and cache identities
  stay unchanged.
- `profiles.py`, `protocol.py`, `manifest.py`, `confirm.py`, `evaluation.py`, and
  `scripts/run_execskill.py`: child table copies, identities, neutral freshness,
  prompt pins, records, manifest registration, confirm and CLI plumbing. Existing
  predicate-driven `v29_limits`, smoke, S0, prelaunch, routes and ALF confirm views
  inherit the new children without edits to those modules.
- Five regression modules under `tests/test_execskill_v292_*.py`; the parent
  snapshot is `tests/fixtures/execskill/v292_parents_before.json`. Tests read their
  fixtures under `tests/`, never from the unshipped handoff directory.

### Prompts, caps and identities

The exact new retry text and all ten child prompt texts/hashes are archived in
[V292-PROMPTS.json](V292-PROMPTS.json) and pinned by the manifest. The instruction
starts: “Return only the change at `change_index` (identified by `change_id` when
given) in the usual format: one JSON manifest with exactly that one change plus
its Python block.” It continues with the schema/parse correction instruction and
unchanged P1–P6 policy. Parent [V29-PROMPTS.json](V29-PROMPTS.json) and
[V291-PROMPTS.json](V291-PROMPTS.json) remain byte-identical.

No budget formula or cap changed. Each child copies its parent's single/train
call budgets 31/41, six-round schedule, patience 4, fault repairs 2, and role/cell
caps. Engineer scope stays 428,351,616; total role caps stay 1,625,560,448 for
Zebra and 1,845,116,288 for ALF. User payload remains 220,000 bytes, engineer
request allowance 236,000 bytes, lint diagnostic extension 4,000 UTF-8 bytes
per change, repair evidence 16,000 UTF-8 bytes, and source/context lines 200
characters. Actual maximum child system-plus-suffix sizes are 4,134 bytes for
Zebra and 4,540 for ALF, inside the existing 16,000-byte system allowance.

Roots, namespaces, real-run labels and the four exact neutral accept/confirm
freshness strings are recorded in the preregistration. Root strings were never
accessed. Sampling, two-judge agreement, audit/confirmation rules, fault repair
thresholds and strict improvement retention are inherited without changes.

### Real-reply findings and validation

The supplied `zpc8_r1_replies.json` remains byte-identical, SHA-256
`5abae2bcdfc7e4722194f0e670d0b6904464a0e66bd9aa4568ae0c6dd8f7142c`.
The child reader recovers both proposal programs, `zebra-solver-v1` and
`zebra-clue-digest-v1`, exactly from their fenced `code` strings. Each retry can
select either requested program by raw ID or, with IDs absent, by position.
The parent still reports `no procedure source block` on both proposal entries
and `format retry must contain exactly the requested change` on the retries.

The brief's suggestion that both retries are fully correct is false. Both
retry solver programs still fail the actual C2 check on `class _Cap(Exception):`
(`module_level` and `statement` / `ClassDef`), at source line 11 in retry 1 and
line 10 in retry 2. The first reply's `routing` declaration is normalized before
C1; a direct pre-normalization structure check is not the final verdict. Both
clue-digest selections pass fatal checks on the authored public fixture but are
inert there (informational C6b/C6c results). This is historical-reply parsing and
offline engineering evidence, not a live rerun or a useful-candidate claim.
No program, hook declaration or fixture was rewritten to manufacture success.

The new tests include 85 reader/retry cases, 30 shape-feedback cases, 7 S3c
cases, 16 profile/plumbing cases and 8 engineer integration cases: **146 new
cases**. Oversized retry tests include 250 entries, complete mappings for all
entries or non-inline source candidates, inherited optional sources, noncoded
changes, and contested incomplete ownership. Small-manifest source matching
keeps at most two distinct selected-owner ties; a 400-block regression checks
that ambiguity remains rejected without unbounded tied-state growth.

Final offline validation against the final source tree:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Targeted v29/v291/v292 plus v28 frozen | **627** | **0 / 0 / 0** |
| Broad v24–v29/v291/v292, Zebra and ALF | **1,564** | **0 / 0 / 0** |

All sixteen historical fingerprints pass, as do the v7/v4 and new v8/v5
registration/prompt/budget snapshots. Protected living documents, the supplied
reply fixture, older prompt archives and all 139 coordinator mutation anchors
remain unchanged. No network, model/paid call, real Docker, remote access,
commit, `dl` or absolute `/data` access was performed. Scratch remains under
`/tmp` or `TMPDIR`, with no `.v29-*` directory in the working copy. No real smoke,
full Linux mutation execution or independent method-effect result is claimed.
No brief item remains unimplemented and no new owner decision is pending; the
historical solver's retained C2 errors above are input findings.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-selected-validation.json
```

Evidence: [final validation summary](V292-VALIDATION.json),
[targeted receipt](v292-targeted-validation.json) / [log](v292-targeted-validation.log),
[broad receipt](v292-selected-validation.json) / [log](v292-selected-validation.log),
[real-reply check probe](v292-real-check-probe.json) / [log](v292-real-check-probe.log).
The interim 1,562-pass broad selection preceded the last two inherited-source
regressions and is retained as `v292-pre-final-selected-validation.*`; the final
selection above supersedes it. The focused shape extension also exercised older
solver/placebo/replay tests (134 passed, 10 Linux-worker skips); those platform
skips are outside the final requested selections.

[V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json) now covers 65 source, test,
fixture and harness files. [V292-INITIAL-SHA256.json](V292-INITIAL-SHA256.json)
and [V292-SOURCE-BEFORE.json](V292-SOURCE-BEFORE.json) preserve starting hashes;
the parent snapshot is shipped under `tests/fixtures/execskill/`. The final
validation summary records exact commands, receipts, prompt/source hashes,
changed production files and preserved-file hashes.

### Addendum G — sandbox cleanup grace

Implemented the cleanup-grace addendum in
[BRIEF-v292-reader-tolerance.md](BRIEF-v292-reader-tolerance.md), with its timing
and recording rules added to [V292-PREREG.md](V292-PREREG.md). Only
`zebra-pc-v9` and `alfworld-v6` receive 120 seconds; all earlier configurations
retain zero grace. No prompt, model-call budget, hook timeout, ready-ping timeout,
or start-retry count changed.

`sandbox.client.cleanup` first performs the same three removal/listing attempts,
with the same one-second pauses and ten-second command limits. Only after those
fail does the extension begin. Its first retry starts at +15 seconds, with later
starts at least 15 seconds apart and no overlapping commands. A pair taking at
least 15 seconds can be followed immediately. Every removal and exact-name
listing uses `min(10, remaining_grace)` as its timeout. Sleep and command time
count toward the 120-second deadline, and a late response cannot become a
confirmation. A successful listing finishing exactly at the deadline is valid;
no command starts at the deadline. Exhaustion raises the same exception class
and message format, with the actual total attempts and elapsed time. The original
cleanup command allowance is `3 × (10 + 10) + 2 × 1 = 62` seconds; the child
extension adds at most 120 seconds, excluding OS scheduling and the separate
existing local-process reaping waits. This adds elapsed-time tolerance, not any
model/token reservation.

`drain_check`/`drain_unit` use the same loop for each valid exact container name
in the initial successful unit-prefix listing. The grace is per lingering
container. Host-side name validation/filtering prevents removal of another unit
or chain even if the CLI filter returns unrelated names. A bare machine-wide
or chain-wide prefix cannot opt into removal. A final prefix check must be clear;
new names appearing after the initial snapshot remain a drain-integrity finding
and are never chased by an unbounded loop. Failed listings never count as
confirmed removal, and an unconfirmed worker retains its live slot.

Each extended confirmation records `container`, `extra_tries`, `extra_seconds`,
and the total cleanup `seconds`. `Worker.cleanups` receives those extra fields
only when grace was used; ordinary cleanup and restart records keep their old
shape. A shared per-unit `cleanup_events` collector captures engineer, replay,
detector/generator and solver workers, plus drain confirmations. This is necessary
for the motivating engineer-start case: merely retaining the worker's in-memory
list would lose that evidence. Confirmation is collected before local process
reaping, so a later reap failure cannot hide the completed removal. `START_TRIES`
remains two; a failed ready ping can take its existing second start only after
the first container's removal is confirmed.

`profiles.cleanup_grace_seconds` supplies the child-only value. Manifest settings,
unit worker/service factories, environment probes, Zebra/ALF S0 workers and
their escape-probe cleanup receive it. Unit completion/status records include
nonempty `sandbox.cleanups`; `sandbox-cleanups.json` sidecars retain confirmations
even if later work or drain fails. The separate evaluation drain path and
environment/S0 probe paths also persist the same evidence. Older settings omit
the new worker/drain keywords and older records omit all new fields. The child
manifest additionally pins `sandbox_cleanup_grace_seconds: 120` in its registered
thresholds; historical registrations and all prompt archives stay unchanged.

Production files changed for G: `sandbox/client.py`, `profiles.py`, `units.py`,
`step.py`, `manifest.py`, `smoke.py`, `smoke_roles.py`, `zebra_smoke.py`,
`alf_smoke.py`, and `evaluation.py`. Two new modules add **79 cases**:
`test_execskill_v292_cleanup.py` (40) and
`test_execskill_v292_cleanup_plumbing.py` (39). The existing
`test_execskill_v292_smoke.py` changes only the child fake worker to accept and
assert the newly forwarded options. Cases cover the same failed-ready-ping
scenario with zero versus positive grace, timing/exhaustion and failed listings,
foreign/malformed/newly appearing names, live-slot retention, cleanup evidence
before reap failure, actual engineer service rebinding, completed/paused units,
evaluation, and environment/S0 success and failure records.

Focused checks passed: core cleanup **40**, plumbing plus profiles/fingerprints
**91**, and additional historical sandbox/solver/cell tests **89 passed with 30
Linux-worker platform skips**. An intermediate Step fixture omitted its temporary
`slot_root`; the offline guard blocked both ALF cases before protected-path access.
The fixture now binds the lock under `tmp_path`, and the preserved
[initial receipt](v292-g-plumbing-initial-validation.json) /
[log](v292-g-plumbing-initial-validation.log) is superseded by the passing
[plumbing receipt](v292-g-plumbing-validation.json). This was a fixture setup
error, not a grace/runtime failure or an authorized data-path operation.

Final G selections against the final source tree:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Targeted v29/v291/v292 plus v28 frozen | **706** | **0 / 0 / 0** |
| Broad v24–v29/v291/v292, Zebra and ALF | **1,643** | **0 / 0 / 0** |

All sixteen historical fingerprints and the v7/v4 and v8/v5 parent snapshots
pass. The three protected living documents, supplied real-reply fixture, all
three prompt archives and all 139 mutation anchors remain unchanged. The source
hash map now has **68 entries**. No network, model/paid call, real Docker, remote
access, commit or protected data-path access occurred; the test guard refused
the fixture's attempted default lock before access. Scratch remains under
`/tmp` or `TMPDIR`, with no `.v29-*` directory in the working copy. No brief item
remains unimplemented or new owner decision is pending. Real daemon behaviour
and the paused running chains were not exercised or changed.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-g-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-g-selected-validation.json
```

Evidence: [updated validation summary](V292-VALIDATION.json),
[targeted receipt](v292-g-targeted-validation.json) / [log](v292-g-targeted-validation.log),
[broad receipt](v292-g-selected-validation.json) / [log](v292-g-selected-validation.log),
[core cleanup receipt](v292-g-cleanup-validation.json), and
[supplemental sandbox receipt](v292-g-sandbox-validation.json).
[Starting hashes](V292-G-INITIAL-SHA256.json),
[prior source hashes](V292-G-SOURCE-BEFORE.json), and
[prior validation summary](V292-G-VALIDATION-BEFORE.json) retain the pre-G state.
The earlier 627/1,564 receipts remain historical evidence, superseded by G's
706/1,643 selections.

### Addendum H — sandbox ready timeout and start latency

Only `zebra-pc-v9` and `alfworld-v6` now pass
`ready_timeout_seconds=90` to their workers. `Worker` still defaults to
`SANDBOX_READY_SECONDS=20`. `_handshake` uses the per-worker value for its first
ping on every container start, including the existing start retry and worker
replacement after a lost call. Loads and later pings remain 20 seconds;
procedure calls retain their timeout plus the existing 10-second reply grace.
`START_TRIES` stays two, with the same slot ordering, release rules and Addendum
G cleanup behavior. The two attempted first-ping waits can therefore consume
`2 × 90 = 180` seconds instead of `2 × 20 = 40`; this is not an end-to-end bound
including slot waits, loads, daemon queries, cleanup or local process reaping.
The G cleanup allowance remains `3 × (10 + 10) + 2 × 1 + 120 = 182` seconds.
No model-call/token cap, cost estimate, prompt, sampling or agreement rule
changes; validation cost is zero paid/model calls.

`Worker.starts` records `{container, seconds, ready_timeout_seconds, ready}`
when a non-default ready timeout or explicit `start_events` sink opts in.
`seconds` is rounded to three decimals and spans host `docker.spawn` invocation
through the first ready-ping answer, excluding runner preparation, live-slot
waiting, load and cleanup. This is the host-observed create/start-to-ready
interval, not a queried Docker daemon event timestamp. A valid worker identity
sets `ready=true`; a failed start or invalid/missing ping sets `ready=false`
and records elapsed time to failure. A successful ping followed by a failed
load still has its successful ready latency. Records enter the collector
before subsequent load/cleanup errors, and a never-started worker contributes
no event. Default workers leave `starts` empty and older records omit the field.

`profiles.ready_timeout_seconds` supplies the child-only setting; manifest
thresholds pin `sandbox_ready_timeout_seconds: 90`. Manifest settings/services,
unit/cell factories, Step service rebinding and environment/S0 workers forward
it. The shared per-unit `start_events` sink retains engineer, replay,
detector/generator and solver starts. Nonempty `sandbox.starts` appears beside
restarts/cleanups in shell/cell evidence, unit completion/status, environment,
S0 and smoke summaries. Cell records retain the originating step. Read attempts
and other failure paths persist `sandbox-starts.json`; environment probes use
`<manifest>.sandbox-starts.json`. Cleanup events and their sidecars retain
their previous shapes. The child environment validator checks the event's
exact fields, valid container name, finite nonnegative latency, boolean outcome
and registered 90-second limit. Older manifests continue to reject this added
environment block.

Production files changed for H: `sandbox/client.py`, `profiles.py`, `units.py`,
`step.py`, `manifest.py`, `smoke.py`, `evaluation.py`, `solver.py`, and `cells.py`.
Three new test modules add **78 cases**: `test_execskill_v292_ready.py` (22),
`test_execskill_v292_ready_plumbing.py` (49), and
`test_execskill_v292_start_records.py` (7). The existing child smoke fake in
`test_execskill_v292_smoke.py` additionally asserts the ready timeout and start
collector arguments.

Fake Docker/container/clock tests exercise the required 30-second start:
default/explicit 20 seconds fails after the two existing tries; 90 seconds
succeeds. They cover both start attempts, replacement after call loss, unchanged
load/later-ping/call deadlines, slot waiting excluded from latency, failed
spawn/identity/cleanup, parent options, shared collectors, and durable evidence
on completed and failed units, environment, S0 and read paths. Focused receipts:
**22 passed** core; **95 passed** plumbing plus prior cleanup/smoke fixtures;
**50 passed, 1 platform skip** shell/cell records plus legacy solver/cell tests.
An initial plumbing assertion expected the manifest validator to reject an
infinite latency; canonical JSON sealing correctly rejected it earlier. Only
the assertion's expected error changed. The preserved
[initial receipt](v292-h-plumbing-initial-validation.json) records 94 passes and
that one fixture assertion failure; the passing plumbing receipt supersedes it.
There were no H protected-path attempts or implementation failures in that run.

Final H selections against the completed source tree:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Targeted v29/v291/v292 plus v28 frozen | **784** | **0 / 0 / 0** |
| Broad v24–v29/v291/v292, Zebra and ALF | **1,721** | **0 / 0 / 0** |

All sixteen historical fingerprints and the v7/v4 and v8/v5 parent snapshots
pass. The protected living documents, supplied real-reply fixture, three prompt
archives and full mutation catalogue are unchanged; every one of the 139
mutation anchors still occurs exactly once. Prompt archives match current prompt
pins, with no new prompt text. The source map now contains **71 entries**.
No H item is unimplemented and no new owner decision is pending. Validation
remains engineering-fixture evidence: no network, model/paid call, real Docker,
remote access, protected data-path access or commit. Scratch stayed under
`/tmp` or `TMPDIR`; no `.v29-*` directory remains in the working copy. Live
daemon timing and the paused chains were not exercised or changed.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-h-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-h-selected-validation.json
```

Evidence: [validation summary](V292-VALIDATION.json),
[targeted receipt](v292-h-targeted-validation.json) / [log](v292-h-targeted-validation.log),
[broad receipt](v292-h-selected-validation.json) / [log](v292-h-selected-validation.log),
[core ready receipt](v292-h-ready-validation.json),
[plumbing receipt](v292-h-plumbing-validation.json), and
[shell/cell receipt](v292-h-records-validation.json).
[Starting hashes](V292-H-INITIAL-SHA256.json),
[prior source hashes](V292-H-SOURCE-BEFORE.json), and
[prior validation summary](V292-H-VALIDATION-BEFORE.json) preserve the pre-H state.
The G receipts remain historical evidence, superseded by H's 784/1,721 selections.

### Addendum I — reviewed reader ownership and inline-fence fixes

Implemented both findings from the one read-only review round, only on the
v2.9.2 paths for `zebra-pc-v9` and `alfworld-v6`. The only production file changed
is `engineer_reader.py`, in `_large_retry_source_owner` and `_inline_source`.
The other 18 top-level definitions, including `_source_owners`, and the legacy
reply-level `FENCE` expression remain byte-identical to the pre-I file.

**I1:** a complete positional mapping is accepted only when every source-needing
entry in that mapping gets its maximal hook score among all blocks. The score
is overlap with declared hooks, or the count of defined hooks when none are
declared. Thus position only resolves hook ties; two `before_call` programs can
still map by position. If any mapped entry fails this condition, the existing
unique positive hook winner and sibling-competition check apply. Ambiguity
raises `Unusable("ambiguous procedure source blocks; ownership is not unique")`.
Required sources retain priority over optional inherited replacements. Cached
block hook sets keep work linear in blocks times source-needing entries, plus
the entry scan and source parsing; oversized replies never enter the small
exponential matcher. The 1,048,576-byte reply bound is unchanged.

**I2:** inline opening delimiters are parsed independently of their closing
line, consuming the entire opening run. The info string cannot begin with its
delimiter character, and backtick-fence info cannot contain backticks. The first
standalone closing run must use the same character with at least the opening
length and end the trimmed inline value. Shorter/mismatched inner fences remain
body text; an earlier valid close followed by more material prevents unfencing.
Both LF and CRLF are covered. Four-open/three-close values remain untouched;
three-open/four-close values unwrap. Invalid inline values pass unchanged to
normal checks. This does not change the historical reply-level fence parser.

New tests: `test_execskill_v292_owner_agreement.py` (**13**) and
`test_execskill_v292_inline_fences.py` (**70**), **83 new cases** total. No existing
test module was edited for I. The named reviewer regression checks both child
configurations: two entries with reversed external Python blocks retain the
requested hook owner's exact source after adding two inline-source siblings.
Other regressions check positional ties, every mapped candidate's score,
competing siblings, bounded hook parsing, both source/code aliases, delimiter
lengths, backtick info, nested inner fences, CRLF, parent parsing and the real
engineer replies.

The exhaustive ownership test uses a two-hook alphabet (neither, A, B, A+B),
one to three source-needing entries, all declared-hook vectors, every
required/inherited mask, every selected index, parent versus selected-fix
inheritance, every 0–3-block hook multiset and labeled-block permutation, plus
all permutations of four blocks carrying the four hook sets. Each unambiguous
small result is compared against minimal appended, larger appended, and
prefix/interleaved inline padding. There are **423,852 baseline cases**,
**312,960 unambiguous small results** (including no-block/inherited outcomes),
and **938,880 enlarged comparisons**: **335,190 identical mappings**,
**603,690 conservative rejections**, and **zero different owners**. Another
72 permutations exercise a small envelope already containing an inline sibling.
Actual AST hook parsing is cached during enumeration, not replaced with
invented hook scores. These are exhaustive counts for the stated finite domain,
not a claim about live model success rates.

Focused selections passed: ownership **13**, inline-fence plus existing v292
reader **155**, and existing v292/v28 reader selections **145**, all with zero
failures or skips. The supplied real-reply bytes remain unchanged: their selected
solver programs still fail actual C2 on `class _Cap(Exception):` at retry lines
11 and 10; these reader fixes do not repair that code. Prompt texts/archives,
model-call and token caps, cost estimates, judge sampling/agreement, and the
G/H sandbox rules are unchanged. Validation made zero paid/model calls.

Final I selections against the completed source tree:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Targeted v29/v291/v292 plus v28 frozen | **867** | **0 / 0 / 0** |
| Broad v24–v29/v291/v292, Zebra and ALF | **1,804** | **0 / 0 / 0** |

All sixteen historical fingerprints and the v7/v4 and v8/v5 parent snapshots
pass. The three protected living documents, supplied real-reply fixture, three
prompt archives and mutation catalogue remain unchanged; all 139 mutation
anchors occur exactly once. The refreshed source hash map has **73 entries**.
No Addendum I item remains unimplemented and no new owner decision is pending.
All evidence is offline engineering validation: no real model, network, Docker,
remote access, protected data-path access or commit. Test scratch stayed under
`/tmp` or `TMPDIR`, with no `.v29-*` directory left in the working copy.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-i-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v292-i-selected-validation.json
```

Evidence: [validation summary](V292-VALIDATION.json),
[targeted receipt](v292-i-targeted-validation.json) / [log](v292-i-targeted-validation.log),
[broad receipt](v292-i-selected-validation.json) / [log](v292-i-selected-validation.log),
[ownership receipt](v292-i-agreement-validation.json) /
[exhaustive-count log](v292-i-agreement-validation.log),
[inline-fence receipt](v292-i-fences-validation.json), and
[existing-reader receipt](v292-i-reader-validation.json).
[Starting hashes](V292-I-INITIAL-SHA256.json),
[prior source hashes](V292-I-SOURCE-BEFORE.json), and
[prior validation summary](V292-I-VALIDATION-BEFORE.json) preserve the pre-I state.
The H receipts remain historical evidence, superseded by I's 867/1,804 selections.

## v2.9.3 — whole-proposal retries and selecting the one manifest

Implemented J1–J4 of [the v2.9.3 brief](BRIEF-v293-envelope-retry.md) for
`alfworld-v7` (parent `alfworld-v6`) and `zebra-pc-v10` (parent `zebra-pc-v9`).
The [preregistration](V293-PREREG.md) was written before any v2.9.3 real run.
Both children inherit `is_v29`, `is_v291`, `is_v292`, every A–I rule, the
120-second cleanup grace and 90-second first-ready timeout; only these two
configurations satisfy `is_v293`. This is offline engineering validation using
the supplied historical replies, not a new model run or method-effect result.

**J1:** `engineer_v28._retry` treats `change is None` and `index is None` as a
whole-envelope retry only for v2.9.3. It passes no selection to the reader,
accepts one to three changes, and records `selected_by: envelope` plus
`reply_change_count` (null only if the retry envelope cannot be read). Empty or
over-three retries are refused. `read_call` retains every usable per-change
result; a broken sibling becomes `{n, reason: unparseable, detail, repairs}`
without another call, because the envelope's one retry is already spent.
Per-change, fix, audit-fix and fault-repair retries retain v2.9.2 selection.
`engineer._ask` and the engineer record dispatch select the new system and
retry pins without sending a new child through the parent's exact-name map.

**J2:** `engineer_reader._read`, only with multiple JSON candidates and
`is_v293`, parses each candidate using `tolerant_json` and chooses it only if
exactly one parsed object has a `changes` key. With zero or multiple qualifying
objects it retains the original error, counting every JSON candidate. Zero or
one candidate follows the previous path. All JSON-candidate blocks are excluded
from source ownership, including unparsable extras; ignored blocks never become
changes, programs or replay tests. Each result gets one
`extra_json_blocks_ignored` repair with the ignored count. Block ownership and
the reply-level fence expression otherwise remain unchanged.

The byte-identical real fixture
`tests/fixtures/execskill/alf6_s3b_replies.json` has SHA256
`6019eae277d6a0673a8ed6de2ce101f4f2d834809489dadb8867829b6db7c2e0`.
Its v7 proposal yields both written identities, `alf_progress_tracker` and
`alf_task_planner`, with their exact nonempty source programs and defined ALF
hooks; the extra advisory array is ignored with count one, and `read_call`
uses no format retry. Forcing the original envelope unreadable and supplying
the real retry answer retains both changes and records an envelope retry with
count two. The v6 context retains `expected one manifest object, found 2`, then
`format retry must contain exactly the requested change` with reply count two;
v5 retains successful retry parsing. These claims concern parsing, not passing
fatal checks or accepted Skills. Written new-change ids remain metadata;
procedure ids are still assigned by the host.

**J3:** all 33 parent-keyed profile tables are inherited, with independent
mutable copies and only the registered identity changes. The roots are the
strings `/data/execskill-20261027-alfworld-v7` and
`/data/execskill-20261027-zebra-pc-v10` (never accessed), manifest paths append
`-manifest.json`, and namespaces are `G-alf7`/`D-alf7` and `G-zpc10`/`D-zpc10`.
Real labels are `alfworld_v7_real_run` and `zebra_pc_v10_real_run`; engineer
records use `engineer-v2-9-3`. Freshness labels are exactly those in the brief
and preregistration. ALF v7 confirmation-view preparation and S0 reject parent
configuration artifacts. Route, prelaunch, smoke and read-arm behavior inherit;
the ALF S3c fixture remains the v2.9.2 fixture. CLI choices include both children.
The explicit configuration roster in `evaluation.sealed_cell` also includes
the children, preserving configuration, applies, keyword-hit and returned-model
fields in sealed evaluation records. Actual cell-to-sealed-record regressions
cover the children and their parents.

Production files changed: `profiles.py`, `protocol.py`, `confirm.py`,
`manifest.py`, `evaluation.py`, `engineer_reader.py`, `engineer_v28.py`,
`engineer.py`, new `engineer_v293.py`, and `scripts/run_execskill.py`.
New test modules: `test_execskill_v293_profile.py` (**22**),
`test_execskill_v293_reader.py` (**53**), and `test_execskill_v293_retry.py`
(**41**), totaling **116 new cases**. The parent snapshot is
`tests/fixtures/execskill/v293_parents_before.json`.
The three changed v292 modules are `test_execskill_v292_profile.py`,
`test_execskill_v292_cleanup_plumbing.py`, and
`test_execskill_v292_ready_plumbing.py`: their configuration-roster checks
include the new descendants, and their temporary-path imports use new
`tests/execskill_v293_fakes.py`. Its neutral temporary directory is under
`/tmp` or `TMPDIR`, so plain pytest needs no plugin to avoid in-repository
`.v28-fixtures`. Test inputs and helpers live under `tests/`.

All system prompt text is the exact v2.9.2 parent text with `(v2.9.3)` substituted
for `(v2.9.2)`, retaining inherited configuration prose. The new retry instruction
explicitly distinguishes a null index (whole proposal, replay tests inside each
change, one Python block per change in order) from a numbered index (one selected
change). Its complete text and all pins are in [V293-PROMPTS.json](V293-PROMPTS.json)
and the preregistration. New SHA256 pins:

| Prompt | SHA256 |
| --- | --- |
| Zebra single | `776c295d336b9688959638f4a887451000c670d6f4c5a51a2a4e053ef541cbd5` |
| Zebra train | `35693fff99649a4851a51ded0ed55b42818db27d1c43f0d1832d271c410503e7` |
| ALF single | `954ad9ccdd130c205f5eacfdd93607824b61f2e4ab8a53ac192ce9084ac7884a` |
| ALF train | `f1c2d8c1100ce58580b06e73f46d1db30609f2fb75998e28972fdb7f232213d3` |
| Format retry | `1c282c66f19d7f56a1c4423c4386ed6f0a5ba8e2fe72ca53371d84a9aed545da` |

Existing note-cap, fix, audit-fix and fault-repair texts are inherited. Prior
prompt archives stay byte-identical. No token/call budget or cost formula
changes: 31 single / 41 training engineer calls, four-round patience, at most
two fault repairs, request floor 236,000 bytes and the 16,000-byte system
allowance remain. Engineer-scope reserve is **428,351,616** tokens; total role
caps are **1,625,560,448** for Zebra and **1,845,116,288** for ALF. Judge sampling,
per-unit agreement and G/H sandbox time formulas are unchanged. No extra retry
allowance is introduced; validation incurred no model/paid calls.

Focused validation passed: reader **53** offline and **53** plain; retry plus
its parent regressions **134** offline and the new retry module **41** plain;
final profile/plumbing/frozen selection **142** offline and profile-related
new/changed modules **126** plain. The initial profile fixture mistakenly
parameterized the parent-snapshot test with child identifiers: its two assertion
failures were corrected without changing the snapshot or production code.
Initial offline and plain receipts are retained. The later review found the
sealed-cell roster omission described above; it was fixed and tested before the
final selections. No protected path was accessed in either case.

The starting source-hash list already had one stale entry for
`tests/test_execskill_v292_profile.py`; no production-file entry differed.
`V293-INITIAL-SHA256.json` records the actual starting bytes, while
`V293-SOURCE-BEFORE.json` preserves the supplied list. The refreshed list records
the final test bytes, and the validation summary retains both starting hashes.

Final selections against the completed source tree:

| Selection | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Targeted v29/v291/v292/v293 plus v28 frozen | **983** | **0 / 0 / 0** |
| Broad v24–v29/v291/v292/v293, Zebra and ALF | **1,920** | **0 / 0 / 0** |
| Plain pytest: every new/changed test module, no `offline_pytest` | **220** | **0 / 0 / 0** |

The plain selection covers all six new/changed test modules and explicitly
includes the new fixture-helper module. A final scratch audit found an empty
`.v28-fixtures` directory whose modification time predates this task's starting
snapshot. It was removed; the plain selection was repeated, again passing all
220 tests and confirming it did not recreate the directory. The earlier passing
plain log/XML are retained as `v293-plain-before-cleanup-validation.*`.
No `.v29-*` or `.v28-fixtures` directory remains in the working copy.

All sixteen historical fingerprints and the v7/v4, v8/v5 and new v9/v6 parent
snapshots pass. The supplied real replies, protected living documents, prior
prompt archives and all 139 mutation anchors remain unchanged. The source hash
map now has **80 entries**. No J1–J4 item remains unimplemented; no new owner
decision is pending. No network, real model, paid, Docker or remote calls,
protected data-path access or commits occurred. No live smoke, final procedure
acceptance or method effect is asserted.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v293-targeted-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=docs/handoff/v29-20261026:. \
  python -m pytest -p no:cacheprovider -p offline_pytest \
  tests/test_execskill_v24*.py tests/test_execskill_v25*.py tests/test_execskill_v26*.py \
  tests/test_execskill_v27*.py tests/test_execskill_v28*.py tests/test_execskill_v29*.py \
  tests/test_execskill_zpc*.py tests/test_execskill_alf*.py --tb=short -q \
  --offline-receipt docs/handoff/v29-20261026/v293-selected-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python -m pytest -p no:cacheprovider tests/execskill_v293_fakes.py \
  tests/test_execskill_v293_profile.py tests/test_execskill_v293_reader.py \
  tests/test_execskill_v293_retry.py tests/test_execskill_v292_profile.py \
  tests/test_execskill_v292_cleanup_plumbing.py tests/test_execskill_v292_ready_plumbing.py \
  --basetemp /tmp/execskill-v293-plain-pkzv_35v/cases --tb=short -q \
  --junitxml docs/handoff/v29-20261026/v293-plain-validation.xml
```

Evidence: [validation summary](V293-VALIDATION.json),
[targeted receipt](v293-targeted-validation.json) / [log](v293-targeted-validation.log),
[broad receipt](v293-selected-validation.json) / [log](v293-selected-validation.log),
[plain-pytest receipt](v293-plain-validation.json) /
[JUnit](v293-plain-validation.xml) / [log](v293-plain-validation.log),
[reader receipt](v293-reader-validation.json),
[retry receipt](v293-retry-validation.json), and
[final profile receipt](v293-profile-final-validation.json).
[Starting hashes](V293-INITIAL-SHA256.json),
[prior source hashes](V293-SOURCE-BEFORE.json), and
[prior validation summary](V293-VALIDATION-BEFORE.json) preserve the starting state.
The v2.9.2 validation and its receipts remain historical artifacts.

## Coordinator fix before commit (v2.9.2, 2026-10-27 07:0x)

The dl pre-test of the pre-Addendum-I diff (plain pytest, as in production checks: 1,859 passed, 1 failed) and a plain
local run both failed `tests/test_execskill_v292_profile.py::test_alf_v6_confirmation_preparation_is_distinct_and_s0_rejects_parent_identity`
at its parent-identity `collect_s0` call: this module's `tmp_path` (imported from `test_execskill_v28_profile`) lies
inside the repository, so `collect_s0` refused with "Preparation artifacts live outside the repository" before the
configuration check the test expects. It passed only under the `offline_pytest` plugin. Test-only change by the
coordinator: that one negative call now writes to a resolved temporary directory outside the repository (and asserts
so); the expected refusal and the "nothing written" check are unchanged. No production file changed. All twelve v2.9.2
test modules then passed with plain pytest locally (386 passed).


## v2.9.4 — inert causes and one repair before audit (2026-10-27)

Implemented [BRIEF-v294-inert-feedback.md](BRIEF-v294-inert-feedback.md), K1–K5,
for **zebra-pc-v11** and **alfworld-v8** only. The [preregistration](V294-PREREG.md)
was written before validation. This is offline engineering evidence using authored
public inputs and the supplied historical engineer reply, not a real v2.9.4 smoke,
accepted Skill or method-effect result. No network, model, paid or Docker calls,
remote development/data access or commits were made. The three protected living
documents remain byte-identical to the start of this increment.

### Files, functions and preservation

Before implementation edits, captured
[the eight-configuration parent snapshot](../../../tests/fixtures/execskill/v294_parents_before.json):
zebra-pc-v7/v8/v9/v10 and alfworld-v4/v5/v6/v7, including feature/registration,
full prompt maps, role settings, budgets and call budgets. SHA-256:
`f30ee94f30026ce49e75a92ac2c7673b63646f0b2caca6c6c787bd4db8c9e6fd`.
The start-of-increment file hashes are in [V294-INITIAL-SHA256.json](V294-INITIAL-SHA256.json);
the exact previous source and validation maps are preserved in
[V294-SOURCE-BEFORE.json](V294-SOURCE-BEFORE.json) and
[V294-VALIDATION-BEFORE.json](V294-VALIDATION-BEFORE.json). All prior source hashes
matched the actual starting files. The refreshed [source list](V29-SOURCE-SHA256.json)
contains 88 files.

Changed production files (11):

- `skillopt/execskill/inert_feedback.py` (new): `remember_declaration`, `describe`,
  `_examples`, `_bound`, `causes_ok` preserve raw hooks, derive causes, bound
  evidence and validate the history list.
- `skillopt/execskill/engineer_v294.py` (new): `hook_names`, `hook_rule`, `system`,
  `inert_repair_instruction`, `prompt_pins`, `repair` implement generated prompts
  and the one-call repair.
- `skillopt/execskill/engineer.py`: `_routing_checks` captures empty-return task
  IDs, `check` attaches cause/evidence fields, `_ask` selects the new pinned
  prompt, and `_history_line`/`Context._training_inputs` accept child history.
- `skillopt/execskill/engineer_v28.py`: `read_call` captures the written hook
  declaration before normalization; `run` runs inert repair after fault repair
  and before audit, retains checked attempts, and seals causes/call counts/pins.
- `skillopt/execskill/step.py`: `_line` puts cause names next to inert fate.
- `skillopt/execskill/profiles.py`, `confirm.py`, `manifest.py`, `protocol.py`,
  `evaluation.py`, and `scripts/run_execskill.py`: child tables, identities,
  freshness labels, prompt/repair pins, record kind, sealed-cell metadata and CLI.

New tests: `test_execskill_v294_profile.py` (28), `test_execskill_v294_feedback.py`
(28), `test_execskill_v294_repair.py` (42), `test_execskill_v294_real.py` (9), all
under `tests/`: **107 new cases**. The only modified existing test module is
`tests/test_execskill_v293_profile.py` (22 cases): its exact-v293 roster excludes
the new descendants. No parent expectation or snapshot was rewritten. All
139 mutation anchors remain present exactly once, and the coordinator's mutation
catalogue is byte-identical. No full Linux mutation execution was attempted.

### Implemented causes, bounds and repair rule

Inert checks attach ordered `inert_causes` names and `inert_evidence` keyed by
those names: `no_effect_hook`, `never_fires`, `empty_notes`, `crashed`,
`excluded_bench`, including every applicable cause. Missing-effect-hook evidence
uses the manifest's hooks as written, before derivation; absence remains absent.
It includes up to 32 top-level function names (128 characters each) and exactly
the existing check's effect-hook tuple. ALF includes `alf_before_step` and
`alf_after_step`. Raw declarations fit 1,000 serialized bytes; truncation is
marked. Never-fires uses existing C6b counts. Empty-notes requires fired > 0,
nonempty = 0 and C6c not not-applicable; counts stay exact, and up to two task IDs
identify actual empty returns. Exceptions and missing replays are not sampled
as returned-nothing examples. Exclusion names the current bench.

Crashed uses the existing from-replay condition with at least one applicable
replay, plus existing bounded fault signatures. This avoids inventing a crash
when every predicate returned false, so `never_fires` stays repairable. The
historical inert Boolean is unchanged. Its corner case with no routing items
and all replay predicates false can yield no evidenced cause: `[]` is valid
history and triggers no repair. Tests cover that history round trip explicitly.

Public examples are selected only from this step's verified run entries, never
other steps or generated items. At most two exact task IDs of at most 512
serialized bytes are included; oversized IDs are omitted, never shortened.
Views fit the existing 4,000-character limit. Total evidence fits the actual
request serializer's 16,000 UTF-8-byte allowance, trimming view prefixes and
then function-name entries without changing counts or cause names. Child
outcomes and history carry names only; full evidence stays in checks and repair
requests. Older configurations receive no new fields.

After fatal fixes and v2.9.1 fault repair, a coded change is eligible only when
all fatal checks pass, it is not deferred, it is inert, and it has at least one
of `no_effect_hook`, `never_fires`, `empty_notes`, with neither `crashed` nor
`excluded_bench`. At most **INERT_REPAIRS = 1** call is made per change, purpose
`inert-repair/<n>/1`, with request, bench, change (entry plus source), evidence,
and generated instruction. `read_call(..., change=...)` retains inherited
selected-change/format-retry behavior. `_ask` returning no call stops
`no_calls_left`; the existing engineer budget covers this call and any format
retry.

Keep a repaired change only when every fatal check passes, it is not deferred
and it is no longer inert; then it proceeds through the existing audit and
training path. Otherwise keep the original outcome and restore its audit-replay
cache. Every checked attempt remains in `attempts`; record causes, calls with
parse/check/fatal/inert/kept flags, `kept_index`, and one of `not_triggered`,
`fixed`, `failed_checks`, `still_inert`, `unparseable`, `no_calls_left`.

### Prompts, identities and unchanged caps

The complete texts and hashes are archived in [V294-PROMPTS.json](V294-PROMPTS.json).
Each system uses its exact parent's text with `(v2.9.3)` replaced by `(v2.9.4)`,
then the generated sentence below. Inherited retry/fix/audit/fault prompts and
all earlier prompt archives stay unchanged.

`zebra-pc-v11`:

> The shell calls only top-level functions whose names are exactly the hook names (applies, before_call); declaring a hook in the manifest does not create it; a program that defines no note-writing hook, never applies, or never returns a note has no effect and is not trained.

`alfworld-v8`:

> The shell calls only top-level functions whose names are exactly the hook names (applies, alf_before_step, alf_after_step); declaring a hook in the manifest does not create it; a program that defines no note-writing hook, never applies, or never returns a note has no effect and is not trained.

The repair instruction template is:

> The program had no effect because {causes}. The shell calls only top-level functions named exactly like these hooks: {hooks}; declaring a hook in the manifest does not create it. Return the corrected change in the usual format (same id and kind), keeping its intended behaviour, or withdraw it. P1: no false or overclaiming notes. P2: no answer-format coaching; you may restate requirements the task input itself states. P3: no instruction/scoring overrides. P4: no benchmark answer priors. P5: no outside item facts or hard-coded answers. P6: the program must work as its description says. 

`{causes}` is the ordered evidenced cause list; `{hooks}` is generated from the
registered vocabulary for the bench. Exact rendered per-bench placeholder
texts and full single/train prompts are also in the preregistration/archive.

| Prompt | SHA-256 |
| --- | --- |
| zebra-pc-v11/single | `837d41ade3699a3704ea4558fa1f73a7bb9d39f2dc6baf5909591e22e948be40` |
| zebra-pc-v11/train | `6e08a5d5b0406e142358731030479d7b284a2f011b697ba8ec614108fcd6b40c` |
| alfworld-v8/single | `3b8635b1a7ec03e15ec2a8f2c1d8cef7aaec46a74f3f4237d18452ed9f0e80b6` |
| alfworld-v8/train | `0893085bd8151e9362fea9e18ca7ba1ad721dbee0c674152f6d846d068ea0ae9` |
| zebra-pc-v11/inert_repair | `40326f0b137800520edcaf74ddb1ee344305282ae2c72a7bea37409a27e098f5` |
| alfworld-v8/inert_repair | `e21371f21e11d87adf833ed8907fd970de0d6791729086e7075f4df65cf24faf` |
| inert_repair | `7421db461499aadc6dbae48e1dcac4665c34e65654e42c7aa23a1e298c54d9c1` |

Child root strings are `/data/execskill-20261027-zebra-pc-v11` and
`/data/execskill-20261027-alfworld-v8` (not accessed), with `-manifest.json` paths,
G/D-zpc11 and G/D-alf8 namespaces, `zebra_pc_v11_real_run` /
`alfworld_v8_real_run`, and `engineer-v2-9-4`. Exact freshness labels are pinned
in preregistration and validation. ALF v8 confirm preparation/S0 reject parent
identities. Both inherit A–I/J1–J2, cleanup grace 120 s and ready timeout 90 s.

**No cap/budget formula changed.** Inert repair competes within the inherited
31 single / 41 training engineer calls, two fault repairs, patience four and
six training rounds. Reservations remain
`R(b,m) = 4 * (b + 512 + m)`, `Re = R(236000,32768) = 1077120`,
`Ro = R(220000,16384) = 947584`; engineer scope
`270*Re + 144*Ro + Re = 428351616`.
Total role reservation: Zebra `1625560448`, ALF `1845116288`.
The request floor 236,000 bytes, public payload limit 220,000 bytes and system
allowance 16,000 bytes are unchanged. Offline monetary cost is zero; no new
measured real-run cost or effect estimate is claimed. Sampling, per-unit judge
agreement, acceptance and smoke fixtures are unchanged.

### Validation and limits

- [Targeted receipt](v294-targeted-validation.json) and
  [log](v294-targeted-validation.log): **1,090 passed**, zero failures/errors/skips;
  `tests/test_execskill_v29*.py tests/test_execskill_v28_frozen.py`.
- [Broad receipt](v294-selected-validation.json) and
  [log](v294-selected-validation.log): **2,027 passed**, zero failures/errors/skips;
  all `test_execskill_v24*.py` through `v29*.py`, plus `zpc*.py` and `alf*.py`.
- [Plain receipt](v294-plain-validation.json), [JUnit](v294-plain-validation.xml)
  and [log](v294-plain-validation.log): **129 passed**, zero failures/errors/skips;
  all four new modules plus the modified v293 profile module, with no
  `-p offline_pytest`. Scratch is `/tmp/execskill-v294-plain-yzygvu6p/cases` and
  the neutral OS fixture root. No repository scratch directory remains.

The first two selections use the existing local `offline_pytest` harness,
`PYTHONDONTWRITEBYTECODE=1`, and `-p no:cacheprovider`. All sixteen historical
fingerprints and all earlier/this-increment parent snapshots passed. Focused
receipts: profile 50, feedback 28, repair 42 and real-reply 9. Both real fixture
programs pass actual fatal checks on authored public inputs, initially diagnose
only `no_effect_hook`, then become non-inert after the fake reply adds
`def before_call(view, state): return _run(view)` and each reaches audit after
exactly one inert-repair call. Parent v9/v10 stay inert without new fields or
calls. This does not establish behavior on the real round-5 run slice.

The supplied [real fixture](../../../tests/fixtures/execskill/zpc9_r5_replies.json)
remains byte-identical, SHA-256
`3ad6732695a4a9190dbe490617517c9f0eec04c1299a5ecccd72704fafb80bd7`.
Initial new-test fixture errors were corrected: the public question omitted
the required house-count sentence suffix (nine failures), and two feedback
tests omitted a sufficient state-byte declaration / valid puzzle prefix.
These initial failed receipts are preserved as `v294-real-initial-validation.*`
and `v294-feedback-initial-validation.*`. They did not require production
changes or cause protected-path access. Read-only review also caught the
empty-cause history coherence edge; its fix and regression are included in all
final selections.

[V294-VALIDATION.json](V294-VALIDATION.json) records exact selections, counts,
files, hashes, prompt pins and constraints. No required work was left undone;
no open implementation decisions. Real network/model/Docker experiments were
outside the authorized scope and were not attempted.


## v2.9.5 — larger Zebra search budget, abstention prompt and integer booleans (2026-10-27)

Implemented [BRIEF-v295-search-budget.md](BRIEF-v295-search-budget.md), L1–L5,
for **zebra-pc-v12** and **alfworld-v9**. The [preregistration](V295-PREREG.md)
was written before validation. This is offline engineering evidence using
historical replies and authored inputs, not a real v2.9.5 run, accepted Skill,
or method-effect result. No network, model, paid or real Docker calls, no dl
or absolute /data access, and no commits. The three protected living documents
are byte-identical to the increment's starting copies.

### Files, functions and frozen parents

Before implementation edits, captured
[ten parent configurations](../../../tests/fixtures/execskill/v295_parents_before.json):
zebra-pc-v7/v8/v9/v10/v11 and alfworld-v4/v5/v6/v7/v8, including registration,
features, full prompts, roles and budgets. Snapshot SHA-256:
`3be881ffe0aefdb83f8c8088820dfade774cbe20e1b8cc57da3d474441506de6`.
Initial files and prior maps are archived in
[V295-INITIAL-SHA256.json](V295-INITIAL-SHA256.json),
[V295-SOURCE-BEFORE.json](V295-SOURCE-BEFORE.json), and
[V295-VALIDATION-BEFORE.json](V295-VALIDATION-BEFORE.json). All starting source
hashes matched. The refreshed [source hash list](V29-SOURCE-SHA256.json)
contains **95 files**; old prompt archives and parent fixtures remain unchanged.

Production files changed (13):

- New `skillopt/execskill/engineer_v295.py`: `system`, `prompt_pins`, and
  `ABSTAIN_RULE` pin the exact new sentence and L1-consistent round numbers.
- `skillopt/execskill/engineer.py`: `_ask` dispatch, context round bounds,
  and training payload's `rounds` use the child protocol.
- `skillopt/execskill/engineer_v28.py`: `prepare` propagates the configuration
  into normalization; `run` pins the child system while retaining inert repair.
- `skillopt/execskill/engineer_reader.py`: `normalize` converts exact integer
  booleans only for the children; read/recursive/test normalization propagate
  the configuration. `tolerant_json` is unchanged.
- `skillopt/execskill/step.py`: `training_units`, `Step.units` and `_train`
  support the configured maximum; frozen UNITS_V2/UNITS_V29 stay unchanged.
- `skillopt/execskill/v29_limits.py`: `judge_calls`, `identity`,
  `v291_role_calls`, `extend_v291_profiles` and `extend_v295_profiles` calculate
  round-dependent caps on the new Zebra clone.
- `skillopt/execskill/smoke.py`: `max_role_calls`/SE6 projections and child SX
  unit observation use the configured count.
- `skillopt/execskill/profiles.py`, `protocol.py`, `manifest.py`, `confirm.py`,
  `evaluation.py`, `scripts/run_execskill.py`: helpers/tables, registered evidence,
  prompt/limit pins, identities, freshness, CLI and sealed evaluation records.

New tests under `tests/`: `test_execskill_v295_profile.py` (32 cases),
`test_execskill_v295_rounds.py` (52), `test_execskill_v295_reader.py` (288),
`test_execskill_v295_engineer.py` (32): **404 new cases**. The only modified
existing module is `tests/test_execskill_v294_profile.py` (28 cases); its exact
v294 roster excludes the new descendants. No frozen expectation was weakened.
All 139 coordinator mutation anchors remain present exactly once, with the
mutation catalogue byte-identical. Full Linux mutation execution was not run.

### Implemented round, prompt and reader rules

Only Zebra v12 has `train_rounds = 10` and patience eight. ALF v9 keeps six and
four; all 26 older configuration entries keep their historical six-round
limits and exact unit tuples. Candidate-free rounds do not count against
patience; adoption resets it. Ten rounds remains the maximum. Units include
engineer/train/confirm-r1 through r10 for Zebra; dispatch rejects r11. Engineer
contexts/payloads accept late rounds, manifests and SE6 price them, and monitoring
already enumerates arbitrary unit names recursively (r10 covered by regression).
No separate monitor source change was necessary. Historical six-round constants
remain for frozen tables, tuples and prompts; child execution uses the helper.

Each system is its exact v2.9.4 parent's text with the `(v2.9.5)` tag, plus the
sentence below; Zebra's single/train round-and-patience numbers also change to
10/8 to satisfy L1. Inherited configuration prose and repair/fix/retry/audit
suffixes remain unchanged. The exact new sentence is:

> When a program cannot verify its result on an item, it should return no note for that item: unverified warnings or partial results tend to turn correct answers wrong, and training counts every answer they break.

Full prompt texts/maps are in [V295-PROMPTS.json](V295-PROMPTS.json).

| Prompt | SHA-256 |
| --- | --- |
| zebra-pc-v12/single | `a61c9bac4c472fab60f75f2d971beeea4c1d366a5ff44945e39388da93779176` |
| zebra-pc-v12/train | `e1ec91e308d004dc3c95d9393bcd09700875dd7241a944b57bc7792524444fd7` |
| alfworld-v9/single | `00f3b23438c18d2ee74bfdfe5528513b71ca3dfd25804ea98ae2079570e13478` |
| alfworld-v9/train | `2cbd24cc5370fd18fac34c90f6e992148ae034a3d62a9ca7c55873f563b248c9` |
| abstain | `06d7dcf419258d2744f38d220130e9b1c227a553b6e56ca75f0e0e80a6570e00` |

For v2.9.5 schema booleans only, actual booleans stay unchanged; exact integer
0/1 becomes false/true, logging `{rule: integer_boolean, path, from}`. The rule
covers requests_second_call, claims_fix, repair_requested property.value and
nonvacuity.withheld_expect, including read/retry/nested/direct-check paths.
All configurations also retain the parent's case-insensitive `"true"`/`"false"`
string conversion, logging the same `lossless_type_conversion` repair at the
same path and no integer-boolean repair. Integers 2/-1, floats 0.0/1.0, null
and every other string (including whitespace-padded booleans) remain invalid
for boolean fields. Missing fields retain existing defaults/inheritance. An
opaque state_equals JSON value is not a boolean-only schema and is unchanged,
including int/float/null. No other coercion was added, and incomplete JSON is
never closed or guessed.

**L3 correction before any real run:** the coordinator corrected the brief's
string clause before any real v2.9.5 run. The new children preserve the parent's
case-insensitive `"true"`/`"false"` tolerance and add only exact integer 0/1;
older configurations keep their integer refusal. The earlier offline validation
receipts are archived under [v295-before-string-correction](v295-before-string-correction/ARCHIVE-SHA256.json).
Those tests are engineering evidence, not experiment runs. Regression tests
cover all four boolean schema paths, lower/upper/mixed case, direct checks,
selected retries, and invalid values across every registered configuration.

The supplied [real ALF fixture](../../../tests/fixtures/execskill/alf7_s3b_replies.json)
remains byte-identical, SHA-256
`fad86bf0f48e2acf800ef976962c1443f0dae1f8939a4e5b10f135f378308e94`.
With ALF v9 its `propose` reply parses both `alf_world_state_tracker` and
`alf_command_guard` without a format call, logging the two integer-boolean
repairs. With ALF v7, both original changes still require retries: the first
retry is usable; the second still lacks the final manifest closing brace and
is refused with `manifest JSON: ('unexpected EOF in multi-line statement', (14, 0))`. No fixture was repaired. This establishes reader behavior only,
not fatal-check acceptance or runtime benefit of these two programs.

### Budgets, identities and inherited rules

Let N be the configured round count. Reservation remains
`R(b,m)=4*(b+512+m)`, `Re=R(236000,32768)=1077120`,
`Ro=R(220000,16384)=947584`, `Rj=R(220000,8192)=914816`.
Engineer/analyst calls = `N*(41+4)`, leakage = `N*3*(1+3+2+1)`, describer =
`min(24,N*3)`. Engineer scope = `(engineer_calls+1)*Re + (leakage+describer)*Ro`.
Each judge gets `(N*3*2+24)*prompts_per_audit*2` calls and `(calls+1)*Rj`
reservation, with five prompts per Zebra audit and six per ALF audit.

| Quantity | Zebra v11 parent | Zebra v12 | ALF v9 (unchanged parent) |
| --- | ---: | ---: | ---: |
| Rounds / patience | 6 / 4 | 10 / 8 | 6 / 4 |
| Engineer + analyst / leakage / describer calls | 270 / 126 / 18 | 450 / 210 / 24 | 270 / 126 / 18 |
| Calls per judge | 600 | 840 | 720 |
| Engineer scope | 428351616 | 707515776 | 428351616 |
| Each judge scope | 549804416 | 769360256 | 659582336 |
| Total role scope | 1625560448 | 2343836288 | 1845116288 |
| Training cells in selftest scope | 720 | 1200 | 1360 |
| Confirmation cells | 480 | 800 | 480 |
| Selftest cap | 43300000 | 55500000 | 312600000 |
| Confirm cap | 37200000 | 45400000 | 128700000 |
| Redo reserve | 43300000 | 55500000 | 312600000 |
| Solver cap | 272200000 | 304800000 | 1220900000 |

Zebra training/confirmation cells are `N*2*60` / `N*2*40`. For C cells,
the corresponding cap is `ceil_to_100000(3*(C*5300*(8/5)+16*520192))`, retaining
any inherited selftest floor. Solver cap changes by the two stage-cap deltas
plus the redo-reserve delta. Fixed run/examiner/accept/read terms do not scale.
Per-round engineer caps remain 31 single/41 train; token limits, request floor
236000 bytes, payload 220000 bytes and system allowance 16000 bytes are unchanged.
These are conservative reservation bounds, not measured monetary costs. Offline
paid cost is zero. No real-run cost or gain estimate was produced.

Roots are the new `/data/execskill-20261027-zebra-pc-v12` and
`/data/execskill-20261027-alfworld-v9` strings (not accessed), manifest strings
append `-manifest.json`, namespaces are G/D-zpc12 and G/D-alf9, evidence labels
`zebra_pc_v12_real_run` / `alfworld_v9_real_run`, record kind `engineer-v2-9-5`.
Exact freshness labels are in preregistration/validation. ALF v9 confirm prep
and S0 reject parent identities. Children inherit A–K, 120-second cleanup grace,
90-second readiness timeout, two fault repairs and one inert repair; sampling,
per-unit agreement, training/acceptance gates and smoke fixtures are unchanged.

### Validation, review and remaining limits

- [Targeted receipt](v295-targeted-validation.json) and
  [log](v295-targeted-validation.log): **1,494 passed**, zero failures/errors/skips;
  all v29 modules plus v28 frozen tests.
- [Broad receipt](v295-selected-validation.json) and
  [log](v295-selected-validation.log): **2,431 passed**, zero failures/errors/skips;
  all v24–v29, Zebra and ALF selections.
- [Plain receipt](v295-plain-validation.json), [JUnit](v295-plain-validation.xml),
  [log](v295-plain-validation.log): **432 passed**, zero failures/errors/skips;
  every new/changed module (the four new modules and v294_profile), without
  offline_pytest. Basetemp is `/tmp/execskill-v295-string-plain-wbh4z9qr/cases`; neutral
  identity fixtures use TMPDIR or /tmp. No repository scratch remains.

Targeted/broad use the existing local offline_pytest harness with network,
Docker and protected-path guards, PYTHONDONTWRITEBYTECODE=1 and no cacheprovider.
All sixteen historical fingerprints and earlier/current parent snapshots pass.
Focused receipts: profile 60 (32 new + 28 parent), rounds 52, refreshed reader
288 (also 288 under plain pytest), engineer 32. The string correction adds
150 cases; final targeted/broad/plain selections include the corrected rule. Independent read-only review of runtime caps/SE6 and reader/prompt
propagation found no remaining gap.

Initial receipts are retained: `v295-profile-initial-validation.*` recorded
58 passes/two failures from initially omitted new real-evidence labels (fixed
in the protocol roster); `v295-engineer-initial-validation.*` recorded a new
test collection error from using pytest's reserved parameter name `request`
(renamed only in that test). No protected-path access occurred. Final selections
include both fixes.

[V295-VALIDATION.json](V295-VALIDATION.json) records files, hashes, exact commands,
counts, formulas and constraints. No required work remains unimplemented.
The corrected string clause and the malformed recorded retry are noted
above; no other deviation or open decision. No real network/model/Docker or
method-effect experiment was authorized or attempted.


## v2.9.6 — readable ALFWorld actions, with share diagnostics (2026-10-28)

Implemented the amended [brief](BRIEF-v296-alf-format-rule.md) for
`alfworld-v10` only, extending `alfworld-v9`. No new Zebra configuration.
[Preregistration](V296-PREREG.md) records the amendment, the full superseded
majority-rule draft, all historical counts and the order in which evidence
became available. The first draft used earlier training/confirm records; the
amendment also used ALFWorld v7 acceptance cells, read only after its final
01:10:45 rejection (EXIT 0, J1/J4 failed). No test outcome was read. The new
run reuses the same split-v1 acceptance slices. No older decision is revised.

At 150 acceptance games, S/C/P_y/S' had wins 86/86/88/90, below-9/10 episodes
37/40/46/44, below-half episodes 1/6/8/5, and zero invalid-action reasons.
The old violations' won/lost splits were 19/18, 18/22, 19/27 and 19/25.
S versus duplicate no-candidate C differed by five under the majority rule,
exceeding J4's margin of three. This motivated replacing that draft rather than
counting non-admissible commands as malformed output. The candidate's 12 fixes
and 8 breaks yielded +2.67 points, below J1's +5 bar, so the historical rejection
stands under all three rules. These are coordinator-supplied replay facts,
not experiments or remote/data reads performed by this writer.

### Files, functions and preservation

Production changes:

- `skillopt/execskill/alfworld_format.py` (new): `bind`, `validate` and
  `environment_runtime` bind the exact rule and separate judge identity from
  original environment/reset-view provenance.
- `skillopt/execskill/judge.py`: `judge`, `_format`, `_alfworld_format` select
  the child rule and distinct version, preserving historical output.
- `skillopt/execskill/profiles.py`: `ALFWORLD_V10`, `is_v296`, inherited version
  predicates, `alfworld_format_rule`, cloned tables and exact new identities.
- `skillopt/execskill/manifest.py`: `make`, `check`, `_check_alfworld`,
  `alfworld_features`, `alfworld_registration_key` pin/validate the runtime and
  rule; all historical configurations reject a child-marked ALF runtime.
- `skillopt/execskill/alf_smoke.py`: `collect_s0` pins `judge_runtime` beside
  the original preparation; `make_manifest` checks it; `_slices` and
  `fixture_items` retain original view digests and identical authored fixtures.
- `skillopt/execskill/alf_confirm_views.py`: `validate` compares prepared views
  to the original environment sheet while preserving the child identity.
- `skillopt/execskill/step.py`: `_alfworld_views` and `_confirm_identities`
  validate the configured rule, compare views using the original sheet, and
  retain the bound runtime digest in confirmation episode identities.
- `skillopt/execskill/engineer_v295.py`: `system` delegates ALFWorld v10 to v9
  verbatim; `prompt_pins` remains byte-identical.
- `skillopt/execskill/confirm.py`, `protocol.py`, `evaluation.py` and
  `scripts/run_execskill.py`: freshness, evidence/judge record tags, sealed
  configuration roster and CLI choices.

Four new test modules: `tests/test_execskill_v296_judge.py`,
`test_execskill_v296_consumers.py`, `test_execskill_v296_profile.py` and
`test_execskill_v296_binding.py`. The only changed existing test is
`test_execskill_v295_profile.py`, whose exact v295-roster assertion now excludes
v296 descendants. No coordinator mutation anchor was changed; all 139 still
occur exactly once.

Before implementation edits, captured
[v296_parents_before.json](../../../tests/fixtures/execskill/v296_parents_before.json),
SHA-256 `ed88862d6cb0abed2ff901496edf42a6a5c5511f96ba6a7c2476c99a8b583395`:
Zebra v7–v12 and ALFWorld v4–v9, with full registrations, prompt maps, role
settings, budgets, unit lists and eleven complete K1 judge outputs each. These
all still matched when the amendment arrived, so the snapshot was retained,
not re-captured. All 95 starting source hashes matched their prior archive.
[V296-INITIAL-SHA256.json](V296-INITIAL-SHA256.json),
[V296-SOURCE-BEFORE.json](V296-SOURCE-BEFORE.json) and
[V296-VALIDATION-BEFORE.json](V296-VALIDATION-BEFORE.json) preserve the starting
state. Older fixtures and prompt archives, protected living documents and the
mutation catalogue remain byte-identical. The refreshed source list has 102
entries: [V29-SOURCE-SHA256.json](V29-SOURCE-SHA256.json).

### Exact deciding rule and runtime binding

For ALFWorld v10, unknown cells or episodes without logged steps (including
absent shell) have `format.violation = None`. Every other episode has
`format.violation = (prediction.reason == "invalid_action_format")`.
Readable commands rejected by the game therefore never create a format
violation, even at 0/8 or 3/8 admissible steps. The outcome/win score is unchanged.

The format record keeps `steps`, `admissible_steps` and `violation`, and adds:

- `violation_at_9_10`: the exact historical verdict for the same episode.
- `violation_below_half`: the superseded majority verdict, `None` wherever the
  historical verdict is `None`; otherwise true for invalid-action reason, or
  for logged steps with `2 * admissible_steps < steps`.
- `rule`: `alfworld-readable-action-v2-9-6`.

An invalid-action episode with zero steps has deciding `None` and both
reporting flags `True`; unknown remains `None` in all three fields. This
implements the explicit no-logged-steps precedence while retaining the exact
historical diagnostic. Neither reporting flag is read by any decision.

`profiles.alfworld_format_rule` returns the readable-action name for the child
and `alfworld-admissible-9-10` otherwise. Only the child receives runtime keys
`execskill_configuration = "alfworld-v10"` and `alfworld_format_rule` with the
exact new name. Partial, missing, mismatched and unknown values are refused,
including the first draft's majority-rule name. The manifest pins the entire
sheet and the feature rule by value. Child judge records use scorer
`execskill-judge-v2-9-6` and version `fivebench-execskill-v1-judge-v2-9-6`;
old records keep their tags.

Manifest/S0/setting/cell paths carry that sheet to the judge. Preparation and
pre-reset views keep their original runtime digest, removing only the two
validated judge markers when comparing environment identity. Confirmation
signatures keep the full bound sheet, preventing cross-rule replay reuse.
The S0 sandbox measurement itself contains no ALF format judgment. All actual
judgments in smoke, training, confirmation, self-test, J4, tables and stored
record re-judging use the same central judge rule.

### Inherited prompts, limits and identities

There is no new engineer prompt text or prompt pin. The complete inherited
systems and maps are archived in [V296-PROMPTS.json](V296-PROMPTS.json).
ALF v10 and ALF v9 share the exact single prompt SHA-256
`00f3b23438c18d2ee74bfdfe5528513b71ca3dfd25804ea98ae2079570e13478`
and train SHA-256
`2cbd24cc5370fd18fac34c90f6e992148ae034a3d62a9ca7c55873f563b248c9`.
The record kind stays `engineer-v2-9-5`; reader string/integer booleans,
repair prompts, two fault repairs, one inert repair, sampling and per-unit
agreement are inherited unchanged.

No cap or budget formula changed. Six rounds/patience four; 31 single and
41 training engineer calls per round; 270 engineer+analyst, 126 leakage,
18 describer and 720 calls per audit judge. With `R(b,m)=4*(b+512+m)`, the
engineer scope remains 428351616, each judge scope 659582336 and total roles
1845116288. Solver cap 1220900000, self-test 312600000, confirm 128700000,
redo 312600000; training/confirmation cells 1360/480. All other parent caps,
request floor 236000, payload 220000 and system allowance 16000 are unchanged.
These are reservation bounds, not measured spend; offline paid cost is zero.

Training/confirm margins, self-test's exact sign test, smoke floor/margin,
J4 margin, gain/acceptance bars and `inadmissible_share > 0.2` diagnosis stay
unchanged. Three additional invalid-action episodes in 60 block training,
confirm and J4. At three worsening pairs, the unchanged self-test sign p is
0.125 and the smoke share is exactly its 0.95 margin; those two tests do not
block at that boundary. Six/seven invalid examples exercise their blocking
conditions. The guard remains active; only its deciding format definition changed.

The root is `/data/execskill-20261028-alfworld-v10` (identity string only),
manifest suffix `-manifest.json`, namespaces G/D-alf10, evidence
`alfworld_v10_real_run`. Accept freshness:
`alfworld_split_v1_slices_after_alfworld_v7_accept_v9_stopped`; confirm freshness:
`alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v9_stopped`.
Parent confirm-view and S0 identities are refused. Cleanup grace 120 seconds,
ready timeout 90 seconds, arms, routes and unit roster are inherited unchanged.


### Validation, amendment history and remaining limits

- [Targeted receipt](v296-targeted-validation.json) and
  [log](v296-targeted-validation.log): **1,816 passed**, zero failures/errors/skips.
- [Broad receipt](v296-selected-validation.json) and
  [log](v296-selected-validation.log): **2,753 passed**, zero failures/errors/skips.
- [Plain receipt](v296-plain-validation.json), [JUnit](v296-plain-validation.xml),
  [log](v296-plain-validation.log): **353 passed**, zero failures/errors/skips,
  across all five new/changed test modules, without the offline plugin.

New cases: judge 219, consumers 33, profile 45, binding 24 = **321**. Plain
also includes the 32-case modified v295 profile module. The existing unchanged
v295 reader's all-configurations parameterization gains one child case, so
final targeted/broad totals increase by 322 over the corrected v295 selections.
All sixteen historical fingerprints and all earlier/current parent snapshots
pass. The amended focused consumer receipt has 33 passes; the independent
plain judge check had 219 new + 113 unchanged judge tests = 332 passes.

Targeted/broad use the local offline harness, blocking network, real Docker
and protected paths. All runs disable bytecode/cache writes. Plain basetemp:
`/tmp/execskill-v296-plain-8z482hlg/cases`; custom fixtures use TMPDIR or /tmp.
No `.v29-*` or `.v28-fixtures` scratch remains in the working copy.

The amendment is labelled by the coordinator as preceding validation/run.
Focused local engineering checks of the majority draft had in fact already
run before the amendment message arrived, while the requested final targeted,
broad and plain selections and every real run had not. The preregistration
states both timelines explicitly. The first draft, source hashes and its focused
receipts are preserved in [v296-majority-draft/](v296-majority-draft/); original
root focused receipts remain superseded evidence, not amended-rule results.
The superseded consumer integration fixture initially failed two cases because
its authored routing view lacked `initial_observation` (28 passed, two failed);
only the fixture was corrected. The archive retains that receipt as well.

[V296-VALIDATION.json](V296-VALIDATION.json) records exact commands, counts,
files, source/artifact hashes, unchanged caps, prompts and constraints.
No required implementation remains open. The chronology qualification above
is the only specification-history discrepancy. The original same-split
acceptance reuse is disclosed; no independent method-effect result is claimed.
No real smoke, network/model/paid/Docker call, protected-data access or commit
was performed; the three protected living documents are unchanged.


## v2.9.7 — full episode audit history and pooled same-text baseline (2026-10-28)

Implemented [the brief](BRIEF-v297-audit-history-pooled-baseline.md) for
`alfworld-v11`, child of `alfworld-v10`. [V297-PREREG.md](V297-PREREG.md)
quotes the owner's decision, records the supplied evidence and discloses test
reuse. The two changes were selected from ALFWorld v10 training/acceptance
records read after its decision, not from test scores. The previously opened
test result (F 92 = C 92 of 134, opened 2026-10-28 14:4x) is disclosed; any new
test read must be reported jointly with it. No real experiment was run here.

### Files, functions and frozen parents

Production files changed:

- `skillopt/execskill/audit.py`: `episode_disclosure`, `system_prompt`,
  `prompt_pins`, `_observation`, `_episode_history`, `_cell_episode_history`,
  `public_view`, both situation constructors, `fit_episode_prompt`, `_request`,
  `run_audit`, and `audit1` add child-only disclosure and bounded requests.
- `skillopt/execskill/step.py`: `_audit_final` passes the configuration into
  request-based situation construction.
- `skillopt/execskill/acceptance.py`: `_v297_rule`, `pooled_differences`,
  `prepare`, and `decide` bind the pooled rule and select its exact J1 contrast.
- `skillopt/execskill/profiles.py`: `ALFWORLD_V11`, `is_v297`, descendant
  predicates, copied tables and a new acceptance rule name.
- `skillopt/execskill/alfworld_format.py`: `bind`/`validate` retain the v2.9.6
  readable-action rule while requiring the exact v10 or v11 runtime identity.
- `skillopt/execskill/manifest.py`: configuration-specific audit pins,
  audit-feature pins, and the ALFWorld v11 registration identity.
- `skillopt/execskill/confirm.py`, `protocol.py`, `evaluation.py`,
  `scripts/run_execskill.py`: freshness, evidence, sealed roster and CLI choices.

New tests are `tests/test_execskill_v297_audit.py`,
`test_execskill_v297_acceptance.py`, `test_execskill_v297_profile.py` and
`test_execskill_v297_binding.py`. Existing `test_execskill_v296_profile.py`
and `test_execskill_v296_judge.py` only adjust descendant roster/runtime
expectations; historical assertions remain. No engineer, solver, statistics
implementation, format-judge, budget or mutation-catalogue file changed.

Before any implementation edit, captured thirteen parents (Zebra v7–v12,
ALFWorld v4–v10) in
[v297_parents_before.json](../../../tests/fixtures/execskill/v297_parents_before.json),
SHA-256 `b21a12fae1001225d644423a5dff0e2325899221c9a164a2bd5102bdec89ad23`.
The snapshot includes registrations, full prompt maps, roles, budgets, units,
runtime sheets, eleven format-judge outputs per parent and four audit views/keys
per parent. All 102 prior source hashes matched before editing. Initial hashes,
source list and validation are retained as `V297-INITIAL-SHA256.json`,
`V297-SOURCE-BEFORE.json` and `V297-VALIDATION-BEFORE.json`.
The refreshed [source hashes](V29-SOURCE-SHA256.json) contain 110 entries.

Both real fixtures remain byte-identical. Trajectory SHA-256:
`f683beee7e5959a43eaefbb33901ccc3b03f6d23303b5cc693468ffe7a407e2c`;
acceptance outcomes SHA-256:
`896fc9f33b5372f39832ed31a3a90c695cec1b8c676401d461ca64b122de64ef`.

### K1 — exact disclosure and prompt limits

Only ALFWorld v11's public audit view gains `episode_history`, containing every
earlier step 0..k−1, with `step`, executed `action`, and the returned
`observation` seen by `alf_after_step`. Step zero has an empty list. The replay
path checks the verified raw trajectory with the same original-index, action
and captured post-observation checks as the request-based path, then requires
its history to equal the captured replay history. Missing or misaligned earlier events
are refused; no history is invented. Recent history and all other public-view
fields are unchanged. `situation_key` already hashes the complete view, so the
child's new field participates while old keys remain exact.

Observations are capped at 240 characters including `…[truncated]`. No step or
action is removed. Initial requests and format retries are fitted independently
from copied structured history, halving the cap through 240, 120, 60, 30, 15,
12 until `len((system + user).encode("utf-8")) <= 220000`. The raw reply,
parse diagnostics and other input remain unchanged. If immutable content still
exceeds the limit with marker-only observations, the request is recorded as
unavailable without dispatch. Child request/retry records retain observation
cap, input bytes, history-step count, limit and whether it fits. Call limits,
policies P1–P6, sampling, both judges, agreement and retry selection are unchanged.

The exact added passage is:

> recent_history shows only the last 5 steps; episode_history is the whole episode before this step; a note's claim about the whole episode (counts, visited places, earlier failures) must be checked against episode_history, and is false only when episode_history contradicts it.

Passage SHA-256:
`231ec231552521c66e272cc12cb0143f3c952e6d36d0a4f4f6c79a4b7e7f8399`.
Templates system: `6a8875e57f7cda4bd58785bfcb2be3227c2b0a5f77bf33d34ff82da356e61e31`.
Situations system: `0710792cbcffd272fd231f2662b89202544350cbbe8c09636d95a1b1c3e8e232`.
Final system: `5047a19e7f12d1a61aedb58aa1364d600f4de43c6c427bc02939e3eb8287513d`.
Full texts, hashes and inherited engineer pins are in
[V297-PROMPTS.json](V297-PROMPTS.json). Engineer single/train hashes stay
`00f3b23438c18d2ee74bfdfe5528513b71ca3dfd25804ea98ae2079570e13478` /
`2cbd24cc5370fd18fac34c90f6e992148ae034a3d62a9ca7c55873f563b248c9`,
with record kind `engineer-v2-9-5` and unchanged reader/repair rules.

The real fixture confirms full counts **3/3/3** for drawers 1/7/8 before each
of steps 44, 45 and 47. Its recent-window counts are **1/0/0**, correcting the
brief's shorthand "one occurrence in the 5-step window." The fixture was not
altered. [Measured prompts](v297-audit-fixture-measurements.json) combine the
three actual stored views/claims and 136 earlier-step rows: round **27040 bytes**,
final **27250 bytes**, versus parent-equivalent 10224/10434. No fitting below
240 characters was needed. Individual round sizes are 11050/11074/11218;
final 11260/11284/11428 for steps 44/45/47. These are fixture-based B prompts
with disclosed helper headings and authored empty C6 counts, not measurements
of original historical wire requests; the fixture does not supply program source.

### K2 — pooled J1 and exact arithmetic

Only ALFWorld v11 seals `practical-v2-9-7-pooled`. When `card_is_parent` holds,
`d_i = S'_i − (S_i + C_i)/2`, computed as the exact Fraction average of the
existing S'−S and S'−C vectors. The existing conservative unknown bounds and
same-origin cancellation are retained. J1's practical condition remains
`100 * sum(d_i) >= 5 * |A|`; the whole-batch denominator is unchanged.
The new `S'-(S+C)/2` contrast uses today's blocked/room-weighted paired t,
bootstrap CI and sensitivity functions. S'−S and S'−C remain reported and are
marked nondeciding. If C is not the parent, J1 continues to use S'−S.
Both cases record the selected baseline and pooling flag.

J2 is label-only, J3 is informational as before, J4 stays S' versus S, and
J5/J6/J7 are unchanged. C−S remains the duplicate test at 1%. No training,
confirmation, adoption, self-test, smoke, format verdict or test-read rule changes.
The readable-action rule remains `alfworld-readable-action-v2-9-6` with the
same judge/scorer, bound to each child's exact runtime identity.

[Real arithmetic replay](v297-acceptance-fixture-replay.json): 150 games,
S/C/P_y/S' wins 83/93/85/92; S'−S = 9/150 = +6 points, S'−C = −1/150,
pooled = 4/150 = +2.67 points. The production practical J1 changes from pass
to fail, so the counterfactual new-rule decision is reject. The historical
acceptance decision remains unchanged. The fixture's recorded duplicate p is
0.012544176512929932, above 0.01. Room/block labels are absent, so new pooled
p_t/CI/sensitivity are explicitly unavailable for this real replay. Full
prepare/decide and design-based statistics are tested separately on authored
room/block data. Those tests reduce resampling counts only inside fixtures
(80 bootstrap, 256 sign flips); production defaults and design remain unchanged.

### Identity, caps and costs

Root string `/data/execskill-20261028-alfworld-v11`, manifest suffix
`-manifest.json`, namespaces G-alf11 (reserved) / D-alf11 (launchable), evidence
`alfworld_v11_real_run`. Accept freshness:
`alfworld_split_v1_slices_after_alfworld_v10_accept_test_read`; confirm freshness:
`alfworld_split_v1_confirm_spare_rooms_after_alfworld_v10`.
Parent confirm-view/S0 and cross-configuration runtime identities are refused.
The source preparation and reset-view provenance remain intact.

No cap/budget formula changed. Six rounds, patience four; 31 single/41 train
engineer calls per round; 270 engineer+analyst, 126 leakage, 18 describer and
720 calls per audit judge. With unchanged `R(b,m)=4*(b+512+m)`, engineer scope
428351616, each judge scope 659582336, total roles 1845116288, solver cap
1220900000. Self-test/confirm/redo caps 312600000/128700000/312600000;
training/confirm cells 1360/480. Routes, arms, fixtures, 120-second cleanup grace,
90-second readiness, fault/inert repairs and per-unit agreement are inherited.
These are reservation bounds, not measured spend. Offline paid cost is zero.


### Validation, corrections and limitations

- [Targeted receipt](v297-targeted-validation.json),
  [log](v297-targeted-validation.log): **2,004 passed**, zero failures/errors/skips;
  all v29 modules plus v28 frozen tests.
- [Broad receipt](v297-selected-validation.json),
  [log](v297-selected-validation.log): **2,941 passed**, zero failures/errors/skips;
  v24–v29, Zebra and ALF selections.
- [Plain receipt](v297-plain-validation.json), [JUnit](v297-plain-validation.xml),
  [log](v297-plain-validation.log): **451 passed**, zero failures/errors/skips;
  the four new modules and the two changed v296 modules, without offline_pytest.

New cases: audit 56, acceptance 59, profile 46, binding 25 = **186**.
Plain also includes v296_judge 220 and v296_profile 45. The existing all-config
parameterizations in v296_judge and unchanged v295_reader each gain one case;
therefore targeted/broad increase by 188 over v296. All sixteen historical
fingerprints and thirteen captured parent configurations pass. All 139 mutation
anchors occur exactly once; the catalogue is unchanged. The independent review subsequently found the round-history integrity issue
fixed below.

Pre-review focused receipts: audit 276 (41 new plus historical audit/reply-parts tests),
acceptance 59, profiles 336 (71 new plus two changed v296 modules).
The initial audit receipt is retained (268 passed, seven failed): six tests
initially assumed the brief's recent-window shorthand instead of its actual
1/0/0 fixture counts, and one synthetic retry was too small to exercise extra
truncation. Those fixture expectations were corrected and one additional
initial-overflow regression was added; no production defect was masked.
The preregistration records when the count clarification was added.

Targeted/broad use the local offline harness with network/Docker/protected-path
blocks. Plain pytest uses `/tmp/execskill-v297-fix1-2loozrgh/plain-cases`; custom
fixtures use TMPDIR or /tmp. Bytecode/cache writes are disabled. No `.v29-*`
or `.v28-fixtures` directories remain in the working copy. Both supplied
fixtures, older snapshots/prompts and the three protected living documents
remain byte-identical.

[V297-VALIDATION.json](V297-VALIDATION.json) contains exact selections, counts,
source/artifact hashes, measured fixture prompt sizes, replay arithmetic and
constraints. [V297-CHANGED-FILES.txt](V297-CHANGED-FILES.txt) lists this increment's
files, excluding the immutable input fixtures and untouched brief.
Nothing required remains unimplemented. The brief's recent-window shorthand
is corrected as above. New pooled design statistics cannot be recovered from
the real fixture without room labels, as anticipated by the brief; they remain
unavailable. Prompt-size measurements are explicitly fixture-based, not real
historical request receipts. No network/model/paid/Docker call, dl or /data
access, commit, secret output or living-document edit was performed.


Review fix (2026-10-28, before any real run): [FIX-BRIEF-v297-1.md](FIX-BRIEF-v297-1.md)
addresses the independent review's one MAJOR. `audit1` retains and passes the
verified raw cell map; only ALFWorld v11's replay constructor requires that map,
validates history with `_cell_episode_history`, and requires equality with its
captured replay history. Missing leading/interior rows, duplicate/misnumbered
indices, contradictory post observations and differing captured actions raise
`ValueError` before either judge is called. Fifteen added regressions exercise
both round entry points and absent maps; intact counts/history and all parents
remain unchanged. Shared replay reconstruction, prompts, pins, valid records,
sampling, pooling and budgets are unchanged. Refreshed targeted/broad/plain
receipts pass 2,004/2,941/451 tests, with no failures, errors or skips; the earlier
focused receipts above remain explicitly pre-review evidence.


## v2.10 — historical instruction cards, blank B, no placebo (2026-10-29)

Implemented the two new five-bench configurations and their local validation paths:
`baseline-v210` (root `/data/execskill-20261029-baseline-v210`, G-base210/D-base210,
`baseline_v210_real_run`) and `main-v3` (root `/data/execskill-20261029-main-v3`,
G-v3/D-v3, `main_v3_real_run`). Both launch G and northgate D. The feature family
remains v2.3; no later single-bench audits, confirmation, repair or pooled-J1
machinery is ported. Supplies/exclusion are imported by value from main-v2-2.

Acceptance removes P_y/P_i and donor/sham preparation, with J2 exactly
`{"removed": true}`. The inherited C instrument, reuse, J1 and J3–J7 remain;
the coordinator's fix brief v2.10-2 explicitly retains S', S, C plus the
withholding/restoration twins, S_dup and J7 probes, with no placebo. These are
per-procedure attribution instruments; the alfworld-v11 twins located the whole
effect in one procedure. Test reads contain F/C/B
for main-v3 and C/B for the baseline, with exact consent, independent C/B,
no P_F/T_F/test twins/stages. Main readout keeps available Q1/Q2/Q3 statistics;
ALFWorld is identified as imported, not newly learned or a transfer target.
The same coordinator decision retains the inherited measured engineering
smoke's fixture controls, including C/X/P and its twins;
`v210-smoke` is explicitly zero-call structural validation, never measured readiness.

The baseline has no learning services/units, training-pool reads, acceptance or
procedure sandbox. It writes chain-complete, test-read.json and five per-bench
read units. Sandbox measurements are null/not applicable. Native task runtimes
remain required for an actual read. Main-v3 learns the first four steps and
imports the pinned v11 package at step 5 (`learning: import`), re-recording its
identity under the new evidence while preserving source bytes and provenance.
An explicit main-only mixed-policy loader checks each v2.3/v2.9 procedure under
its own policy. Learning reserves the immutable import's 5,404 bytes and three
slots within the unchanged 64,000-byte/24-procedure package limit; joint
candidates cannot consume the reserved space.

Caps and cell arithmetic are in [V210-PREREG.md](V210-PREREG.md). Per chain,
baseline reads 2,220 logical cells and main reads up to 3,330 before valid F/C
reuse. Baseline test/solver caps are 188M/190M. Main test/redo/solver caps are
238M/87M/1,140M, and role cap is 470.4M. These are ceilings, not measured spend.
The code preserves historical instruction-card bytes and manifest/S0 hashes,
keeps the same cards for the solver and roles, and binds the actual new engineer system in both manifests and
engineer records. Historical fingerprints were captured before edits in
`tests/fixtures/execskill/v210_parents_before.json` (all 30 existing profiles).

### Card definition resolved by fix brief v2.10-1

The original brief's assumption about the inherited card was inconsistent with local source:
`scripts/run_execskill.py:CARD_IDENTITY` and `import_texts` already bind the
**same five instruction texts** as the v210 fixture. Literal concatenation
would put the instruction twice in C/F and once in B, violating K5. No remote
manifest or v11 hold-out summary was opened to discover this.

The coordinator resolved this on 2026-10-29 in
[FIX-BRIEF-v210-1.md](FIX-BRIEF-v210-1.md), confirming the same identities in
the real main-v2-2 and alfworld-v11 manifests. Every route-B C arm since v1
was already an instruction baseline, including main-v2-2's step baselines
and alfworld-v10/v11's acceptance C = 93/150. The v10 test F = C = 92/134
has a separate denominator; the v11 hold-out summary remains unopened here.
The v11 accepted package's gain was already above the instruction baseline.

C/F and every other nonblank arm now keep the historical instruction card
byte-for-byte. No concatenation or public task card is used. B is `card: ""`,
kind `blank`, with no programs: the frozen base prompt and bench contract,
without a `GUIDANCE` block (`QA_SYSTEM` for QA/sheet, `ALF_SYSTEM` for
interactive ALFWorld). Solver prompts remain unchanged. This matches route A's No-Skill prompt on the
same frozen backends. The roles retain the historical cards and the engineer
sentence remains. Manifest and test-read records pin B; S0 and manifest pin
card/instruction equality and record
`instruction_start: historical_card_is_the_instruction`.

The refusing guard is removed, and both configurations' S0 and manifest paths
accept the registered cards in tests using the frozen instruction fixture.
The card-definition blocker is resolved. baseline-v210's C-versus-B read is
the planned measurement of the instruction's own effect inside the route-B
prompt; no effect is established by these engineering fixtures. Future
measured readiness and consent remain required; see
[V210-OPERATIONS.md](V210-OPERATIONS.md). Earlier preregistration, notes and
receipts are preserved in [v210-before-fix-1](v210-before-fix-1/V210-VALIDATION.json).

### Read-only review fixes — v2.10-2 (2026-10-29)

[The read-only review](codex-review-v210.md) found that the documented snapshot
could not run the registered S0 checks: the new profile tests depended on handoff
hash files and living documents omitted from the snapshot, while S0 tests injected
successful checks. [FIX-BRIEF-v210-2.md](FIX-BRIEF-v210-2.md) requires those pins
in `tests/fixtures/execskill/v210_protected_fixture_sha256.json` and an actual `prelaunch.zero_call_checks` run
against a temporary `v210_smoke.snapshot` for both configurations. The snapshot
continues to copy only `skillopt/`, `scripts/`, `tests/` and the frozen instruction
JSON, plus writing its own provenance/hash receipts; it carries no other handoff
or living documents. The protocol test's frozen `execskill-calc-20261021.py` is
also under `tests/fixtures/execskill/`, without a handoff or `/data` fallback.
At that historical revision, `tests/test_execskill_v210_snapshot.py` invoked the
registered checks with a child guard and explicit macOS/recursion skips. Fix
v2.11-1 ports the bounded replacement and removes that child guard. The earlier
counts remain historical observations, not current Linux launch readiness.

The first full snapshot attempt is preserved in
[v210-snapshot-initial-validation.json](v210-snapshot-initial-validation.json):
4,917 passed, 18 failed, 174 errors and 120 skipped. It exposed a frozen XLSX
serializer assumption: local openpyxl 3.1.5/lxml emits `<v></v>`, while the fixture
expects `<v/>`. The subsequent local check and documented S0 command set
`OPENPYXL_LXML=False` to select the standard-library serializer for that process.
Solver/runtime prompts remain unchanged. The final child result belongs in the
post-fix-2 validation receipt.

The baseline's read-canary construction now skips training-side canaries and
records that skip; a missing training-pool file must not block preparation or
reading. Main-v3 retains the historical training-side canaries. Both new
configurations' direct `evaluate-unit` entry requires the chain's first-response
confirmation before canary construction or test-panel access, closing the path
that could bypass `run`'s `first_call_unconfirmed` pause. Older configurations
retain their existing behavior. The acceptance/smoke arm finding is resolved by
the explicit coordinator decision above, with no scheduling change.

The previous preregistration, notes and receipts are preserved in
[v210-before-fix-2](v210-before-fix-2/V210-VALIDATION.json).
[V210-OPERATIONS.md](V210-OPERATIONS.md) gives the exact S0 command run from
inside the snapshot and the unchanged real-launch readiness requirements.

### Local validation

- [Targeted receipt](v210-targeted-validation.json): **2,223 passed**, zero failures/errors/skips
  (v297 selection plus nine new modules).
- [Broad receipt](v210-selected-validation.json): **3,160 passed**, zero failures/errors/skips
  (v297 broad selection plus nine new modules).
- [Plain receipt](v210-plain-validation.json), [JUnit](v210-plain-validation.xml):
  **393 passed**, zero failures/errors/skips, for all nine new and six changed test modules,
  without the offline harness in the parent pytest process; the snapshot child uses the explicit guard below.
- The nine new modules contain **209 cases**. The actual full registered snapshot check
  [passed](v210-snapshot-validation.json): **5,073 passed, 156 skipped, zero failures/errors**,
  5,229 collected. The two configuration snapshots contain the same 1,462 copied files.
  Skips are explicit: 125 Linux worker cases, nine thread/subclass/CLI cases, 12 mutation
  targets needing Linux, five existing Linux markers, three blocked listeners, and two
  recursive snapshot-test cases. This is local engineering evidence, not Linux isolation readiness.
  Failed/interrupted attempts remain in [the attempt index](v210-snapshot-attempts/index.json).
  An intermediate full local check reached 5,073 passes and 151 skips, with five remaining
  Linux-dependent failures ([platform receipt](v210-snapshot-platform-validation.json));
  their exact worker/subprocess dependencies are explicitly platform-skipped in the final local guard.
- After fix v2.10-1, the required selections passed 2,199 / 3,136 / 333 tests
  respectively, with zero failures/errors/skips; the seven new modules contained
  185 cases. Those receipts are archived in `v210-before-fix-2`; their S0 fixtures
  did not establish that the snapshot could run its real zero-call checks.
- Before the fix, the required selections passed 2,164 / 3,101 / 298 tests
  respectively, with zero failures/errors/skips; the seven new modules
  contained 150 cases. Their receipts are archived in `v210-before-fix-1`.
- The pre-fix route/manifest supplement passed **78** after retaining the exact
  historical route mutation anchor; all **139 mutation anchors** occur once.
- The additional old chain/step suite under the established harness passed
  **50**, skipped **7** Linux worker cases. Two exploratory plain attempts
  had 51 passes/6 failures in those platform-dependent cases; they are not
  hidden or counted as model evidence.

Five older test modules now exclude the new configurations from historical
learning/Zebra-only assumptions; the sixth, `test_execskill_protocol.py`, reads
the frozen calculator fixture under `tests/`. No old case is removed. Initial targeted
(2,105 passed/1 failed) and broad (3,065 passed/8 failed) receipts are retained:
the former exposed an unnecessary confirmation freshness entry (removed), the
latter exposed those old all-configuration fixture assumptions. The final
required selections above pass. New tests additionally caught and fixed a
phantom placebo reuse class, mixed-policy loading, import-capacity overflow,
and engineer record/prompt pin mismatch.

[V210-VALIDATION.json](V210-VALIDATION.json) records exact commands, counts,
hashes and the resolved coordinator decision. [V210-CHANGED-FILES.txt](V210-CHANGED-FILES.txt),
[V210-SOURCE-SHA256.json](V210-SOURCE-SHA256.json), and
[V210-PROMPTS.json](V210-PROMPTS.json) are new artifacts; historical receipts
and source/prompt archives remain frozen. The three living documents and all
supplied/frozen fixtures retain their starting hashes. No network/model/paid/
Docker call, dl or /data access, commit, secret output, or sealed test-summary
read occurred. No `.v29-*` or `.v28-fixtures` checkout was created.


2026-10-29 — **v2.11.1 compatibility correction for baseline-v210 / main-v3:** [fix brief v2.11-3](FIX-BRIEF-v211-3.md) requires these configurations to qualify SpreadsheetBench against their own launch snapshot too. The manifest and S0 now bind `--sheet-runtime`, retain inherited sheet provenance, and refuse stale-source or unsupported scorer qualification at preparation/create/load. The scorer and historical qualification commands are byte-identical. Current joint validation: **2,715 targeted / 3,652 broad / 865 plain passed**, with zero failures/errors/skips; [V210 validation](V210-VALIDATION.json) and [operations](V210-OPERATIONS.md) are updated. Earlier v2.10 run counts above remain historical, preserved with the old deliverables in [the fix-3 archive](v211-fix3-history.zip). No corrected Linux launch or successful measured smoke is claimed.

## v2.11 — main-v4 (2026-10-29)

Implemented the coordinator's [Phase B brief](BRIEF-v211-phase-b.md), in [design §10](V211-DESIGN.md#10-implementation-order) order: **four learned steps + imported ALFWorld**. The child uses G-v4 / D-v4, evidence `main_v4_real_run`, root `/data/execskill-20261029-main-v4`, and manifest `/data/execskill-20261029-main-v4-manifest.json`. G is GLM-5.3; D is northgate deepseek-v4-flash. The final read retains F/C/B, 1,110 items / 3,330 logical cells per chain, 6,660 across both chains.

The four learned benchmarks now use their own frozen engineer/repair/audit prompts, full routing/effect coverage, benchmark-specific public audit adapters, six preassigned confirmation rounds with no cross-round incumbent cache, and full independent C under `practical-v2-11-pooled`. Six rounds, candidate-counted patience four, 31/41 unit-call budgets, retained gates/twins/restoration/S_dup/J7, and the unchanged ALF import are pinned. Acceptance C has 1,400 cells per chain; S′/S/C has 4,200 before reuse. Per-chain ceilings remain solver 1,250,000,000, method 7,009,579,520, total 8,259,579,520 ledger tokens; these are ceilings, not measured spend.

[Preregistration](V211-PREREG.md) records exact allocations, historical exposure unknowns and the accepted within-run amendment; it states the known v11 acceptance result, unavailable v11 test numbers, v10 F=C=92/134 and main-v2-2's 0/10 acceptances without making a new effectiveness claim. [Prompt export](V211-PROMPTS.json) matches the live manifest. [Operations](V211-OPERATIONS.md) gives executable snapshot, consent, child selftest, S0, measured smoke, separate D probes, real-manifest and run commands. The finite smoke schedule/caps are pinned; structural/authored receipts cannot authorize a real manifest. Deliberate fallback, final-audit removal/source checks and confirmation resume/refusal are separately labelled zero-model-call controls, excluded from measured costs.

Fix **v2.11-2** (2026-10-29) addresses the [independent review](codex-review-v211.md) under the [coordinator’s fix brief](FIX-BRIEF-v211-2.md). The child selftest now translates the inherited worker receipt into exactly the manifest’s four measured fields and obtains native peak RSS through historical `s0.native_peak` on the largest training workbook. A real CLI selftest→S0 fixture connection passes with only sandbox Docker/worker I/O injected; failed, missing and zero native measurements cannot produce the child receipt. These are local engineering controls, not a Docker measurement on this Mac or Linux readiness.

S0 now derives nonempty protected-ID hashes per benchmark from pinned split/layout metadata under `TestAccess`, including every nontraining partition and closed extension evaluation blocks. SearchQA dropped-ID hashes and the passing ALFWorld test identity are bound too. Native `final`, closed partitions, empty protection and protected-ID overlaps stop S0; all five digests are pinned in S0/manifest and the four learned allocation identities. The registered historical train+val pools remain training-side. Test item text is never read. At fix v2.11-2 the v2.10.1 preparation parser, authored real-shape fixture and manifest tests were copied byte-for-byte from the named working copy; OfficeQA/LiveMath use layouts/upstream/split and inherited exclusions use `exclusion.EXCLUSION_DIR`.

Historical validation after fix v2.11-2: **2,693 targeted**, **3,630 broad**, **843 plain pytest** passes, with zero failures/errors/skips. Plain selection includes the newly ported v2.10 manifest tests and all 14 new plus 6 changed test modules; new v2.11 modules contain 379 cases. The bounded snapshot checks pass for all three configurations, copying **1,489 identical files** and collecting **5,699 tests each** with a 120-second timeout, executing no nested test bodies. [Validation](V211-VALIDATION.json), [receipts](v211-targeted-validation.json), [source hashes](V211-SOURCE-SHA256.json), were current for fix v2.11-2; v2.11.1 below supersedes their launch interface. Prior v2.11-1 deliverable bytes are preserved in [the fix-2 history archive](v211-fix2-history.zip) with [original hashes](v211-fix2-history.json). No model/network/Docker/dl/`/data` action or commit occurred; the three living documents and frozen pre-edit capture remain unchanged.

Previous validation after **fix v2.11-1** (historical): targeted **2,577 passed**, broad **3,514 passed**, and plain pytest **671 passed**, all with zero failures/errors/skips. All 12 new and 5 changed test modules ran under plain pytest; the new modules contain 350 cases. Each selection ran without an extra pytest plugin from a source-identical snapshot under `/tmp`, keeping historical relative scratch outside the checkout.

The bounded snapshot regression has **4 passing checks** and retains baseline-v210, main-v3 and main-v4. All three snapshots contain the same **1,485 files**, include only the instruction fixture under `docs/handoff/`, and each collects **5,583 tests** within the **120-second timeout**. The static source scan passes. Collection executes no test bodies. The former nested full-suite path, lock/cache, recursion guard and child plugin were removed; full registered execution occurs once through Linux `v211-s0`, with sufficient TMPDIR inodes. [Validation](V211-VALIDATION.json) and the [bounded snapshot receipt](v211-snapshot-validation.json) record exact commands and hashes.

The prior 2,576 / 3,513 / 661 selected passes and 5,425 passes / 157 skips in the nested run remain **historical results**, superseded as current validation. Their exact bytes, along with obsolete helper references in earlier records, are preserved in [the history archive](v211-fix1-history.zip), indexed by [original hashes](v211-fix1-history.json). No earlier score is relabelled as a result of this fix. The immutable pre-edit capture retains its deleted-helper provenance hash; no executable test or current launch instruction depends on that entry.

The [two-chain rehearsal](v211-two-chain-rehearsal.json) runs both actual chains on shared authored items in separate namespaces: four synthetic acceptances each, frozen three-procedure ALF import, five synthetic F/C/B read units, and zero additional calls on resume. Compact 12-run/12-accept cuts exercise control flow; separate allocation tests cover full registered counts. S2 exercises all 172 cells, S3 all four learned benchmarks, and SX production training/acceptance with fake providers. These are engineering fixtures, not real model runs or method-effect evidence.

The initial broad attempt's 5,286 passes / 29 failures / 142 skips are retained in [its receipt](v211-initial-broad-validation.json) and [log](v211-initial-broad-validation.log). It exposed old-roster assumptions, a missing-setting coverage guard, an incidental local bytecode file, and mutation targets whose platform skips were not printed without `-rs`; these were resolved before the final selections. The first full snapshot attempt is retained in [its receipt](v211-precontrol-validation.json): 5,414 passed / 10 failed / 157 skipped on each of two interpreter-path identities. All ten failures came from two incidental interpreter caches recorded by the pre-edit capture but intentionally absent from snapshots. The capture remains unchanged; portable checks explicitly exclude those two generated caches while verifying all 28 source fixtures. Duplicate outer selections were stopped after that known failure. The explicit §8.1 controls were then integrated before the final complete rerun.

[Changed files](V211-CHANGED-FILES.txt), [source hashes](V211-SOURCE-SHA256.json), and [Mac hash list](mac-hashes-v211.txt) distinguish this phase from the dirty starting tree. All 32 historical fingerprints, pre-existing frozen fixtures, and the three coordinator-owned living documents retain their captured hashes. No network/model/paid/Docker calls, dl or `/data` access, commits, sealed test-summary reads, or new data acquisition occurred. Real qualified-tail eligibility, Linux isolation, measured S0/S2/S3/SE6/SX and D probes remain pending the later authorized operator phase. The seven original local implementation judgments are individually enumerated in the preregistration. Fix v2.11-1 changed test orchestration and documentation only; the subsequent v2.11-2 corrections are described above.


## v2.11.1 — snapshot-owned sheet qualification (2026-10-29)

The coordinator reports that the first real main-v4 chain-G (GLM-5.3) S2 attempt, 16:16–16:20, stopped at its first SpreadsheetBench cell with `native_scoring_input_error:ValueError`. The zero-call reproduction identified `Engine/source/image changed`: the inherited main-v2-2 qualification pinned absolute scorer paths under source snapshot h. This is the [fix brief’s reported evidence](FIX-BRIEF-v211-3.md), not a new run performed here. Completed preceding-cell denominators, tokens and cost were not supplied in this handoff; no accuracy or method-effect conclusion follows from this infrastructure failure. Existing failed-smoke receipts remain untouched.

The correction applies only to main-v4, main-v3 and baseline-v210. `v211-manifest` / `v210-manifest` now require `--sheet-runtime PATH`; `v211-s0` / `v210-s0` accept it optionally, but an S0 without the verified runtime cannot authorize a manifest. The supplied block replaces the active sheet runtime and top-level `sheet_qualification`, bound to this snapshot; the inherited runtime/qualification remain in `data.inherited_sheet_runtime` for provenance. S0, manifest creation and load invoke the unchanged numeric qualification validator and readiness check before any solver work. Another source tree or unsupported readiness is refused. The unchanged qualification/scorer code and original `sheet-runtime` command are hash-checked. [v2.11 operations](V211-OPERATIONS.md) and [v2.10 operations](V210-OPERATIONS.md) include the exact qualification command and require re-qualification after any re-snapshot or move.

Current local engineering validation: **2,715 targeted / 3,652 broad / 865 plain pytest passed**, zero failures/errors/skips. The 22 new regression cases exercise actual CLI S0→manifest for all three configurations, real qualification binding validation, foreign-source refusal at S0/create/load, unsupported readiness and missing S0 runtime binding. Native control judgments and image inspection are authored fixtures; no Docker or model call was made. All 32 historical configuration fingerprints and 28 frozen source fixtures pass. The snapshot check copies **1,492 identical files** for the three configurations and collects **5,721 tests each** under 120-second timeouts, with no nested full-suite execution. [Validation](V211-VALIDATION.json), [receipts](v211-targeted-validation.json), [changed files](V211-CHANGED-FILES.txt) and [source hashes](V211-SOURCE-SHA256.json) are current; the exact previous deliverables are in [the history archive](v211-fix3-history.zip), [indexed by original hash](v211-fix3-history.json). The three living documents and immutable pre-edit captures are unchanged. Corrected Linux qualification and measured smoke remain pending the operator phase.


## v2.12 — zebra-pc-v13 (2026-10-30)

Implemented the [single-benchmark brief](BRIEF-v212-zebra-pc-v13.md) as a
child of `zebra-pc-v12`: six training rounds, patience four, inherited
v2.9.1–v2.9.5 training/confirmation/repair behavior, D-only northgate
`deepseek-v4-flash`, engineer GLM-5.3 and the existing two audit judges.
Root `/data/execskill-20261030-zebra-pc-v13`, namespaces G-zpc13 (reserved)
and D-zpc13, evidence `zebra_pc_v13_real_run`. ALFWorld's readable-action
and episode-history rules remain ALFWorld-only. No five-benchmark import
or real experiment is included.

J1 seals **`practical-v2-12-pooled`**: with an empty parent, exact per-item
`S' − (S+C)/2`, the existing +5-point whole-batch practical bar and paired-t
statistics. S'−S and S'−C are informational. Zebra uses `main-v4`'s explicit
full independent C mechanism because Zebra can otherwise reuse identical
S/C requests; the sealed plan reports `full_independent_astar` and dispatches
fresh C cells on every A* item, even an otherwise zero-dispatch item.
J2/P_y/donors are removed and J6's C−S test at 1% is enabled as in `main-v4`
(historical Zebra omitted it). J3 remains informational; J4, J5,
the Zebra-inapplicable J7 and acceptance withholding twins retain v12
semantics. The one conditional chain-end read has only F/C, with no blank,
placebo or test withholding arm and no read if no package is accepted.

[Preregistration](V212-PREREG.md) quotes the owner decision and the supplied
training-side evidence, discloses reuse of the 100 acceptance puzzles and
their post-hoc upper-bound probes, and derives every reservation. Solver
cap **249,600,000**, test cap **34,000,000**, redo **43,300,000**; aggregate
role cap **1,625,560,448**, overall **1,875,160,448** tokens. Engineer scope
**428,351,616**, each audit judge **549,804,416**. These are reservation
bounds, not measured usage or an effectiveness result.

[Operations](V212-OPERATIONS.md) supplies the future Linux snapshot,
delegated F/C consent, configured sandbox selftest, S0 with TMPDIR,
manifest, offline structural fixture smoke, measured S1/S2/S3/SE6,
background D launch and conditional read/report sequence. v13's snapshot
also includes the single public instruction fixture needed by current S0
tests; the older snapshot path is unchanged. Actual Linux readiness,
endpoint authorization and measured cost fit remain unestablished locally.

The pre-edit [capture](../../../tests/fixtures/execskill/v212_parents_before.json)
covers all 33 earlier configurations. [Validation](V212-VALIDATION.json)
records the actual plain pytest selections/counts and frozen-parent checks;
[changed files](V212-CHANGED-FILES.txt) and [source hashes](V212-SOURCE-SHA256.json)
identify this increment relative to the dirty starting tree. All validation
here is offline engineering work, with zero model calls and zero paid cost.
No network, Docker, `dl`, `/data`, sealed/test-data access, commit or secret
output is part of this work. The three living documents remain untouched.


## v2.13 — zebra-hp-v3r4 (2026-10-30)

Implemented the [fixed-program brief](BRIEF-v213-zebra-hp-v3r4.md) as an
import-only child of `zebra-pc-v13`. Only D-zhp launches; G-zhp is reserved.
Root `/data/execskill-20261030-zebra-hp-v3r4`, evidence
`zebra_hp_v3r4_test_read`, readout evidence kind
`post_hoc_selected_upper_bound`. The one step imports the fixed v3 round-four
program and makes no engineer, training, confirmation, acceptance, audit
or solver call. Its nonempty import permits the inherited single F/C
chain-end read without an acceptance; an empty F=C import is refused.
The chain's first solver connectivity response remains separate.

The supplied brief reports the historical 2026-10-26 elucid-route probe:
96/100 versus 83/100 acceptance, +13 points (95% CI +6..+21), 15 better /
two worse, 1,023,080 tokens; offline grids correct on 188/200 practice
puzzles. These are supplied training/acceptance-side observations, not a
new replay. The program was chosen post-hoc using those results and was
never kept by the method or run through the v2.9 LLM audit. Only v3r4 is
fixed before this read; v4r2 is excluded. This read uses northgate
`deepseek-v4-flash`, which differs from the probe's elucid route. Its result
is **not evidence that the method's gates work**.

The immutable [fixture](../../../tests/fixtures/execskill/v213_zebra_hp_v3r4_package/)
rebuilds one NEW procedure on an empty parent, with unchanged 10,955-byte
program source, the documented 648→600 description truncation and no
replay tests. Current package validation and v2.9 static policy pass.
The new source-package record hash is
`404415581c92ea6fe9caa03c22d41e5b5e5617ce66bec7a3356555f378bbf0b8`.
It differs from the historical `f93c90fb…ce5ba` wrapper through current
v2.9 policy/schema and evidence metadata; current id/step/lineage choices
are explicit in [provenance](../../../tests/fixtures/execskill/v213_zebra_hp_v3r4_package/provenance.json).
The historical builder and package records were not supplied, so their
exact id/step/lineage fields are unknown and no complete historical wrapper
reconstruction is claimed. Program SHA-256 remains
`c9d5fc91962a79d83b0ce9882d55545798a7a4a58e856e195e6d39c0f05fcc85`.

[Preregistration](V213-PREREG.md) quotes the owner, states the selection and
audit limits, and fixes all identities and reservations. Read cap
**34,000,000**, plus the existing first-response headroom **1,100,000**,
gives solver and overall caps **35,100,000** tokens; method-role,
learning-stage and redo allocations are zero. [Operations](V213-OPERATIONS.md)
gives future Linux snapshot/consent/S0/TMPDIR, S1/S2/SE6, manifest and
chain-D/read commands. S3 is inapplicable. The real manifest requires the
three matching passing stage receipts and valid measured read projection;
offline structural smoke cannot qualify it. S2 measures card-only costs;
the procedure multiplier remains an assumption.

The pre-edit [capture](../../../tests/fixtures/execskill/v213_parents_before.json)
covers all 34 prior configurations. [Validation](V213-VALIDATION.json)
records actual targeted, changed-module and requested full-suite results
and limitations; [changed files](V213-CHANGED-FILES.txt) and
[source hashes](V213-SOURCE-SHA256.json) identify this increment. All local
validation is offline engineering evidence. Linux isolation, route
authorization and measured smoke fit remain pending. No network/model/paid/
Docker calls, `dl` or real sealed/test-data access, repository commits or
secret output occurred. Validation discloses an inherited `/data` mkdir
denied before data opened and a legacy checkout-scratch helper corrected
to `/tmp`/`TMPDIR`. The three living documents and v2.12 behavior remain
unchanged.

## v2.14 — main-v5 five-bench chain with stage reads (2026-10-30)

This additive main-v4 child replaces LiveMath with ZebraLogic in the order
SearchQA → OfficeQA → ZebraLogic → SpreadsheetBench → ALFWorld. The retained
learned benches keep main-v4 machinery; Zebra selects the exact zebra-pc-v13
v2.12 machinery, including full independent C acceptance and 40-item confirmation.
Step 5 remains the unchanged alfworld-v11 import. The pre-edit capture covers
all 35 older configurations, including both finalized v2.13 parents.

The owner's two named decisions are fixed in [preregistration](V214-PREREG.md):
Zebra/ALF have no related benchmark; every frozen step package is read on all
five benches at chain end, sealed until both chains end. F/C/B and up to four
stage arms share identical requests at zero dispatch; Zebra B shares C. Every
step row remains in the stage table with home, related and unrelated questions,
including explicit zero/no-test rows. Related pairs are Search–Office and
Office–Sheet only. Logical read maximum is 8,295 cells per chain; the unreduced
worst-case read cap is 456,000,000 tokens. After fix1, the overall cap is 8,500,923,008 per
chain; ceilings are not measured spending.

The configuration gates the Sheet qualification ordering and vanished-file scan
recording. The lean two-chain smoke pins every later stage's solver bound to S1
and verifies S1's measured longest against its three D probe receipts. A
structural fixture receipt cannot authorize a real manifest. G Zebra settings,
all writer decisions, source changes, prompt text and future operator commands
are documented in [design](V214-DESIGN.md), [operations](V214-OPERATIONS.md),
[prompts](V214-PROMPTS.json), [changed files](V214-CHANGED-FILES.txt), and
[source hashes](V214-SOURCE-SHA256.json). [Validation](V214-VALIDATION.json)
contains exact test counts, failed-run history and remaining host limitations.

This is offline engineering evidence only: no real smoke, accepted Skill,
transfer improvement or non-inferiority result is claimed. No network, model,
paid, Docker, dl, real sealed/test-data or `/data` access was used. No commits
were made. The finalized v2.13 hash list and the three living documents were
left unchanged.

Fix1 addresses the four confirmed [review findings](codex-review-v214.md) under
the [fix brief](FIX-BRIEF-v214-1.md). Zebra's mixed-chain selftest now includes the
inherited earlier OfficeQA cells: its scope cap is 49,400,000, the learned-step
solver total is 882,100,000 and the rounded chain solver ceiling is 1,430,000,000.
Replay, firing, fault and audit inputs obey intrinsic procedure scope as well
as exclusions only for main-v5. Sheet repair effects persist into feedback, and
inert-repair examples retain their execution report. The composition sweep also
separates mixed audit adapters and validates fault feedback by the current
benchmark. Prompts and all older configuration identities remain frozen.
The `fix1` section of [validation](V214-VALIDATION.json) records the new tests,
scope/sweep findings and preserved parent comparisons. The optional full-suite
rerun is skipped; original full-suite evidence is retained separately.

Fix1 validation: 205 v2.14 tests passed. The same 3,209 historical selection
selectors executed 3,213 passing cases because one S3 test now has five
variants. All 35 older identity checks and the complete historical profile-table
comparison pass. Changed-module tests produced 303 passed, 22 failed and 139
setup errors; the 22 failures and the detector failure blocking those setups
reproduce before fix1 with matching messages (23/23 baseline failures).
These local worker limitations remain; real smoke was not run. The final
[sweep ledger](V214-DESIGN.md#fix1-sweep-ledger) lists every inspected dispatch
site and its disposition. Decisions 19–26 record the writer choices.

## v2.15 — zebra-pc-v14 engineer-only diagnostics (2026-10-31)

This additive child of zebra-pc-v13 gives the engineer bounded explanations
from a procedure that abstains or encounters a fault. The supplied brief reports
13 Zebra method runs with zero adoptions; the selected v2.13 hand-picked solver's
188/200 versus 165/200 is an upper bound, not method evidence. No run artifacts,
sealed data or test panels were opened to implement this change.

The new top-level hook `diagnostics` channel holds at most five strings of
240 characters, with truncation, screening and SHA256 metadata. It is removed
before note rendering and solver request construction, and stays outside
delivered-note audits, note caps and request reuse identities. Inert repair,
fault repair and next-round training feedback receive run-item diagnostics
and up to eight aggregate reasons. Strict helpers can now explain which public
input text they could not interpret. The appended general prompt requires
complete condition interpretation and a unique verified conclusion before
presenting an answer; otherwise the program abstains and reports why.

The child preserves the original engineer evidence allowance and adds a
fixed 64,000-byte diagnostic envelope. Engineer cap is 497,727,616 tokens,
method total 1,694,936,448, solver 249,600,000 and overall 1,944,536,448.
These are reservation ceilings. Chain D, split-v1 supplies, six rounds,
patience four, full independent C acceptance and conditional chain-end F/C
read remain inherited. The registration discloses prior acceptance exposure
and the one earlier hand-picked hold-out read. All 36 older configurations
are covered by the capture made before any edit, including running main-v5.

See [design and decisions](V215-DESIGN.md), [preregistration](V215-PREREG.md),
[operations](V215-OPERATIONS.md), [validation](V215-VALIDATION.json),
[prompt pins](V215-PROMPTS.json), [changed files](V215-CHANGED-FILES.txt), and
[source hashes](V215-SOURCE-SHA256.json). Operations are future commands only.
This work is offline engineering evidence; it establishes no real smoke,
adoption, transfer or method-effect result. The optional full-suite rerun is
skipped. No network, model, Docker, dl or `/data` access, secret output or
commit is part of this implementation. The three protected living documents
and finalized older handoff artifacts remain unchanged.

V2.15 final validation: 634 new-and-parent cases passed (227 new v2.15;
114 v2.12, 87 v2.13, 206 v2.14). The exact prior 3,213 historical cases
passed. Affected modules: 382 passed, 44 failed, 5 Linux-only skips. The
44 failures reproduced with matching categories and normalized messages on
the captured pre-edit source; exact results and
comparison evidence are retained in validation. These host limitations do
not establish Linux sandbox readiness. All 36 historical identities and
profile tables, all older prompt pins, and the original worker bytes match.

V2.15 fix round 1: F1 re-screens fitted diagnostic displays and omits invalid
envelopes with counted unit-local reasons; F2 bounds screening and separates
diagnostic extraction from the accepted hook outcome; F3 retains screened
diagnostics alongside output faults. Caps and all prompt pins are unchanged.
Final tests: 736 new-and-parent cases passed (329 v2.15), and the exact historical 3,213 cases passed.
Affected modules: 382 passed, 44 pre-existing failures, 5 skipped; failure messages match the pre-fix evidence.
The optional full suite was skipped. All 36 older identities and original
worker bytes match. No real smoke or method-effect result is established.

## v2.17 — zebra-hp-g3r2 fixed chain-G solver read (2026-10-31)

**Superseded scope:** this tested configuration has never been launched.
The owner's 2026-11-01 02:30 decision makes `implant-v5` the active read;
the completed Zebra-only implementation and its validation history below
remain intact.

The owner chose “导出第 2 轮求解程序” after main-v5 training-side inspection.
This child of zebra-hp-v3r4 imports only `p-zebralogic-3-3`, the strict
round-2 solver from main-v5 chain G, with its exact 6,872 source bytes and
stored metadata. The helper is excluded. The brief reports 16/16 correct
among 16/57 practice items with a note and 11/11 among 11/38 confirmation
items with a note; the whole candidate with its helper failed confirmation
(four fixed, eight broken). The selected solver passed main-v5's v2.9
phase-1 audit, with zero findings in 12 sampled / 16 eligible situations.
These supplied training facts were not independently replayed here.

Only G launches, using main-v5's GLM-5.3 roles repository/client/route.
The new fixture package is
`3a624e69b8d371eec2ac427ca439e03baedb9028a99b95f0a972fe734e796eb2`.
Its new hash reflects fixture evidence, package/parent step identities and
the omission of the helper; source, id, lineage and all other stored
procedure metadata are unchanged. Current package validation and main-v5's
Zebra v2.9 policy pass. One import step makes no learning calls, followed
by the existing 200-item F/C read. The sealed split-v1 panel is also the
panel main-v5 pins, established from code/configuration only.

The G solver bound is 65,536 tokens per logical cell: 400 cells give
26,214,400 tokens. The existing 13/10 start gate requires a 34,078,720 read
cap; 1,100,000 first-call headroom gives 35,178,720 solver/overall caps.
Learning caps are zero. S1, ten-cell S2 and SE6 must pass on the same G
solver probe; S3 is inapplicable. No local fixture test establishes a real
GLM reply, measured smoke or Linux readiness.

The registered F−C read is `post_hoc_selected_upper_bound`, with no learned
benchmarks and imported `[zebralogic]`. It is not evidence that the method's
gates work. Report the registered primary analysis alongside the owner's
second analysis that counts byte-identical F/C requests as ties; conclusions
follow the primary analysis. Per-call request hashes support that read-only
analysis. The additional preregistration file referenced in the brief is
not present locally; only the explicit rule in this brief is adopted here.

All 38 older configurations were captured before edits and pass canonical
byte-identity checks. The targeted 44-module regression selection passed
1,186 tests; the final four new modules passed 118 tests separately. These
counts overlap and are engineering-fixture evidence only. See
[preregistration](V217-PREREG.md),
[future operations](V217-OPERATIONS.md), [validation](V217-VALIDATION.json),
[changed files](V217-CHANGED-FILES.txt) and [source hashes](V217-SOURCE-SHA256.json).
This increment is offline engineering work: no network/model/paid/Docker
calls, dl or `/data` access, secrets or commits. No sealed or test data was
opened, and the three living documents remain untouched.

### Active v2.17 addendum — implant-v5 (2026-11-01 02:30)

The owner's instruction is preserved verbatim in
[the active preregistration](V217-PREREG.md#active-addendum--implant-v5-owner-decision-2026-11-01-0230).
The active child inherits main-v5's two solver routes, instruction cards,
F/C/B/stage machinery, five frozen test panels, read locks, Sheet
qualification and cleanup, and reporting controls by value. The panels
are SearchQA, OfficeQA, ZebraLogic, SpreadsheetBench and ALFWorld; panel
identity was checked from configuration/preparation pins without opening
sealed or test data. Similar pairs remain SearchQA–OfficeQA and
OfficeQA–SpreadsheetBench, with no related bench for ZebraLogic or
ALFWorld.

There are no learning units or method-role calls. Steps 1, 2 and 4 preserve
the exact parent package and persist the registered skip reason. At step
3, G imports the exact selected `p-zebralogic-3-3` program from the v2.17
fixture and D imports the exact v3r4 program from the v2.13 fixture. Both
pass main-v5's Zebra policy and current package validation unchanged.
At step 5, the existing alfworld-v11 composer appends its same three
procedures with the same ordering and capacity check. Both chains' rows
are exactly **[C, C, C, S3, S3, F]**, asserted from persisted step records
and exact package membership before any read cell. The G and D real S3
package hashes and every field changed from the source fixture are pinned
in preregistration; evidence and chain/step identities change, while the
selected source and remaining stored procedure fields stay unchanged.

This is **main-v5 with one Zebra program implanted, learning skipped**,
labelled `post_hoc_selected_upper_bound`. G was selected after training
and confirmation inspection and before its hold-out read. D v3r4 already
had one Zebra read, F 188/200 versus C 165/200; its next Zebra read is a
replication of a known result. ALFWorld is main-v5's registered fifth-step
import, and the supplied main-v5 history says steps 1–4 adopted nothing.
These facts establish no success of the method's learning gates. On
ZebraLogic F and S3 supply the same note: existing sharing can make them
zero-dispatch aliases, and any independently dispatched difference is
same-text rerun noise. On non-Zebra benches S3 is expected to equal C where
Zebra `applies` is false; F is expected to equal C only where the ALFWorld
procedures also do not apply. F may differ on ALFWorld.

The registered primary row-minus-C, row-minus-previous-row and F−C/C−B/F−B
contrasts must be shown beside the planned analysis counting byte-identical
requests as ties, with conclusions following the primary analysis. The
request-hash tie analysis is a separate reporting step; the existing
readout's statistical sensitivity analysis does not automatically produce
it. Report every row/bench and its denominators, not only favorable cells.

All 39 pre-existing configurations, including the unlaunched Zebra-only
v2.17 child, were fingerprinted before the first addendum edit. The base
read allowance stays main-v5's 456,000,000 per chain without discounting
repeated rows. After [fix1](FIX-BRIEF-v217-1.md), the 206,000,000 reserve
for the largest single inherited worst-case seven-arm unit (ALFWorld)
is included in `<chain>:test`, making its cap **662,000,000**. There is
no separate `<chain>:redo` scope. With unchanged first-call headroom of
1,100,000, solver/overall stay **663,100,000**. Method caps remain zero.
The exact per-bench formula and numeric ALFWorld calculation are
preregistered.

The review found that the former separate redo scope was never charged by
read attempts. Merging its allowance into the test scope lets the unchanged
relaunch gate see and spend it. In the reviewer's scenario, a 300M estimate
still needs 390M at first start; after four panels complete and test spending
reaches 300M, the remaining 150M ALFWorld estimate needs 195M. The test scope
now has 362M left instead of 156M. SE6 prices the read plus one whole-unit
retry in both test and solver scopes. Evaluation charging, retry/reuse rules
and older configurations are unchanged. Old-cap smoke receipts and
manifests must be regenerated on a fresh snapshot, not patched or resealed.

The active operations use the v214 CLI with `--configuration implant-v5`.
S0 writes the exact supplied owner consent before launch and retains the
snapshot-specific q23/scorer checks. Both chains require S1, S2 and SE6 on
the same pinned solver probe; neither S3 nor SX applies. The structural
smoke writes both fixed chains and checks the six rows with zero model
calls and zero sealed reads; it is engineering evidence, not measured
readiness. Future blockers include actual Linux isolation/dependencies,
q23/Sheet runtime, route access, first responses, usage and format checks,
SE6 fit, pin consistency, consent and read-release controls. No launch or
Linux access occurred in this work. The active
[operations](V217-OPERATIONS.md), [validation](V217-VALIDATION.json),
[changed-file list](V217-CHANGED-FILES.txt) and
[source hashes](V217-SOURCE-SHA256.json) record the handoff and exact local
test counts. No network/model/paid/Docker calls, dl or `/data` access,
secrets, commits, or edits to the three protected living documents were
made for this addendum.

The expanded local check also reproduced five generic step-test failures
on the captured pre-addendum source tree, with identical error lines. They
are outside this child and remain unchanged; they may block the full S0
pytest gate. The validation receipt distinguishes these baseline failures
from the final required regression selection.

Before fix1, the final required selection was **1,324 passed in 167.60s**
across 48 modules, including 136 new implant cases and all 39 older-configuration identity
checks. The earlier expanded 80-module run was 2,221 passed and six failed:
one older-roster test incorrectly included the new child and was corrected;
the other five reproduce on the untouched baseline (five failed in 19.84s).
These counts overlap and establish engineering behavior only.

Fix1 validation: **605 passed in 55.79s**, including ten new retry-budget
cases for both chains and all 39 older-configuration identity checks.
The reviewer scenario now passes the relaunch gate; SE6 checks the combined
read-and-retry cost, and manifests reject the old caps. The historical five
generic step-test failures remain outside this fix and were not rerun.

## v2.18 — main-v6, four owner-approved changes (2026-11-01)

[The brief](BRIEF-v218-main-v6.md) adds a new main-v5 child while freezing
all 40 earlier configurations, including implant-v5, main-v5, zebra-pc-v15
and the still-unlaunched zebra-hp-g3r2. Their complete pre-edit configuration
fingerprint was captured before any source edit and is tested after the
change. No historical result or V217 deliverable is rewritten.

Main-v6 keeps the five-benchmark order, instructions, pools, slices, panels,
training/confirmation/acceptance rules and chain-end F/C/B/stage read. Four
changes are isolated to it: (1) a train-adopted, confirm-failed multi-procedure
candidate may be split into immutable incumbent-plus-one subcandidates,
with at most one adopted after both verdicts; (2) read cells share exact,
fault-free request identities, preferring C, then F/earlier running stages;
(3) memory locking surrounds Sheet environment/workbook/native work and
ALF episodes/reset, with wait and holder receipts, leaving role-only work
and completed readback unlocked; (4) Zebra uses v15 engineer diagnostics
and the three-inert-repair/two-audit-fix cycle. Other learned benches retain
main-v4 machinery, and step 5 still imports alfworld-v11.

Split history contains counts only; confirmation contents never enter the
engineer context. Splitting re-tests up to three subcandidates on the same
confirmation items, an explicitly approved multiplicity relaxation.
Unchanged fresh-item acceptance remains the final gate. Split evaluations
use one run per item, deterministic run 0 when reusing parent results, and
price both sides of every pair for the missing-incumbent case. Original
whole-candidate OfficeQA/Sheet training retains its two-run schedule.

The primary read contrasts remain authoritative, with the complete
request-hash-sequence tie analysis beside them. The authored reuse fixture
reduces 72 logical cells to 40 dispatches; this is engineering coverage.
Actual main-v5 savings cannot be computed from permitted fixtures without
opening unavailable historical request records, which was not done.
Neither code availability, a split confirmation pass nor imported solver
performance establishes accepted Skill evolution.

[The preregistration](V218-PREREG.md) enumerates all 13 differing tables,
the v13-to-v15 table changes, design decisions and cap formulas. Per chain:
step scopes sum to 1,352,700,000; after fix1, read is 662,000,000;
learning redo reserve remains 263,200,000; solver rounds up to 2,280,000,000.
Method is 7,070,923,008 + 521,867,776 = 7,592,790,784.
Overall is 9,872,790,784 per chain.
Root is `/data/execskill-20261101-main-v6`, namespaces G-m6/D-m6 and
evidence `main_v6_real_run`; these are strings only in local work.

[Operations](V218-OPERATIONS.md) retains the v214 default and adds explicit
`--configuration main-v6`. Preparation writes exact owner consent and binds
a new snapshot, both sandbox workers, q23 and active Sheet runtime. Both
chains require all six measured smoke stages S0/S1/S2/S3/SE6/SX. SX uses
zero-call split/reuse fixtures. The real manifest requires both summaries;
G starts first and D follows G's verified first response. These future
steps were not executed. Linux isolation/dependencies, q23/runtime,
credentials/routes, ALF availability, response format/usage, measured SE6
fit and the inherited read-budget/release gates can still block readiness.

[Validation](V218-VALIDATION.json) records exact local test counts and
intermediate failures separately from the final passing selection. The
known five macOS generic-step failures remain outside this configuration.
A broader run was interrupted during a legacy CLI rehearsal after 227
passes; it is not claimed as a complete suite result. The final required
selection covers zhp/zpc, v214–v218 and affected modules. No network,
model, paid, Docker, dl or `/data` access, secrets, commits or edits to the
three protected living documents occurred. All scratch is outside the
checkout. [Changed files](V218-CHANGED-FILES.txt) and
[source hashes](V218-SOURCE-SHA256.json) identify this task's exact output.

The expanded check also exercised older worker fixtures outside the requested
version selection. Forty such failures (including the five known step cases)
reproduced on the 1,414-file pre-edit Python tree. A separate old v295 roster
assertion for implant-v5 was corrected to check its frozen zero-round contract;
production behavior is unchanged. Three unrelated localhost-proxy fixtures
were blocked at socket bind, before any connection/request, and were not
rerun. These are recorded as local limitations, not main-v6 results. Final
SX retains the parent's persisted stage-row demo in addition to split/reuse.

Initial implementation's final configuration regression: **2,228 passed in 340.15s (0:05:40)**,
including **148 new v2.18 cases** and all 40 older-configuration fingerprints.
The recomputed post-edit capture is byte-identical to the pre-edit file
(SHA256 `cfb663c420fe5004c7ea68bd469835735ac05d859c7f2aaa0e6970ebdf7c80bb`).
The initial task changed 54 files (31 implementation/CLI, 16 tests, one capture and
six handoff documents). The three living documents, audit.py and all V217
handoff artifacts retain their pre-task bytes. These counts overlap the
intermediate runs in validation and are not a full-suite pass claim.

### v2.18 fix1 — three reviewed findings (2026-11-01)

[Fix brief](FIX-BRIEF-v218-1.md) and [review](codex-review-v218.md).
Reused split cells and trajectories keep their original source-package
attribution. Main-v6 subcandidate coverage instead binds its own captured
notes to its package, source cell and identical delivered request. The
authored A+B scenario (B returns no note on training, A alone passes
confirmation) covers real feedback, diagnostics, source immutability and
resume without repeating dispatch.

The test scope now funds one largest registered read-unit retry:
456,000,000 + 206,000,000 (ALFWorld) = 662,000,000. Learning redo keeps
263,200,000 separately. Solver is
`ceil_5000000(1,352,700,000 + 662,000,000 + 263,200,000)` = 2,280,000,000;
the 205M increase from the initial solver cap follows the existing rounding.
The runtime 1.3 gate is unchanged. The reviewer's interrupted read leaves
362M for the 195M ALFWorld relaunch requirement. SE6 prices the full read
plus the largest measured read-unit retry as well as independent learning
redo; manifests reject initial main-v6 caps. Fresh snapshot/S0/smoke/manifest
receipts are required before launch.

Shared F/stage cells now bind their own keyword-hit metadata in the request
plan, alongside their own enabled procedures and applicability. Scores and
provider provenance still come from the actual source, so scores remain
exact ties even when a silent procedure adds two keyword hits.

Fix1 affected regression: **790 passed in 65.48s (0:01:05)**, including
all **168 v2.18 cases** (20 new fix1 cases) and all 40 older-configuration
fingerprints. The first focused run was 166 passed and two failed because
the new test passed an unsupported attempt argument to the existing read
scope API; correcting that test call required no production change. The
final run includes those corrected cases. Counts overlap; no full-suite or
real smoke result is claimed. The older capture retains SHA256
`cfb663c420fe5004c7ea68bd469835735ac05d859c7f2aaa0e6970ebdf7c80bb`.

Fix1 changes 17 files: seven implementation files, four test files and six
handoff documents. The cumulative V218 list now has 58 files. The three
protected living documents, audit.py, V217 artifacts and earlier sections
of these notes retain their bytes. No prohibited calls/access or commits
occurred in this fix round; scratch and pytest output stayed under `/tmp`.

## v2.19 — cross-v5, fixed package plus cross-benchmark instruction cards (2026-11-02)

[The brief](BRIEF-v219-cross-v5.md) adds a child of implant-v5 after the
final v2.18 review fix. The owner describes the baseline as the 1,576-file
hash-list prefix `65069ec05cbf6ae1`, remote commit `60af599`, and main-v6
launch at 12:50 on 2026-11-01. These are supplied provenance; the writer
did not access Linux or the running snapshot. The pre-edit capture covers
all 41 older configurations and has SHA256
`7bfbff8fc6b65953a51dbb4ae7ff8ac717da8ec633bf704c59040e52c0066509`.

Cross-v5 reuses the exact implant chain: skip SearchQA/OfficeQA/Sheet,
implant the chain's fixed Zebra procedure at s3, and compose the unchanged
alfworld-v11 procedures at s5. Source bytes, procedure fields and package
composition match the parent except evidence stamps and resulting identity
hashes. This is a post-hoc selected upper-bound transfer description, not
learning or evidence that the method works.

Each target panel reads F/C/B plus the four `X_<source>` arms from the
other benchmarks, with no stage arms or rows. Every X uses the same final
package and the target shell, substituting only the frozen source card in
its ordinary card slot. `card_source` identifies that source benchmark in
each raw, sealed and unsealed cell; B has null. X_zebralogic sends the neutral
“Follow the format in the user message.” card on another target, not blank
guidance. F and X score on L; C and B on H.

Main-v6's exact-request reuse is reused by value. SearchQA, OfficeQA and
Sheet have no effective program hooks, so F shares C and X measures card
transfer alone. Broad inherited ALFWorld predicates can still appear in
enabled metadata there; their episode hooks are not invoked. Zebra's shell omits every card: all X share F and B shares C, making
the Zebra column F−C by construction, explicitly not transfer evidence.
ALFWorld dispatches all seven arms; X−F isolates the card while X−C mixes
card and package. The full panel has 8,295 logical cells and a registered
6,444-dispatch construction bound per chain, before further exact ties.

The registered matrix reports every target/source accuracy (diagonal F),
X−C and X−F with the existing paired estimate, beside the main-v6 analysis
that sets byte-identical full request sequences to zero. F−C/C−B/F−B remain
the primary contrasts. Same-text rerun noise still applies to dispatched
pairs. Both selected Zebra programs were chosen after viewing training;
D's v3r4 panel results already include v2.13 188/165 and implant-v5 188/162.
The 134-episode ALF panel is on its fifth read after alfworld-v11, main-v4,
main-v5 and implant-v5. The other three panels have already been read in
main-v4, main-v5, baseline-v210 and implant-v5.

[Preregistration](V219-PREREG.md) states the owner quote, interpretation,
all seven table differences and exact cap arithmetic. The specified
6/6/2/6/7 arm schedule gives a 413M base read and 206M largest-unit retry;
adding 1.1M first-call headroom gives 620.1M solver/overall per chain,
with zero method or learning budgets. The charged test scope combines the
base and retry as 619M. This is lower than implant-v5's retained all-stage
456M base/662M funded read allowance; the brief's rough “about twice”
expectation does not follow its specified arm counts. No extra multiplier
was invented. Card-slot fixture comparisons use C with an empty/inert
package, and F when testing an active package, preserving actual program
notes where the literal C comparison cannot hold.

[Operations](V219-OPERATIONS.md) describes fresh snapshot, owner consent,
q23/Sheet runtime and S0/S1/S2/SE6 on both chains, with no S3/SX. S2 retains
76 C practice measurements and adds all other arms on one item per target:
106 logical cells. It measures source-card shapes and sharing before launch;
SE6 uses conservative measured arm costs and funds the read-unit retry.
Environment-only locking, waits and holder metadata are reused from main-v6
so both runs can share the machine without changing its running snapshot.
Read opening waits for both chains to end and the existing release gates;
the operator records the owner's 2026-11-02 request in project-status §5.
The writer has not edited that protected living document.

[Validation](V219-VALIDATION.json), [changed files](V219-CHANGED-FILES.txt)
and [source hashes](V219-SOURCE-SHA256.json) identify local engineering
coverage and integrity checks. Measured Linux readiness, q23/runtime,
isolation, credentials/routes, ALF availability, actual solver format/usage,
SE6 fit and release remain pending. No prohibited calls/access, commits or
protected-document edits are part of this work; scratch is outside the checkout.

Final v2.19 local regression: **1,819 passed in 218.36s (0:03:38)**,
including **206 new cross-v5 cases**. The selection covers v214–v219,
fixed Zebra v213/v217, zpc and affected modules. All 41 older configuration
fingerprints remain byte-identical to the pre-edit capture. The first run
had 19 integration failures and 187 passes; those were corrected, a second
focused run passed all 206 new cases, and a final exposure-roster correction
and regression assertion are included in the 1,819-case pass. Counts overlap.
The five owner-reported generic macOS step failures were not rerun; this is
not a full-suite/S0 pass claim.

The change spans 35 files: 18 implementation/CLI files, ten test files,
one pre-edit capture and six handoff documents. The three protected living
documents, audit.py, V217/V218 deliverables and all earlier notes retain
their bytes; no new bytecode or scratch was left in the checkout.

Fix round 1 (2026-11-02): cross arms exist only in registered chain-end test-read and v214 S2 practice units.


## v2.20 SearchQA rejected-candidate read (2026-11-02)

Implemented `searchqa-hp-v6` from the [owner brief](BRIEF-v220-searchqa-hp-v6.md).
This is an owner-requested post-hoc upper-bound description of the SearchQA
candidates rejected by J1 under practical-v2-11-pooled, never method evidence.
G's training acceptance was -0.4206 points on 951 items (17 up, 21 down);
D's was +1.0 points on 1,000 items (21 up, 11 down). The reused SearchQA panel
has the exposure history disclosed in the [preregistration](V220-PREREG.md).

Both main-v6 chains must finish before S0 pins their completion records,
ordered final packages and every procedure, with record hashes, raw-file
hashes and self-contained copies bound to the source manifest. Step 1 imports
those copies; step 2 appends G's p-searchqa-1-2/p-searchqa-1-3 or D's
p-searchqa-1-10/p-searchqa-1-11 as NEW procedures. All nine supplied candidate
fixture files and all program bytes remain unchanged. The live main-v6
prefixes and derived final hashes are S0 outputs; they were not read locally.

Only SearchQA is read: 400 items, F/C, no B or stage rows, no Sheet work or
memory lock. Main-v6's fault-free request reuse and paired F-C/identical-request
second analysis are retained; note-emission counts and enabled predicates
are reported separately. Per chain: 36M read + 36M retry + 1.1M first call =
73.1M solver/overall, method zero; both chains total 146.2M. S0/S1/S2/SE6 only.
S2 has 20 inherited C practice cells plus three explicitly authored C/F
mechanism probes, 26 logical cells, requiring both candidate emissions and
a shared silent request. These are engineering checks, not effect evidence.

Local required regression: 194 new v2.20 cases pass. After restoring legacy
implicit-consent refusal, the repeat result is `5 failed, 1912 passed,
2 deselected in 182.36s (0:03:02)`: the five failures are the known macOS
step cases. The two deselected legacy CLI rehearsals both completed and
failed in the initial full selection with fake-worker EOF/not_loaded in S3;
those exact CLI nodes were not reproduced on the parent here, so platform
causation is likely rather than established. All 42 parent fingerprints match
byte-for-byte. The original failed runs are retained in
[V220-VALIDATION.json](V220-VALIDATION.json); no full-suite or measured Linux
S0 pass is claimed.

[Operations](V220-OPERATIONS.md), [changed files](V220-CHANGED-FILES.txt) and
[source hashes](V220-SOURCE-SHA256.json) are delivered. No model, network, paid,
Docker, Linux/dl or /data access, commits, secret output, actual sealed/test
reads or living-document edits occurred. Both source completions, valid
consent, a reviewed snapshot/selftest/S0, both measured route smoke summaries
and inherited release gates remain pending operator prerequisites.


## v2.21 — main-v7: touched-item gain and no harm (2026-11-02)

Implementation and local authored fixtures only; no measured operator S0,
model smoke, real learning run or method-effect result. The additive child
preserves main-v6's pools, practice slices, four learning steps plus alfworld-v11
import, F/C/B/stage read, consent, request reuse and environment-only lock.
All 43 older configuration fingerprints match the pre-edit capture byte-for-byte;
all older fixtures, including v2.20's candidate files, remain unchanged.
Rollback means selecting the older configuration and matching frozen snapshot;
the owner identifies `route-b-v2.19-frozen-20261102` / `1de2a067` as the rollback
point, which the writer did not access remotely.

The shared training/confirmation/immediate-acceptance rule requires net fixed
minus broken on touched items ≥ max(3, ceil(0.10*T)), broken ≤ 2/3 fixed, and
whole-batch gain ≥ −0.01. Its constants are named in each decision. Brief-supplied
SearchQA G 17/21 rejects; D 21/11 at T=32 accepts; T=2 rejects; dense 40/5 at
T=100 accepts. These are engineering worked cases, not new task scores.
Request and post-call identity differences define T on SearchQA, OfficeQA,
ZebraLogic and SpreadsheetBench; changed-procedure delivered notes define it
on ALFWorld. Repeated runs stay within each item's mean pass rate.

J3–J6 remain stored diagnostics; J1/practical decision is replaced. Both judges
plus own-confirmation net harm are required for truth-based removal; policy
remains hard. Qualifying rounds consume unseen acceptance prefixes, stop at
60 touched or A-size/pool exhaustion, and retain accepted improvements.
Failed immediate acceptance rolls back. Split merges all passing sub-candidates
in registered order, rechecks training then confirmation, and falls back by
confirmation net, training net, then order. Final audit sees training and
confirmation histories only; inherited hard final checks can still release a
step. Broad-coverage guidance, cumulative candidate coverage and fewer-than-3
repair use the existing bounded engineer machinery. A no-candidate round has
null coverage. Pure infrastructure pauses get one durable, logged retry after
60 seconds; all other owner pause paths remain.

Freshness has a finite supply: practice remains reused across rounds as in
main-v6, while confirmation/acceptance samples are fresh under their frozen
allocations. Zebra's single 40-item confirmation slice is consumed once, even
on failure; later qualifying rounds reject without calls. This default was
stated after optional clarification received no reply. A nonempty last
acceptance sample can pass below 60 touched; an empty fresh pool cannot.
Several fresh samples per step create multiplicity. Each adoption has its own
fresh acceptance evidence; the later sealed chain-end read remains the only
test evidence. No such read was performed here.

Caps retain the old first acceptance allowance and add five full maximum
reads plus merged training/confirmation checks, without reuse/exhaustion credit.
Step caps sum to 1,841,400,000, read stays 662,000,000 and learning redo becomes
322,000,000. Rounding their sum to 5M gives 2,830,000,000 solver per chain;
method remains 7,592,790,784, total 10,422,790,784 per chain / 20,845,581,568 both.

All 230 new tests pass (profile 58, preparation 11, rule 83, learning 26,
recovery 40, smoke 12). The initial required regression returned
`14 failed, 2441 passed in 963.83s (0:16:03)`. After the final prompt-record and null-coverage fixes,
the repeat returned `7 failed, 2458 passed, 7 deselected in 203.85s (0:03:23)`; only the five known macOS step nodes and
two legacy CLI rehearsals were deselected. The seven remaining legacy engineer
failures reproduce on exact captured pre-edit sources: `7 failed, 6 passed in 22.89s`.
A narrow diagnostic reports C6 `crash:worker`; its underlying process cause
was not further isolated. Receipts remain intact; no full-suite or measured
operator S0 pass is claimed. Exact commands, failure nodes, source pins and
implementation decisions are in [V221-VALIDATION.json](V221-VALIDATION.json).

[Preregistration](V221-PREREG.md), [operations](V221-OPERATIONS.md),
[changed files](V221-CHANGED-FILES.txt) and [source hashes](V221-SOURCE-SHA256.json)
complete the handoff. SX tests the three-stage rule, early acceptance, split
merge, audit non-drop and automatic retry with zero model calls. Reviewed
source/runtime pins, native Sheet qualification, G/D first responses, S3/SX
and measured SE6 fit remain operator prerequisites. Only S0 and smoke follow
review; a real launch is **not before the owner's go**. No network, model,
paid, Docker, Linux/dl or /data access, commits, secrets, actual sealed/test
reads or living-document edits occurred; scratch and bytecode stay outside
the checkout.


Fix round 1 (2026-11-02): all five findings in
[FIX-BRIEF-v221-1.md](FIX-BRIEF-v221-1.md) are addressed. Silent Sheet callbacks
are diagnostic registrations only; actual request/note/repair effects determine
touches, and no touches records `no_touched_items`. Final audit pruning now
rolls back to the latest compatible package with its own acceptance decision
or to the step parent, with `training.acceptance_binding` naming the action;
no additional acceptance read or cap increase. Confirmation evidence retains
comparison direction, package hashes and procedure version: rejected deletion
0 fixes/7 breaks cannot turn retained P's 6 fixes/0 breaks into harm. Narrowing
compares the previous scope. Shared qualification recovery uses unit-only
identity, separate initiating-chain metadata, and permits D to finish G's
remaining wait. These changes apply only to main-v7.

Fix-round required plain pytest: `12 failed, 2442 passed in 204.42s (0:03:24)`, with no deselections.
All 254 main-v7 cases pass, including 24 added regression cases.
The remaining failures are the five previously acknowledged macOS step cases
and seven legacy engineer cases already reproduced on the captured pre-edit
source. No new failure node appeared; the full receipts remain in
[V221-VALIDATION.json](V221-VALIDATION.json). All 43 parent fingerprints still
match byte-for-byte; older fixtures and the protected living documents are
unchanged. No measured operator smoke or real launch occurred.


Fix round 2 (2026-11-03; [brief](FIX-BRIEF-v221-2.md)): restored the unique
legacy endpoint/qualification mutation anchors with main-v7 recovery gated
separately, tolerated missing manifest configuration, and corrected the canonical
exception import exposed by the named integration test. Four named tests:
`2 failed, 2 errors in 8.74s` before, `2 passed, 2 errors in 9.22s` after; the mutation cases remain blocked
in unchanged detector-worker fixture setup. Exact registered target probes
passed unmutated and failed when mutated: one case for mutation 06 and two
cases for mutation 80.
Versioned selection: `1813 passed in 134.10s (0:02:14)`. Broad selection: `94 failed, 7512 passed, 5 skipped, 3 deselected, 2 warnings, 169 errors in 3789.19s (1:03:09)`,
with only three live-loopback tests deselected under the no-network constraint;
all 254 main-v7 cases pass. No full-suite or measured Linux pass is claimed.
All 43 fingerprints match; tests, mutation registry, frozen fixtures and protected
living docs are unchanged. [Validation](V221-VALIDATION.json) retains commands,
failures and supplemental evidence. No external calls or launch occurred.


## v2.22 — main-v8 routed instruction segments and cross-bench gate (2026-11-03)

This is an offline engineering implementation of
[BRIEF-v222-main-v8.md](BRIEF-v222-main-v8.md), not a measured method result or
launch authorization. The cited `docs/handoff/cross-v5-readout-20261103/`
extraction is absent here; its numbers are owner-supplied motivation quoted in
the brief, not independently re-extracted evidence. The separate card probe was
read but not run. All 44 pre-existing configuration fingerprints were captured
before code edits in `tests/fixtures/execskill/v222_parents_before.json` and
recomputed byte-identically afterwards (SHA256
`7bc4aac383ccbedb476b4506e5f6169be8f8e128cb304eaa29d259104f8e6195`).

`v222_cards.py` pins all five historical decompositions, their exhaustive source
line partitions, text hashes and structural predicates. The historical fifth
card is LiveMath, now inactive; its three segments are retained in the fixture.
Zebra's registered neutral card is entirely format and gains no invented content.
Active P0 has 11 note procedures: SearchQA 2, OfficeQA 3, Sheet 3, ALFWorld 3.
SearchQA evidence without quantity cues and OfficeQA evidence with quantity/scale
cues distinguish the shared public QA structure; missed home coverage must pass
the measured decomposition check. Workbook previews and admissible commands
supply the other predicates. Every segment is at most 1,500 rendered characters
and uses unchanged note limits. A new policy and isolated worker admit the exact
pinned seed sources, including public ALF command examples, while old policies
and both old worker files stay unchanged. Learned segments use the existing
new/revision change schema and the same training, confirmation and acceptance
rules as computational procedures.

Main-v8 alone starts from P0 and reads B (blank), C0 (format shell), C (format +
P0), F (learned package), plus the existing stage rows. Empty intermediate
packages remain distinct stages, and P0 remains C. C_hist is restricted to the
one-time practice decomposition unit: 100 items per bench, 20 ALF games, whole
accuracy no worse than -1 point and no worse format counters. Retries reuse the
original historical cells. A failed split uses one verbatim remainder segment
only if it fits the unchanged cap; oversized fallbacks stop explicitly.

`v222_gate.py` and `v222_runtime.py` register seeded 60-item/20-game harm slices,
exclude all protected home confirmation/acceptance allocations, inspect rendered
requests without a solver and run one paired cell only for each fired item.
Changed dynamic ALF hooks or unreplayed Sheet callbacks are conservatively
potential firing, never a false zero-cost identity proof. Every other bench
must have nonnegative net fixes and whole-slice change >= -1 point. Whole,
split and merged confirmation candidates and immediate acceptance all carry
bound cross decisions. New additions may be narrowed through the existing
bench exclusion layer, then all other benches are rechecked inertly; revisions,
deletions, or residual unsafe changes reject. No task IDs enter predicates.
Receipt bindings include configuration, home, unit, parent, candidate and harm
registration; acceptance retries charge redo scopes and reuse completed pairs.
An exact-unit filter keeps nested cross-gate trajectories out of the home final
audit sample; cross-gate evidence remains in its separate gate records. Split and
merged retries isolate only cross cells bound to their registered pair plan;
unrelated or unbound cells still reject, and main-v7 keeps its original refusal.

`v222_hygiene.py` enumerates each original own-segment deletion and applies the
unchanged home count rule. Neutral cached comparisons retain the segment.
**Production hygiene is blocked pending an owner measurement schedule:**
removing a delivered note creates a distinct request, and the inherited first
training slice does not already contain those deletion arms. The brief's zero
extra calls cannot supply their scores. A qualifying deletion also needs fresh
home confirmation/acceptance and cross decisions without consuming or changing
the six inherited engineer rounds. Missing measurements and qualifying drops
therefore write an explicit pending record and pause before training; ALF's
fixed import has the same prerequisite. This is not an operationally completed
hygiene experiment and does not silently skip hygiene.

`v222_read.py` records actual non-home F-cell note/request effects, including
verified Sheet callback delivery and shared-cell provenance, with no extra read
calls. Its `cross_identity` block reports item and procedure counts and F-C
fixed/broken counts on the touched subset. Those contrasts are descriptive,
not isolated causal attribution to an individual procedure. Frozen P0 and the
fixed ALF import are not called learned improvements. Count-only feedback adds
segment coverage and cross-gate aggregates; protected harm rows and answers do
not enter the engineer channel. Existing J3-J6 diagnostics, two-judge audit,
early acceptance, split/merge, recovery, ALF import capacity and Sheet locking
remain inherited.

The conservative reservation is 5 confirmation candidates (whole + 3 split +
merge) and 1 acceptance candidate per round, times 6 rounds, times 4 other
benches x 60 items x 2 arms = 17,280 paired item cells per learned step. ALF's
actual slice is 20 episodes, while the cap keeps 60; episode token anchors price
its internal calls. No reuse, sparse-firing or narrowing discount is assumed.
Step caps sum to 6,874,100,000; read cap is 743,000,000 (including its largest
unit retry), learning redo is 1,144,200,000, and the rounded solver cap is
8,765,000,000 per chain. Method cap stays 7,592,790,784, giving 16,357,790,784
per chain and 32,715,581,568 for both. Additional hygiene measurements are not
invented or hidden inside those unchanged training reservations.

The existing practice supplies also cannot satisfy the exact new denominators:
OfficeQA has 74 items and an 18-item training allocation; Sheet has 91 and 31.
Neither supplies a 100-item decomposition slice or a 60-item harm slice while
preserving protected decisions. S0 fails before native/model work. An optional
explicit SHA-pinned additional practice supply can be reviewed by the owner;
it does not recut home slices or permit protected IDs. The owner must resolve
this supply question, the hygiene schedule (including ALF), and the possible
oversized verbatim fallback before operational readiness can be claimed.

Eight operator templates provide m8 environment/preparation/smoke/launch/driver,
Linux full-suite pre-test, delegated consent-writer patch and commit script.
No m7 shell scripts or delegated writer source were present, so the commands
follow V221-OPERATIONS and the consent patch requires an exact reviewed writer
hash and whitelist line. Drivers check each step's last log line and exit code;
Python `-c` strings use single quotes internally. Exact pinned copies under
`tests/fixtures/execskill/v222_ops/` make the ops regressions executable in
source snapshots without handoff documents; when the documents are present,
their bytes must match. No template was launched.

Final v214-v222 selection: `2073 passed in 213.42s (0:03:33)`; all 260 main-v8 cases and all 254 main-v7 cases pass. Final-source macOS-supported broad selection: `7774 passed, 5 skipped, 266 deselected, 2 errors in 694.38s (0:11:34)`. Its 263 inherited failure/error-node exclusions come verbatim from V221, in addition to the three real loopback exclusions; no new v2.22 node is excluded. Broad route-B attempt retaining all known macOS cases: `96 failed, 7756 passed, 5 skipped, 3 deselected, 2 warnings, 171 errors in 4345.33s (1:12:25)`. In that all-cases attempt, only the three real loopback tests were deselected under the no-network constraint. The first broad run started before the main-v8 confirmation/audit isolation filter, cross-cell retry isolation, and the two broad-regression fixes; the final versioned and supported broad selections cover the finished source. All 94 inherited failure nodes and 169 inherited error nodes recur in the first full attempt; its two extra regression failures are corrected in the final source, and its two extra mutation wrappers share the inherited detector-worker setup blocker. No Linux full-suite pass is claimed. Both new exact registered mutation targets passed unmodified and failed after mutation in isolated scratch copies (139: baseline 7 passed, mutant 3 failed/4 passed; 140: baseline 2 passed, mutant 2 failed). Those supplemental checks do not turn setup-blocked official mutation wrappers into passes.

[Validation](V222-VALIDATION.json), [changed files](V222-CHANGED-FILES.txt) and
[source hashes](V222-SOURCE-SHA256.json) retain commands, counts, mutation
receipts, decisions and remaining smoke blockers. No network, model, paid,
Docker, Linux/dl or /data access, commits, secret output, real sealed/test reads,
or edits to the three living documents occurred. Scratch is confined to
`/tmp/v222-vqgwpef2`; no new checkout bytecode or scratch is retained.


**Fix 1 (2026-11-03):** [FIX-BRIEF-v222-1.md](FIX-BRIEF-v222-1.md) resolves and supersedes the three blockers above. D1 now draws from all pinned practice (including the qualified SearchQA tail and optional pinned extras), excluding only each bench's own acceptance allocation. Decomposition uses min(100, available), harm uses min(60, available), both capped at 20 ALF games; available <18 stops S0 explicitly. Run/confirmation items and overlap between the two seeded draws are allowed. Actual counts are registered as `v222_practice_supply` in preparation, S0 and manifest, and verified by smoke/runtime checks. D2 uses at most one measured own-P0 deletion as the ordinary round candidate; it replaces that round's engineer proposal, makes no extra role call, and uses unchanged training, confirmation, acceptance, cross-gate and cap rules. The trigger is the worst negative parent pass-minus-fail net on at least three distinct scored items with verified delivered seed notes; repeated outcomes are averaged within items and ties use P0 order. This is a proposal heuristic, not measured causal harm. Failed deletions may use later ordinary rounds and patience; no new retry policy or budget was added. No hygiene runs on ALFWorld or whole-card benches, and no pre-training pause/zero-call measurement assumption remains. D3 restores the whole historical shell card after a failed decomposition, removes that bench's P0 segments, excludes remaining seed notes there, records `whole_card_fallback` with the measured numbers, and continues without another fallback arm. All five fallback C request hashes match main-v7; other benches retain their routed splits. The verbatim-remainder path is removed. The Zebra-only historical prompt marker is excluded from all other runtimes, preserving ALFWorld environment/view digests. The operator-side m7 scripts remain outside this tree; m8 scripts remain adaptation references. Validation: `2129 passed in 187.18s (0:03:07)` (316 main-v8 cases; 254 main-v7 cases); macOS-supported broad run: `7830 passed, 5 skipped, 266 deselected, 2 errors in 662.32s (0:11:02)`. Its 263 inherited failure/error exclusions are copied exactly from V221, plus three real loopback cases excluded under the no-network rule; no main-v8 node is excluded. The two official mutation wrappers retain the known detector-worker setup blocker; both exact direct mutation probes pass before mutation and fail after mutation. All 44 parent fingerprints remain byte-identical, all frozen card/operator fixtures and three living documents are unchanged, and caps are unchanged from pre-fix main-v8. Remaining blockers: review and Linux full suite, then the real smoke. No network, model, paid, Docker, Linux/dl or /data operation, commit, or real sealed/test read occurred.


**Fix 2 (2026-11-03):** [REVIEW-v222-r1.md](REVIEW-v222-r1.md) identified three integration blockers, now fixed with regression tests. Practice supply paths reject all ten protected-name substrings case-insensitively in every component before byte reads; explicit closed-source aliases remain blocked during preparation and manifest reload. Hygiene provenance stays in persisted engineer/round receipts and is excluded from the exact engineer history schema; real two-round ordinary→ordinary and deletion→ordinary Context validation and resume are exercised. A main-v8-only `alfworld_routing_overlay` is pinned by value in `data.v222_practice` at S0 for the union of seeded harm/decomposition games. It binds both draws, original per-game bytes and source-row hashes, the normalized environment runtime, and every public reset-view hash. All selected game bytes are checked before any native reset; intact exported views are reused, only missing views are reset, and attachment changes copies only. Reconstruction/verification uses the pinned S0 record without reset; setting reload, smoke and runtime refuse missing or mismatched overlays before paid work and compare the harm registration to S0. Separate preflight/selftest/S0 preparation invocations may perform zero-model resets; S0 is the canonical immutable pin. The exporter-shaped authored regression uses the real 108-room/540-game export and room cuts: 150 acceptance games excluded, 390 available, 20 harm and 20 decomposition games. These are synthetic engineering counts, not production-data measurements. Validation: `2221 passed in 160.46s (0:02:40)` (408 main-v8 cases, including 92 new fix-2 cases); macOS-supported broad run: `7922 passed, 5 skipped, 266 deselected, 2 errors in 633.94s (0:10:33)`. The two known detector-worker mutation setup errors remain errors; exact direct registered mutation probes and three isolated fix-removal probes are supplemental evidence. All 44 older fingerprints are byte-identical; all old registry entries, frozen cards/operator fixtures, cap arithmetic and the three living documents remain unchanged. One development integration fixture attempted mkdir(`/data`) using a legacy default; macOS denied it before any read or creation. That fixture now remaps slot/history paths into scratch. No network, model, paid, Docker or Linux/dl call, commit, secret output, or real sealed/test read occurred. Remaining validation: review, Linux full suite and real smoke; no unresolved implementation question was found.


**Fix 3 (2026-11-04):** Operator-fixture equality now checks each handoff deliverable independently: absent snapshot files are skipped, and every present file still requires exact byte equality. The snapshot regression covers absent documentation, a partial directory omitting `commit-v222.sh`, and a changed present file that must fail. The partial case reproduced the reported `FileNotFoundError` before the fix. No sibling availability check had the same assumption; no source module or frozen fixture changed. Local validation: `26 passed in 1.56s`; v214–v222: `2223 passed in 149.23s (0:02:29)`. All 44 older fingerprints remain byte-identical. The owner reported Linux dev-tree 8,187/8,187 before this fix; that is user-provided evidence, not a local re-execution. Snapshot S0 rerun and real smoke remain pending.


**Fix 4 (2026-11-04):** The owner reported real fix-3 Linux smoke S0/S1 passes on G and D, followed by S2 decomposition failures on G/SpreadsheetBench unknown outcomes and D/OfficeQA non-applicable format counters, after paid calls. These are user-reported operational observations; no remote records were opened here. Both decomposition card arms now use the registered H-side score for all registered unknown tokens. Records preserve `observed_passed`, credited `passed`, separate `unknown`/`unknown_by_token`, and `scoring_side`; the cross-gate retains unchanged v221 method scoring (S and S' both L), with separate unknown counts per arm. Boolean format flags are counted separately from None or omitted specific flags in a real judge format record. N/A values leave the format denominator; not-worse compares rates over applicable observations, preserving the previous count comparison when denominators match. If either arm has no applicable flag, `format_compared=false` and `format_not_worse=null` explicitly exclude that comparison. Readiness recomputes and validates these counts; malformed outcomes/counters still fail closed and applicable format regressions still trigger the whole-card fallback. The main-v8 C0 price check accepts registered unknown completions, and same-root retries reuse final, fault-free unknown receipts without additional calls. Authored S2 integrations on both chains create all 396 authored cells and 11 units per chain/root inside a fresh root while trapping reads of an archived root, whether retained or removed; subsequent reuse reads only the new root. Old smoke cells are not required. Restoring the exact old aggregate function reproduces both Linux errors; restoring the old cross measurement reproduces its unknown rejection. Local validation: `2299 passed in 164.78s (0:02:44)` (486 main-v8 cases, 76 new fix-4 regressions); macOS-supported broad: `8000 passed, 5 skipped, 266 deselected, 2 errors in 643.04s (0:10:43)`. The broad run retains the inherited 263 platform exclusions plus three no-network cases, with no new main-v8 exclusion. Two known detector-worker mutation setup errors remain separate from the passing direct baseline/negative mutation probes. All 44 older configuration fingerprints, the frozen fixture files, the three living documents, and cap arithmetic are unchanged. No network, model, paid, Docker, Linux/dl or /data access, commit, secret output, or real sealed/test-data read occurred in fix 4. Linux validation of this fix and fresh-root S2/remaining smoke stages are pending.


**Fix 5 (2026-11-04):** The owner reported that the fourth real Linux smoke (fix-4 code) passed all stages on D, and G passed S0, S1 and all five decomposition checks but stopped at S2 because the synthetic cross probe caused no measured harm. The original probe fired on 42 OfficeQA items on each chain: D fixed 0/broke 12 and narrowed; G fixed 3/broke 2, net +1 and whole-slice +1/42, correctly accepted without narrowing. These are user-reported operational observations; no remote receipts were opened here. The main-v8 smoke now records two independent paired cases: `harmful_format` first requests an exact nonnumeric reply in a deliberately invalid answer tag (the unchanged official OfficeQA scorer and v2 reject that authored reply without JSON rescue); `benign` second preserves the original candidate text and its legitimate accept path. Both use the unchanged cross gate and the same seeded harm registration, structural public-evidence predicate and fallback-aware parent. Measured harm must narrow and pass every routing recheck. A correctly accepted case with no measured harm passes with `narrowing_exercised=false` and `reason=no_measured_harm`; aggregate narrowing is reported only when actually observed. Solver obedience to a note is not claimed to be deterministic. The deliberately invalid prescribed form is deterministic; measured absence of harm is an allowed, explicit result. Readiness reconstructs the exact parent and proposal package identities for each source, and validates both hashed gate records, actual denominators, fix-4 unknown counts, paired-call totals, acceptance versus narrowing, source pins and the S0 registration. Each case has its own persisted unit and cell bindings. Authored fresh-root tests on G and D retain/read-trap or remove archived roots, exercise harm and no-harm responses and verify current-root completion/retry reuse without cross-case cell reuse. At the reported 42 OfficeQA firings, the added case costs 2*42=84 solver cells per chain (168 across G and D), excluding retries; both cases cost 168 per chain. The conservative registered smoke bound is two times the unchanged 480 paired-item cap, or 960 per chain; narrowing adds zero model calls. Training, confirmation/acceptance gate and overall registered token caps are unchanged. Local validation: `2344 passed in 183.61s (0:03:03)` (531 main-v8 cases; 45 cases in the new fix-5 regression modules); macOS-supported broad: `8045 passed, 5 skipped, 266 deselected, 2 errors in 664.20s (0:11:04)`. The broad run retains 263 inherited platform exclusions and three no-network cases, with no new main-v8 exclusion. The two known detector-worker mutation setup errors remain distinct from supplemental baseline/negative mutation probes. All 44 older configuration fingerprints, pinned card/operator fixtures and the three living documents remain byte-identical. This round made no network, model, paid, Docker, Linux/dl or /data calls/access, commits, secret output, or real sealed/test-data reads. Linux validation and a fresh-root smoke of fix 5 remain pending.

## v2.25 / main-v9 — offline writer implementation (2026-11-04)

This tree implements [BRIEF-v225-main-v9](BRIEF-v225-main-v9.md) with the
[operator decisions](DECISIONS-v225.md) taking precedence. The two draft files
remain v2.26 material and are not implemented. The main-v8 and 44 older
configuration fingerprints were captured before source edits; all 45 still
match. Of the 1,582 baseline inventory entries, 1,579 permitted filenames
matched before edits and none mismatched; three forbidden source filenames
were not opened. The frozen worker sources, procedure rule, compute module,
coevo5 and continual_eval sources, and the three living documents are unchanged.

The four learned benches now have a bounded instruction writer and a card
phase before procedure evolution. Cards use the separate 5% gain rule;
procedures retain 10%. Cross cards need the same positive gain on an empty
similar-bench slot. Routing uses the item's bench and leaves other requests
byte-identical. The fixed format follows learned content. There is no P0,
decomposition execution, whole-card fallback, hygiene, or ALF card; ALF remains
the fixed v11 import. Accepted cards and imported behavior are not independent
method-effect evidence.

Every chain has eight events and 40 sealed read units: anchor B/C0/C, five
stage reads, I and historical C_end. All 50 panel-arm reads are fresh, including
unchanged steps. Stage reads overlap the next learner step. Child processes own
the read stores and retry records; the parent observes mirrored status only.
Active nested read locks prevent termination/unsealing. The fivebench aggregates
and CL metrics retain exact vendored reference anchor_C fields, real-start C0
and other supplemental analyses, same-text variation and descriptive drift.

Step caps sum to 6,966,400,000; C_end makes the derived read requirement
574,000,000 + 80,000,000 = 654,000,000, below the unchanged registered 743,000,000.
Solver/method caps are 8,865,000,000 / 7,607,505,664 per chain, total
16,472,505,664 per chain or 32,945,011,328 for both. These are ceilings, not spend.
New smoke probes separately enforce 1,000,000 solver tokens, 1,839,360 method
tokens, at most 60 attempted solver cells and three writer calls. Maximum-call
reservations or interrupted-attempt counters can stop smoke before completion.

Validation is engineering-only. The 45 fingerprints and all 11 direct mutation
probes pass their intended checks. The v214–v225 selection passed 2,677 cases. The broad run recorded 8,288 passes,
39 failures, 16 errors, 5 skips and 266 inherited deselections while edits were
still in progress. All non-wrapper issues were resolved and 79 repair cases
passed on frozen source; 288 post-policy checks also passed. Thirteen inherited
mutation-wrapper setup errors remain; their mutations never execute because
the shared detector-worker fixture fails first. All 11 new direct probes detect
their target faults from 74 passing baseline cases. Complete commands and hashes are in [V225-VALIDATION.json](V225-VALIDATION.json);
changes and public source hashes are in [V225-CHANGED-FILES.txt](V225-CHANGED-FILES.txt)
and [V225-SOURCE-SHA256.json](V225-SOURCE-SHA256.json). The
[preregistration](V225-PREREG.md) preserves owner quotes, exact writer texts,
simulation provenance, decisions, deviations and remaining operational checks.

No network, model, paid, Docker or Linux operation was performed, and no commit
or operator template was executed. Independent review, the Linux suite alone,
current exposure counts, native S0/qualification, exact reviewed consent and
both measured smokes remain prerequisites to an owner-authorized launch.

Fix 1 (2026-11-04): all nine review findings are corrected: card handoff rebasing
and gate-hash bindings; unchanged/full-touch screening; durable writer limits
and reply replay; smoke evidence guards; mutation 146 on real dispatch; per-arm
diagnostic clocks; post-join protocol termination and locked-read unseal guard;
actual consent-arm validation; and broader ALONE process detection with a shared
cooperative machine lock. The source/test/fixture/template tree was frozen before
the complete macOS-supported broad run: 8,450 passed, 0 failed, 13 errors and 5 skipped, with 266 inherited deselections.
All 13 remaining errors are individually classified inherited macOS
mutation-wrapper setup errors; no new regression remains. Subsequent runs passed
2,766 v214–v225 cases (422 v2.25 cases, 89 added), all 45 parent
fingerprints and all 11 direct mutation detections. Frozen hashes match before
and after every suite. See the fix-1 section of [V225-VALIDATION.json](V225-VALIDATION.json).
A writer reservation without a persisted reply remains fail-closed; native S0,
measured smoke, Linux-alone validation and owner launch approval remain unperformed.

Fix 2 (2026-11-05): the unmodified main-v9 v214-snapshot command produced fresh
source-only snapshots. The initial snapshot had no missing documentation input;
no provenance fixture relocation was needed. A new guard rejects unregistered
documentation dependencies in v225 tests/fixtures. Exact pinned documentary
exceptions preserve the upstream CL reference and never-executed operator text;
provenance/value checks continue, and reference import/compute is checked without
documentation reads. The optional source-deliverable mirror comparison has an
explicit documentary skip inside source-only snapshots.

The templates create and validate mode-1777 scratch, remove only owned cases after
a successful standalone suite, retain failed scratch/logs, and hold the shared
nonblocking host S0 lock throughout preparation. Standalone suites acquire the
same lock or verify/reuse the inherited descriptor. The optional
M9_SKIP_LINUX_SUITE=1 path logs a receipt and retains the complete S0 gate.
S0 checks at least 170,000 free /tmp inodes immediately before execution and sets
its own snapshot cwd/PYTHONPATH. No production module or registered value changed.

The completed in-snapshot v225 plus version-changed-module run: 775 passed,
1 explicit documentary skip, 13 inherited macOS mutation-wrapper setup errors,
and 139 inherited safety deselections (all old mutation wrappers; no v225 node
excluded). The in-snapshot v214–v225 selection passed 2843 cases, with
1 explicit documentary skip; all 45 parent fingerprints passed. The v225
selection now has 500 cases (78 added), and checkout template checks passed
156 cases, including bash -n and actual argparse. See the fix2 section of
[V225-VALIDATION.json](V225-VALIDATION.json) for commands, exact failure names,
judgment calls and the exact fix-2 file list. Native Linux/S0/smoke remain unrun.

**Operator fix 2026-11-05 (v2.25 card screen):** the real D smoke's writer produced a healthy card twice and both were rejected as `item_identity`, because `\w[/\\]\w` called `a/an/the` and `city/state/number` file paths, and the retry prompt then told the writer it had written a file path. `PATH_LIKE` now needs a root, a drive, a backslash, a URL or a file extension. Practice ids match as whole words, because sheet ids are short numbers such as 6698. Rejected reasons stay the same otherwise.

## 2026-11-05 — main-v9 small procedure confirmation clause

Owner decision, verbatim: "可以，放宽确认规则，改完冒烟通过后直接启动 main-v9".
As supplied in the brief, this change follows the first passed smoke and precedes
every main-v9 chain. No test number informed it; main-v9 test numbers do not
exist yet. The reported main-v7 bottleneck was four training-passing candidates
all rejected at confirmation (fixed/broken 0/1, 0/1, 2/0, 1/0); these historical
observations were not re-read remotely in this work.

`v225_phase.procedure_confirmation` changes only main-v9 procedure confirmation
with fewer than 30 items to net fixed ≥ 1. Broken ≤ 2/3 of fixed and whole-batch
change ≥ −0.01 remain required. The result retains the existing rule fields,
sets `gain_floor=1`, adds `small_slice_clause=true`, and derives the outward
decision/reason/passed from the resulting rule. `step._confirm_eval` passes the
configuration explicitly; callers omitting it retain the old behavior.
The main-v9 profile pins the constants for manifest/S0. Training, acceptance,
≥30-item confirmation, card rules and all 45 older fingerprints stay frozen;
per-procedure confirmation counts remain feedback only.

The follow-up review found a major omission: `v221_split.evaluate` did not pass the configuration, so both split children and merged candidates still used the old small-slice floor.
The call now passes the real configuration, with regressions through `evaluate` for both paths and a 3-fixed/2-broken boundary case; the caller audit and follow-up validation (70/70 focused; 832 passed with the same five known failures in the requested v221/v225 selection) are recorded in [the dated receipt](V225-SMALL-CONFIRMATION-20261105.json), while the results below remain the initial validation.

Validation used `<python>` (Python 3.10.20)
with `-B -m pytest -q -p no:cacheprovider`. The new module passed **44/44** in
the original checkout. The full requested selection (`test_execskill_v225_*.py`,
`test_execskill_v221*.py`, `test_execskill_v222*.py` and
`test_execskill_v210_snapshot.py`) recorded **1,341 passed, 5 failed, 1 warning
in 177.43s**. It ran from a byte-identical nested source copy with a sibling
TMPDIR, both inside this tree: legacy snapshot/temporary fixtures require
scratch outside the tested source checkout. All 44 new cases and all 45 parent
fingerprint checks passed; all 113 pre-existing fixtures remained byte-identical.

The five failures are unrelated to this change. Four operator tests require
scratch strictly under `/tmp`, which conflicts with this task's in-tree-only
boundary: `test_ops_are_self_contained_snapshot_with_optional_documentation`
(`absent` and `partial`),
`test_scratch_helper_creates_sticky_shared_directory_without_requiring_root`,
and `test_suite_removes_only_owned_cases_after_verified_success[passing_summary]`.
The fifth, `test_execskill_v221_recovery.py::test_real_endpoint_receipt_settles_before_zero_socket_pause_and_unit_retry`,
freezes time at 1000 before importing the workbook fixture in
`test_execskill_cells`; ZIP rejects the resulting pre-1980 timestamp. This fifth
failure reproduced identically after restoring the four changed production
files to their pre-change bytes in the disposable copy. No unrelated code or
test was changed to work around them.

The new tests reach the real `step._confirm_eval` production path; no source
check substitutes for behavior. They exercise the real confirmation gate and
the retained harm guard. Since valid binary one-run confirmation implies
`whole_batch=net/items`, the whole-batch rejection case uses an authored upstream
aggregate override to isolate that guard. These are offline engineering checks,
not a measured model smoke or method-effect evidence. Python 3.13 and Linux
Python 3.11 were not rerun. This writer made no network/model call, launch or
commit; the post-change measured smoke/launch remains outside this task's scope.
Exact commands, failure names and baseline reproduction are recorded in
[the dated validation receipt](V225-SMALL-CONFIRMATION-20261105.json); older
validation receipts are preserved.
The dated [preregistration amendment](V225-PREREG.md#2026-11-05-amendment--small-procedure-confirmation-slices)
records the protocol boundary; [the changed-file list](V225-CHANGED-FILES.txt)
and [source inventory](V225-SOURCE-SHA256.json) identify the new local bytes.

### Same-day engineer prompt and inert repair amendment

The operator made these two main-v9-only changes under the owner's standing
mandate to fix defects and improve the method, not under an owner sentence
about the new prompt text. The post-hoc source is
[the main-v6/main-v7 ZebraLogic analysis](<docs-repo>/docs/paper/zebra-candidates-v6-v7-20261105.md),
sections 4.3 and 7, written knowing that main-v6's learned solver helped on the
held-out panel; main-v9's ZebraLogic result is influenced by those earlier
results and must be reported with that qualification. Main-v9 has not run, no
main-v9 number existed, and the effect of these changes is unmeasured.

The main-v9 engineer prompt now prioritizes a complete public-input solution
over coverage and warns against interpreting a non-answering note's near miss
as progress. Its low-coverage inert repair path uses `never_fires` only when
`C6b.fires_on == 0`; procedures that fired but produced notes on fewer than three items
receive the existing `empty_notes` cause and diagnostics together with the
coverage count. The inert decision, cause vocabulary, repairability and gates
do not change, and main-v8/older prompt and feedback behavior remain frozen.

The [second dated preregistration clause](V225-PREREG.md#2026-11-05-second-amendment--engineer-priority-and-truthful-inert-feedback)
records the exact new text and provenance; the separate
[engineer validation receipt](V225-ENGINEER-20261105.json) records local tests
and main-v9-only prompt-pin changes without relabeling the earlier confirmation
validation. These are engineering checks, not measured method-effect evidence.

Validation on Mac Python 3.10.20: **28/28 new tests passed**, using real `engineer.check` and repair-request serialization with authored workers; restoring the three original production files in a disposable copy produced exactly seven expected main-v9 failures and 21 passes. The 241-file engineer/prompt dependency selection recorded **6,535 passed, 75 failed, 193 setup errors**; within it, the required v225/v221/snapshot subset recorded **865 passed and only the four known `/tmp` failures**, and all 45 parent fingerprints passed.

There were **264 issues outside the known `/tmp` and ZIP-timestamp set**: 207 worker/cleanup or mutation-baseline issues, 27 workbook-fixture issues, 25 legacy pipeline state/assertion issues, three denied loopback binds, and two missing-`os.waitid` failures on macOS. Four representative failures (worker cleanup, workbook cache, workbook bytes, and `os.waitid`) reproduced with pre-change source and fixtures; other state/assertion cases were not individually isolated, and loopback binds were not retried. No unrelated fix was made. The dated receipt lists every selected file, failure, and control; only the two main-v9 prompt fixtures changed, with 111 prior fixture files and older pins unchanged. No method-effect claim follows from these local checks.

Review follow-up (2026-11-05) fixed main-v9's coverage-only feedback falsely adding `crashed` and omitting the `empty_notes` evidence block when revisions change only one or two requests despite four nonempty notes; real `engineer.run_train` regressions exercise SearchQA repair orchestration and Zebra's v216 cycle, the restricted selection passed **198/198** including all 45 parent fingerprints, all 113 existing fixtures stayed unchanged, and restoring pre-fix source reproduced exactly three expected main-v9 failures without rerunning the broad selection.

## 2026-11-06 — main-v9 route-B thinking request

Main-v9 D now adds explicit thinking disabled alongside effort none through a separately pinned adapter, preserving older client/route identities and every receipt/resend/ledger guard; the [dated receipt](V225-ROUTE-THINKING-20261106.json) records the operator-supplied incident/probe numbers without relabelling earlier single-field data, 872 scoped passes with four known `/tmp` failures and 93 focused passes, and the 2026-11-06 decision keeps S1 at first-call confirmation plus three length probes with `v225_client.control_client` unused in production, closing the earlier scope question without a source change.
