# Report of piece P1 (program learning: version switch, probe, repair rounds, paid round, archive), 2026-11-15 ~02:5x

Built in <repo-root> on top of the docs commits d25619c..75f89f3 (no conflict).
914 typed tests pass (874 + 40 new), fakes only.

(a) Files: typed/__init__.py (VERSION/CONFIGURATION 'typed-v3', evidence typed_v3_real_run / typed_v3_smoke,
is_typed_v2 -> is_typed_v3 (nothing outside typed/ used it), PROGRAM_LEARNING ('single','repair'; default 'single'),
PROGRAM_REPAIR_ROUNDS=3, PROGRAM_PAID_FEEDBACK=1, REPAIR_LIMITS, ARCHIVE_CHOICES ('none','index'; default 'none'));
prepare.py (root name from VERSION; prepare(program_learning=, archive=) checked before writing and always sealed;
program_learning_of / archive_of; a manifest without the fields reads 'single', no archive; load_manifest checks
both); NEW archives.py (verified loader; pins the index bytes INDEX_SHA256; accepts exactly G zebralogic
main-v6-G-s3-p-zebralogic-3-5, D zebralogic main-v6-D-s3-p-zebralogic-3-3, G/D alfworld alfworld-v11-accepted;
refuses oracle-reference, zebra-pc-*, main-v5-*; checks every file sha256 and record hash against the index and the
sealed value); NEW typed/archive/ (index.json + the five records, byte-identical to SkillOpt/skill-archive/skills/);
mount.py (package candidate {'procedures': [...], 'home_type'} mounts all records together in mount, mount_identity
and the candidate checks; identity = the list of record hashes; single-program shape and identity unchanged);
engineer_prompt.py (repair_system(bench), five repair texts pinned in REPAIR_PINS, HOOKS/NOTES/CONTENT/STATIC SCREEN
paragraphs word for word the propose text's; RUN LIMITS paragraph from profiles.SANDBOX_TIMEOUTS: 5 s per hook call,
2 s for applies, exhaustive search must prune; REPAIR_SHOWN_ITEMS=5; verify() also checks the repair texts, return
unchanged); machinery.py (profiles.SANDBOX_TIMEOUTS required; the engineer_prompt.PINS row covers both tables, new
hash 4a06b375..., pin count stays 33); writers.py (repair_program: one call, fix reader with its own single format
retry, screened by build_procedure, never a fix call; coverage_report, learn_report, repair_entry, same_program,
screen_record); chain.py (Services.probe_call, Services.repair_program, ProbeCall; _Run.probe, programs_repair,
program_repair, repair_decision, refine, repair_round, learn_round, archive_candidate, archive_decision,
archive_skills; finalize adds decisions['program_learning'] under 'repair' only; run() verifies archive bytes before
writing; _open_state records program learning and archive hash only when not default, refuses a mixed resume);
scripts/run_typed.py (prepare --program-learning {single,repair} --archive {none,index}); NEW
tests/test_typed3_program_learning.py (40 tests).

(b) TMPDIR=/tmp/typed3-neutral python3 -m pytest $(ls tests/test_typed*.py) -q -p no:cacheprovider -> 914 passed.
'single' records byte-identical to the base commit's: dumps of both golden scenarios from a git archive of the base
give 719/719 and 769/769 identical files after mapping version/evidence labels back and dropping timestamps, derived
hashes and ledger snapshots in read units' done.json. A five-bench fake smoke under 'repair' with the archive index
completed on both chains in-process; through the CLI's replay child it paused with replay_different (the child
rebuilds the synthetic 'single' manifest because the manifest was injected in memory): a prepared smoke root
avoids this; that path was NOT run.

(c) Existing tests edited (version/evidence pins only): test_typed_chain L756; test_typed_cli L100; test_typed_mount
L355, L448; test_typed_readplan L144/150/162; test_typed_schedule L171-184; test_typed_reads (root names, minimal
manifest version, evidence L367/370, other version now typed-v2); test_typed2_base L702-758; test_typed2_services
(RUN_NAME/SMOKE_NAME, scope prefix 'typed-v3:'); test_typed2_identity (literals, is_typed_v3, typed-v2 as other
version, typed-v30 root and typed-v2 library/type-map refusals, READOUT_VERSION 'typed-v3-readout-v1');
test_typed2_shared golden (decisions mapped back to typed-v2 labels: version, evidence, type-map hash with module label
'typed-v2', so the frozen digests still match).

(d) Deviations: 1 repair prompt = separate repair_system() + REPAIR_PINS (a test pins purposes to ('propose','fix'));
2 repair replies read with replies.read_fix; 3 repair limits in Services.limits with REPAIR_LIMITS defaults, recorded
under decisions['program_learning'] (decisions['limits'] keeps typed-v2's five keys); 4 the probe answers the
selection call with a probe call so no other program of the type is enabled on either side; 5 added routed /
not_routed (about 5 % of a bench's items lie beyond the p95 routing threshold: not counted as failures, not shown,
not used to decide repair); 6 a version that notes on every routed item without fault gets no repair call
(nothing_to_repair); 7 with program_paid_feedback = 0 there is no learn unit, the version goes straight to the gate;
8 archived records mounted as archived (own v2-9 policy and evidence labels); all five pass the typed screen; skill
origin = typed-v2's dict + kind 'archive', package, archive_record_sha256; 9 each archive skill its own write-once
skill-<n>.json; 10 prepare seals both fields always.

(e) Open risks: after an accepted archive, the engineer's examples and the paid round's fixed/broken counts use learn
outcomes WITHOUT the archive mounted (no outcomes-archive unit like outcomes-card): "fixed" can be inflated and the
feedback repair suppressed (the gate itself is judged against the archive's gate arm); the probe never ran through
the real mount.solve / solver shell with sandbox workers (ALFWorld two resets per item under the memory lock; sheet
pre-checks; scopes asserted, not observed; note_chars = request-length difference; a slow program up to 5 s per hook
call per item per probe): a dl smoke must check real probe records; a feedback revision gets no paid run of its own;
shared-type member checks combined with the archive coded but not tested; no docs changed.
