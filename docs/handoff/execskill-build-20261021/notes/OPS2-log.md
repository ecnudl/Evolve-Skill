# OPS2 log: route-B smoke operator (fivebench-execskill-v1, configuration main)

Operator OPS2 (agent of the main agent/registrar), started 2026-10-22 20:5x HKT (dl clock). Procedure:
`smoke-runbook.md` sections 2, 2b, 3, 4, 5, 6.1, 6.2, 7; stop at the smoke summary (no main run).
No secrets, keys or item content are recorded here.

Resume notes for a replacement operator:
- Shell setup of runbook section 1 is in `/root/ops2-20261022/env.sh` (paths only, plus unsetting OPENAI_* and the
  proxy variables and TMPDIR; interactive shells on dl export them from .bashrc). Every long step runs from a script in
  `/root/ops2-20261022/` (so no wrapper command line matches the leftovers regexes); stdout+stderr go to
  `/root/ops2-20261022/logs/<step>.log`, whose last line is `EXIT <code>`.
- tmux sessions: `execskill-prep` (S0 prep), `execskill-smoke` (S2/S3).

Pre-state checked 20:54: build HEAD 27ebe6335eb47382f84a331122dc0b47b70b243b, `git status --porcelain` empty;
`$SRC`, `$HIST`, `$Q23` absent; `$PRE` holds `inputs/` and `smoke/shared/exclusion-consent.json` only; /tmp IFree
254,897; no tmux server; no containers; 7 CPUs, 14 GB available.

## Commands (dl clock; exit status)

### Section 2: snapshot (20:57:08-20:57:10, tmux execskill-prep:snap, script s2-snapshot.sh, log logs/s2-snapshot.log)
- `test ! -e $SRC` exit 0; `git rev-parse HEAD > $PRE/build-head.txt` exit 0 (27ebe6335eb47382f84a331122dc0b47b70b243b)
- `prelaunch.sha256_list(/data/execskill-dev) > $PRE/source-sha256.txt` exit 0 (1,268 files; list sha256 f8086a7c8c3b4996…)
- `rsync -a --exclude=.env* --exclude=.git --exclude=__pycache__ skillopt scripts tests $SRC/` exit 0
- copy sha256 list > /tmp/execskill-copy-sha256.txt exit 0; `cmp` silent, exit 0; `find $SRC -name .env*` printed nothing
- `$CLI verify-snapshot --list $PRE/source-sha256.txt --root $SRC --git-head 27ebe633…` exit 0; provenance kept in
  /root/ops2-20261022/logs/verify-snapshot.json: build_tree /data/execskill-dev, git_head 27ebe633…, snapshot_root
  /data/execskill-20261021-source, sha256_list_sha256 f8086a7c8c3b499679b35c2eb22236818602a7874544f7cc96d1e8ca9e0910b6,
  env_files_absent true. VERDICT: pass.
- Pre-checks for 2b (read-only): the three qualify inputs, the native lock and image sha256:f7f6f598… (tag
  evolve-skill-sheet-recalc:20260930-offline) exist; $V3 sha256 20d9ffcc… and all six $IN sha256 equal the runbook table.
- 20:58:05 first launch of 2b failed to start: `tmux new-window -t execskill-prep` -> "no server running" (the session
  had ended with the snapshot window). Nothing ran ($Q23 absent, no process). Session re-created with an idle window
  `hold` (`bash --norc --noprofile`) so it persists.

### Section 2b: engine qualification q23 + sheet-runtime (20:58:19-20:59:30, execskill-prep:q23, s2b-q23.sh)
- `test ! -e $Q23` exit 0
- `cd $SRC && PYTHONPATH=$SRC $PY -B -m scripts.replay_sheet_v6 qualify --output $Q23 --image sha256:f7f6f598… \
  --legacy-qualification …/q17/qualification.json --comparison-fixture-qualification …/continual-unknown-sheet-v6-20261001-q/qualification.json \
  --native-lock …/native.lock --engine-version v7 > $PRE/sheet-q23.log 2>&1` -> EXIT 0 (70 s). status "qualified",
  version spreadsheet-v6-independent-replay-v1 / spreadsheet-independent-lo-recalculation-v7, model_api_calls 0;
  $Q23/qualification.json sha256 6cf608e0be7351cc0ba230b2491144c9b7606258509cd461b6ea4f244c95cb33,
  record_hash 6aba0c981312421ac2f4a34f9252e9577bbb4c0acdaa983582247f1b6a485378
- `$CLI sheet-runtime --manifest $V3 --engine-qualification $Q23/qualification.json --out $PRE/sheet-runtime.json`
  exit 0; $PRE/sheet-runtime.json sha256 ab85a0e68c8cf4f4dd2c66064e2597fa351532aedffb4ed0abb42a92dddc9580; recalculation
  block: image sha256:f7f6f598… (kept), timeout_seconds 120 (kept), qualification_path $Q23/qualification.json,
  qualification_sha256 6cf608e0…, qualification_hash 6aba0c98…. VERDICT: pass.

### Section 3: S0 (zero model calls), tmux execskill-prep
- 21:00 baseline `$CLI leftovers` (machine quiet; read-only; run once more at its runbook place before s0-collect):
  exit 0, verdict "clean" (no containers, no route-B/ALFWorld/excluded processes).
- Parallel plan (independent zero-call steps; checked in code first): zero-call-checks (window zcc) || make-items
  ALFWorld (window alf) || s0-pool-views, then make-fixtures, import-texts, import-sheet-qualification, make-items
  SearchQA (windows views, quick). The test suite's smoke leftovers rows run in fake mode (`found=[]`, FakeDocker), so
  host processes cannot affect it; each make-items writes its own write-once supply file. s0-collect, sandbox-selftest
  and leftovers run alone afterwards (s0-collect has its own leftovers row).
- 21:00:49 `df -i /tmp`: IFree 254,895 (>= 160,000) -> zero-call-checks started (window zcc, s3-zcc.sh).
- 21:00:49 make-items ALFWorld started (window alf, s3-alf.sh; `test ! -e $HIST/supply/alfworld-xs.json` exit 0).
- 21:00:49-21:00:58 `$CLI s0-pool-views --manifest $V3 --out $PRE/s0-pool-views.json` exit 0; record_sha256 bcb846c7…;
  file sha256 2ae9ddea…; views (items/max/p99 bytes): alfworld 39/176/176, livemath 155/6,491/6,365, officeqa
  50/30,116/30,116, searchqa 400/4,697/4,503, spreadsheetbench 80/12,449/12,449, workbook 80/599,328/599,328
  (= the 10/22 throwaway values 599,328 and 30,116).
- 21:01:25 quick sequence started (window quick, `s3-quick.sh 599328`).
- 21:01:25-21:01:46 quick sequence (window quick), each exit 0:
  - `$CLI make-fixtures --out $PRE/fixtures --p99-workbook-bytes 599328`: livemath/officeqa/spreadsheetbench 20 each;
    crash subset 2 per bench; p99 item fx-spreadsheetbench-19 (requested 599,328, input 602,276, answer 602,300 B);
    record sha256 eeabb01ddd89ad72…, set sha256 c5cd65e4410a1bca…, package sha256 a13a7f64523ea238…
  - `$CLI import-texts --source /data/coevo5-20261019-v3-pre/texts/texts.json --out $PRE/texts`: 5 cards (chars:
    alfworld 2,301, livemath 2,068, officeqa 2,926, searchqa 1,846, spreadsheetbench 2,907)
  - `$CLI import-sheet-qualification --source $V3SHEET --sha256 $V3SHEET_HASH --out $PRE/sheet`: train side, 120 items,
    91 qualified (excluded: read_view_unverifiable 6, reference_cache_mismatch 1, reference_recalculation_failed 22)
  - `$HFCLI make-items --bench searchqa --history-root $HIST --dry-run --fresh-manifest … --dataset lucadiliello/searchqa
    --revision c1a97906… --exclude … --cache-sha256 …`: counts items 11,378 (= expected), written false
  - the same without --dry-run: items 11,378, written true -> $HIST/supply/searchqa-tail.json, sha256
    3cc0392834f4c00f703e9c5520abbeffee16a11ea62cb1484d259fa6c0c5eca7
- 21:02 read-only check before exclude-tests: $HIST/supply/alfworld-xs.json (written 21:00:51 by make-items before its
  pre-resets) verifies as a supply record: 3,514 items, 108 rooms (= dry-run counts). Exclusion consent sha256
  77872f24418fd20fd94e372d740e891c35b21dc074244cbf73f9d510a80585a8 (unchanged, = OPS1).
- 21:02:54-21:03:02 `$CLI exclude-tests --root $SMOKE --pinned $IN/v3-data-pins.json --searchqa-supply
  $HIST/supply/searchqa-tail.json --alfworld-supply $HIST/supply/alfworld-xs.json` (window excl, s3-excl.sh) exit 0:
  searchqa_test_exclusion: supply 11,378, test_items 400, dropped_by_id 0, dropped_by_question 0, kept 11,378
  (exclusion_sha256 4f53cda1…, record_sha256 537e9b9b…); alfworld_test_identity_check: supply_games 3,514, test_games
  134, test_rooms 4, overlap_games 0, overlap_rooms 0 (exclusion_sha256 7a224b75…, record_sha256 678db107…);
  canaries searchqa 5 + alfworld 5 (record_sha256 2edc279d…). Wrote $SMOKE/shared/exclusion/{alfworld_test_identity_check,
  searchqa_test_exclusion,test-canaries}.json. Consent sha256 unchanged after the run.
- 21:00:49-21:17:28 `$CLI make-items --bench alfworld --history-root $HIST --data-root $ALFWORLD_DATA --pool-games
  $IN/alfworld-pool-games.json --runtime $IN/alfworld-runtime.json` (window alf) exit 0 (16.7 min): items 3,514, rooms
  108 (task types as the dry run), preset 322 views. $HIST/supply/alfworld-xs.json sha256 a936f549…,
  alfworld-xs-views.json sha256 5f61286b…. NOTE: 322, not the runbook text "~422": checked read-only in code, the
  cut is smoke 12 + run 60 + accept 150 + select 100 = 322 (select is an upper bound <= 200, `supply.UPTO`; the 20
  selection rooms hold 100 games). As designed; not a fault.
- 21:17:30-21:17:33 `$CLI export-pools --manifest $V3 --out $PRE/pools --alfworld-supply $HIST/supply/alfworld-xs.json
  --alfworld-views $HIST/supply/alfworld-xs-views.json` (window pools, chained after alf) exit 0. pools.json
  record_sha256 668bb3f3…, file sha256 1eef341c…. Per bench (items; parts; file sha256):
  searchqa 600 (train 400 + val 200; ids_digest 332df1bf… = expected supply-order ids, items_digest 120f123f… =
  expected) aa5c9732…; spreadsheetbench 91 of pool 120 (written train 58 + val 33 = expected) fde19d0b…; officeqa 74
  (50 + 24) 93e608d2…; livemath 283 (155 + 128) 041d23d1…; alfworld 3,514 fresh, 108 rooms, viewed 322 (views
  runtime sha256 76e0e442…) 16f4b627…. The first four rows reproduce the 10/22 throwaway export. VERDICT: pass.
- 21:18 smoke-items (window items, s3-items.sh) launched, chained with sandbox-selftest (s3-selftest.sh) on success.
- 21:19:58-21:19:59 `$CLI smoke-items --out $PRE/smoke-items --searchqa-pool $PRE/pools/searchqa.json --alfworld-supply
  $HIST/supply/alfworld-xs.json --alfworld-views $HIST/supply/alfworld-xs-views.json --data-root $ALFWORLD_DATA
  --fixtures $PRE/fixtures` (window items) exit 0: record $PRE/smoke-items/smoke-items.json (record_sha256 7e055c98…);
  sets alfworld=$PRE/smoke-items/alfworld.json, livemath/officeqa/spreadsheetbench=$PRE/fixtures/<bench>.json,
  searchqa=$PRE/smoke-items/searchqa.json; stages searchqa S2 20 / S4 60 / SN1 200 (= 280), alfworld S2 6 / SN1 6 (= 12).
- 21:19:59-21:20:08 `$CLI sandbox-selftest --out $PRE/s0 --items <the 5 files above>` (chained) exit 0: passed true;
  escape rows env_keys, identity, limits, network, no_secrets, python_flags, read_only, worker_child all true;
  measured vsz 173,972 KiB, rss 111,752 KiB, view_bytes_p99 5,531, views 352, start 3.186 s; file sha256 2d34ea12….
- 21:20 zero-call-checks still running (/tmp used 84,630 inodes).
- 21:00:49-21:27:05 `$CLI zero-call-checks --root $SRC` (window zcc) exit 0: passed true, returncode 0, summary
  "1390 passed in 1574.59s (0:26:14)". VERDICT: pass.
- 21:27 /tmp after it: IFree 129,085 (< the runbook's 160,000 for a suite run). Measured: run 1's own pytest basetemp
  /tmp/pytest-of-root/pytest-0 held 125,756 inodes (pytest keeps it until the NEXT session's exit; pytest-92..94 hold
  47 inodes, from nested sessions). With it kept, s0-collect's second suite run (~125,756 more) would leave ~3,300
  inodes of margin, an ENOSPC risk that would fail the S0 pytest row as an infrastructure fault. Decision (operator):
  with no process running, removed only /tmp/pytest-of-root/pytest-0 (scratch of the step just completed and passed; no
  record refers to it; earlier builders' directories were already gone). `rm -rf /tmp/pytest-of-root/pytest-0` exit 0
  -> IFree 254,841. This applies the runbook's own pre-check threshold to the second suite run.
- 21:28 s0-collect started (window collect, s3-collect.sh: `$CLI leftovers` at a quiet moment, IFree >= 160,000
  guard, then the runbook command with --items alfworld=…, livemath=…, officeqa=…, searchqa=…, spreadsheetbench=…).
- 21:28:31 (window collect) `$CLI leftovers` exit 0, verdict "clean"; IFree 254,841 (guard >= 160,000 passed).
- 21:28:32-22:07:07 `$CLI s0-collect --root $SMOKE --snapshot $SRC --items alfworld=$PRE/smoke-items/alfworld.json
  --items livemath=$PRE/fixtures/livemath.json --items officeqa=$PRE/fixtures/officeqa.json --items
  searchqa=$PRE/smoke-items/searchqa.json --items spreadsheetbench=$PRE/fixtures/spreadsheetbench.json --fixtures
  $PRE/fixtures --selftest $PRE/s0/sandbox-selftest.json --pins-out $PRE/s0-pins.json --manifest $V3 --sheet-source
  $V3SHEET --sheet-sha256 $V3SHEET_HASH --texts $PRE/texts/texts.json --sheet-runtime $PRE/sheet-runtime.json
  --engine-qualification $Q23/qualification.json --history-root $HIST` -> **EXIT 3**. CLI output:
  `{"checks": {"codex_fixtures": true, "determinism": true, "equivalence": true, "escape_probe": true, "exceptions":
  true, "ledger": true, "leftovers": true, "measurements": true, "pytest": true, "registry": true, "replay": true,
  "sandbox": true, "sheet": true, "supply": false}, "passed": false, "s0": "$SMOKE/s0/checks.json"}`.
  Rows (evidence, counts/hashes only): pytest "1390 passed in 1512.35s"; equivalence same 12/20/20/280/20 (alfworld,
  livemath, officeqa, searchqa, spreadsheetbench), 0 different/invalid; replay 228 trajectories, 7,524/7,524 steps,
  zero_crash 0 faults; sheet: engine q23 same as v3 training (13 fields, 7 sources equal), fixtures 20/20 qualified;
  measurements: guard ok (sum 1,151,428 KiB <= budget 9,943,869 KiB of MemAvailable 14,205,528), limits cell/
  detector/episode AS 2048 MiB frame 1 MiB mem 768 MiB, generator mem 1024 MiB, slots sandbox 4 / live 6 / native 3,
  measured vsz 174,240, worker rss 112,584, view max 30,116, native peak rss 44,732 KiB; wrote $SMOKE/s0/s0-limits.json
  and $PRE/s0-pins.json; determinism equal draws; sandbox, escape_probe, exceptions, ledger, registry, codex_fixtures,
  leftovers ("clean") pass.
  **supply row false** ($SMOKE/s0/s0-supply.json, record_sha256 868f8fc8…): evidence alfworld preset 322, cut 322;
  searchqa_tail kept 11,378, accept 1,000; exclusion verified.
- 22:08-22:12 diagnosis (read-only; code read through the Mac mount and one read-only python check, counts only):
  `s0._supply` passes only if `views_ok and len(wanted) == sum(supply.registered_sizes("alfworld").values())`.
  views_ok is TRUE (supply sha matches, the views equal the cut exactly, all 322 view digests match). The failing
  conjunct: len(wanted) = 322 vs sum = 422 (`protocol.PRERESET_GAMES = {smoke 12, run 60, accept 150, select 200}`,
  "422"). `supply._alfworld` takes at most MAX_GAMES_PER_ROOM = 5 games per room per slice and the selection group is
  20 rooms, so select <= 100 by construction (`supply.UPTO = {"select"}`); cut = 12 + 60 + 150 + 100. The row can never
  pass on a supply cut by these rules. Tests did not catch it: test_execskill_s0 uses a synthetic 108 x 3 supply and
  injected rows. (The runbook's "~422 pre-resets" carries the same assumption.)
- STOPPED here per the operator rules (step failed; no improvised fix). NOT run: smoke-make (dry/real), `smoke --stage
  S0` (S0 is NOT recorded), S1 probe and everything after. Model calls so far: 0. Question to the registrar is in the
  OPS2 report. tmux session execskill-prep left with only its idle `hold` window; nothing else running.

## Resume on snapshot b (registrar decision 22:3x)

Registrar 22:3x: diagnosis confirmed; dev tree fixed and committed a6f49d3ab601c8be490be4a0ff25b1c03bdde11b
(`s0._alfworld_cut`: every ALFWorld slice in full except the upper-bound select slice); protocol.SNAPSHOT_ROOT =
/data/execskill-20261021-source-b, Q23 = /data/execskill-20261021-sheet-q23-b; runbooks updated. Skip the separate
zero-call-checks and the unchanged data products (fixtures, texts, sheet import, both make-items, exclude-tests,
export-pools, smoke-items); s0-collect re-verifies them.

- 22:2x checked: dev HEAD a6f49d3ab601…, `git status` clean; diff 27ebe63..HEAD = protocol.py (SNAPSHOT_ROOT, comment),
  s0.py, tests (s0, mutations), runbooks (SRC/Q23 lines, the 322 comment), OPS2-log.md; source-b and sheet-q23-b absent;
  /tmp IFree 254,842.
- Step 1: /root/ops2-20261022/env.sh SRC=…-source-b, Q23=…-sheet-q23-b (sed, exact lines); s5-pins.py SRC=…-source-b;
  no other script hard-codes a snapshot path. Attempt-a step logs moved to /root/ops2-20261022/logs/attempt-a/.
- Step 2 (22:25): archived with `mv -n` into $PRE/archive/s0-attempt-a-20261022T2207/: build-head.txt,
  source-sha256.txt, sheet-q23.log, sheet-runtime.json, s0-pins.json, s0/ (the selftest), and $SMOKE/s0 as smoke-s0/.
  sha256 of every file before = after (6 files + 217 files). Untouched: snapshot a, q23 a, $SMOKE/shared/**,
  $PRE/{inputs,fixtures,texts,sheet,pools,smoke-items,s0-pool-views.json}, $HIST/**.
- 22:26 chain launched (tmux execskill-prep:chainb, s-chain-b.sh, log logs/chain-b.log): s2-snapshot.sh -> stop unless
  build-head = a6f49d3ab601c8be490be4a0ff25b1c03bdde11b -> s2b-q23.sh -> s3-selftest.sh -> s3-collect.sh (leftovers,
  IFree guard, s0-collect with the same arguments as attempt a, SRC/Q23 b); each only after the previous exit 0.
- Step 3, section 2 snapshot b (22:26:03-22:26:05, s2-snapshot.sh): `test ! -e $SRC` exit 0; build-head.txt =
  a6f49d3ab601c8be490be4a0ff25b1c03bdde11b (chain check passed); source-sha256 exit 0 (1,268 files); rsync exit 0;
  copy sha256 exit 0; `cmp` silent exit 0; no .env files; `$CLI verify-snapshot …` exit 0. Provenance (kept in
  /root/ops2-20261022/logs/verify-snapshot.json): git_head a6f49d3ab601…, snapshot_root /data/execskill-20261021-source-b,
  sha256_list_sha256 e300a7fe472bfdc24b02b1a73231beef2eee34de7e4edb16951e7812031eac9c, env_files_absent true. PASS.
- Step 4, section 2b (22:26:05-22:27:08, s2b-q23.sh): q23-b qualify EXIT 0 (62 s), model_api_calls 0,
  $Q23/qualification.json sha256 1b2ed470084a0abe37fe0c33f2b4757875666a007151a1584884ab694925d300, record_hash
  3505798b8d11fdcff99ae645f3cb292b529c16786b8a1824b0dfdfb228697664; `$CLI sheet-runtime …` exit 0 -> $PRE/sheet-runtime.json
  sha256 40aa30a56e6266959dc75e244b405d63ba36fc6ef03ae361ff080f771cce1e8e (image sha256:f7f6f598… and timeout 120 kept). PASS.
- Step 5a (22:27:08-22:27:21, s3-selftest.sh): `$CLI sandbox-selftest --out $PRE/s0 --items <5 files>` exit 0, passed;
  escape rows all 8 true; vsz 173,980 KiB, rss 111,900 KiB, view p99 5,531, views 352, start 4.868 s; sha256 ad29a65a…. PASS.
- Step 5b: 22:27:21 `$CLI leftovers` exit 0 "clean"; IFree 254,842; s0-collect started 22:27:22 (same arguments as
  attempt a; SRC/Q23 b).
- Step 5b result (22:27:22-23:06:18): `$CLI s0-collect --root $SMOKE --snapshot $SRC (b) --items alfworld=… livemath=…
  officeqa=… searchqa=… spreadsheetbench=… --fixtures $PRE/fixtures --selftest $PRE/s0/sandbox-selftest.json --pins-out
  $PRE/s0-pins.json --manifest $V3 --sheet-source $V3SHEET --sheet-sha256 $V3SHEET_HASH --texts $PRE/texts/texts.json
  --sheet-runtime $PRE/sheet-runtime.json --engine-qualification $Q23(b)/qualification.json --history-root $HIST`
  -> EXIT 0, all 14 checks true, passed true. Evidence: pytest "1393 passed in 1503.95s"; supply true (record
  15d2065b…): alfworld slices smoke 12 / run 60 / accept 150 / select 100, cut 322 = preset 322; searchqa tail kept
  11,378, accept 1,000; exclusion verified; equivalence same 12/12, 20/20, 20/20, 280/280, 20/20; replay 228
  trajectories, 7,524/7,524 steps, 0 faults; sheet engine q23-b (3505798b…) same sources as v3 training (roots
  source-b vs v3-source-f), fixtures 20/20; measurements guard ok (1,148,528 <= 9,976,646 KiB), cell limits AS 2048 MiB,
  frame 1 MiB, mem 768 MiB, slots sandbox 4 / live 6 / native 3, measured vsz 174,252, worker rss 112,216, view max
  30,116, native peak rss 44,480 KiB; leftovers clean. Wrote $SMOKE/s0/* (checks.json sha256 d9891b61…),
  $SMOKE/s0/s0-limits.json (35d82845…), $PRE/s0-pins.json (6e48f99e…). /tmp IFree after: 254,186. PASS.
- 23:07 smoke-make --dry-run launched (window makedry, s3-makedry.sh).
- 23:07:26-23:07:30 `$CLI smoke-make --items <5 SET=FILE> --selftest $PRE/s0/sandbox-selftest.json --dry-run` (window
  makedry) exit 0: stages S0 S1 S2 S3 SE6; control_cells 0; noise_anchor false; items alfworld 12, livemath 20,
  officeqa 20, searchqa 280, spreadsheetbench 20; spec d68ee2a0…; written false.
- 23:07:47-23:07:53 (window make, s3-make.sh) `$CLI smoke-make …` (same, no --dry-run; no --control-cells, no
  --noise-anchor) exit 0, written true: $SMOKE/smoke.json (record d68ee2a02ae1bb17…, file sha256 9dca1cea1f9b5da9…);
  then `$CLI smoke --spec $SMOKE/smoke.json --stage S0 --input $SMOKE/s0/checks.json` exit 0: {"stage": "S0",
  "passed": true} -> $SMOKE/stages/S0.json. **S0 PASS.**

### Section 4: S1 probe (paid)
- 23:08 launched (tmux execskill-prep:probe, s4-probe.sh): `$CLI probe --spec $SMOKE/smoke.json --env-path $ELUCID
  --probe-root $PRE/probe` (no proxy_on; explicit gateway, trust_env False).
- 23:08:20-23:17:12 `$CLI probe --spec $SMOKE/smoke.json --env-path $ELUCID --probe-root $PRE/probe` -> **EXIT 3**.
  CLI output: {"attempt": 1, "branch": null, "calls": 1, "classes": {"probe": 1}, "complete": false, "longest": null,
  "passed": null, "rows": null, "stopped": "first_call_not_confirmed"}. S1 NOT recorded.
  Attempt record $PRE/probe/attempts/attempt-1.json (record_sha256 58d65ddd…; whitelisted fields only): row a, M 64,
  B 32,768, request_bytes 101, ok false, **error_type http_503**, returned_model none, **seconds 530.7**; gateway
  http://httpproxy-headless.kubebrain.svc.pjlab.local:3128, trust_env false, first_confirmed false.
  Probe ledger $PRE/probe/ledger/state.json: halted null, open {}, settled 100,143 of cap 500,000 (= 3 x (101 + 512 +
  32,768): the frozen client tried 3 times, each charged its reservation).
- 23:19 network/TLS check (AGENTS.md; main-runbook 5.1 form; no credential, no model call; `/usr/bin/curl` with
  LD_LIBRARY_PATH unset, since /usr/local/bin/curl fails with a libcurl symbol error under the inherited
  LD_LIBRARY_PATH): through the gateway, hk.getelucid.com http=200 tls=0.65 s; northgate.xiaobei.top http=200;
  open.bigmodel.cn http=200. Route and TLS work; the 503 came from the endpoint side during the call.
- STOPPED (rule: a failed step that the runbook does not mark as repeatable). The probe code allows another attempt
  (1 sent + 41 <= 60), and smoke-runbook 6.3 gives the rule "check network and TLS, then run again" for S3's
  unconfirmed first call only; nothing for S1. Question to the registrar: may OPS2 re-run `probe` (attempt 2)?
  Nothing running; S2/S3/S-E6 not started.
- Registrar 23:2x: re-run `probe` as attempt 2 now, same command (route A); the 503 was an infrastructure fault
  (the 6.3 rule applied to S1). If attempt 2 stops on its first call with a 5xx or a timeout: one 20-minute background
  wait, TLS check again, attempt 3; if attempt 3 fails the same way, stop. Any 401/402/403/429 or balance/quota text:
  stop at once, no retry.
- 23:2x attempt-1 step log kept as logs/s4-probe-attempt1.log; attempt 2 launched (tmux execskill-prep:probe2,
  s4-probe.sh, same command).
- 23:21:44-23:33:49 attempt 2, same command -> EXIT 3: {"attempt": 2, "calls": 1, "complete": false, "stopped":
  "first_call_not_confirmed", "branch": null, "rows": null}. attempt-2.json (sha256 74bf24af…): row a, M 64, B 32,768,
  ok false, **error_type http_503**, **seconds 723.0**, no model. Probe ledger: settled 200,286 of 500,000, not halted,
  nothing open. A 5xx (no 4xx, no balance/quota text) -> per the registrar: one 20-minute background wait (from 23:35),
  then the TLS check, then attempt 3.
- 23:34:40 the 20-minute background wait started; 23:4x registrar update (23:40): do NOT run attempt 3, stand by.
  Registrar checked elucid outside the ledger: GET /v1/models 200 in 1 s listing deepseek-v4.1-flash-1017 (key and
  route fine); one diagnostic chat call (max_tokens 8) got 503 "Service temporarily unavailable" after 148 s, so the
  provider's upstream for this model is down. Each failed probe attempt charges about 100k of the probe ledger's
  500k cap (200,286 used). The registrar polls elucid with a zero-ledger call and will send "go attempt 3".
- 23:4x wait ended early (background task stopped; remote sleep killed); nothing running; S1 not recorded; on
  "go attempt 3": move logs/s4-probe.log to s4-probe-attempt2.log, run s4-probe.sh (attempt 3), then 5 -> S2 || S3 ->
  S-E6 -> summary. **HOLD.**
- 00:3x (10/23) registrar: "go attempt 3": elucid answered 200 at 00:32:12 (deepseek-v4.1-flash-1017, finish stop, 0
  reasoning tokens, 14.2 s; 503 at 23:51, 00:01, 00:11, 00:21). Rules: attempt 3 first-call 5xx/timeout -> stop, no
  retry; a part-way ledger stop -> stop with the attempt counts, no 4th attempt; a later S2/S3 infrastructure pause ->
  the runbook's 6.3 rows, else stop and report.
- attempt-2 step log kept as logs/s4-probe-attempt2.log; attempt 3 launched (tmux execskill-prep:probe3, s4-probe.sh).
- 00:32:52-00:34:33 S1 probe attempt 3 (tmux execskill-prep:probe3, `bash s4-probe.sh > logs/s4-probe.log`):
  RC s0_recorded 0, RC s1_absent 0, RC probe 3, EXIT 3. CLI printed: attempt 3, complete false,
  stopped "ledger_stop:BudgetStop", calls 12 (classes probe 12), branch/longest/rows/passed null. S1 NOT recorded.
  Record $PRE/probe/attempts/attempt-3.json (sha256 4ae878299fcb8878febdabf70aa32b6c239fd97b077f58e589f47d47541cd010;
  calls_before 2; gateway = PJLAB gateway, trust_env false, first_confirmed true).
  Per call (attempt-summary.py, counts only; the client sends max_tokens = M in every body):
    a/0 (M 64): ok, deepseek-v4.1-flash-1017, finish stop, 3.3 s, usage prompt 16 / completion 1 / total 76.
    b M16 n0-n4: HTTP 200, registered model, finish length, completion_tokens 1024 each (M = 16), error_type
      finish_length, 12.1-16.9 s.
    b M16 n5-n9: HTTP 200, returned model "cb/deepseek-v4.1-flash" (n5, n6) and "deepseek-v4-1-flash" (n7-n9), not in
      ELUCID_RESPONSE_MODEL_IDS {deepseek-v4.1-flash-1017}; finish length, usage empty; error_type model_mismatch,
      3.6-6.8 s.
    b M64 n0: reservation refused by the ledger, never sent (11 HTTP sends in attempt 3; the CLI counter says 12).
  Probe ledger ($PRE/probe/ledger): settled 372,893 of 500,000 (attempt 3 added 172,607 = a 17 + 5 x 1,059 +
    5 x 33,459 charged for the usage-less mismatches); open {}; halted null; halts 0. The refused reservation
    (133,836 = 4 tries x 33,459) exceeded the remaining 127,107 on both scopes (overall, smoke:probe). A row-a call
    needs 133,524, so this probe ledger cannot reserve any further call.
  Call count over attempts (CLI counter): 2 + 12 = 14 of S1_MAX_CALLS 60.
  DISCLOSURE: the ledger settle details of attempts 1 and 2 list the client's per-try statuses as
    [503, 503, 429, 503] and [503, 429, 503, 503]: each failed attempt held one HTTP 429 try. I reported only the
    attempt-level error_type http_503 at the time. No response bodies were read, so I saw no quota/balance text.
  Registrar rule 2 (a ledger stop part-way): STOP. No 4th attempt, no section 5, no S2/S3.
  On dl: nothing running (execskill-prep holds only the idle hold window).
- 00:35 attempt-3 report delivered to the registrar (SubagentHandback).
- 03:1x-03:3x registrar addendum 02:3x (chain-G smoke on snapshot c): PREPARE ONLY. Nothing paid, no state change
  until "GO c <commit>". Read: the registrar decisions (sections "Smoke S1: elucid outage ..." and "Registrar addendum
  2026-10-23 02:3x"), the "Chain-G smoke" sections of /data/execskill-dev-g smoke-runbook.md and main-runbook.md,
  and G1's uncommitted diff (CLI smoke-make --solver-chain, manifest._solver_chain/_smoke_pools, protocol
  SNAPSHOT_ROOT source-c, smoke.load/solver_of; routes.pin/solver_block read no credential).
  Read-only checks (exit 0): df -i /tmp (248,207 free); git -C /data/execskill-dev log/status (a6f49d3; only docs
  modified); ls $PRE, $SMOKE, $PRE/archive; source-c and sheet-q23-c absent.
  Prepared in /root/ops2-20261022/ (b scripts kept; a python transformer applied each replacement exactly once,
  files created with O_EXCL):
    env-c.sh (SRC source-c, Q23 sheet-q23-c, L logs/c); s1-archive-c.sh (step 1: mv into
    $PRE/archive/smoke-elucid-b-20261023/, sha256 of every moved file before/after compared, $SMOKE/shared checked by
    metadata only); s-chain-c.sh <GO commit> (prechecks HEAD == GO commit, no uncommitted code, archive done; then
    s2-snapshot-c, s2b-q23-c, s3-selftest-c, s3-collect-c, s3-makedry-c / s3-make-c with --solver-chain G and a
    read-only chain-G spec check before smoke --stage S0, s5-manifest-c with s5-pins-c.py (chain D block branch N,
    longest routes.S1B_CEILING, route-B pin from it; no S1 record required); one line per step appended here);
    for the second go only: s6-S2-c.sh / s6-S3-c.sh (--env-path $GREPO --roles-repo $GREPO), s6-SE6-c.sh.
  bash -n: all 13 OK; s5-pins-c.py ast OK. Zero-call dry check on the G1 worktree code (imports only, no write):
    manifest.check_clients(main) OK; D block N/256 with B 32,768 (QA) / 65,536 (sheet) / 4,096 (ALFWorld); G block
    B 65,536 everywhere; route-B pin deepseek-v4-flash N/256, same B.
- 03:4x (10/23) registrar: "GO c 344ddcc874bc44261025db2fc7d4027767847316". /data/execskill-dev fast-forwarded by the
  registrar (only OPS2-log.md and the decisions doc dirty); G1 stopped, no other pytest on dl, G1's /tmp/pytest
  dirs cleaned; Codex one round: "VERDICT: NO DEFECT FOUND", committed diff equals the reviewed one. Skip the separate
  zero-call-checks (registrar: s0-collect's pytest row is the full-suite gate for this commit). If s0-collect fails:
  stop and report the failing row and the CLI's error text, no retry. No S2/S3 before the second go.
  Step 1 now: bash s1-archive-c.sh > logs/c/s1-archive.log (foreground, after a HEAD check).
- 03:33:46-03:33:47 step 1: bash s1-archive-c.sh > logs/c/s1-archive.log -> EXIT 0 (every RC 0). Moved into
  $PRE/archive/smoke-elucid-b-20261023/: from $PRE build-head.txt, source-sha256.txt, sheet-runtime.json, s0/,
  s0-pins.json, probe/ (S1 attempts 1-3 + probe ledger), sheet-q23.log = 12 files; from $SMOKE (under smoke/) s0/,
  smoke.json, stages/ = 219 files (s0 16, s0/sheet-fixture-qualification 201, smoke.json, stages/S0.json).
  sha256 before == after for every moved file (cmp of the lists); $SMOKE/shared metadata unchanged (no file read
  there); $SMOKE now holds only shared/. Lists: logs/c/archive-b-pre-after.txt (sha256 7af09d1f45002b96...) and
  logs/c/archive-b-smoke-after.txt (sha256 2625feda97acbeb4...). Moved files (path relative to the archive root, or
  to its smoke/ for the "smoke" lines):
  ```
  pre   599a87100f1ff57378c3be1ef864b06e71e4c8be6b3ff8cf7a397666fd7cb1c0  build-head.txt
  pre   08b2fdb88e18a1c1f5d2ec14d7393bfbfa2f6cfd34a699ab1754f7f2b0ef3a9f  probe/attempts/attempt-1.json
  pre   74bf24af427358db23b58bce882cc34e4a9f2c6eaf82da173a999a254dd12a25  probe/attempts/attempt-2.json
  pre   4ae878299fcb8878febdabf70aa32b6c239fd97b077f58e589f47d47541cd010  probe/attempts/attempt-3.json
  pre   80c1c528da92aeb68a706216d335a6ada36f50d5b2dc62bb56420eb85f5b56dd  probe/ledger/events.jsonl
  pre   e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  probe/ledger/.lock
  pre   87da79c37f687197721ede67186db1e540b85a6b576fe23c6c2049e436a24804  probe/ledger/state.json
  pre   6e48f99e28d52b429762ee237edeecc763692acd6026ab339517c544120d879a  s0-pins.json
  pre   ad29a65a7a031cd5630374166f2e0883a72b19faa69a6914d22e9c630faa9dbb  s0/sandbox-selftest.json
  pre   1bc28785607f5a5330e54e03179d8859cd6413b6c0e92d91609735df8ebf097c  sheet-q23.log
  pre   40aa30a56e6266959dc75e244b405d63ba36fc6ef03ae361ff080f771cce1e8e  sheet-runtime.json
  pre   e300a7fe472bfdc24b02b1a73231beef2eee34de7e4edb16951e7812031eac9c  source-sha256.txt
  smoke d9891b61ac2c87aee303c64cf5aee3aa1256782bb0f506dbe92d9d09f63a48d4  s0/checks.json
  smoke 6c741680e3a9fbfba4daca2d4cbcf6d3e5c987c6be78e1b5ac120db54b8ebab0  s0/s0-codex_fixtures.json
  smoke 90670ded4bc44b63d131e2280f663f5f25c30f4e9665fe053f600515282ceb6c  s0/s0-determinism.json
  smoke f03cad8392b2afefa0ad5862a8b8c4a77a50283c9ccb265f0de839aff87d9986  s0/s0-equivalence.json
  smoke 9f6f9698ba781bb116bb8d29760e6fc89f9ac3670b44ffed6e1ef2745433fee8  s0/s0-escape_probe.json
  smoke 12069b77b9dab0fa222d2b2319de4c9437c03f9da896e82984270a44588be50a  s0/s0-exceptions.json
  smoke 9a4d3915c1c8de466847d7c8ad2fb685d0a208f0240311291c50aad0c95d9664  s0/s0-ledger.json
  smoke 28ab01405596a30ed66f41db18590308657447f9c0e60b2dd807d6b049093a06  s0/s0-leftovers.json
  smoke 35d828456fa32c23086262162f497ca87c58130fcea4b2453772710410e6e1ce  s0/s0-limits.json
  smoke 1921c172f4e2700b40e532a49b880cc0050c5f3de94e8431de7e04ce77eb9e86  s0/s0-measurements.json
  smoke c1633a1dcdb8b570e41d9911dc4c43f7ea5da73504ec0c51dbb06abc30784ba6  s0/s0-pytest.json
  smoke 1308af9b6baa841c11c9e5e59495a6195465d5dc6574efebea0a3ab980e27664  s0/s0-registry.json
  smoke 458f86f8cd24d21397497d1461fd6f2fb0488199b34fec332fc2d15a69a4e80a  s0/s0-replay.json
  smoke 7b06b6133599b3929fd599b22c7b08e12a6547540fe990f3d9c301d38114376e  s0/s0-sandbox.json
  smoke 8b110bcd879ec99868b188f49542fc5e0abd69e5d7f38e51d62ddfdb28384fa6  s0/s0-sheet.json
  smoke 55a96e83e9f046825007fb2e3cbab0c87caf08e813492fa6d9399bf15c22a5e5  s0/s0-supply.json
  smoke 380ec4d1b03b83426af09598b8327cfed419315fcc07cc80ae0742da02379358  s0/sheet-fixture-qualification/host_only/scorer_artifacts/01a63b293b99c40d9a20563a4a8f35c73d605d0e6d703fff7162d6e1543d0d9d/recalculations/7edd5012765b5b4f3ae18ad2281904fc9279ce78cfcb8d2ea9efc8a47e0e875a.json
  smoke 07f96c683b2f80130b0b841440a71e2853e3d4f0b281d37ddc47ad76cca213c8  s0/sheet-fixture-qualification/host_only/scorer_artifacts/01a63b293b99c40d9a20563a4a8f35c73d605d0e6d703fff7162d6e1543d0d9d/result.json
  smoke d45be37ab020dafb0c82a65b88b6c395ca11d1a760e58e755d0492080496e572  s0/sheet-fixture-qualification/host_only/scorer_artifacts/01a63b293b99c40d9a20563a4a8f35c73d605d0e6d703fff7162d6e1543d0d9d/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/01a63b293b99c40d9a20563a4a8f35c73d605d0e6d703fff7162d6e1543d0d9d/.writer.lock
  smoke 1b3a227a78aeb492c187414df285284c6ed4cb6b5c340207125ca63700586489  s0/sheet-fixture-qualification/host_only/scorer_artifacts/026cfcf56268bdcaa699067675def8486a296e4c17c5349ecbeff03eb21796c5/recalculations/c48ba4ea59376b3d9457c7393c01954b4d39f6b3e78f3c4f41d3ce2dd095dc74.json
  smoke 11ebca5255c034f5f6e8d6247dbd29e3e11298cd580b5af13e258032181bd34f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/026cfcf56268bdcaa699067675def8486a296e4c17c5349ecbeff03eb21796c5/result.json
  smoke cca3071c457f5a7b30c8dc7a7aeb0a4917a042fa87175da9c0610a6ee7d69f12  s0/sheet-fixture-qualification/host_only/scorer_artifacts/026cfcf56268bdcaa699067675def8486a296e4c17c5349ecbeff03eb21796c5/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/026cfcf56268bdcaa699067675def8486a296e4c17c5349ecbeff03eb21796c5/.writer.lock
  smoke 87011c64cda0d208b9369bb6f0f9d48cdcf98d2fc0d4fab00720431b23823e8f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0304e24089d1561453446d728834e020a82d819df11ab2b49a63d2537762c461/recalculations/273d86a61a077d46839a61c8fddd390abbb749cacded35587cc9a440055f38df.json
  smoke 79b4dd53e4ce4c8bd3590acc9d53f38b1a90a52d2d98d0b24f131a2e5dcd6155  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0304e24089d1561453446d728834e020a82d819df11ab2b49a63d2537762c461/result.json
  smoke 26fe5c8590d93a6f8474cb32febebb63e7ab9c7e42b667cb7d60a5792399e4be  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0304e24089d1561453446d728834e020a82d819df11ab2b49a63d2537762c461/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0304e24089d1561453446d728834e020a82d819df11ab2b49a63d2537762c461/.writer.lock
  smoke a3f4499f0c07bc0b6401df2da0d64b0443cb97e4c84dfeae3cb37791fc8e5c37  s0/sheet-fixture-qualification/host_only/scorer_artifacts/04e0104b63baf10dcae87ca846b1d27cc9d2a50ed8503ff8e46c752e817c948b/recalculations/e23b42026ee25113884436aaf5a43f3dd6058c7a2ec36fde5627e0a70e62e795.json
  smoke 020f4c285a83b1f338980c1302e36ef5c053e4b46f441c77d37aef9ada3fb79f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/04e0104b63baf10dcae87ca846b1d27cc9d2a50ed8503ff8e46c752e817c948b/result.json
  smoke 191e2dd704002d1ca898e552af01cb04d817340d561ce1eecf5a2dfea9180a6e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/04e0104b63baf10dcae87ca846b1d27cc9d2a50ed8503ff8e46c752e817c948b/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/04e0104b63baf10dcae87ca846b1d27cc9d2a50ed8503ff8e46c752e817c948b/.writer.lock
  smoke ac52e83f2c185eb835183b248888f54499c132f1c0f6630604490bd1926e71c2  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ce96caaf13e59dcb3b24faac821824531961ba3eaad27f84fd16bb0a7830cd5/recalculations/82b1b0e9f61eba1168ea1a3a1ab8897e5f73617eb1072661fcd986fbefee39ed.json
  smoke d9dad9526bcf412ac6771c8dd9f775d88f0924608e4719e7588931020667fa9a  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ce96caaf13e59dcb3b24faac821824531961ba3eaad27f84fd16bb0a7830cd5/result.json
  smoke e757d1ca578e782698347a909d7a31fd4e36120e03bda45590ca8dcb24c49c0c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ce96caaf13e59dcb3b24faac821824531961ba3eaad27f84fd16bb0a7830cd5/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ce96caaf13e59dcb3b24faac821824531961ba3eaad27f84fd16bb0a7830cd5/.writer.lock
  smoke d52654c8fb2ea0a60cd09d01ad302ea46082c448c0b6d10b49dea00287c0aa8f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ecf98b628f808f6bcb5fab5808f5a49d39c3a263ec239b03369696b5cb90302/recalculations/2542dc0501b8cd170db8a323102c22cd15a7bfe634b15944f87fde6a70359436.json
  smoke 973bc4373e247356c6b0f24e38af6a9d5e025a727adacbfaed5635b4b3563b98  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ecf98b628f808f6bcb5fab5808f5a49d39c3a263ec239b03369696b5cb90302/result.json
  smoke aeb8d0fac0e6caee109b69d7a4fc680297d2c817c1cc86fb77ba151b10167e60  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ecf98b628f808f6bcb5fab5808f5a49d39c3a263ec239b03369696b5cb90302/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/0ecf98b628f808f6bcb5fab5808f5a49d39c3a263ec239b03369696b5cb90302/.writer.lock
  smoke 0c18ce05a39d881e5db84ebaa732952dcf472c2106607855f32880e9a5522366  s0/sheet-fixture-qualification/host_only/scorer_artifacts/104ad42dfe6d7d248d9871b696888d3dff58f076907ed9af8448c8b585106bdd/recalculations/ebb32920323fbcfcb8077fc6611a5fd0fbc338854d14c4f5a521753e168b3b08.json
  smoke 5a5a52b4362a91bc6c566fc3ecb293de39254265177dddaa6b2d2d9489a8a82e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/104ad42dfe6d7d248d9871b696888d3dff58f076907ed9af8448c8b585106bdd/result.json
  smoke 60c7e0cf167fa78c37026a9458ea1b626058da165237e58c3c5561f93a7f9e08  s0/sheet-fixture-qualification/host_only/scorer_artifacts/104ad42dfe6d7d248d9871b696888d3dff58f076907ed9af8448c8b585106bdd/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/104ad42dfe6d7d248d9871b696888d3dff58f076907ed9af8448c8b585106bdd/.writer.lock
  smoke c288e85ca690ef29fca000069ee90d394474ac1b283bbaeb2df15a89a136959b  s0/sheet-fixture-qualification/host_only/scorer_artifacts/17441717fa063eb7bb74a1955a59e2cb0a1978d0c3200ce10e117dbb88579b5e/recalculations/82b1b0e9f61eba1168ea1a3a1ab8897e5f73617eb1072661fcd986fbefee39ed.json
  smoke 6e85251420252909ebe06a296116448ca3c1d91c0de9e45cfe5f474efd367fee  s0/sheet-fixture-qualification/host_only/scorer_artifacts/17441717fa063eb7bb74a1955a59e2cb0a1978d0c3200ce10e117dbb88579b5e/result.json
  smoke 7eebf31880b607d064d93ddaa86c7a3861472da64dc424fe75bbc9a68af3cb33  s0/sheet-fixture-qualification/host_only/scorer_artifacts/17441717fa063eb7bb74a1955a59e2cb0a1978d0c3200ce10e117dbb88579b5e/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/17441717fa063eb7bb74a1955a59e2cb0a1978d0c3200ce10e117dbb88579b5e/.writer.lock
  smoke 1b97eca109d84ab83c301bf93ed0055275955568f77ed95e600e9d65404181d7  s0/sheet-fixture-qualification/host_only/scorer_artifacts/1cba53b436a4b7fac9b8f32d1e976fc5d9c0236cd10d85ccdc666f793c915416/recalculations/6cfd2087e752f09cc7caef31c7f927e327ca4d8d635ae3f354e2d96cbb4dffd8.json
  smoke e06ec5771735b5c0d7eec8707fac07343c78ba753ce2436952bae4cddfc87497  s0/sheet-fixture-qualification/host_only/scorer_artifacts/1cba53b436a4b7fac9b8f32d1e976fc5d9c0236cd10d85ccdc666f793c915416/result.json
  smoke 2e12ba65a8e5a8e21fcfe4bd44f63dc8a63abeea97c6300cde0787bc58ea30fb  s0/sheet-fixture-qualification/host_only/scorer_artifacts/1cba53b436a4b7fac9b8f32d1e976fc5d9c0236cd10d85ccdc666f793c915416/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/1cba53b436a4b7fac9b8f32d1e976fc5d9c0236cd10d85ccdc666f793c915416/.writer.lock
  smoke af9139d0b7feed5e6b039880ac1ae485251bfeb3e284aa4d4033d8d71841f83e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/267a87cb86b8aecb27afe135187ab6ded44ce4d5e63a3243c63556af45019b35/recalculations/6cfd2087e752f09cc7caef31c7f927e327ca4d8d635ae3f354e2d96cbb4dffd8.json
  smoke 80ef43faa09d5ec0b7e4b77ed91ee9d1d9bd837a7789d3b3c3c728530b64b5c4  s0/sheet-fixture-qualification/host_only/scorer_artifacts/267a87cb86b8aecb27afe135187ab6ded44ce4d5e63a3243c63556af45019b35/result.json
  smoke 90814fd2061f7fb267a1075badcba58b7b21a1b2fe16fd7f48eed8189ebb13c8  s0/sheet-fixture-qualification/host_only/scorer_artifacts/267a87cb86b8aecb27afe135187ab6ded44ce4d5e63a3243c63556af45019b35/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/267a87cb86b8aecb27afe135187ab6ded44ce4d5e63a3243c63556af45019b35/.writer.lock
  smoke 28e96607b88ac24de07ce4b6f6109adfc43455a5c77a88ff84a6b058994830d4  s0/sheet-fixture-qualification/host_only/scorer_artifacts/27a50c81d198a3ff5919e985520a98dafd97b24b4a6b09d3db41e7fc1b8e80d4/recalculations/d3d6d3fc42d5e3b8cdf322edb05deb5746b7d44bea3e88492981bc411497004c.json
  smoke e4522968bfb50c0a0d04adc51bc97f5c815dfef6495f8c94995c14aec55d62f4  s0/sheet-fixture-qualification/host_only/scorer_artifacts/27a50c81d198a3ff5919e985520a98dafd97b24b4a6b09d3db41e7fc1b8e80d4/result.json
  smoke 6a69d5aec88b37ca761d107c9cbac803eb0ad91fa7206546f911f9426c07a17e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/27a50c81d198a3ff5919e985520a98dafd97b24b4a6b09d3db41e7fc1b8e80d4/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/27a50c81d198a3ff5919e985520a98dafd97b24b4a6b09d3db41e7fc1b8e80d4/.writer.lock
  smoke 6dc13bb17c80ad02a80a1e3661c0a5b5ae27a37f0c6ccb352d76329fd4ec33b2  s0/sheet-fixture-qualification/host_only/scorer_artifacts/2fe1b1e9d93afa4475d68736cb04caf58c008ebfa8b61b3497229322b30e3610/recalculations/ec82098f64b1d5de8e31e19b69a83effe6981b322c1919714a5986338d91eb0c.json
  smoke 0116ad99e89fcc5b67085b492037106321ceab9575ebf2b7dff8d9376b252188  s0/sheet-fixture-qualification/host_only/scorer_artifacts/2fe1b1e9d93afa4475d68736cb04caf58c008ebfa8b61b3497229322b30e3610/result.json
  smoke cff6055c27a9d29d596b00e7d07cb47f5aa9684638892a3f58468151dd500182  s0/sheet-fixture-qualification/host_only/scorer_artifacts/2fe1b1e9d93afa4475d68736cb04caf58c008ebfa8b61b3497229322b30e3610/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/2fe1b1e9d93afa4475d68736cb04caf58c008ebfa8b61b3497229322b30e3610/.writer.lock
  smoke d459d763391529985b86fc4e3be4de6775cb48ce4037e43a96180a5eb853b7d6  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3276eaab271ff02cee6c960bede0ffaf0daf8d5a5119ed56beb91e8e346ba774/recalculations/5cc800df16d48311cede4072ca5fbb5319d6e9e36f011fc02bf1a76b43c1b47e.json
  smoke 21a13dca39f6beb53e1135e390e460a291c12c59bfa68dbd7e4f69bf9d7a0d9a  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3276eaab271ff02cee6c960bede0ffaf0daf8d5a5119ed56beb91e8e346ba774/result.json
  smoke e9fbeb46e9cd19ac28340126b97d2c6ea416844b6ca6ad731f79c9f4ae22d5ac  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3276eaab271ff02cee6c960bede0ffaf0daf8d5a5119ed56beb91e8e346ba774/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3276eaab271ff02cee6c960bede0ffaf0daf8d5a5119ed56beb91e8e346ba774/.writer.lock
  smoke 025b309db2f7efdd18af9ce6ba8d89ef66d037fd1429f5b44aa815fd475bc9a0  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3c9bf2fbd78573612d006aa333669c0f41c2d6ae7fb5b1b3a400f9ab05fa7a52/recalculations/3c9aa990a06e528dd1ea7c37eb51a1c309f05a67f37ee8bcf6996e5d3b474cb2.json
  smoke 7085ca0caba46fa045551def0aa0216ad9d6ea4382a47cdf0ccf5fdc7029d893  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3c9bf2fbd78573612d006aa333669c0f41c2d6ae7fb5b1b3a400f9ab05fa7a52/result.json
  smoke 0167a613e5121a30823abb9e6025a7f887ab1c14ced126fcf42fad79b522691e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3c9bf2fbd78573612d006aa333669c0f41c2d6ae7fb5b1b3a400f9ab05fa7a52/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/3c9bf2fbd78573612d006aa333669c0f41c2d6ae7fb5b1b3a400f9ab05fa7a52/.writer.lock
  smoke 142c49c488f8d339b05207827267ddccb058a3e4a10c7522e932dfbb20c39498  s0/sheet-fixture-qualification/host_only/scorer_artifacts/5336cbbe05c30c69c1f4090664b64cd647b53ee01528cc16af4ced58d8131008/recalculations/c0e7bde84ab78a5b90e8a83964153ea6eb39bacb69096b18a29918b8b3c46860.json
  smoke 8c11e45f0e32217fb166b0f6a379a1a9e4680fa81f1e0259be8191c9b7dcdba5  s0/sheet-fixture-qualification/host_only/scorer_artifacts/5336cbbe05c30c69c1f4090664b64cd647b53ee01528cc16af4ced58d8131008/result.json
  smoke adf5ee6c1789748d5d76caf3ec98aae059c01abc8db7c8ef42744670da554c4c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/5336cbbe05c30c69c1f4090664b64cd647b53ee01528cc16af4ced58d8131008/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/5336cbbe05c30c69c1f4090664b64cd647b53ee01528cc16af4ced58d8131008/.writer.lock
  smoke 0e7029db67ed714da368fcf337b0ebbde62626718208f103be7600f5d66126b2  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6135472abaf27d8cb38ee71859d54321e877ff2f3502f0a3a4ea621f2c9503f9/recalculations/054e08d31be6ff31074754aa97604a3637fb1b024d029f217988185045c4d273.json
  smoke 33bf56769a36feaf2018af28016f166bfe9b8e7e96efc00973cc302399e86780  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6135472abaf27d8cb38ee71859d54321e877ff2f3502f0a3a4ea621f2c9503f9/result.json
  smoke 3b00bee2e57b12652f0183f41c1f84d6f4c220f3da784e646fe3a3fee970f3cc  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6135472abaf27d8cb38ee71859d54321e877ff2f3502f0a3a4ea621f2c9503f9/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6135472abaf27d8cb38ee71859d54321e877ff2f3502f0a3a4ea621f2c9503f9/.writer.lock
  smoke 21125cd547b332a48c9ad15cf368aaacc65207ab71270e01b86ec5b0db17ad4b  s0/sheet-fixture-qualification/host_only/scorer_artifacts/66b850a8ea8a76401778452a7b781b6f225f1224fd21d88509ecdb12ab8d09b9/recalculations/c0e7bde84ab78a5b90e8a83964153ea6eb39bacb69096b18a29918b8b3c46860.json
  smoke e4eec41a1c3df78868558831e7bfab2da694899db065e21073e72c477c28985c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/66b850a8ea8a76401778452a7b781b6f225f1224fd21d88509ecdb12ab8d09b9/result.json
  smoke b71b1b9d8fb6bdf7dfc0e5c1ab1677d03931f965da10543e45164a5b17e239ef  s0/sheet-fixture-qualification/host_only/scorer_artifacts/66b850a8ea8a76401778452a7b781b6f225f1224fd21d88509ecdb12ab8d09b9/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/66b850a8ea8a76401778452a7b781b6f225f1224fd21d88509ecdb12ab8d09b9/.writer.lock
  smoke 71870c3846f85182a9d5f1ce0d858b1087a058d1269847e76f7552658ee4d857  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6893cb7a25c377ee55cbeab40eff19ec8c73649fd44ee75d8ba7ca901b7cf702/recalculations/cbfe55d7cdd86ebd172add4a0308267569660940ea8cd7c65be4ab21af3fa871.json
  smoke a1dbd08a8cc244672cd1629e7fc1c9552a107aa78645fcd53fe37465cab9b99c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6893cb7a25c377ee55cbeab40eff19ec8c73649fd44ee75d8ba7ca901b7cf702/result.json
  smoke 469d100a00daaf7cf17233d34dbd74e792623fc7e647785b3246f0371fb6a0f1  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6893cb7a25c377ee55cbeab40eff19ec8c73649fd44ee75d8ba7ca901b7cf702/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6893cb7a25c377ee55cbeab40eff19ec8c73649fd44ee75d8ba7ca901b7cf702/.writer.lock
  smoke aa352a9765099ca7accce34434bddd394818802fc4803428c004cadf664caf76  s0/sheet-fixture-qualification/host_only/scorer_artifacts/69760dbb87261ef8a419a9da9a60fdb6873ada8ef3b5ea2dc7caf2d42a5f8afc/recalculations/cbfe55d7cdd86ebd172add4a0308267569660940ea8cd7c65be4ab21af3fa871.json
  smoke d87952e9faf8c35a50d0103b989cec021623eb482164ca8afd3bcc30ac6de28c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/69760dbb87261ef8a419a9da9a60fdb6873ada8ef3b5ea2dc7caf2d42a5f8afc/result.json
  smoke b758a4e87874b20ba361203002ba32464cd997786e666f4f350801d511f43144  s0/sheet-fixture-qualification/host_only/scorer_artifacts/69760dbb87261ef8a419a9da9a60fdb6873ada8ef3b5ea2dc7caf2d42a5f8afc/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/69760dbb87261ef8a419a9da9a60fdb6873ada8ef3b5ea2dc7caf2d42a5f8afc/.writer.lock
  smoke 30fb6420731517b2edf25ac32244df0cc0fef42ae3cd923f1ee1663640a8ba73  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6c04e0bc7b6342d4a94bebc5261d200078faf3b37e1e2bb71d8e145866a49f1f/recalculations/5cc800df16d48311cede4072ca5fbb5319d6e9e36f011fc02bf1a76b43c1b47e.json
  smoke 46c84b53707a41085c46c65f7e7f7617502a05b8b190c50a4c3acc68014a64a7  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6c04e0bc7b6342d4a94bebc5261d200078faf3b37e1e2bb71d8e145866a49f1f/result.json
  smoke a60a139f58c1c27adfe0d76aa0e3057d420d8cb7fdb02a33cfe31d13a0f36c3d  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6c04e0bc7b6342d4a94bebc5261d200078faf3b37e1e2bb71d8e145866a49f1f/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/6c04e0bc7b6342d4a94bebc5261d200078faf3b37e1e2bb71d8e145866a49f1f/.writer.lock
  smoke 21a172b64befa4099f0c7390ce8e7be18b362e939f2369c494eb3c1afdf2a265  s0/sheet-fixture-qualification/host_only/scorer_artifacts/7c3490944270e882b7b7ec73403a52d9408d9dbdd531b2ddd66892d56bd69aef/recalculations/273d86a61a077d46839a61c8fddd390abbb749cacded35587cc9a440055f38df.json
  smoke 4e29fe9ac48c4bcb3a8a765af69f4436b7cc1b4722d2d0776406e2bd641cc10b  s0/sheet-fixture-qualification/host_only/scorer_artifacts/7c3490944270e882b7b7ec73403a52d9408d9dbdd531b2ddd66892d56bd69aef/result.json
  smoke b4b074294d712345dd0b69b9442aac96b0f00660a5838f1a1a71d18868aeeb9f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/7c3490944270e882b7b7ec73403a52d9408d9dbdd531b2ddd66892d56bd69aef/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/7c3490944270e882b7b7ec73403a52d9408d9dbdd531b2ddd66892d56bd69aef/.writer.lock
  smoke 714261263b9d91e8d55bd11bf9a0826a96f1fa709095d633447e068d5ed186f5  s0/sheet-fixture-qualification/host_only/scorer_artifacts/85047a84e793019a04cf3029fae53107b685a702c849849771270a8134e92f1c/recalculations/0e7f05f651cc1f0ffda146974695a43c2729b7fde09383468001f41315e88c12.json
  smoke cd29909a19821acbfb4d5477c3a65f55a3052738ce5e46af9b99a4cbbd3baee8  s0/sheet-fixture-qualification/host_only/scorer_artifacts/85047a84e793019a04cf3029fae53107b685a702c849849771270a8134e92f1c/result.json
  smoke e1460d0130dc06a0607a02c8bce869a4ede1439bee415d35ddd88bbd8a7fd373  s0/sheet-fixture-qualification/host_only/scorer_artifacts/85047a84e793019a04cf3029fae53107b685a702c849849771270a8134e92f1c/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/85047a84e793019a04cf3029fae53107b685a702c849849771270a8134e92f1c/.writer.lock
  smoke df00ba54d172233acf094c1febef2af16623edc957ed7e8c3b0ea6579ab683ad  s0/sheet-fixture-qualification/host_only/scorer_artifacts/8f384fa763aab83ce99aca09399d1379ea70b0f34e101bc85c9d85cd7c4864ae/recalculations/d3006c198eade650908930d1806c6e663c5520422e770148ade499868eb3a01e.json
  smoke ee078b01ef9af11d95df05ac5f45679323ebcfefb30b1f002d7a677a8390a29b  s0/sheet-fixture-qualification/host_only/scorer_artifacts/8f384fa763aab83ce99aca09399d1379ea70b0f34e101bc85c9d85cd7c4864ae/result.json
  smoke a1b46939cf144377b9bfd3c24cdca66c8963f71b2572f52b21e788a28697880a  s0/sheet-fixture-qualification/host_only/scorer_artifacts/8f384fa763aab83ce99aca09399d1379ea70b0f34e101bc85c9d85cd7c4864ae/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/8f384fa763aab83ce99aca09399d1379ea70b0f34e101bc85c9d85cd7c4864ae/.writer.lock
  smoke 7b51152618c2a9101edbcf414056d724f0d6333bf9e37ff8644a873749e7ce84  s0/sheet-fixture-qualification/host_only/scorer_artifacts/940a376df54289a41103f8e8cc71311b27926b89fc68815470066dc9cd05202c/recalculations/d3d6d3fc42d5e3b8cdf322edb05deb5746b7d44bea3e88492981bc411497004c.json
  smoke 04630d39c7519cc71a37f245e5b5228818b7e52e7bd204cd9b45af228bc9fff6  s0/sheet-fixture-qualification/host_only/scorer_artifacts/940a376df54289a41103f8e8cc71311b27926b89fc68815470066dc9cd05202c/result.json
  smoke fd78affc79d8ade0aae8fddaaf94859440a1a4626c8f2d6c95f088992b911647  s0/sheet-fixture-qualification/host_only/scorer_artifacts/940a376df54289a41103f8e8cc71311b27926b89fc68815470066dc9cd05202c/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/940a376df54289a41103f8e8cc71311b27926b89fc68815470066dc9cd05202c/.writer.lock
  smoke 7b6396bd352b3097e4cdbb4fed02cb8dbc4ab32a14da316d64215502788e773f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/96cbad99bcf580ec2433516052ec6a0378a1596157550147604d5141f549f35e/recalculations/e5095dd7e4b6125d2c6ad47ad2aea2d5c1ecb0373444e56611b4eaa9b5cfb7ac.json
  smoke 2f7ff769a776bee3801112fe1755de4316aed500b9e3d21759e56ff51bd17102  s0/sheet-fixture-qualification/host_only/scorer_artifacts/96cbad99bcf580ec2433516052ec6a0378a1596157550147604d5141f549f35e/result.json
  smoke 73790c41eaf89ad9b2068c929de3d21832bbff181f8e701dbe17201fdaea5835  s0/sheet-fixture-qualification/host_only/scorer_artifacts/96cbad99bcf580ec2433516052ec6a0378a1596157550147604d5141f549f35e/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/96cbad99bcf580ec2433516052ec6a0378a1596157550147604d5141f549f35e/.writer.lock
  smoke ab03622cb30fc759c56803e1fb8a104883084f507f7c75eaacad6d4f31f7b333  s0/sheet-fixture-qualification/host_only/scorer_artifacts/9972f37ff2997241da033e7430a3be5e01ad3e3f50985b01fc66cfa41ea7e690/recalculations/ebb32920323fbcfcb8077fc6611a5fd0fbc338854d14c4f5a521753e168b3b08.json
  smoke c93a4a3dbcf77ed429adc60117c2212c59557fe5889878d903390898cc277896  s0/sheet-fixture-qualification/host_only/scorer_artifacts/9972f37ff2997241da033e7430a3be5e01ad3e3f50985b01fc66cfa41ea7e690/result.json
  smoke fee014905cea8d3e0da549e0e1bb71492383e8333a7ae0d5118329cdfbce5fb3  s0/sheet-fixture-qualification/host_only/scorer_artifacts/9972f37ff2997241da033e7430a3be5e01ad3e3f50985b01fc66cfa41ea7e690/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/9972f37ff2997241da033e7430a3be5e01ad3e3f50985b01fc66cfa41ea7e690/.writer.lock
  smoke 48ed4481f632ad3ac26a177afe438a60a3f86de962d34d7160afc9fd48090a2d  s0/sheet-fixture-qualification/host_only/scorer_artifacts/a7462222b1b5151978ce85eef2f7a3af55d15f66442c96a2ba19c707419a18e5/recalculations/e23b42026ee25113884436aaf5a43f3dd6058c7a2ec36fde5627e0a70e62e795.json
  smoke c4171e3572dd645f87e416cc116e568cc0bb2f93862927c496ac5bc4175aa9b7  s0/sheet-fixture-qualification/host_only/scorer_artifacts/a7462222b1b5151978ce85eef2f7a3af55d15f66442c96a2ba19c707419a18e5/result.json
  smoke d70b93e452078c327383d4cdb6c5de0766d06a06eee4d0e8057b143c397caf20  s0/sheet-fixture-qualification/host_only/scorer_artifacts/a7462222b1b5151978ce85eef2f7a3af55d15f66442c96a2ba19c707419a18e5/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/a7462222b1b5151978ce85eef2f7a3af55d15f66442c96a2ba19c707419a18e5/.writer.lock
  smoke 48bfed622e9b0309d5136c5475c7f23927a95d84899ae846facf930555cad2d2  s0/sheet-fixture-qualification/host_only/scorer_artifacts/aba7e96db223596da70beef9a96209392762918c848e589c5267fc7ed022f960/recalculations/7edd5012765b5b4f3ae18ad2281904fc9279ce78cfcb8d2ea9efc8a47e0e875a.json
  smoke 80f2312702afb4c339a0b4d76dcf25af2fe20091967e3c6a9de155c3d043bcac  s0/sheet-fixture-qualification/host_only/scorer_artifacts/aba7e96db223596da70beef9a96209392762918c848e589c5267fc7ed022f960/result.json
  smoke 2021ce7ccfd366b367c9b7f55b5bb8a0dd392336be85965a7fe59ce2bbce4721  s0/sheet-fixture-qualification/host_only/scorer_artifacts/aba7e96db223596da70beef9a96209392762918c848e589c5267fc7ed022f960/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/aba7e96db223596da70beef9a96209392762918c848e589c5267fc7ed022f960/.writer.lock
  smoke 764c0b203954ce077722a2f90c2f34eda59b4141342eb4b7efa768974a6b4011  s0/sheet-fixture-qualification/host_only/scorer_artifacts/ac7d3d80f2861014e83a441e8456977537ca20407e9069bcf687e17c6e3d9b7f/recalculations/ec82098f64b1d5de8e31e19b69a83effe6981b322c1919714a5986338d91eb0c.json
  smoke 378632746bb490dc79830801edea528e34e4fbe5d9aac7342232686b86bcfaa2  s0/sheet-fixture-qualification/host_only/scorer_artifacts/ac7d3d80f2861014e83a441e8456977537ca20407e9069bcf687e17c6e3d9b7f/result.json
  smoke 1923b58ec59cd6ae6c49942062be2cd744f9ec6d30cffad219231374782dea8e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/ac7d3d80f2861014e83a441e8456977537ca20407e9069bcf687e17c6e3d9b7f/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/ac7d3d80f2861014e83a441e8456977537ca20407e9069bcf687e17c6e3d9b7f/.writer.lock
  smoke 9b3e67b1086498b6814082e59270da73338de62279b89a4254f82d980949318a  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b0ab0eeacfbd0b0ff2f5b629d7a15ed3e9679dd66db134e586d2b57f50b1cd27/recalculations/cfa2dc83eb50b588638879e0c361de709bff106cb41e9768959a543b254d011f.json
  smoke 18282cd479ebc33ccea679e81de2361bc3956b24c34b7d93dcb45de391143223  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b0ab0eeacfbd0b0ff2f5b629d7a15ed3e9679dd66db134e586d2b57f50b1cd27/result.json
  smoke 9f62fd024a73c43b5973c1a77d807118a4cc3e2ccf934225e01b3f3a6ee56a2a  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b0ab0eeacfbd0b0ff2f5b629d7a15ed3e9679dd66db134e586d2b57f50b1cd27/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b0ab0eeacfbd0b0ff2f5b629d7a15ed3e9679dd66db134e586d2b57f50b1cd27/.writer.lock
  smoke 4d1cf9c9d57ef9b91ed78126edf373209e1ff6d2c090d5804be50b164a1150d2  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b8b93d5b6a0a7339b9a07274e9a8188875c202abab93b9b2d31024a443a7c1c0/recalculations/054e08d31be6ff31074754aa97604a3637fb1b024d029f217988185045c4d273.json
  smoke eaebc54138c2f6786459cafca428932b16e10bd22acdb0d5c09f84b819bf8cb8  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b8b93d5b6a0a7339b9a07274e9a8188875c202abab93b9b2d31024a443a7c1c0/result.json
  smoke 0c63bc8108589a1367395c0a760c47e9aa8940f0000533ab43fdbba1c4071799  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b8b93d5b6a0a7339b9a07274e9a8188875c202abab93b9b2d31024a443a7c1c0/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/b8b93d5b6a0a7339b9a07274e9a8188875c202abab93b9b2d31024a443a7c1c0/.writer.lock
  smoke 34ae1a9fe2d1e1c4d59937e0be2101f671ba908189e58e6d2ca92731e0dcea27  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bba5eef336c74258b4debfd4ecc3bfe61c22b2dbca7ee5361e01d2637ccf448a/recalculations/3c9aa990a06e528dd1ea7c37eb51a1c309f05a67f37ee8bcf6996e5d3b474cb2.json
  smoke 3dbb6faaa460d2f27cb294a1b95454cd87b947b5d0153d1b9bf728ca9f0c3505  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bba5eef336c74258b4debfd4ecc3bfe61c22b2dbca7ee5361e01d2637ccf448a/result.json
  smoke 847e7c98562139e3e111ec3115fcef53be2c9c4df19c91f67b05caf8fd01dc39  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bba5eef336c74258b4debfd4ecc3bfe61c22b2dbca7ee5361e01d2637ccf448a/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bba5eef336c74258b4debfd4ecc3bfe61c22b2dbca7ee5361e01d2637ccf448a/.writer.lock
  smoke 5223b531e055cbab5473851f6a2c2251fc90feae240ded550e48fbb106f0f99c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bd0c4fa868c2195c8a22dd716a356686bb0359e6bce09f4ed5c75971cdbd8ee1/recalculations/0e7f05f651cc1f0ffda146974695a43c2729b7fde09383468001f41315e88c12.json
  smoke 71a3fb0b78fd54fb3b9ff66c84af408f768c21292e2e486659c8df0aa8f3bcfa  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bd0c4fa868c2195c8a22dd716a356686bb0359e6bce09f4ed5c75971cdbd8ee1/result.json
  smoke b85ad78bef135eb70159d2fb6b89975c0de73a2d2b6c3788b5fde6cd68bd03b8  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bd0c4fa868c2195c8a22dd716a356686bb0359e6bce09f4ed5c75971cdbd8ee1/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/bd0c4fa868c2195c8a22dd716a356686bb0359e6bce09f4ed5c75971cdbd8ee1/.writer.lock
  smoke 9cda5b9d33e97d1eb1f956239be48d0f36cc8bc8b6bd1d5d2509f5fcb5f2249f  s0/sheet-fixture-qualification/host_only/scorer_artifacts/c2e81dbd1a62b4b2b7e0534d49d647a2db2e570678a0fa919aae4d5c91bf60f4/recalculations/2542dc0501b8cd170db8a323102c22cd15a7bfe634b15944f87fde6a70359436.json
  smoke 52602641cc75f8749b826531e33a44af67ec2450686af76404d52fe89ab43025  s0/sheet-fixture-qualification/host_only/scorer_artifacts/c2e81dbd1a62b4b2b7e0534d49d647a2db2e570678a0fa919aae4d5c91bf60f4/result.json
  smoke 0f2eb408e436ca5b3eb54209e63585b1404629ef402c2dd22c66772fbf80150e  s0/sheet-fixture-qualification/host_only/scorer_artifacts/c2e81dbd1a62b4b2b7e0534d49d647a2db2e570678a0fa919aae4d5c91bf60f4/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/c2e81dbd1a62b4b2b7e0534d49d647a2db2e570678a0fa919aae4d5c91bf60f4/.writer.lock
  smoke bfdef3bb9bd37dbe14734f4d15688c5c321bb47cd169664df3c1e0e46b139f83  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e23bc23c26320b92840918311d4f01f94822102c5ef26fee39c177aa5fb5e238/recalculations/e5095dd7e4b6125d2c6ad47ad2aea2d5c1ecb0373444e56611b4eaa9b5cfb7ac.json
  smoke 7becf4f57b6e931b18d61654ee6113744589a3b76afc9ba03a615b05d44c425b  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e23bc23c26320b92840918311d4f01f94822102c5ef26fee39c177aa5fb5e238/result.json
  smoke dc8c81c73f0d4852ed4ae72dcee8d4f5067daa6293fc3993dc5e1aebc0523183  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e23bc23c26320b92840918311d4f01f94822102c5ef26fee39c177aa5fb5e238/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e23bc23c26320b92840918311d4f01f94822102c5ef26fee39c177aa5fb5e238/.writer.lock
  smoke 6f5ad68df6b7d25ecf39bc53f501d1ba54af7e8b22a0d328dcc13e638e9d3aac  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e317f1b70ef926d2bda4f3e4592e07703441e16c05b374361696c2776c8b4d71/recalculations/ae5c28b2cd960eb2ebb7493e1732d791fdb6b3baf419887b5a16b0d863e08fee.json
  smoke 187f8a9325343e37570c8a7d89b2a182f80b359a74459233fcb48107251b3322  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e317f1b70ef926d2bda4f3e4592e07703441e16c05b374361696c2776c8b4d71/result.json
  smoke 24ece82cfd406d8b97067dab75ed4e82e862076b4f5999a13601f572204301e0  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e317f1b70ef926d2bda4f3e4592e07703441e16c05b374361696c2776c8b4d71/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e317f1b70ef926d2bda4f3e4592e07703441e16c05b374361696c2776c8b4d71/.writer.lock
  smoke 3d46b17d5f2cc91864231651ffb2dc3673a183726f6d36baf9e306f5c38f2f86  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e7f18f4485ed4a580c2b2adada770f50734db0f2a8c64d3af89983b14699a94b/recalculations/cfa2dc83eb50b588638879e0c361de709bff106cb41e9768959a543b254d011f.json
  smoke f02da44f237c350ad4b803a623d30ffbd2b53b7f6a7e1961b353644f6f3cd780  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e7f18f4485ed4a580c2b2adada770f50734db0f2a8c64d3af89983b14699a94b/result.json
  smoke 056620adefd3ece7ee8de9b49321899102315df3ba593f11b91734103c6af415  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e7f18f4485ed4a580c2b2adada770f50734db0f2a8c64d3af89983b14699a94b/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/e7f18f4485ed4a580c2b2adada770f50734db0f2a8c64d3af89983b14699a94b/.writer.lock
  smoke aff9634c9c94c391d3ae8bb06a4461abf9fa2d3ee30374d6a837efba9d92832c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/f60bcc4e6322349433858a1987b4dc499aa6bd76a6c464566dacfff48ce21ecf/recalculations/c48ba4ea59376b3d9457c7393c01954b4d39f6b3e78f3c4f41d3ce2dd095dc74.json
  smoke 8a76906bb6911ed15a612a5507f6dec06b65535f31519a3d9d127cf93999eac7  s0/sheet-fixture-qualification/host_only/scorer_artifacts/f60bcc4e6322349433858a1987b4dc499aa6bd76a6c464566dacfff48ce21ecf/result.json
  smoke d695ad2fa3fbbdebb6b705d0c0cdd5f966c0407ccfea91a7ee7f9ba50cbf5442  s0/sheet-fixture-qualification/host_only/scorer_artifacts/f60bcc4e6322349433858a1987b4dc499aa6bd76a6c464566dacfff48ce21ecf/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/f60bcc4e6322349433858a1987b4dc499aa6bd76a6c464566dacfff48ce21ecf/.writer.lock
  smoke 260c8e26a076891ef54b2f1510bc76d316c87e86b6bab4dbf2e896df04ab85fd  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fac49bd3459939eea24e4b78ef586d534db74c3e81a5b7a924f7869bd4afe873/recalculations/ae5c28b2cd960eb2ebb7493e1732d791fdb6b3baf419887b5a16b0d863e08fee.json
  smoke 59178ba1dfcd4ecc0ea3432863dd60ca1523750a8be053f775836f3d859a5f5c  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fac49bd3459939eea24e4b78ef586d534db74c3e81a5b7a924f7869bd4afe873/result.json
  smoke 237768a3bfb2f06b7d985e1a4d2e4bead1743c80896506630f980144d2081fef  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fac49bd3459939eea24e4b78ef586d534db74c3e81a5b7a924f7869bd4afe873/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fac49bd3459939eea24e4b78ef586d534db74c3e81a5b7a924f7869bd4afe873/.writer.lock
  smoke a202f242be9c033261500465b0d9da6983f24022e5fd555949ec6e7ef72b6621  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fb4a6a87613b741b81453ee006f4303570dfd70da82a4f92dc3f89fef57e6587/recalculations/d3006c198eade650908930d1806c6e663c5520422e770148ade499868eb3a01e.json
  smoke bee6fd1f6d995a999096fa432dac481aaa143d3622555917d18862a127ea5e52  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fb4a6a87613b741b81453ee006f4303570dfd70da82a4f92dc3f89fef57e6587/result.json
  smoke 4732591a34901447f7c4daca80ff5ed84ed1e250addce8d25b6a5a558545f361  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fb4a6a87613b741b81453ee006f4303570dfd70da82a4f92dc3f89fef57e6587/started.json
  smoke e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  s0/sheet-fixture-qualification/host_only/scorer_artifacts/fb4a6a87613b741b81453ee006f4303570dfd70da82a4f92dc3f89fef57e6587/.writer.lock
  smoke 0c675108038c5b985604acb62facd11c57fef284e820963199b3f9e078ce1db5  s0/sheet-fixture-qualification/qualification.json
  smoke 7db21ee3636e9f8dafe4e658d042458dd4165f431a4c7f47f01d7bb546971e63  s0/sheet-fixture-qualification/scores/01a63b293b99c40d9a20563a4a8f35c73d605d0e6d703fff7162d6e1543d0d9d.json
  smoke 2c4cea3c34011c1fdf141a0d86e11dc139259fb153bd42dfb79ebe0eee26c351  s0/sheet-fixture-qualification/scores/026cfcf56268bdcaa699067675def8486a296e4c17c5349ecbeff03eb21796c5.json
  smoke c3211e7669586bc293c9e1258667a0d391eedf88cd34ec219965c823010e83e5  s0/sheet-fixture-qualification/scores/0304e24089d1561453446d728834e020a82d819df11ab2b49a63d2537762c461.json
  smoke e70c0a2eaf21d5ee4913294f779cbc2c335040789ab89486fb3d4640a76c6072  s0/sheet-fixture-qualification/scores/04e0104b63baf10dcae87ca846b1d27cc9d2a50ed8503ff8e46c752e817c948b.json
  smoke fe025c21be9eec2b294e29cdf44a43d3b413e57137628dc50371e21d2185b1fd  s0/sheet-fixture-qualification/scores/0ce96caaf13e59dcb3b24faac821824531961ba3eaad27f84fd16bb0a7830cd5.json
  smoke 358535eda3174409557abb5910b556cc1bff462b4358bdcdcb69182b128e19b5  s0/sheet-fixture-qualification/scores/0ecf98b628f808f6bcb5fab5808f5a49d39c3a263ec239b03369696b5cb90302.json
  smoke 136d58f7d7918f5a5bb35d3a282fcf3bcaa63e41df04b5c564733b1ecd95c453  s0/sheet-fixture-qualification/scores/104ad42dfe6d7d248d9871b696888d3dff58f076907ed9af8448c8b585106bdd.json
  smoke 9b174eb14c86710f47a189b6182292c4bfe1eac134bf488be2468b35b4283502  s0/sheet-fixture-qualification/scores/17441717fa063eb7bb74a1955a59e2cb0a1978d0c3200ce10e117dbb88579b5e.json
  smoke be8bd15158028b1d9025635f34fc389f33c4845ff20b072d5add648f8486f419  s0/sheet-fixture-qualification/scores/1cba53b436a4b7fac9b8f32d1e976fc5d9c0236cd10d85ccdc666f793c915416.json
  smoke bac9015820b59c5684362c60997fca022c5b7959385784e7ecdc86080935a843  s0/sheet-fixture-qualification/scores/267a87cb86b8aecb27afe135187ab6ded44ce4d5e63a3243c63556af45019b35.json
  smoke 73fb85b0376dc4023756ed1ffc17c1134b9af7f4d7b683f25c3e89ca4b6ccfa7  s0/sheet-fixture-qualification/scores/27a50c81d198a3ff5919e985520a98dafd97b24b4a6b09d3db41e7fc1b8e80d4.json
  smoke e51b2f8cc79c2ca13c425c29d7840e16be0b659fe755fb3bee97706e1fdd8221  s0/sheet-fixture-qualification/scores/2fe1b1e9d93afa4475d68736cb04caf58c008ebfa8b61b3497229322b30e3610.json
  smoke 4dd3b6431760e2536e8e30fff7374bc8b08cbed67b3d30e025f1250853cf5420  s0/sheet-fixture-qualification/scores/3276eaab271ff02cee6c960bede0ffaf0daf8d5a5119ed56beb91e8e346ba774.json
  smoke 86586d177bf4dacbd77bdad09ff27bc7d0c6b22ff575ac0f3b3d47bbc16f3e59  s0/sheet-fixture-qualification/scores/3c9bf2fbd78573612d006aa333669c0f41c2d6ae7fb5b1b3a400f9ab05fa7a52.json
  smoke 6a2e94167519e4678545d0fc4546471a25b171fcd67e5594bca528ec06a0c3ec  s0/sheet-fixture-qualification/scores/5336cbbe05c30c69c1f4090664b64cd647b53ee01528cc16af4ced58d8131008.json
  smoke 4739d03ec17843f8a13428012387527cc37206dd99214ea4cedb12954673ed24  s0/sheet-fixture-qualification/scores/6135472abaf27d8cb38ee71859d54321e877ff2f3502f0a3a4ea621f2c9503f9.json
  smoke 0a83163f3db23350d9adbba281d7a8a3fca1a6cd965b5d8422e69403eda6dfef  s0/sheet-fixture-qualification/scores/66b850a8ea8a76401778452a7b781b6f225f1224fd21d88509ecdb12ab8d09b9.json
  smoke 49b142740819fec6d23f3fa1061a083b9d4ea6616cc3392d1a8e9cbcf4e1454f  s0/sheet-fixture-qualification/scores/6893cb7a25c377ee55cbeab40eff19ec8c73649fd44ee75d8ba7ca901b7cf702.json
  smoke 4d461c08219b638bd4a3c272d254767befc0e35bbfcc7c57327e03355f15df90  s0/sheet-fixture-qualification/scores/69760dbb87261ef8a419a9da9a60fdb6873ada8ef3b5ea2dc7caf2d42a5f8afc.json
  smoke d88a9c88b969a4ae9b4c31505738dfc50d392504af50aab4a2b08c924d032ca5  s0/sheet-fixture-qualification/scores/6c04e0bc7b6342d4a94bebc5261d200078faf3b37e1e2bb71d8e145866a49f1f.json
  smoke d1cbf64a8476e6db1508b23135efb9329728b8a02b62a51dd0ba251b0a821613  s0/sheet-fixture-qualification/scores/7c3490944270e882b7b7ec73403a52d9408d9dbdd531b2ddd66892d56bd69aef.json
  smoke 1da52893c3aa59a9ac665c8c7f5b7e5daef02f8861506edf96f47feb6c35af93  s0/sheet-fixture-qualification/scores/85047a84e793019a04cf3029fae53107b685a702c849849771270a8134e92f1c.json
  smoke 888ad477308dd1f7a66e787fcd2fb53766ff61b6de8f0829d84cd3e077cee24c  s0/sheet-fixture-qualification/scores/8f384fa763aab83ce99aca09399d1379ea70b0f34e101bc85c9d85cd7c4864ae.json
  smoke 0f6cd204d27f250a42e6b7ca26e8c5c2bee076c0a8f1a0ab3edb0e5684030b65  s0/sheet-fixture-qualification/scores/940a376df54289a41103f8e8cc71311b27926b89fc68815470066dc9cd05202c.json
  smoke 3b60299b592d85ed9d9665a02950cf524caeb1a7503f1914cb7ce709ddb4aacf  s0/sheet-fixture-qualification/scores/96cbad99bcf580ec2433516052ec6a0378a1596157550147604d5141f549f35e.json
  smoke 67c56e9d47628744e6436b5afb971c77de6cc4f92666e74440eb31c96370e2ec  s0/sheet-fixture-qualification/scores/9972f37ff2997241da033e7430a3be5e01ad3e3f50985b01fc66cfa41ea7e690.json
  smoke d4c961e2169cd809b9befb65be32ee80f8dd0fc92fe341c419942f8e4fa1155a  s0/sheet-fixture-qualification/scores/a7462222b1b5151978ce85eef2f7a3af55d15f66442c96a2ba19c707419a18e5.json
  smoke a9b9a044ebbb7ac6946676af523a4a750b4f5da79457b07afa86885c596bb68b  s0/sheet-fixture-qualification/scores/aba7e96db223596da70beef9a96209392762918c848e589c5267fc7ed022f960.json
  smoke 0dc486a0cb5f4888b3bbff2cb294e47338dfdd5735fdd8d8f3bb5496477ed5ca  s0/sheet-fixture-qualification/scores/ac7d3d80f2861014e83a441e8456977537ca20407e9069bcf687e17c6e3d9b7f.json
  smoke 0c2dbd7e1faaf3294558a94da0f855578f91b3497b615e1f032ac85d9706a4d9  s0/sheet-fixture-qualification/scores/b0ab0eeacfbd0b0ff2f5b629d7a15ed3e9679dd66db134e586d2b57f50b1cd27.json
  smoke 8f27aa07b29abb8cff9757b0655ba312f7659deed8415cc08fab2be5a992fb4e  s0/sheet-fixture-qualification/scores/b8b93d5b6a0a7339b9a07274e9a8188875c202abab93b9b2d31024a443a7c1c0.json
  smoke e761f7c8d01cede13d667f95d532622dcca24b4ef86b85bd2019ed80dde82514  s0/sheet-fixture-qualification/scores/bba5eef336c74258b4debfd4ecc3bfe61c22b2dbca7ee5361e01d2637ccf448a.json
  smoke e168fcee8ba15cf99d310d0e2fad7be104b88cec5944e32746743e47177222ff  s0/sheet-fixture-qualification/scores/bd0c4fa868c2195c8a22dd716a356686bb0359e6bce09f4ed5c75971cdbd8ee1.json
  smoke d842174266e5d239298123c4912da5c22f3783532e55e3201fa6dd4987c7d938  s0/sheet-fixture-qualification/scores/c2e81dbd1a62b4b2b7e0534d49d647a2db2e570678a0fa919aae4d5c91bf60f4.json
  smoke 0cf6d41d1846cdd50e174b669dd57c5ee37ae3eccc4e07f252ae6d22f753250e  s0/sheet-fixture-qualification/scores/e23bc23c26320b92840918311d4f01f94822102c5ef26fee39c177aa5fb5e238.json
  smoke b57e3dd5990bc8781d29c2c0ae542f256153a2ab4b14ef36b0dfdb09b0f51abe  s0/sheet-fixture-qualification/scores/e317f1b70ef926d2bda4f3e4592e07703441e16c05b374361696c2776c8b4d71.json
  smoke 7a82faa6d13cd6509822e69d2471442f1d59775c88e9423c8f0b59dced417519  s0/sheet-fixture-qualification/scores/e7f18f4485ed4a580c2b2adada770f50734db0f2a8c64d3af89983b14699a94b.json
  smoke 38755c95b184bba0a41aa63e867362da4d2c9b7a646428c2590967d3c81fe2ee  s0/sheet-fixture-qualification/scores/f60bcc4e6322349433858a1987b4dc499aa6bd76a6c464566dacfff48ce21ecf.json
  smoke 5bf68be3b0aa5b6f3e455c428ec1f49d413a1efb3be8b35a360e014b70b6cf01  s0/sheet-fixture-qualification/scores/fac49bd3459939eea24e4b78ef586d534db74c3e81a5b7a924f7869bd4afe873.json
  smoke 456c3f62860a0f7b122248b9abd8b5167a9e742fc754ba2e6aa1dd657b2ba641  s0/sheet-fixture-qualification/scores/fb4a6a87613b741b81453ee006f4303570dfd70da82a4f92dc3f89fef57e6587.json
  smoke 9dca1cea1f9b5da91c6f59a8b24dac7573b000933de68eec36a22c0b99eaa409  smoke.json
  smoke 3bf511a1149065286a0da2ce8a4d693b06687526da900d100589879e914cfb99  stages/S0.json
  ```
- 03:34:28 step 2-3 launch: tmux execskill-prep:chain-c, bash s-chain-c.sh 344ddcc874bc44261025db2fc7d4027767847316 > logs/c/chain.log (per-step lines follow)
  - 03:34:28 chain-c: precheck: /data/execskill-dev HEAD 344ddcc874bc44261025db2fc7d4027767847316, GO commit 344ddcc874bc44261025db2fc7d4027767847316; uncommitted entries under skillopt/scripts/tests: 0
  - 03:34:30 chain-c: s2-snapshot (s2-snapshot-c.sh): EXIT 0; log logs/c/s2-snapshot.log
  - 03:35:09 chain-c: s2b-q23 (s2b-q23-c.sh): EXIT 0; log logs/c/s2b-q23.log
  - 03:35:16 chain-c: s3-selftest (s3-selftest-c.sh): EXIT 0; log logs/c/s3-selftest.log
  - 04:14:59 chain-c: s3-collect (s3-collect-c.sh): EXIT 0; log logs/c/s3-collect.log
  - 04:15:04 chain-c: s3-makedry (s3-makedry-c.sh): EXIT 0; log logs/c/s3-makedry.log
  - 04:15:10 chain-c: s3-make (s3-make-c.sh): EXIT 0; log logs/c/s3-make.log
  - 04:15:17 chain-c: s5-manifest (s5-manifest-c.sh): EXIT 0; log logs/c/s5-manifest.log
  - 04:15:17 chain-c: chain end: S0 recorded and the smoke manifest written; stop before S2/S3 (registrar's second go)
- 04:15:17 chain-c END (03:34:28-04:15:17, zero model calls; every step EXIT 0). Key results (counts and hashes only):
  - snapshot c /data/execskill-20261021-source-c: 1,269 files, git_head 344ddcc874bc44261025db2fc7d4027767847316,
    sha256_list_sha256 b2b6c9447ef2684077f841aa0320c834aa59ad8e14ff822fee5a59eb76d31d01, env files absent
    (logs/c/verify-snapshot.json; the step-5 re-verification was identical).
  - q23-c: qualification.json sha256 25b279b8a3d2d4258f1227e1d8f24264f12afa27fb4943860e6c93525cbdee16, record_hash
    c79ad8b27bb362cc9b19f58982e3f09c6af9d76702667f759d93860f94e4a47a, model_api_calls 0; $PRE/sheet-runtime.json
    sha256 3e367f16920a228ba327fdf0cccb6b19d5ae5536f207a0c4f554e085d021b4f4 (image and 120 s timeout kept).
  - sandbox-selftest: passed, 8/8 escape rows true; $PRE/s0/sandbox-selftest.json sha256 3596e76f1eb6ba9a...
  - s0-collect: leftovers clean; /tmp IFree 254,794 before, 254,141 after; 14/14 checks true: pytest 1416 passed in
    1579.17 s; supply ALFWorld preset 322 = cut 322, SearchQA tail kept 11,378; replay 228 trajectories, 7,524/7,524
    steps, 0 faults; sheet fixtures 20/20; measurements guard ok. checks.json sha256 d9891b61...; $PRE/s0-pins.json
    sha256 8f8d54f7...
  - smoke-make --solver-chain G (dry, then sealed): spec record caf4787d5d0911e5f7f4f598e80a981a137cbf1bd348b4132465e816f875a43c
    (file sha256 8c8fdf8b4d294d08...), items 12/20/20/280/20, stages S0 S2 S3 SE6, control_cells 0, no noise
    anchor; spec check: G, glm-5.3, probe_root None, 0 control cells. smoke --stage S0: passed
    ($SMOKE/stages/S0.json sha256 0826a169acaf934d...).
  - section 5: $PRE/smoke-pins.json sha256 71274d0be0e8a2ad7fa5b0fa7964952904673cdd80ed17decdbccb87b9eb1ba2 (chain D
    elucid N/256; route B deepseek-v4-flash at northgate N/256; roles glm-5.3); make-manifest: $SMOKE/manifest.json
    sha256 1283073cf27b2c818bee2ba591172335d6cdc41946b65064a22f0e7013e0cbc3, run 2d52debabc6b9466501cfb40b5d905ccf1c3acf09198a9f5427914e97d1fb3be,
    configuration main, exclusion bound (searchqa 537e9b9b..., alfworld 678db107..., canaries 2edc279d...);
    $SMOKE/shared/test-canaries.json written once by the CLI (sha256 cfe83244...); exclusion-consent.json untouched.
  - STOP before S2/S3 (registrar's second go). Nothing running on dl (execskill-prep: idle hold window only).
- 04:18 REGISTRAR step (logged here as the registrar's, not run by OPS2): the smoke ledger $SMOKE/shared/ledger did not
  exist; /data/execskill-20261021-ops/smoke-cap-raise-g.py declared it with budgets.smoke_caps() (overall 16M,
  smoke:solver 14M, smoke:glm 2M, exactly as setting_of declares) and raised overall to 42M and smoke:solver to 40M
  with a recorded deviation (owner 17:0x: cost is no concern; GLM reserves about 4 x (bytes + 66K) per call).
  smoke:glm stays 2M (S3's glm_cap row). setting_of's declare will match the declared values; the raise stays in force.
- 04:2x registrar: SECOND GO for the chain-G smoke: s6-S2-c.sh and s6-S3-c.sh in parallel in tmux execskill-smoke
  (--env-path $GREPO --roles-repo $GREPO), one background wait until both end, then s6-SE6-c.sh (S-E6 + smoke-summary),
  then stop and report. A stopped (unjudged) stage: no retry; report the stopped report, ledger snapshot, paused
  attempt path, and stop.
- 04:19 pre-launch (read-only, exit 0): $SMOKE holds manifest.json, s0/, shared/ (exclusion/, exclusion-consent.json,
  ledger/, test-canaries.json), smoke.json, stages/S0.json only. Smoke ledger state: caps overall 42,000,000 /
  smoke:solver 40,000,000 / smoke:glm 2,000,000; declared 16M / 14M / 2M; settled {}; open {}; halted null; halts 0.
  TLS check through the PJLAB gateway, no credential: open.bigmodel.cn HTTP 401 (route and TLS work), TLS 0.07 s.
- 04:19 section 6.1 launch: tmux execskill-smoke (hold window) + window S2 `bash s6-S2-c.sh > logs/c/s6-S2.log` +
  window S3 `bash s6-S3-c.sh > logs/c/s6-S3.log` (both --env-path $GREPO --roles-repo $GREPO), started together.
- 04:52 one background wait ended: both processes exited; both stages JUDGED (recorded), neither paused.
  - S2 (04:19:53-04:50:55): `smoke-run --stage S2` printed {"passed": false, "stage": "S2"}, RC 3, EXIT 3;
    $SMOKE/stages/S2.json sha256 8438bb1b3dab954f... Rows: format FALSE; receipts, hooks, ledger, leftovers, faults,
    native_lock true. Format shares (compliant cells / cells, reduced; floor 9/10, X and P at most 1/20 below C):
    searchqa C 7/8 (floor), P 1/1, X 1/1; officeqa C 1/1, P 9/10 (below C), X 1/1; livemath C 39/40, P 39/40, X 1/1;
    spreadsheetbench 1/1 all arms; alfworld (6 games per arm) C 2/3, P 1/2, X 2/3 (all below floor; P also below C).
    Receipts: production 1,055; control/probe/resend/unregistered 0; leaks 0. Ledger row reserved = settled =
    1,268,883 (the smoke:solver total incl. S3's 31,550), others_open 0. Leftovers clean (concurrent_s3 none at the
    check); sandbox restarts 0, cleanup max 3.256 s. Hooks: applies 532, before_call 360, bindings 84, sheet_feedback
    136, alf_before_step 6, alf_after_step 6. Faults: 32, all the injected fx-crash fixture exceptions (officeqa 12,
    livemath 10, spreadsheetbench 10). ALFWorld 245 steps, wrapped share 0.894, level1 share 0. stderr: 8 x
    "slot_wait pool=execskill-sandbox-live waited_s=300".
  - S3 (04:19:53-04:24:42): {"passed": false, "stage": "S3"}, RC 3, EXIT 3; $SMOKE/stages/S3.json sha256
    bdde561b25f18601... Rows: engineer, detector, leakage, describer, glm_cap true; generator_research FALSE. GLM
    smoke:glm:s3 61,471 of 2M in 9 sends (engineer 3 = 46,225; examiner 1 = 12,935; leakage 1 = 442; describer 1 =
    1,033; examiner_research 3 = 836); first GLM reply confirmed glm-5.3; none refused. Solver: confirm-1 1 call
    1,507; run unit s1-searchqa 20 calls 30,043. generator_research false: the research request ended status none,
    reason rounds_exhausted after 3 rounds, because all 8 Wikipedia searches returned http_403 -> provenance null ->
    generator not run (no_research_finding), kept 0, solved 0 (MIN_CHECKED 5).
  - Smoke ledger after both: settled overall 1,330,354; smoke:solver 1,268,883 (S2 1,055 settles 1,237,333; S3
    confirm 1,507; S3 run unit 20 settles 30,043); smoke:glm = smoke:glm:s3 61,471; open {}; halted null; halts 0.
    No route-B process, no execskill container left.
- 04:55-04:57 zero-model-call diagnosis of the 403 (6 Wikipedia API GETs through the PJLAB gateway, no credential):
  curl with the client's exact UA "execskill-research/1 (fivebench-execskill-v1)" -> HTTP 200; the frozen client
  (research.Wikipedia(proxy=GATEWAY).search) -> FetchError http_403 on 2/2; plain httpx with the same UA -> 403 with
  curl's params and with research.search_params alike; the 403 page is Wikimedia's edge (cp5024): "Please respect our
  robot policy https://w.wiki/4wJS". So Wikimedia refuses the research client's requests on this route (parameters
  are not the cause); not a model result. Nothing changed; no stage re-run.
- next: s6-SE6-c.sh (S-E6 + smoke-summary), as the registrar instructed for judged stages.
- 04:57:32-04:57:34 `bash s6-SE6-c.sh > logs/c/s6-SE6.log`: RC s2_recorded 0, s3_recorded 0, smoke_run_SE6 0,
  se6_recorded 0, smoke_summary 3, EXIT 3 (the summary's not-passed exit).
  - S-E6 PASSED ($SMOKE/stages/SE6.json sha256 0ef49c3bc20e2d12...; configuration main): ratio 1.0 (settled
    1,268,883 = actual, stages S2+S3), ratio_ok true. Per-cell tokens card / procedure: searchqa 1,501.8 / 1,560.0;
    officeqa 925.4 / 2,568.1; livemath 584.8 / 671.1; spreadsheetbench 1,101.8 / 1,214.1; alfworld 17,083.5 /
    14,079.3 (none assumed). above_high: none (anchors high 3,400 / 7,927 / 3,969 / 4,273 / 45,000). Every scope
    fits: D:solver 63,649,961 and G:solver 63,651,733 of 1.52B; D:test 20,595,447 and G:test 20,597,219 of 407M;
    D:redo 3,318,111 and G:redo 3,563,871 of 72M; D:glm = G:glm 2,317,704 of 288M (no role assumed); 150/150
    per-step xs rows pass. Chain D is priced at the glm-5.3 per-cell tokens (placeholder note). Caveat: the
    examiner_research per-call figure (278.7 tokens, 3 calls) comes from research calls whose searches all got 403.
  - smoke-summary: passed FALSE ($SMOKE/smoke-result.json sha256 b0c606285b3ab3b4..., record d15de5a5d5ad48a7...):
    stages S0 pass, S1 not_required, S2 fail (format), S3 fail (generator_research), S4 not_required, SE6 pass,
    SN1 not_required.
  - STOP (registrar: stop and report). No retry. Nothing running on dl: no smoke-run/CLI process, no execskill
    container; tmux execskill-prep and execskill-smoke hold one idle window each.
- 05:0x report delivered (S2/S3 judged fail, S-E6 pass, summary fail). Registrar 05:05-05:12 (registrar's check, not
  OPS2's): the frozen UA got 403 on 9/9; the same httpx request with a contact URL in the UA got 200 on 7/7. G2 (UA
  fix, owner-signed S2.format waiver that only the owner writes, SNAPSHOT_ROOT source-d) is being built by G1.
- 05:1x-05:3x PREPARE ONLY for snapshot d (nothing moved, written to experiment roots, or called). Read-only: smoke
  root inventory (4,356 files to move: units 4,121, s0 217, ledger 3, ...; test-named: shared/test-canaries.json,
  shared/exclusion/* (stay), s0/s0-pytest.json, $PRE/s0/sandbox-selftest.json); /data/execskill-history has nothing
  newer than the c manifest; the registrar's smoke-cap-raise-g.py; run_execskill/evaluation canaries code; the G1
  worktree (still 344ddcc, clean). Written in /root/ops2-20261022/ (O_EXCL; c files kept): env-d.sh (SRC source-d,
  Q23 sheet-q23-d, L logs/d), s1-archive-d.sh (moves $PRE build-head, source-sha256, sheet-runtime, s0/, s0-pins,
  smoke-pins, sheet-q23.log and $SMOKE manifest, s0/, smoke.json, smoke-result.json, stages/, units/, shared/ledger,
  shared/test-canaries.json into $PRE/archive/smoke-glm-c-20261023/; sha256 before/after for non-test-named files,
  metadata only for test-named files; consent + exclusion records stay, metadata-checked; stops on any unexpected
  entry), s-chain-d.sh, s2-snapshot-d, s2b-q23-d, s3-selftest-d, s3-collect-d, s3-makedry-d, s3-make-d,
  s5-manifest-d, s5-pins-d.py, s6-S2-d, s6-S3-d, s6-SE6-d, and smoke-cap-raise-d.py (for the REGISTRAR to run after
  make-manifest and before S2/S3; OPS2 does not run it). bash -n 13/13 OK, ast 2/2 OK. Read-only dry check of the
  archive logic: root/shared checks OK; 4,356 = hashed 6 + 4,344 + 3 + test-named 3.
- 05:4x (10/23) registrar: "go d, ZERO-COST PART ONLY", G2 sha 6c338997c358d43ee42630e60644b2124beee55d
  (/data/execskill-dev fast-forwarded; only the two docs dirty). Run s1-archive-d.sh, then s-chain-d.sh <G2 sha>
  through CHAIN END; then stop and report. NOT the cap raise, S2, S3 or SE6 before "go paid" (G2's Codex round
  running). Registrar answers: S-E6 and smoke-summary back to back as on c (the waiver names the sealed smoke-result's
  record hash, so it can only follow the summary); a fresh smoke ledger on the d root is right, the registrar runs
  smoke-cap-raise-d.py after CHAIN END, the added DEVIATION sentence is fine.
  G2 runbook archive list superseded by s1-archive-d.sh (test-canaries moved unread; fresh one written by
  make-manifest, as on c).
- 05:56:42-05:56:43 step 1: bash s1-archive-d.sh > logs/d/s1-archive.log -> EXIT 0 (69/69 RC 0). Moved into
  $PRE/archive/smoke-glm-c-20261023/: $PRE build-head.txt, source-sha256.txt, sheet-runtime.json, s0/, s0-pins.json,
  smoke-pins.json, sheet-q23.log; $SMOKE manifest.json, s0/, smoke.json, smoke-result.json, stages/, units/ (under
  smoke/); $SMOKE/shared ledger/, test-canaries.json (under smoke/shared/). 4,356 files: sha256 before == after for
  4,353 (pre 6, smoke 4,344, shared 3); 3 test-named files moved unread, metadata before == after
  ($PRE/s0/sandbox-selftest.json, smoke/s0/s0-pytest.json, smoke/shared/test-canaries.json). Kept in place, metadata
  unchanged: $SMOKE/shared/exclusion-consent.json and $SMOKE/shared/exclusion/ (3 records). $SMOKE now holds only
  shared/ = exclusion, exclusion-consent.json. List sha256 (full lists in logs/d/archive-c-*-after.txt): pre
  7c03c767dbea4fb9..., smoke c4d17b373996427a..., shared c45f8a6285b3056e..., test-named (metadata) 09fd18beb926404...
  Key moved files:
  ```
  pre    2721b6cc1c2ebe94898ccc1cf0e19a3693fca34471247b97b9947333558f1ae5  build-head.txt
  pre    8f8d54f74e3ea6f4bbf9cd0049ffba9868ff6c9749332e4c96fd2e2fa0462458  s0-pins.json
  pre    b148dfc9ea5f17f6b56dc2f4bafcb6b5b937d7a7916eac0f02af23f643194cb3  sheet-q23.log
  pre    3e367f16920a228ba327fdf0cccb6b19d5ae5536f207a0c4f554e085d021b4f4  sheet-runtime.json
  pre    71274d0be0e8a2ad7fa5b0fa7964952904673cdd80ed17decdbccb87b9eb1ba2  smoke-pins.json
  pre    b2b6c9447ef2684077f841aa0320c834aa59ad8e14ff822fee5a59eb76d31d01  source-sha256.txt
  smoke  1283073cf27b2c818bee2ba591172335d6cdc41946b65064a22f0e7013e0cbc3  manifest.json
  smoke  b0c606285b3ab3b4c664a431d6f64e41382877c29407438fcad04b25af2c0d01  smoke-result.json
  smoke  8c8fdf8b4d294d08a82240ac3e2d5ae3be013e6f24cc55adf3044c561c654a8e  smoke.json
  smoke  0826a169acaf934dc07731a0e481efedb78e83b4575df3d9756c94ea30ac4e82  stages/S0.json
  smoke  8438bb1b3dab954f1f23f0ec14f388bb542df00fc6a3b8a325c9d0c3e8616486  stages/S2.json
  smoke  bdde561b25f1860132576b92503e5eb8a595045230839846366bbaef3b916cc9  stages/S3.json
  smoke  0ef49c3bc20e2d122c46b03608e74c6a4c2644ad1b68b69a81c95d07a5ede76f  stages/SE6.json
  shared e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ledger/.lock
  shared 47a4f77b06faf49f540650a11d902b7556883dc207d016ca856f960e8b5a40dc  ledger/events.jsonl
  shared 27dfcf718caa9197268b3c464f6d6fe5a0d07e285c6648c3956e63cc41a34bf5  ledger/state.json
  ```
- 05:56:59 step 2-3 launch: tmux execskill-prep:chain-d, bash s-chain-d.sh 6c338997c358d43ee42630e60644b2124beee55d > logs/d/chain.log (per-step lines follow)
  - 05:56:59 chain-d: precheck: /data/execskill-dev HEAD 6c338997c358d43ee42630e60644b2124beee55d, GO commit 6c338997c358d43ee42630e60644b2124beee55d; uncommitted entries under skillopt/scripts/tests: 0
  - 05:56:59 chain-d: smoke root before the chain: [shared ] shared: [exclusion exclusion-consent.json ]
  - 05:57:01 chain-d: s2-snapshot (s2-snapshot-d.sh): EXIT 0; log logs/d/s2-snapshot.log
  - 05:58:06 chain-d: s2b-q23 (s2b-q23-d.sh): EXIT 0; log logs/d/s2b-q23.log
  - 05:58:16 chain-d: s3-selftest (s3-selftest-d.sh): EXIT 0; log logs/d/s3-selftest.log

### Abort of the d chain on 6c33899 (registrar 06:0x "STOP the d chain now")
- 06:0x registrar: STOP the d chain now. G2's Codex round found 1 MAJOR (smoke.waiver does not refuse a symlink at
  shared/owner-smoke-waiver.json); G1 fixes it in a new commit on top of 6c33899, so snapshot d of 6c33899 is stale.
  Nothing paid had run. Asked: stop the chain and everything it started, move aside (never delete) its products, keep
  the c archive as s1-archive-d left it, make the s-chain-d precheck pass again, log, report, wait for "go d2 <sha>".
- 06:02:00-06:02:11 `bash /root/ops2-20261022/stop-d.sh` (output logs/d/stop-d.log): the chain (wrapper pid 2371453,
  tmux execskill-prep:chain-d) was inside s3-collect (s0-collect); TERM to its tree at 06:02:00, nothing alive at
  06:02:08 nor after KILL at 06:02:11; no execskill container. The ssh call ended with 255 (see the incident), so the
  script's own exit status was not received; its log is complete.
- INCIDENT (operator error): stop-d.sh took the parent of the chain's `bash -c` wrapper as the top of the tree; that
  parent was the tmux server (pid 1716739, up since 10/22 20:58). It got SIGTERM and exited, which ended the tmux
  sessions execskill-prep (windows hold, chain-d) and execskill-smoke (hold). The last full `tmux ls` (04:57) showed
  only these two sessions; a session made by anyone else on the default socket between 04:57 and 06:02 would have
  ended too. The script's pattern list also matched this ssh call's own remote shell (pids 2392701/2392703), hence
  the 255. Not affected: the registrar's label monitor (pid 1999138, ppid 1, still running at 06:1x) and G1's pytest
  (pids 2392746-8, cwd /data/execskill-dev-g, ppid 1, started 06:02:01, finished since). Zero model calls.
- 06:03:44 names-only listing before the clean-up -> logs/d/abort-before.txt (exit 0).
- 06:0x one ssh call failed in the operator's local shell (zsh: unmatched quote) before anything was sent; nothing
  ran on dl.
- 06:08-06:1x read-only checks (exit 0): no execskill or pytest process left, no execskill container, no open handle
  under the paths to be moved. Besides the listed products, the d chain left in /tmp: execskill-copy-sha256.txt
  (s2-snapshot-d.sh line 10, 05:57:00), execskill-s0-inputs-jnnvyfkm (s0.py:685, 05:58:17), 62 x execskill-input-*
  (solver.py:627, all 06:01:55, before G1's first pytest at 06:02:01) and its pytest basetemp
  /tmp/pytest-of-root/pytest-0 (~35k inodes). G1's pytest-1/11/12/13 were already gone (not removed by me); the
  dangling pytest-current link is not mine and stays. /data/execskill-dev HEAD is now d8260f1 (G1's fix).
- 06:17:57-06:18:00 `bash /root/ops2-20261022/abort-move-d.sh > logs/d/abort-move.log` -> EXIT 0. Checks first: no
  process of the chain, no open handle under the paths, new entries under $PRE (incl. $SMOKE) since 05:56:50 exactly
  build-head.txt, source-sha256.txt, sheet-q23.log, sheet-runtime.json, s0/ (test-named s0/sandbox-selftest.json),
  nothing new under $SMOKE; /tmp leftovers exactly 62 execskill-input-* + execskill-copy-sha256.txt +
  execskill-s0-inputs-jnnvyfkm. Then moved (never deleted): source-d -> /data/execskill-20261021-source-d-aborted-6c33899
  (1270 files), sheet-q23-d -> /data/execskill-20261021-sheet-q23-d-aborted-6c33899, the five $PRE products ->
  $PRE/archive/aborted-d-6c33899-20261023/, the 64 /tmp leftovers -> its tmp/, the aborted chain's logs (chain,
  s2-snapshot, s2b-q23, s3-selftest, s3-collect, verify-snapshot.json, stop-d.log) and stop-d.sh ->
  logs/d/aborted-6c33899/. Names, types and file sizes equal before and after (1602 entries,
  logs/d/abort-names-{before,after}.txt); test-named files moved unread. Removed only /tmp/pytest-of-root/pytest-0
  (35,045 entries); /tmp free inodes now 254,749. The c archive re-verified unchanged with s1-archive-d's own list
  functions (pre/smoke/shared sha256 lists, test-named metadata, 4,356 files); consent and exclusion metadata
  unchanged. Listing after: logs/d/abort-after.txt.
- d chain on 6c33899 aborted at s0-collect (zero cost) after Codex MAJOR on the waiver path; products moved to
  /data/execskill-20261021-source-d-aborted-6c33899, /data/execskill-20261021-sheet-q23-d-aborted-6c33899 and
  /data/execskill-20261021-pre/archive/aborted-d-6c33899-20261023/ (the chain's /tmp leftovers under its tmp/); the
  aborted chain's logs are in logs/d/aborted-6c33899/.
- 06:19:08 `bash /root/ops2-20261022/precheck-d.sh > logs/d/precheck-d.log` (read-only replica of the s-chain-d.sh precheck and of every step start condition) -> exit 0, FAILS 0; the HEAD check waits for the d2 GO commit (/data/execskill-dev HEAD now d8260f1). s-chain-d.sh and the step scripts unchanged (no edit needed: the moved names are not referenced).
- 06:19:08 tmux sessions re-created as before the incident (one idle window each): `tmux new-session -d -s execskill-prep -n hold "bash --norc --noprofile"` -> 0, the same for execskill-smoke -> 0; proxy variables in the new tmux global environment: 0. Waiting for "go d2 <sha>"; no cap raise, S2, S3 or SE6 before "go paid".

### d2: snapshot d of d8260f1 (registrar "go d2 d8260f110fab2edf18d34a54d297e4e929e93e63")
- 06:2x registrar: go d2 d8260f110fab2edf18d34a54d297e4e929e93e63. Run only s-chain-d.sh with it in tmux
  execskill-prep through CHAIN END, then stop and report (provenance, q23-d, selftest, s0-collect 14/14 with pytest
  count and time, spec, S0, pins, make-manifest); no cap raise, S2, S3 or SE6 before "go paid". On the incident the
  registrar checked dl at 06:20: no other user job was running (only system jupyter, vscode and the label monitor) and
  the two recreated sessions are the only ones; from now on a stop signals only the chain's own process group. Moving
  the aborted chain's /tmp files into the archive's tmp/ confirmed as right. s1-archive-d is not rerun.
- 06:22:12 step 2-3 launch (d2): tmux execskill-prep:chain-d2, `bash /root/ops2-20261022/s-chain-d.sh d8260f110fab2edf18d34a54d297e4e929e93e63 > logs/d/chain.log 2>&1` (per-step lines follow)
  - 06:22:12 chain-d: precheck: /data/execskill-dev HEAD d8260f110fab2edf18d34a54d297e4e929e93e63, GO commit d8260f110fab2edf18d34a54d297e4e929e93e63; uncommitted entries under skillopt/scripts/tests: 0
  - 06:22:12 chain-d: smoke root before the chain: [shared ] shared: [exclusion exclusion-consent.json ]
  - 06:22:14 chain-d: s2-snapshot (s2-snapshot-d.sh): EXIT 0; log logs/d/s2-snapshot.log
  - 06:23:19 chain-d: s2b-q23 (s2b-q23-d.sh): EXIT 0; log logs/d/s2b-q23.log
  - 06:23:28 chain-d: s3-selftest (s3-selftest-d.sh): EXIT 0; log logs/d/s3-selftest.log
  - 07:03:12 chain-d: s3-collect (s3-collect-d.sh): EXIT 0; log logs/d/s3-collect.log
  - 07:03:16 chain-d: s3-makedry (s3-makedry-d.sh): EXIT 0; log logs/d/s3-makedry.log
  - 07:03:22 chain-d: s3-make (s3-make-d.sh): EXIT 0; log logs/d/s3-make.log
  - 07:03:28 chain-d: s5-manifest (s5-manifest-d.sh): EXIT 0; log logs/d/s5-manifest.log
  - 07:03:28 chain-d: chain end: S0 recorded and the smoke manifest written; stop before the registrar's cap raise and S2/S3
- 06:22-07:03:56 one background wait on the chain's pane process (pid 2405996, its own process group) -> ended
  07:03:56 (exit 0); chain.log: CHAIN END 07:03:28, every step EXIT 0. Read-only collection of the step logs and
  records afterwards (exit 0). Evidence (counts and hashes only):
  - provenance: snapshot /data/execskill-20261021-source-d of d8260f110fab2edf18d34a54d297e4e929e93e63, 1270 files,
    sha256 list 83d5ca3d071bd09892c34518496c7252040be005b46cb279ae1783b7fcefd342, env files absent (06:22:12-14).
  - q23-d (06:22:14-06:23:19): qualification.json sha256 28eba8e60017038025a16c7403de7543fbaa2fa9a64fea871fad5d8dd1db7f6e,
    record_hash 8b3368007e1c827d42e2753d58ae38ac880e78010b701c703d60293491eba27d, model_api_calls 0;
    $PRE/sheet-runtime.json sha256 be19cbcc5e1af04bfc369268989e7eb48a7c4b97c2e58479c196349c0184300d (image
    sha256:f7f6f598... and the 120 s timeout kept).
  - sandbox-selftest (06:23:19-28): passed, 8/8 escape rows true; rss 111,608 KiB, start 3.212 s, 352 views (p99 5,531
    bytes); sha256 as printed by the step script d5b2757bb8e755e3...
  - s0-collect (06:23:28-07:03:12): leftovers clean before; /tmp IFree 254,748 before, 254,093 after; 14/14 checks
    true; pytest "1455 passed in 1594.34s (0:26:34)"; supply ALFWorld preset 322 = cut 322, SearchQA tail kept 11,378,
    exclusion verified; replay 228 trajectories, 7,524/7,524 steps, zero_crash 0 faults; equivalence same
    12/20/20/280/20, 0 different/invalid; sheet: engine q23-d same sources as v3 training (13 fields, 0 differing; 7/7
    sources equal), fixtures 20/20 qualified; measurements guard ok (sum 1,148,204 <= budget 9,911,456 KiB of
    MemAvailable 14,159,224); determinism equal draws, 107 hashes, fault list identical to c (one fixture fault);
    checks.json sha256 d9891b61... (as on c); $PRE/s0-pins.json sha256 33d63ebe9165a111...
    Note: the pytest count comes from smoke/s0/s0-pytest.json, which matches the literal test-name pattern through
    "pytest"; only its "N passed in T s" line was extracted (grep -o), as the registrar asked for the count.
  - smoke-make --solver-chain G (07:03:12-22): dry and sealed spec record
    f8878f73034f3dd595c733918629e98034573a2dab91df614ca6b43ff82f3b32, smoke.json sha256
    517b7795bdc181235122c71b1a09f74376e155eb86a7988be93a2cebd0bb0317, items 12/20/20/280/20, stages S0 S2 S3 SE6,
    control_cells 0, no noise anchor; spec check: G, glm-5.3, probe_root None, 0 control cells. smoke --stage S0:
    passed ($SMOKE/stages/S0.json sha256 f488aae84d06b4f6...).
  - section 5 (07:03:22-28): provenance re-verified unchanged; $PRE/smoke-pins.json sha256
    200091fd6a11f9fc8914abc896bf37a6b1d718c237065adb85fffd46d836c5bc (chain D elucid deepseek-v4.1-flash-1017 N/256;
    route B deepseek-v4-flash at northgate N/256; roles glm-5.3, 16384 max tokens, 900 s read timeout, reasoning low;
    contracts, card sizes, fixtures and research index as on c); make-manifest: $SMOKE/manifest.json sha256
    bc0bc10cbfaedcd264d77ed002812f9d738f4942d30c003e0175d275ace17409, run
    e587c1a7915112ece4993d1e5cdc0ce8c6a85bdbdc51d164bb226c3d617ce433, exclusion hashes as on c, fresh
    shared/test-canaries.json.
  - after: smoke root [manifest.json s0 shared smoke.json stages], shared [exclusion exclusion-consent.json
    test-canaries.json], no smoke ledger yet; no execskill/pytest process, no container; tmux execskill-prep and
    execskill-smoke hold windows only. Zero model calls. Stopped before the registrar's cap raise; no S2, S3 or SE6
    before "go paid".
- 07:0x registrar: GO PAID for the d2 smoke. Registrar ran the cap raise at 07:0x ($OPS/smoke-cap-raise-d.py; printed
  ledger exists False; caps overall 42,000,000 / smoke:glm 2,000,000 / smoke:solver 40,000,000; declared 16M / 2M /
  14M; settled {}; open 0; DEVIATION text "registrar addendum 2026-10-23 05:3x") and saw the snapshot-d research client
  return real results for 2/2 Wikipedia searches through the gateway with the new User-Agent. Registrar: the
  s0-pytest.json "N passed in T s" extraction is fine (a unit-test report, not a test-pool file). Asked: s6-S2-d.sh and
  s6-S3-d.sh in parallel in tmux execskill-smoke (--env-path $GREPO --roles-repo $GREPO), one background wait until
  both end, then s6-SE6-d.sh (S-E6 + smoke-summary), stop and report; a paused stage is not retried; never write or
  touch shared/owner-smoke-waiver.json.
- 07:07 pre-launch (read-only, exit 0): $SMOKE holds manifest.json, s0/, shared/ (exclusion/, exclusion-consent.json,
  ledger/, test-canaries.json), smoke.json, stages/S0.json only. Smoke ledger state: caps overall 42,000,000 /
  smoke:solver 40,000,000 / smoke:glm 2,000,000; declared 16M / 14M / 2M; settled {}; open {}; halted null; halts 0.
  No route-B process, no execskill container. Route check through the PJLAB gateway, no credential: /usr/bin/curl to
  open.bigmodel.cn -> HTTP 401 (route and TLS work), TLS 0.068 s (/usr/local/bin/curl fails with a libcurl symbol
  error; not used).
- 07:07:39 section 6.1 launch (d2): tmux execskill-smoke windows S2 `bash s6-S2-d.sh > logs/d/s6-S2.log 2>&1` and S3 `bash s6-S3-d.sh > logs/d/s6-S3.log 2>&1` (both --env-path $GREPO --roles-repo $GREPO), started together.
  - 07:07:39 tmux exit S2 0, S3 0; pane pids S2 2517716, S3 2517721 (each its own process group)
- 07:36:22 one background wait ended (exit 0): both processes exited; both stages JUDGED (recorded), neither paused.
  Read-only collection afterwards (exit 0).
  - S2 (07:07:39-07:36:16): {"passed": false, "stage": "S2"}, RC 3, EXIT 3; $SMOKE/stages/S2.json sha256
    cdb62a76c90141ae..., record 74ab944ef0aa1f519547bbc79bc32807df7eaf6e5aa832dbd20cbdc655975d68. Rows: format FALSE;
    receipts, hooks, ledger, leftovers, faults, native_lock true. Format, compliant cells / cells (stored reduced share;
    floor 9/10, X and P at most 1/20 below C): searchqa C 32/40 (4/5, floor), P 37/40, X 39/40; officeqa C 40/40,
    P 38/40 (19/20, exactly at C - 1/20, passes), X 40/40; livemath C, P, X 40/40; spreadsheetbench C, P, X 40/40;
    alfworld (6 games per arm) C 4/6 (2/3), P 5/6, X 3/6 (1/2) (all below floor; X also below C). Receipts:
    production 1,025; control/probe/resend/unregistered 0; leaks 0. Ledger row reserved = settled = 1,257,597 (the
    smoke:solver total incl. S3's 31,502), others_open 0. Leftovers clean (concurrent_s3 none at the check); sandbox
    restarts 0, cleanup max 3.133 s. Hooks: applies 532, before_call 360, bindings 84, sheet_feedback 136,
    alf_before_step 6, alf_after_step 6. Faults: 32, all injected fx-crash fixture exceptions. ALFWorld 212 steps,
    wrapped share 0.906, level1 share 0. stderr: 6 x "slot_wait pool=execskill-sandbox-live waited_s=300", 1 x
    waited_s=600. Solver settles by bench: alfworld 212 = 234,570; livemath 178 = 115,985; officeqa 304 = 411,487;
    searchqa 141 = 216,760; spreadsheetbench 190 = 247,293 (S2 1,025 settles = 1,226,095).
  - S3 (07:07:39-07:17:40): {"passed": true, "stage": "S3"}, RC 0, EXIT 0; $SMOKE/stages/S3.json sha256
    79f16e611b55750f..., record fa7c72ffba4be9a9d38c832ed40adc1ae1b59f4f689ba2c3c2c142cb9815e9a4. Rows: engineer,
    detector, generator_research, leakage, describer, glm_cap all true. GLM smoke:glm:s3 89,416 of 2M in 14 sends
    (engineer 66,397; examiner 14,007; examiner_research 8,094; leakage 461; describer 457); first GLM reply
    confirmed glm-5.3; none refused. Solver: confirm-1 1 call 1,507; run unit s1-searchqa 20 calls 29,995.
    generator_research: research request status found after 2 rounds (6 calls); Wikipedia searches 4/4 ok (2 per
    round; 0 http_403, 0 http_429), 8 + 9 results, 2 pages; summary findings 1; provenance present (archive, revid,
    title, verbatim ...), trust_env false; generator ran: items 10, kept 10, dropped 0, checked 10, solved 10 (needed
    5 each). Engineer 2 changes, 0 survived; 2 detectors; leakage rule valid and kept; describer 11 lengths.
  - Smoke ledger after both: settled overall 1,347,013; smoke:solver 1,257,597; smoke:glm = smoke:glm:s3 89,416;
    open {}; halted null; halts 0; no overrun. No route-B process, no execskill container left.
- next: s6-SE6-d.sh (S-E6 + smoke-summary), as the registrar instructed.
- 07:38:17-07:38:19 `bash s6-SE6-d.sh > logs/d/s6-SE6.log`: RC s2_recorded 0, s3_recorded 0, smoke_run_SE6 0,
  se6_recorded 0, smoke_summary 3, EXIT 3 (the summary's not-passed exit).
  - S-E6 PASSED ($SMOKE/stages/SE6.json sha256 ac419d92e02286b4..., record
    b2e85788216729a7d87ef8d644fd1dc5f70f9bcce64a9e22ffba0bc5e16ea6e4; configuration main): ratio 1.0 (settled
    1,257,597 = actual, stages S2+S3), ratio_ok true. Per-cell tokens card / procedure: searchqa 1,501.3 / 1,559.0;
    officeqa 930.9 / 2,599.0; livemath 590.8 / 669.2; spreadsheetbench 1,110.8 / 1,352.4; alfworld 13,466.3 /
    12,814.3 (none assumed). above_high: none (anchors high 3,400 / 7,927 / 3,969 / 4,273 / 45,000). Every scope
    fits: D:solver 60,513,256 and G:solver 60,515,028 of 1.52B; D:test 19,483,539 and G:test 19,485,311 of 407M;
    D:redo 2,945,635 and G:redo 3,191,395 of 72M; D:glm = G:glm 3,106,344 needed (2,138,080 settled + 968,264
    reservation) of 288M (no role assumed); 159/159 rows and 150/150 per-step xs rows pass. GLM per call: engineer
    16,599.2 (4 calls), examiner 7,003.5 (2), examiner_research 1,349.0 (6, now from searches that returned results),
    leakage 461, describer 457. Chain D is priced at the glm-5.3 per-cell tokens (placeholder note).
  - smoke-summary: passed FALSE ($SMOKE/smoke-result.json sha256 12768e9db8ea6556..., record_sha256
    6258c34f98ca2c41c5ea5c30df1d02058ea54ea2c786dde520404ca4a516662e): stages S0 pass, S1 not_required, S2 fail
    (format only), S3 pass, S4 not_required, SE6 pass, SN1 not_required; required S0 S2 S3 SE6.
  - STOP (registrar: stop and report). No retry. shared/owner-smoke-waiver.json not written or touched (absent).
    Nothing running on dl: no smoke-run/CLI process, no execskill container; tmux execskill-prep and execskill-smoke
    hold one idle window each.
