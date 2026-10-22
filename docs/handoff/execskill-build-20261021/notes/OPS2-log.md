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
