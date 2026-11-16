# read-plan.md: critic B (validity of the result, resume/atomicity, the carry command)

2026-11-12. Subject: `docs/handoff/typed-v2/spec/read-plan.md` (draft for D9-D12). Method: default "this is
wrong" until the code proves otherwise. Paths relative to `<repo-root>`;
`T/` = `skillopt/execskill/typed/`.

Marks: [V] = opened and read at the cited file:line in this tree; [I] = inferred, not read. This tree's `T/` still
holds the typed-v1 code (`T/__init__.py:10` `VERSION = 'typed-v1'` [V]), so a `T/` line reference describes both
the code that produced the typed-v1 carry source and the code typed-v2 starts from. The typed-v1 tree itself was
not opened. No code, test or script was edited. No data or result root was opened. No ssh, no call.

Ids: CB1.. (the draft already uses B1-B5 for its own section 0, so "B<n>" would collide).
Severity: blocker = the draft cannot work as written, or as written it prints a wrong number;
must-fix = a gap to close in the spec before implementation; minor = wording or a cheap extra record.

Count: 31 findings (3 blocker, 26 must-fix, 2 minor). Two points were checked and gave no finding (end of B and D).

## A. The carry command (D11)

**CB1. blocker (fails safe, silently). K7 demands equality of the manifest field `evidence`; identity.md changes it.**
Evidence: K7 `carry.EQUAL_FIELDS` holds `'evidence'` and `'route_b_evidence'` (draft R53). The manifest has both:
`T/prepare.py:271` [V] `'evidence': EVIDENCE[mode], 'route_b_evidence': ROUTE_B_EVIDENCE[mode]`. Today
`EVIDENCE = {'run': 'typed_v1_real_run', 'smoke': 'typed_v1_smoke', ...}` (`T/__init__.py:63` [V]); identity.md
:21 and :146 [V] set the typed-v2 values to `typed_v2_real_run` / `typed_v2_smoke`. So the two manifests differ in
`evidence` for every pair, real or smoke. K7 refuses every carry. D11 can never produce a receipt. The fake smoke
does not show it (its source is built by a typed-v2 helper, 4.1) and the real smoke passes on "a verdict" (S4).
Correction: move `evidence` to "different by construction, recorded only"; keep `route_b_evidence` and
`machinery_manifest.evidence` (`T/prepare.py:277-278` [V]) in the equal list. Add a test that builds both manifests
with the real `prepare` of each version and proves K7 passes (see CB30).

**CB2. must-fix. K10(ii) demands `reasoning_chars == 0` for both chains; chain G has no reasoning rule.**
Evidence: `T/chain.py:210-218` [V]: `'reasoning': None if chain == 'G' else (...)`. A chain G reply may carry
reasoning. As written K10(ii) refuses every chain G carry, or, if coded as "skip when absent", checks nothing.
Correction: a per-chain rule. Chain D: every send of every carried cell has `reasoning_chars == 0` and
`reasoning_tokens == 0` (keys: `T/units.py:33-34`; stored per send `T/units.py:222` [V]). Chain G: record the
count of sends with reasoning as a fact; the receipt says the thinking setting of chain G is proven by code
equality only.

**CB3. must-fix. "In the echo set" does not prove the same model, and `confirm.json` is not a read-time record.**
Evidence: for chain D the echo set is `client.NORTHGATE_RESPONSE_MODEL_IDS`, several ids (`T/chain.py:199-207`
[V]). A typed-v1 cell answered by id A and a typed-v2 confirm answered by id B both pass K10(iii). `confirm()`
returns the stored record when the file exists (`T/chain.py:536-538` [V]): one call per root, at chain start.
Under `learn_first` that is more than a day before the reads. So K10(ii) compares two chain-start records.
Correction: require that the set of `returned_model` over ALL sends of the carried unit has one element, and that
it equals the set over the sends of the typed-v2 fresh units already complete on that bench (the S5 unit always
is, R36). The key exists: `cell['sends'][i]['receipt']['returned_model']` (`T/units.py:209-222`,
`T/mount.py:425-429` [V]). This closes the draft's [I] in K10 and N10.

**CB4. must-fix. Solver settings are stored nowhere. `settings_proof: 'observed'` overclaims.**
Evidence: a send record holds `system`, `user`, `logical_call`, `charge_bound`, `reserved` and ten receipt keys
(`T/units.py:209-222` [V]). No temperature, stop, tools, thinking, seed, max tokens. The manifest `clients` field
is two paths (`T/prepare.py:276` [V]); the solver blocks are built at run start from frozen code plus the content
of those files (`T/chain.py:1017-1029` [V]). So K7 `clients` is path equality, not settings equality. A changed
credential or settings file under the same path passes K7.
Provable without a call: max tokens. `charge_bound = request bytes + RESERVATION_OVERHEAD + max_tokens`
(`T/units.py:143-165`, `:213-214` [V]), so the bound of every typed-v1 send can be derived and compared with the
typed-v2 bound `block['B'][bench]` (`T/chain.py:1067` [V]). Chain D nominal tokens are stored per cell
(`T/mount.py:361` [V]) and comparable with `block['M'][bench]` (`T/chain.py:1102` [V]).
Correction: (a) typed-v2 writes a credential-free, readable `solver_settings` record at chain start (per bench:
bound B, nominal M, model asked, thinking / reasoning setting, temperature, stop, tools, route name), not only a
hash as Q3 proposes; `carry` reads it (the module has no client, R48). (b) New check: derived typed-v1
`max_tokens` and stored `nominal_tokens` equal that record for every send / cell. (c) The receipt replaces
`settings_proof: 'observed'` by two lists: `proven` (max tokens, nominal tokens, returned model, reasoning counts)
and `by_code_equality_only` (temperature, stop, tools, thinking, seed, provider route, content of the client
files). The readout prints the second list beside every `c` mark.

**CB5. must-fix. Nothing checks the scoring path that produced a carried `correct`.**
Evidence: `correct` is decided in typed code: `T/mount.py:405-419` [V] (`_judged`: token to correct, the
configuration rule), `:394-402` [V] (`_failed`), `:502-517` [V] (`_sheet_score`), and `T/reads.py:351-383` [V]
(`_normalized`). These are `T/` files; D1 lets typed-v2 edit them. The draft compares manifests and requests only;
`provenance` is "recorded only". The judge and scorers below are frozen machinery, but the typed-v1 manifest has
no snapshot list hash (draft B4), so their equality rests on F2.
Correction: a pinned drift guard. `carry` hashes the source of the functions named above in the typed-v2 tree and
compares with pinned hashes of the same functions in typed-v1 (anchor:
`docs/handoff/typed-v2/typed-v1-source-manifest.txt`; exists, not opened). A difference refuses the carry unless
the spec lists it with a proof that it cannot change `correct`, `token`, or the unknown / fault flags. The receipt
says `judge_and_scorers: by F2 only`.

**CB6. must-fix. K3 accepts a unit with fault rows and hides a unit finished across resumes.**
Evidence: a mirror is `complete` iff `stop_reason is None and missing_cells == 0` (`T/reads.py:456-475` [V]). A
complete unit can hold cells with `correct None` and `infrastructure_unknown` or `configuration_error`
(`T/mount.py:402`, `:418-419`, `:430` [V]). Only an UNFINISHED unit gets its fault cells rerun on resume; "a done
unit is never touched" (`T/units.py:301-321` [V], called at `T/reads.py:288` [V]). A resumed unit leaves
`rerun/<tag>-<n>.json` (`T/units.py:317-318` [V]) and may leave `done-stopped-<n>.json`, `stop.json`,
`failure.json`. `done.json` `finished` is the time of the last process only (`T/units.py:428-431` [V]).
Consequences: a carried C with infrastructure unknowns enters the table; "read 2026-11-11" (R55) can be false for
part of the cells; cells of one unit can come from two provider states.
Correction: K3 also reads the mirror counts `infrastructure_unknown` and `configuration_errors`
(`T/reads.py:470-471` [V]) and requires both zero for a C used by R58 (else replicate only);
records the number of `rerun/*` and `done-stopped-*` files; refuses R58 use when either is non-zero; the receipt
shows `read_started` and `read_finished` (3.5 has both) and the readout prints both, not the date part alone.

**CB7. must-fix. K9 does not cover the SpreadsheetBench qualification result.**
Evidence: the registry entry is built from ALL task ids before the qualification (`T/reads.py:132-135` [V]); the
qualified subset is applied afterwards (`:136-137`, `:152-160` [V]). The registry is equal even when the qualified
sets differ. K4 would catch it, but only as "items differ". The common item set of a bench is the intersection
over all loaded events (`T/readout.py:460` [V]), so a different item set would also move every fresh number.
Correction: a named check `same_qualification`: the two qualification records agree on `qualified` and
`task_hashes`. State that typed-v2 always runs the qualification in its own root and that the carry never copies
a qualification record.

**CB8. must-fix. Multi-turn cells: only the first request is compared (K5).**
Evidence: a cell stores one hash per send (`T/mount.py:429` [V]). ALFWorld episodes and repair turns send later
requests that depend on earlier replies, the environment and the shell code. Their equality in distribution rests
on `runtime` equality (K7), on the ALFWorld data PATH only (`T/chain.py:1093-1094` [V]; game files are not
hashed) and on CB5.
Correction: the receipt says `later_turns: by_code_and_runtime_equality`. Add two zero-call checks: (a) the number
of sends per cell never exceeds the typed-v2 runtime's turn / step budget; (b) for ALFWorld the stored
`output.steps` / `trace_steps` (`T/mount.py:463-468` [V]) never exceed the typed-v2 step budget. For ALFWorld,
recommend replicate-only (no R58 use) unless the game data is hashed on both sides.

**CB9. blocker. R64 makes `read_units_of` find two units for one pair in the normal case.**
Evidence: `read_units_of` keys units by the parsed (event, bench) and requires uniqueness:
`require(parsed not in found, 'Two read units for one event and bench: ...')` (`T/readout.py:340-351`, the
require at `:349` [V]). R64 adds a scan of `carried/typed-v1/`. The carried unit keeps its name
`test-read-<event>-<bench>` (R54). R59 carries C0 for every bench while C0 is always read fresh, so both
directories parse to (`C0`, bench). The same holds for a late C (P10). The open readout raises for every root with
one carried C0. If the implementer drops the guard, one unit shadows the other by dict order and a typed-v1
reading can stand in a fresh typed-v2 row.
Correction: `read_units_of` never scans `carried/`. A separate `carried_units_of` returns
`{('typed-v1', event, bench): dir}`. Only two callers may use it: the resolver for a state entry of kind
`carried`, and the replicate block (R69). Test: fresh C0 plus carried C0 on one bench renders, and the C0 row is
the fresh unit.

**CB10. must-fix. A copied typed-v1 unit does not have typed-v2 record shapes.**
Evidence: carried `aggregate.json` and mirror carry `version: 'typed-v1'` (`T/reads.py:449`, `:462` [V]); cells
carry `evidence: 'typed_v1_real_run'` (`T/mount.py:360` [V]); `done.json` embeds the typed-v1 ledger snapshot
(`T/units.py:428-431` [V]), which a cost reader would add to typed-v2 tokens; per-read tokens come from the cells
(`T/readout.py:409`, `:580` [V]), so a carried C would show typed-v1 tokens as typed-v2 read cost unless R71 is
enforced in code. The directory `carried/typed-v1/` has a path component `typed-v1`, which identity.md 1.3
refuses and 1.17 forbids naming.
Correction: one loader `carry.load(receipt)` re-verifies the file hashes and returns only the projected cells
plus `source: 'typed-v1'`; no generic loader reads `carried/`. `read_tokens` and `_costs` exclude carried pairs and
print one separate line "tokens spent in typed-v1, not in this run". Rename the directory (for example
`carried/v1/`) or state the identity.md exception in both specs.

**CB11. must-fix (decision needed). R68 makes every carried C unusable for a claim; the saving is small.**
Evidence: R68: a number against a carried C "enters no claim, no decision and no test". R67 flags it
`cross_date`. R40: ZebraLogic C is in the C0 class, so R58 can save at most four one-arm units per chain out of
35. Against that stand CB2-CB8 (settings, scoring, faults and later turns proven by code equality only) and K-B
(no in-run replicate at all).
Consequence: on every bench with a carried C, typed-v2 has no claimable contrast against the historical card.
The draft does not say this in plain words.
Correction: put the trade before the coordinator. Recommended: drop R58. Read C fresh in the read phase on all
panels; carry both C0 and C as replicates only. This gives two cross-date replicate arms per bench (the only
noise / drift reference of the run), keeps every table cell same-phase, and removes R58, P9, P10, CB23 and CB26.
If R58 stays: the readout header says "no contrast against C is a result on benches marked c".

**CB12. must-fix. A crash inside the copy blocks the pair for good; the copy set is undefined.**
Evidence: R54 renames `.incoming-<unit>/` to `<unit>/`, then writes the mirror copy, the file list and, last, the
receipt. A crash after the rename leaves a carried directory without a receipt. A second run finds no receipt
(K11), copies again and renames onto a non-empty directory, which fails. R56 removes only `.incoming-`. "Every
file of the source unit" also includes `calls/` (`T/reads.py:331` [V]), `rerun/` and stop / failure files.
Correction: at start, a carried directory without a receipt is an orphan: compare it with a fresh source hash
list; equal: continue with the list and the receipt; unequal: move it to `.orphan-<n>/` and report. Define the
copy set by name (`cells/`, `done.json`, `aggregate.json`, `rerun/`, `done-stopped-*`, `stop.json`,
`failure.json`, `calls/` yes or no) and record every excluded path with a count.

## B. Validity of the readout (D12)

**CB13. blocker. `forgetting` gets a floor of 0 by construction and is printed as measured.**
Evidence: `forgetting = max(earlier) - final_acc` over the events S1..S(K-1), "signed, no floor"
(`T/readout.py:491-496`, definition `:534-535` [V]). R70 sends alias values "through the resolver" into the
formula and only blanks "a term that differences two events of one class". A max is not such a term. R40's
typical classes put S(k)..S(K-1) in the class of S(K). Then an earlier event holds the final reading itself, so
`max(earlier) >= final` always. With the draft's own layout example, bench B1: max(62.5, 62.5, 65.0, 65.0) - 65.0
= 0.0. The class-aware value is 62.5 - 65.0 = -2.5. `_macro` then averages the 0.0 (`T/readout.py:514-521` [V]).
The same holds for `forgetting_after_home` (`:492`, `:496` [V]).
Correction: define both on distinct classes other than the final event's class:
`max over classes != class(S_K) of acc - acc(S_K)`; `-` when no such class exists; print "distinct readings in
the max: m". State that the value is not comparable with a `full` run or with baseline tables, where the max
runs over K-1 independent noisy readings and is biased upward.

**CB14. must-fix. R64 loads the representative's cells under the member's key: unsafe by default.**
Evidence: `_open` builds `by_bench[bench][event] = cells` and passes it on (`T/readout.py:566-580` [V]). Every
consumer then sees a full seven-event grid. Unpatched results: `_pairs` gives mean 0.0, se 0, 0 better, 0 worse
and a zero-width interval (`:412-441` [V]); `_same_request_noise(C0, C)` on ZebraLogic compares a dict with
itself and reports zero flips (`:444-454` [V]); `_five_by_five` prints 0.0 (`:476` [V]); `_formulas` gives exact
zeros (`:483-499` [V]). R66-R70 patch each consumer by rule. One missed or future consumer prints a zero by
construction as measured.
Correction: invert the default. `by_event` holds fresh units only (plus a carried C only if R58 stays). Alias
pairs live in a separate map `alias_of`. A consumer that wants a member's value must dereference on purpose. T20
gains one case per function above, called WITHOUT its patch, proving that an alias member never yields a number.

**CB15. must-fix. R70 changes the denominator of every macro mean without saying which quantity is meant.**
Evidence: `_macro` is the equal-weight mean over the benches where the value is defined, with `n_benches`
(`T/readout.py:514-521` [V]). Under R70 a same-class term is `-`, so it leaves the mean. `gain_over_C0` then
averages only the benches whose mounts changed: a conditional mean, not the five-bench mean of the `full` run or
of the baseline tables. `forward_transfer` (`:498`) and `backward_transfer` (`:497`) are same-class on almost
every bench by R40, so their macro rests on zero or one bench. Chains G and D will have different n.
Correction: pre-register two columns and print both: (a) "five-bench mean, identical-request benches entered as a
structural 0 (k of 5 structural)"; (b) "mean over measured benches (n of 5)". No standard error uses a structural
0 as a sample. Any comparison with a five-bench baseline number uses (a) and says so.

**CB16. must-fix. Cross-date terms enter `gain_over_C`, its macro mean and paired intervals.**
Evidence: `gain_over_C = acc(final) - acc(C)` (`T/readout.py:494` [V]) and `_macro` averages it over benches
(`:517-520` [V]). With C carried on some benches and fresh on others the mean mixes cross-date and same-phase
terms. `_pairs` computes `S<k>-C` for every k (`:435-437` [V]) and `_paired` prints se, a t interval and a
bootstrap interval (`:416-422` [V]). Such an interval covers item noise, not drift, yet it looks like a 95 percent
interval of a method effect. R67 / R68 flag the single column only.
Correction: with a carried C, `gain_over_C` and every `S<k>-C` of that bench go to the reference block only, as a
point difference without se, interval or better / worse. The macro of `gain_over_C` is printed only when all its
terms are same-phase; otherwise "mixed: k same-phase, m cross-date, no mean".

**CB17. must-fix. After a fallback, identical-request pairs are printed as measured effects; R69's claim is false.**
Evidence: R42 and R44 (void plan) make every unsettled pair of a bench "its own class", read fresh. R67 computes
a delta for "two events of different classes". So two fresh units that the plan itself holds to be identical in
requests give a pure-noise difference under an effect heading, while the legend tells the reader that `-` marks
all same-request pairs. R69 says "no class is read twice in the run", which is false after any fallback.
Correction: label every printed delta with `requests: identical | different | unverified`, taken from the cells
themselves: per item, compare the two units' `request_sha256` lists, as `_same_request_noise` does today for C0
and C (`T/readout.py:448-450` [V]). A delta whose items are all identical is printed as "noise sample, not an
effect" and feeds the in-run noise block. `in_run_replicates` is counted from these, not set to 0.

**CB18. must-fix. R66: a JSON alias cell carries a number.**
Evidence: R66: "an alias cell carries the representative's value AND `independent: false`, so no consumer can
count it twice by accident". A consumer that ignores the flag gets 35 numbers of which up to 30 are copies.
Consumers exist outside this tree (dashboard generator, report tables) [I].
Correction: an alias cell has `value: null` and `of: <event>` in every export. The existing plain-float fields
`accuracy_L` / `accuracy_H` (`T/readout.py:478-479` [V]) become objects, so an old consumer fails loudly.

**CB19. must-fix. "Same phase" is not defined and does not survive a resume.**
Evidence: D12 asks for a fresh same-phase baseline. A pause inside the read phase (P5, P8) can separate S5 from
the C0 class by days and by an owner recovery. The model is confirmed once per root (`T/chain.py:536-538` [V]),
so no check at the start of the read phase or after a resume shows the same returned model. K-C mentions hours.
Correction: define the phase in the spec: all fresh units of the chain, with (a) one returned-model set over all
sends (zero-call, from the cells, key as in CB3), (b) no entry of `state['recoveries']` between the first and the
last unit, or else each contrast across a recovery is flagged `split_phase` with both time ranges. The readout
prints start and finish per fresh unit (K-C) and the flag per contrast.

**CB20. minor. One unit with infrastructure unknowns can define up to six table cells.**
Evidence: a done unit is never rerun (`T/units.py:308-312` [V]); a complete mirror allows unknown cells
(`T/reads.py:461` [V]). R39 settles on "complete".
Correction: the alias record stores the representative's `infrastructure_unknown` and `configuration_errors`
counts; the readout prints them beside every `=X` mark and beside the L / H accuracies.

Checked, no finding: the read plan does not change a learning decision. The pass runs after the s5 freeze (R20),
R2 / R3 refuse `economy` without `learn_first`, and no gate reads a test cell, an alias or a carried cell (5.4).
The pass sends no call and charges nothing (R33, T11). Condition: CB27.

## C. Resume and atomicity

**CB21. must-fix. `run --resume` always consumes an owner recovery record; S2's exit code 0 means "complete".**
Evidence: `run` calls `runner.recover()` when `resume` is set, before the `try` (`T/chain.py:976-978` [V]).
`recover` requires `recovery.json` unless a consumed record is unapplied:
`require(path.exists(), 'resume requires the owner recovery record ...')` (`T/chain.py:341-347` [V]). This is a
hard error, not a pause. So S2 ("exits cleanly, state not paused, exit code 0, and `run --resume` continues")
fails without a recovery record. R45 and T16 resume at eleven points and never mention the record. Exit code 0 is
`EXIT_COMPLETE` (`T/__init__.py:69` [V]). A stopped chain that is neither complete nor paused reads as `running`
(`chain_status`, `T/readout.py:677-687` [V]). A watcher that launches on exit 0 would treat the chain as finished.
Correction: `--stop-after-plan` records a normal pause, reason `stopped_after_plan`, exit `EXIT_PAUSED` (3).
Resume uses the standard recovery record. R45 states for every point which record the resume consumes. R44 runs
inside the `try`, after `recover()`, so a changed plan is a recorded pause.

**CB22. must-fix. R33 can swallow the qualification pause and create a recovery loop.**
Evidence: R33: "any other error that prevents writing the plan pauses with `read_plan_failed`". Under `economy`
the pass is the first caller of the SpreadsheetBench test qualification (R22). The owner's decision is forwarded
to the qualification attempt only when the pause detail holds `QUALIFICATION_PAUSE`
(`T/chain.py:374-391` [V]); without forwarding "the chain's record alone would re-raise the same
pause at the next sheet read" (`T/chain.py:333-335` [V]). The draft marks this path [I] and tests it with a stub
(T12).
Correction: the pass re-raises `Paused` and `units.Stop` unchanged; only other exceptions become
`read_plan_failed`. State which unit name the pause carries (the pseudo-unit `read-plan`) and prove that
`bind_qualification_target` finds its attempt from it. T12 runs the real `recover` /
`bind_qualification_target` / `forward_qualification_recovery`.

**CB23. must-fix. P9 / P10: the meaning of C depends on when an operator ran `carry` relative to a pause.**
Evidence: R58 decides per bench, at the moment the chain reaches C, on "receipt present and no unit directory".
`read_event` starts the five units of an event in parallel (`T/chain.py:576-587` [V]); a stop
can leave some C units started and some not. A receipt that appears during the pause turns the unstarted ones
into carried C (P9) and leaves the started ones fresh (P10). If an operator archives a faulty C unit during a
recovery, "no unit directory" becomes true again and a C already partly read fresh becomes carried. Two resumes
of one root can end with different class structures. D10 g wants a replayable plan.
Correction: bind once. At the first arrival at event C the chain writes
`state['read_plan']['carry'][bench] = {decision: carried | fresh, receipt_sha256, reason}` for all five benches,
then persists, before any C unit starts. Later resumes follow the bound decision whatever appears or disappears
on disk. A receipt arriving later is a replicate only. T15 / T16 gain: stop after the binding, add a receipt,
resume: C stays fresh.

**CB24. must-fix. A stale alias record can exist beside a fresh unit; "write-once" has three meanings.**
Evidence: R58 writes the alias record of kind `carried`, then sets the state, then marks. A crash after the
record and a receipt that no longer verifies on resume lead to a fresh C read; the record stays on disk. R65 lets
`_mirrors` "merge the alias records", a directory scan (`T/readout.py:272-282` [V]). 3.4 says "exclusive
create"; P7 says "an existing record must be byte-equal to the recomputed one"; `units.write_json` always
replaces through a fixed `<name>.tmp` (`T/units.py:55-63` [V]).
Correction: the state entry is the only authority. The resolver reports an alias record without a matching state
entry as `stale_alias_record` and never merges it. The chain archives a stale record before it reads the pair
fresh. Specify one helper `write_once(path, record)`: exclusive create; if the file exists, byte-compare; a
difference is `read_alias_invalid`. Use it for the plan, the sealed identity files, alias records and receipts.

**CB25. must-fix. A void plan keeps the aliases it settled; the place of the R44 recovery is not specified.**
Evidence: R44: if the replay does not reproduce the bound hash, the plan is void and "every unsettled pair is
read fresh". Pairs already settled as aliases keep their value, although the plan that proved them cannot be
reproduced. R44 does not say whether the "standing recovery" runs inside `recover()` (before the `try`,
`T/chain.py:976-978` [V]) or by hand. "Archive the doubtful file" then "replay" rewrites a write-once file.
Correction: on void, every alias of that chain is re-proven against the replayed identities (member list hash
equals representative list hash in the replay, and R41 holds against the replay); an alias that fails becomes
`invalid`, shows no value, and R46 requires a fresh read of it. The recovery is a branch of `recover()` keyed on
the pause reason, like the qualification forwarding; its outcome is stored in `state['recoveries']`.

**CB26. must-fix. After a post-read mismatch on a bench, R58 still accepts a carried C for that bench.**
Evidence: R42: after a failed check "the identity function is in doubt for that bench" and every unsettled pair
becomes its own class. Then R58 (a) "C is the only member of its class" is true by construction. K1 and K5 rest
on the same plan's first-request hashes.
Correction: R58 gets condition (d): no entry in `state['read_plan']['fallbacks']` for the bench and the plan not
void. T15 gains the case.

**CB27. minor. State that `anchors()` reads nothing under `economy`.**
Evidence: today `run` calls `anchors()` before the steps (`T/chain.py:980` [V]) and `anchors` reads C0 and C
(`T/chain.py:631-634` [V]). schedule-lock moves these reads; the draft says only that R35 "replaces
schedule-lock's read loop".
Correction: one sentence in R35, and a test: with `economy`, no read unit directory, no `TestAccess` and no
registry file exist before `read-plan` is in `done_units`.

## D. Budget, ledger, completion, status

**CB28. must-fix. R46's "complete unit status" is vacuously true for an alias entry and for `{}`.**
Evidence: `_read_complete(status)` is true for any dict without `stop_reason`, without `missing_cells` and
without a `status` key (`T/chain.py:248-251` [V]). The alias state entry of R39 (`kind`, `alias_of`, `items`,
`alias_sha256`) has none of them. An empty entry passes too.
Correction: R46 decides per `kind`. Fresh: the unit's sealed `done.json` and mirror are re-read
(`_existing_status`, `T/reads.py:522-531` [V]) and `cells == expected_cells == planned items`.
Alias / carried: the record verifies AND its representative passes the fresh rule (or the carried rule). Alias
entries carry `status: 'alias'` so that `_read_complete` is false for them.

**CB29. must-fix. Status readers that count mirrors or expect the order C0, C, S1.. break.**
Evidence: `status` returns `read_status = _mirrors(chain_dir)`, one file per fresh unit
(`T/readout.py:645-655`, `:272-282` [V]). Under `economy` there are between 5 and 35 mirrors, S5 comes first, and
C0 may never have one. A helper that waits for 35 mirrors, or for the C0 mirror first, never finishes or reports a
healthy run as stuck. The ops helpers on the Linux machine are outside this tree [I].
Correction: R73 adds to `status`: `reads: {settled: n, of: 35, fresh_done, fresh_planned, alias, carried,
fallbacks}` and `phase`. The spec lists every ops helper that reads mirrors, and each is re-keyed on `done_units`
plus `state['read_plan']` before the smoke.

Checked, no finding: caps and charges. Only fresh units charge; an alias pair has no ledger entry; the cap keeps
the D6 value, so the hard error `Ledger cap changed` (`T/units.py:114-115` [V]) cannot fire;
`_costs` counts ledger units by name (`T/readout.py:139-150` [V]) and so counts fresh units only. The one
exception is the carried `done.json` ledger snapshot (CB10).

## E. Smoke

**CB30. must-fix. The carried path runs on fixtures only, and the real smoke passes when every carry is refused.**
Evidence: T13-T15 and S3 use "a typed-v1-shaped source root" built by a typed-v2 test helper (4.1). S4 passes
when `carry` "returned a verdict for every (C0, C) pair". S5 accepts `refused` and counts the path "as exercised
by the fake smoke only". CB1 is a defect that this design cannot see: the fixture has equal `evidence` fields,
the real roots never do.
Correction: (a) a zero-cost test generates the source root with the REAL typed-v1 code (the typed-v1 tree's own
fake smoke, run read-only from that tree in a subprocess into the scratch directory) and runs the typed-v2
`carry` and the R58 use against it [I: that the two fake smokes share panels and format blocks]. (b) The real
smoke passes only if at least one C is really carried and settled as `carried`; otherwise the smoke report says
"carry not exercised" and the real run starts with R58 switched off.

**CB31. must-fix. The pass's real consent / registry / qualification path first runs in the paid real run; S2
contradicts K-D.**
Evidence: the smoke opens no test panel and writes no registry entry (R25, S1). So R22 (the pass is the first
caller of `panel_tasks`, with the new label) and CB22 run with real code for the first time in the real run.
Fallback, void and resume paths run with fakes only (T9, T16, T19). S2 says the real run does not need
`--stop-after-plan`; K-D says it "lets ops look before paying".
Correction: make the stop after the plan the standard procedure of the REAL run (with CB21's pause form). At the
stop, before any paid read: check the plan counts, run `plan-replay` in a second process, run `carry`. The real
smoke includes one stop and resume between the plan and the reads, and one inside a fresh unit.

## NOT DONE

1. The identity function itself (R8-R19b) and the planning pass internals (R28-R31) were not attacked: another
   critic's lens.
2. `X/evaluation.py` (registry writer, sheet qualification, `alfworld_reset`) was not read. The race of two
   chains at the pass (Q18) and the exact qualification record keys (CB7) are [I].
3. `T/smoke.py` bodies and the existing tests were not read. Whether a typed-v1 fake smoke root is a usable
   carry source (CB30 a) is [I].
4. `scripts/run_typed.py` was not read: how a process exit code follows from the state (CB21) is [I] beyond the
   constants in `T/__init__.py:69`.
5. The typed-v1 tree was not opened (rule). "This tree's `T/` equals typed-v1" rests on `T/__init__.py:10` and
   on DECISIONS F2 / F3.
6. Whether a send record carries a time stamp was not checked; CB6 and CB19 use unit-level times only.
7. Ops helpers on the Linux machine (CB29) could not be listed: no ssh in this task.
8. Time: this review ran past the 40 minutes allowed.
