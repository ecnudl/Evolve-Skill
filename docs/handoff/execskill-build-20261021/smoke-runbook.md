# Route-B smoke runbook (dl, fivebench-execskill-v1)

Written by build agent C7b-1 on 2026-10-22 and merged by integrator I1 the same day (phase 1); rewritten by I1 in
phase 2a/2b for the trimmed smoke (registrar addenda 13:0x, 13:4x, 13:5x, 14:3x, 14:10 row 12 and 14:4x at the end of
`docs/handoff/execskill-registrar-decisions-20261022.md`). It follows plan §10 steps 1-8, registration §10, registrar
decisions A5-1, C5-3 and C7b1-3, and ticket C6-3 for the manifest contract. The resolved operator inputs come from OPS1
(`smoke-inputs.md`, 12:00-12:35 dl clock), S3 from C7d (`notes/C7d.md`) as rewired by I1 (`notes/I1-phase2a.md`).
**The operator is the main agent.** No build agent ran a paid stage or wrote under a real run root. Real-container rows
ran only in throwaway roots (`/tmp/c7b1-*`, `/tmp/i1-*`) with zero model calls, and those roots were deleted. Results:
`notes/C7b1.md`, `notes/C7c.md`, `notes/C7d.md`, `notes/I1-phase1.md`, `notes/I1-phase2a.md`.

**Status of this runbook.** The smoke has five gating stages (registrar addendum 13:0x, owner instruction): S0 → S1 →
S2 ∥ S3 → S-E6, then `smoke-summary`, which passes when all five are recorded and passed. S-N1 (noise) and S4 (the
mini-step and its recovery drill) no longer gate; their code stays, and either may run later without ever gating
(section 6.4). S0 can pass once step 2b (this snapshot's own engine qualification) has run. Do not start S2 or S3
before S0 and S1 have passed (S1 fixes branch E/N and `longest` in the smoke manifest, step 5). A passing
`smoke-summary` starts the five-bench main experiment without waiting for the owner (owner instructions 17:0x and
17:3x; `main-runbook.md`). The smoke is of configuration `main` (section 5), and the SB → OQ pilot of
`pilot-runbook.md` is not run.

## Registrar addendum 2026-10-23 05:3x: research User-Agent; owner smoke waiver; re-smoke on snapshot d

The chain-G smoke on snapshot c failed (smoke-result `passed: false`). S3 `generator_research` got HTTP 403 from
Wikimedia on every search, because the User-Agent had no contact. S2 `format` failed on GLM-5.3's merits: ALFWorld's
J4 admissible share, SearchQA C 35/40 and OfficeQA P 36/40. Snapshot d (`protocol.SNAPSHOT_ROOT` =
`/data/execskill-20261021-source-d`; the next section now names d) changes two things:

- `research.USER_AGENT` carries a contact URL. Nothing else in the research client changed.
- The owner may waive the failed `S2.format` row and no other row (`protocol.WAIVABLE_SMOKE_ROWS`), in
  `$SMOKE/shared/owner-smoke-waiver.json` (`protocol.SMOKE_WAIVER`). Only the owner writes that file. An agent never
  creates, edits or moves it.

Re-smoke:

1. Archive the snapshot-c attempt with a sha256 check, as the snapshot-b attempt was archived. The owner's exclusion
   consent, S0's exclusion records and the canaries stay in place. The c smoke's ledger goes into the archive, so the
   d smoke starts on a fresh ledger.

   ```bash
   A=$PRE/archive/smoke-glm-c-20261023
   cd $PRE && test ! -e $A && mkdir -p $A/smoke/shared && echo ready      # stop unless it prints ready
   L="build-head.txt s0 s0-pins.json sheet-q23.log sheet-runtime.json smoke-pins.json source-sha256.txt
      smoke/manifest.json smoke/s0 smoke/smoke.json smoke/smoke-result.json smoke/stages smoke/units smoke/shared/ledger"
   find $L -type f -print0 | sort -z | xargs -0 sha256sum > $A.sha256      # every listed path must exist
   for p in $L; do mv $p $A/$p; done
   (cd $A && sha256sum -c --quiet $A.sha256) && echo archive-ok
   find $SMOKE -type f | sort   # left: shared/exclusion-consent.json, shared/exclusion/*, shared/test-canaries.json
   $CLI consent --root $SMOKE   # {"exclusion": "valid"}
   ```

2. Run the chain-G sequence of the next section on snapshot d: steps 2 and 2b, S0 (its pytest row runs the whole
   suite), `smoke-make --solver-chain G`, the pins of section 5, S2 and S3, S-E6, then `smoke-summary`.
3. If the smoke fails only on `S2.format` and S-E6 passed, the main agent shows the owner the rows and the result's
   hash, `$PY -c "import json; print(json.load(open('$SMOKE/smoke-result.json'))['record_sha256'])"`. The owner
   decides. To waive, the owner runs this one line, with `<SMOKE_RESULT_SHA256>` and `<NOTE>` filled in:

   ```bash
   python3 -c 'import json,sys; json.dump({"decision": "waive", "smoke_result": sys.argv[1], "rows": ["S2.format"], "note": sys.argv[2]}, open(sys.argv[3], "x"))' '<SMOKE_RESULT_SHA256>' '<NOTE>' /data/execskill-20261021-pre/smoke/shared/owner-smoke-waiver.json
   ```

4. `$CLI smoke-waiver --spec $SMOKE/smoke.json` (zero calls, writes nothing) prints `{"waiver": "absent"}`, or
   `{"waiver": "valid", "rows": ["S2.format"], "sha256": ...}`. Otherwise it is refused with the reason: another
   failing row, another hash, other keys, a missing stage, a failed S-E6, or a waiver beside a passed smoke. Then
   there is no main run. `test-read-estimate` accepts a waived smoke and records the waiver's sha256 and rows.

## Chain-G smoke (registrar addendum 10/23 02:3x): this run

Elucid's upstream rotation makes the elucid-only smoke unpassable, so this smoke runs GLM-5.3 as its solver (owner
10/21 21:18: the smoke may use any model). Code: branch `research/exec-skill-glm-smoke` (`smoke.make(...,
solver_chain="G")`); snapshot d, `protocol.SNAPSHOT_ROOT` = `/data/execskill-20261021-source-d` (addendum 10/23 05:3x;
snapshot c ran the first chain-G smoke). Step 2 copies `/data/execskill-dev`, so fast-forward that checkout to the
branch first. The sections below apply with these changes:

1. Section 1: `SRC=/data/execskill-20261021-source-d`, and a new `Q23=/data/execskill-20261021-sheet-q23-d` for step 2b.
2. Section 3: `$CLI smoke-make --solver-chain G --items <SET=FILE ...> --selftest $PRE/s0/sandbox-selftest.json`, with
   no `--probe-root`, `--control-cells` or `--noise-anchor` (each is refused). The spec records `solver.chain: "G"`,
   glm-5.3 with M = B = 65,536 and a 2,400 s read timeout on every bench, echo `["glm-5.3"]`, `probe_root: null`,
   `control_cells: []` and `stages: S0 S2 S3 SE6`. S0 is recorded as before.
3. Section 4 (S1) is skipped. `probe` and `smoke --stage S1` refuse the spec ("S1 is chain D's elucid probe; a chain-G
   smoke has no S1"). S1 stays chain D's launch precondition for later.
4. Section 5: with no S1 record, chain D's block takes the conservative unprobed bound, branch N with longest
   `routes.S1B_CEILING` = 256 (B = max(4M, 384): 32,768 on the QA benches, 65,536 on SpreadsheetBench, 4,096 on
   ALFWorld), and the route-B pin is built from it. In the pins builder, replace the `s1 = ...` and `d = ...` lines with
   `d = manifest.solver_block('D', env_path='$ELUCID', branch='N', longest=routes.S1B_CEILING)`. A `main` manifest needs
   chain D's block and route-B pin by format only; the chain-G smoke sends nothing to elucid.
5. Section 6.1: the smoke solver's credential is chain G's repository (the manifest's `clients.solver.G.env_path`):
   `$RUN --stage S2 --env-path $GREPO --roles-repo $GREPO` and the same for S3. An omitted `--env-path` (default
   `$ELUCID`) or `$ELUCID` is refused as "not the smoke manifest's". S2, S3's run unit and S3's roles now share the
   GLM-5.3 slot pool (10). A QA call reserves about 4 x (request bytes + 66K) on `smoke:solver` (cap 14M), so
   admission may slow S2 ∥ S3; the cell anchors put the settled spend near 4M.
6. Section 6.2: S-E6 prices chain D at the glm-5.3 per-cell tokens (its `chain_d` note) and chain G at its own.
7. Section 7: `smoke-summary` passes on S0, S2, S3 and SE6; S1 shows `not_required`.
8. Section 9: this path's rehearsal is
   `tests/test_execskill_glm_smoke.py::test_cli_rehearsal_runs_the_chain_g_smoke_end_to_end_as_an_engineering_fixture`.

## 0. Open items

| What | Effect | Ticket |
|---|---|---|
| An acceptance redo keeps the blocks an earlier attempt completed, redoes the paused block whole on `...:accept:attempt-N` + the redo reserve, and runs the remaining blocks on `...:accept` (§9.3, owner decision #15; C7e). The S4 drill stops in block 1, so attempt-2 redoes b1 and runs b2-b4; nothing is kept. | Closed by C7e. The S4 drill no longer gates (13:0x). | C7c-2 (closed), C7e-1, C7e-2 |
| The manifest has no per-call sandbox slot size (A5-1, C6-3). **Deferred.** | Safe failure. If the S0 memory guard fails at the start sizes (per-call 4, live 6), the S0 measurements row fails and writes no pins, so nothing can run on unregistered sizes. On 10/22 the guard held with a wide margin: 1,146,384 KiB ≤ 7,762,974 KiB (0.7 × MemAvailable 11,089,964 KiB). | C7b1-2 (slot part) |
| The smoke spec binds the self-test's start limits (`sandbox.LIMITS`), and `manifest._smoke_pools` requires the manifest's limits to equal them. **Current behaviour, documented.** | S0 fails its measurements row whenever the S0-derived limits differ from the start limits, and writes no pins. On 10/22 they were equal: AS 2048 MiB and frame 1 MiB (worker VSZ 174,140 KiB, largest training public view 30,116 B). | C7b1-1 |

Resolved since C7b-1 first wrote this runbook:

- C7b1-3, the SpreadsheetBench scorer bound to v3's checkout: step 2b, `sheet-runtime`,
  `s0-collect --engine-qualification`, and the revalidation in `make-manifest`.
- C7b1-2, pool part: `export-pools` (section 3).
- C7c-1: `smoke-run` prints the stage verdict or the stopped report, and `smoke-recovery` is wired.
- S4 and S-E6 are built (C7c). S4 and S-N1 no longer gate (13:0x).
- `smoke-make --control-cells` and `--noise-anchor` are optional and given by no one (13:4x; section 3).
- I1-1, the 57-game ALFWorld pool: deferred to the formal chain's ALFWorld step (13:4x). The default pilot
  (SpreadsheetBench → OfficeQA) does not need it. Closed for main (registrar 17:0x): `export-pools` exports
  ALFWorld from the fresh supply (section 3).
- C7e-2, 14:10 row 17: `recover` refuses an acceptance round that paused after its last cell (P2C).
- Registrar addendum 15:0x (I1 phase 2b (c)): the manual `smoke --stage` path records S0 and S1 only; S2, S3 and S-E6
  are recorded only by `smoke-run` (section 3). `probe --fake` and `smoke-make --probe-root` serve the zero-call CLI
  rehearsal only (section 9), whose records are labelled `engineering_fixture`, never `smoke`.
- S3 is built (C7d) and wired (I1 phase 2a): its own run unit and the 2M GLM limit (14:3x); S3 in
  `smoke.BUILT_STAGES` and in the rehearsal (C7d-1); LiveMath's checker in `step.Services` (C7d-2); `smoke-run --fake`
  names no credential (C7d-3).
- S-E6 reads S2 and S3 only, and also projects every GLM scope of both pilot chains (13:0x, 14:3x).
- The manifest field shapes follow `pilot-runbook.md` §3.1 (14:10 row 12; section 5); `manifest.check` refuses
  cards that are hashes, blank or missing a bench.
- Registrar addendum 14:4x confirmed S3's run unit as the registered mini-step run cut (20 SearchQA cells + 1
  confirmation cell; the 14:3x "about 60" is superseded) and the S2 ledger and leftovers rows for S2 ∥ S3, and
  registered the GLM maxima for leakage (6 per step) and the describer (3 per step) as constants
  (`smoke.LEAKAGE_CALLS`, `smoke.DESCRIBER_CALLS`). The R7 decision (16:1x) counts leakage at the code's per-step
  maximum, 10, once the six engineer calls are shared by both engineer units (R7a, R7c).
- S-E6's GLM projection sizes each next reservation by max(the largest request S3 sent for the role,
  `ROLE_INPUT_BYTES` = 220,000), so a full SpreadsheetBench or OfficeQA role request (about 0.95M reserved) is
  priced (14:4x).
- Ticket I1-2: a step's LiveMath build holds one checker session (`step._build`; 14:4x). S3's generator piece
  already held its own session (`smoke_roles`).

## 1. Shell setup (every tmux window)

```bash
PY=/root/continual-alf-prep-20260928/env/bin/python                  # 3.11.16
SRC=/data/execskill-20261021-source-b      # protocol.SNAPSHOT_ROOT: created in step 2, never edited afterwards
PRE=/data/execskill-20261021-pre           # protocol.PRE_ROOT
IN=$PRE/inputs                             # OPS1's six input files (directory 700, files 600)
SMOKE=$PRE/smoke                           # protocol.SMOKE_ROOT; shared/exclusion-consent.json: NEVER modify
HIST=/data/execskill-history               # protocol.HISTORY_ROOT (registry + supply files); the first non-dry make-items creates it
V3=/data/coevo5-20261019-v3-run-manifest.json                        # sha256 20d9ffcc5ad00a96bb1d90360c2ad43d157aaa72e774bb4109d12b9941e5ad5c
V3SHEET=/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json
V3SHEET_HASH=acc5c07f76a088969181cf45e8224fae2d4d033aa49385713802cba5338827a1   # its RECORD hash, not the file sha256
Q23=/data/execskill-20261021-sheet-q23-b   # step 2b: this snapshot's v7 engine qualification (a new directory)
ELUCID=/root/.config/weak-solver/elucid.env          # chain D credentials: path only, never printed
GREPO=/root/continual-noskill-bcb-20260928-a         # GLM role credentials repository: path only
export ALFWORLD_DATA=/root/continual-alf-prep-20260928/data     # json_2.1.1/train holds 3,553 games
unset OPENAI_API_KEY OPENAI_BASE_URL; export PYTHONDONTWRITEBYTECODE=1
CLI="$PY -B $SRC/scripts/run_execskill.py"
HFCLI="env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy HF_HOME=/data/execskill-tools/hf-home HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1 /data/execskill-tools/hfenv/bin/python -B $SRC/scripts/run_execskill.py"
```

`V3SHEET_HASH` is v3's `sheet_qualification.record_hash`. `reverify` compares the record's own hash, and it refuses the
file sha256 `83ae6be2…` ("not the pinned one"). `HFCLI` is only for `make-items --bench searchqa`: `$PY` has no
`datasets`, and the pinned cache key in `$IN/searchqa-cache-sha256.json` is the absolute arrow path under that
`HF_HOME`. Any other `HF_HOME` fails `_pinned_cache`.

Proxy: do not run `proxy_on`, and do not export `HTTP(S)_PROXY`. Every client registered for the paid stages uses
`trust_env=False`, and the manifest's clients carry the explicit gateway `protocol.GATEWAY` =
`http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`. That covers the deepseek solver, the GLM roles and the
research Wikipedia source. The zero-call steps need no network.

## 2. Snapshot (plan §10 step 1), in tmux `execskill-prep`

```bash
tmux new -s execskill-prep
cd /data/execskill-dev && git rev-parse HEAD > $PRE/build-head.txt          # read-only git
$PY -B -c "import sys; sys.path.insert(0, '.'); from skillopt.execskill import prelaunch; sys.stdout.write(prelaunch.sha256_list('/data/execskill-dev'))" > $PRE/source-sha256.txt
rsync -a --exclude='.env*' --exclude='.git' --exclude='__pycache__' /data/execskill-dev/skillopt /data/execskill-dev/scripts /data/execskill-dev/tests $SRC/
cd $SRC && $PY -B -c "import sys; sys.path.insert(0, '.'); from skillopt.execskill import prelaunch; sys.stdout.write(prelaunch.sha256_list('$SRC'))" > /tmp/execskill-copy-sha256.txt
cmp $PRE/source-sha256.txt /tmp/execskill-copy-sha256.txt                # must be silent
find $SRC -name '.env*'                                                  # must print nothing
$CLI verify-snapshot --list $PRE/source-sha256.txt --root $SRC --git-head "$(cat $PRE/build-head.txt)"
```

`verify-snapshot` prints the manifest's `provenance` block. Keep it for step 5.

## 2b. This snapshot's engine qualification (registrar decision C7b1-3; zero model calls)

The frozen v7 identity keys the scorer sources by absolute path, so the scorer refuses any checkout other than the
one its qualification was made from. As in v3 (`/data/coevo5-20261019-v3-ops/f/prep-v3f.sh:11`, q23-a … q23-f), each
snapshot gets its own qualification, with v3's exact inputs. Run it from `$SRC` after step 2:

```bash
cd $SRC && PYTHONPATH=$SRC $PY -B -m scripts.replay_sheet_v6 qualify --output $Q23 \
     --image sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790 \
     --legacy-qualification /root/continual-spreadsheet-long-20261001-study/q17/qualification.json \
     --comparison-fixture-qualification /root/continual-unknown-sheet-v6-20261001-q/qualification.json \
     --native-lock /root/continual-baselines-long-20261001-study/native.lock --engine-version v7 \
     > $PRE/sheet-q23.log 2>&1; echo "EXIT $?" >> $PRE/sheet-q23.log
#   zero model calls; it starts recalculation containers only (v3's run took 48 s). Writes $Q23/qualification.json
$CLI sheet-runtime --manifest $V3 --engine-qualification $Q23/qualification.json --out $PRE/sheet-runtime.json
#   = v3's runtime.spreadsheetbench with only recalculation.{qualification_path, qualification_sha256,
#   qualification_hash} replaced (image and timeout kept), revalidated offline with the frozen
#   sheet_numeric_adapter.qualified_engine, written once; prints its sha256 and the recalculation block
```

All three input files exist on dl. `sheet-runtime` refuses a qualification whose image or timeout differs from v3's
block, and a block that does not revalidate from this checkout ("does not revalidate from this checkout (ticket
C7b1-3)"). The v3 training qualification stays imported (owner #7). The S0 sheet row records that its engine and the
new one are the same: the 13 non-source identity fields are equal, and the 7 scorer sources are equal by content,
relative to each snapshot root. On 10/22 the dev tree's identity matched q23-f's on all 13 fields and all 7 sources.

## 3. S0, zero model calls (plan §10 step 3), in `execskill-prep`

Check the inodes of `/tmp` first (I1, 10/22 20:1x). dl's `/tmp` is a 7 GB tmpfs with 254,962 inodes. S0 runs the
route-B suite twice with pytest's default temporary directory (`zero-call-checks`, then `s0-collect`'s pytest row),
and one run writes about 125,000 files under `/tmp/pytest-of-root`. On 10/22 earlier builders' throwaway directories
held about 100,000 inodes (`/tmp/c7b2-suite`, `/tmp/pytest-of-root`, `/tmp/c7b2-rehearsal`). An exhausted inode table
fails the row with "No space left on device": an infrastructure fault, not a test result. The main agent decides
whether to remove those stale directories.

```bash
df -i /tmp | tail -1                             # IFree must be at least 160,000
$CLI zero-call-checks --root $SRC
$CLI leftovers                                   # D3/D14 workers excluded by command line -> "cannot_judge" is a pass
$CLI s0-pool-views --manifest $V3 --out $PRE/s0-pool-views.json
#   train paths only (never val/test); prints per-bench max/p99 public-view bytes and "workbook" p99
#   (10/22 throwaway: workbook p99 = 599,328 B; officeqa max 30,116 B)
$CLI make-fixtures --out $PRE/fixtures --p99-workbook-bytes <views.workbook.p99 from s0-pool-views>
$CLI import-texts --source /data/coevo5-20261019-v3-pre/texts/texts.json --out $PRE/texts
#   file 195f24f4…, record_hash 14187ae5…; verify_texts passes, all 5 cards match CARD_IDENTITY (OPS1)
$CLI import-sheet-qualification --source $V3SHEET --sha256 $V3SHEET_HASH --out $PRE/sheet
#   train side, 120 items, 91 qualified
$CLI make-items --bench alfworld --history-root $HIST --data-root $ALFWORLD_DATA \
     --pool-games $IN/alfworld-pool-games.json --runtime $IN/alfworld-runtime.json
#   322 zero-call pre-resets (12 + 60 + 150 + select 100: 20 rooms x 5 games; select is an upper bound), 7-21 min; writes $HIST/supply/alfworld-xs.json and alfworld-xs-views.json
#   (10/22 dry run, --dry-run: 3,514 games in 108 rooms, 81 s, no reset)
$HFCLI make-items --bench searchqa --history-root $HIST --dry-run \
     --fresh-manifest $IN/searchqa-sample-manifest.json --dataset lucadiliello/searchqa \
     --revision c1a979068ba118d85467179b704031d113d689cc --exclude $IN/searchqa-exclude.json \
     --cache-sha256 $IN/searchqa-cache-sha256.json
#   counts only (10/22: 11,378 tail items, 4.8 s); then the same command without --dry-run
#   -> $HIST/supply/searchqa-tail.json. Local files only, no download
```

The input files and their sha256 (all in `$IN`, written once by OPS1):

| File | sha256 | Content |
|---|---|---|
| `alfworld-pool-games.json` | `63eeccabfd01567832c72ff7193505b3714b6569ede7217bc498f9bcfb33e614` | 57 `{task_id: game file}` of the v3 pool |
| `alfworld-runtime.json` | `840f10c5cc5dea7d9fe4b4ab6a1a289ea6b7ed13eb885126c1807af9d59fa8c2` | v3's `runtime.alfworld`, verbatim |
| `searchqa-sample-manifest.json` | `e65b9f564267beb29f9bd3c937df4fb5a0cea380a24d34d9b6cbec0925e0a742` | the 10/12 fresh draw (ids and hashes only) |
| `searchqa-exclude.json` | `66536d2678129cbd3e9e27d96248616feab691db79937fd2063495e686884e52` | 2,000 ids, 600 pool questions |
| `searchqa-cache-sha256.json` | `191900ed19f9901c7a333b4e8a4775b401af738b4bf60148a6377b1964d2e354` | the validation arrow's pinned sha256 |
| `v3-data-pins.json` | `0f07ad4869a7909ea4a4fe2e8302d55109beadb09db6e5332680a0ae39edc23c` | v3's `data` block, verbatim (16 pins) |

Operator only, under the owner's exclusion consent. This step reads TestAccess through the consented code path:

```bash
$CLI exclude-tests --root $SMOKE --pinned $IN/v3-data-pins.json \
     --searchqa-supply $HIST/supply/searchqa-tail.json --alfworld-supply $HIST/supply/alfworld-xs.json
#   writes $SMOKE/shared/exclusion/ (two records + test canaries; counts and hashes only)
```

The pools (ticket C7b1-2 / C6-3). They are exported once, from the frozen reader `coevo5.data.pool` on v3's data pins:
train and val only, never test.

```bash
$CLI export-pools --manifest $V3 --out $PRE/pools \
     --alfworld-supply $HIST/supply/alfworld-xs.json --alfworld-views $HIST/supply/alfworld-xs-views.json
#   zero calls, about 1 min; writes <bench>.json for the five benches + the sealed pools.json, and prints the counts,
#   each file's sha256 and the data.pools pins block (section 8). ALFWorld's pool is the fresh supply (registrar
#   17:0x, closes I1-1), so run it after make-items; the two supply paths shown are the defaults
```

`supply.alfworld_pool` refuses views that were not reset on the runtime the run pins (M2b). So make-items'
`--data-root` must be v3's `runtime.alfworld.alfworld_data` (= `$ALFWORLD_DATA`, `/root/continual-alf-prep-20260928/data`),
and its `--runtime` must be `$IN/alfworld-runtime.json`, whose digest the views record carries (`runtime_sha256`).

What the 10/22 throwaway export printed (before 17:0x). The operator's run must reproduce the first four rows:

| Bench | Pool | Written | Digests and slices |
|---|---|---|---|
| searchqa | 600 (400 train + 200 val) | 600 | sorted ids `901fb49e…`; supply-order ids `332df1bf…`; items `120f123f…`; smoke slice 280 = 198 train + 82 val (`7033d48d…`); run slice 300 (`50ce4833…`) |
| spreadsheetbench | 120 | 91 qualified (58 train + 33 val, by the v3 training qualification) | run 31 + accept 60 |
| officeqa | 74 | 74 | run 24 + accept 50 |
| livemath | 283 | 283 | run 119, accept 100, probe 64 |
| alfworld | v3's 57 (old code) | now the fresh supply `alfworld-xs`, with rooms and the views' runtime digest; not yet exported with this code | run 60 / accept 150 in room groups, cut at step 5 |

Smoke items. These are written once, and the real items are registered under consumption namespace `smoke`:

```bash
$CLI smoke-items --out $PRE/smoke-items --searchqa-pool $PRE/pools/searchqa.json \
     --alfworld-supply $HIST/supply/alfworld-xs.json --alfworld-views $HIST/supply/alfworld-xs-views.json \
     --data-root $ALFWORLD_DATA --fixtures $PRE/fixtures
```

`smoke-items` reads only an exported pool file: it checks the file against the sealed `pools.json` beside it (the
recorded absolute path and sha256, so do not move the export) and requires exactly 600 items. It writes the following, plus `smoke-items.json`, which lists the five files as
`SET=FILE` for `smoke-make --items` and `s0-collect --items`:

- SearchQA, the last 280 of the pool order: S2 20, S-N1 200 and S4 60. S-N1's 200 stay unused unless S-N1 runs
  later; S3's own run unit runs the first 20 of S4's 60, and its confirmation cell the first of those.
- ALFWorld: 12 games of the smoke room group.
- The fixture sets: OQ, LM and SB, 20 items each (the files of `$PRE/fixtures`).

Sandbox self-test and every S0 row:

```bash
$CLI sandbox-selftest --out $PRE/s0 --items <file> --items <file> ...   # one --items per file smoke-items.json lists
$CLI s0-collect --root $SMOKE --snapshot $SRC --items <SET=FILE ... as smoke-items.json lists> \
     --fixtures $PRE/fixtures --selftest $PRE/s0/sandbox-selftest.json --pins-out $PRE/s0-pins.json \
     --manifest $V3 --sheet-source $V3SHEET --sheet-sha256 $V3SHEET_HASH \
     --texts $PRE/texts/texts.json --sheet-runtime $PRE/sheet-runtime.json \
     --engine-qualification $Q23/qualification.json --history-root $HIST
```

`s0-collect` refuses to start without `--engine-qualification` (unless `--fake`). On the real path it also needs
`--manifest`, `--sheet-source`, `--sheet-sha256`, `--texts` and `--sheet-runtime` (Codex #13). The equivalence row
runs on the imported cards, verified against `CARD_IDENTITY`, and on the pinned runtimes: v3's, with this snapshot's
SpreadsheetBench block. It records both by hash, and it passes only if every frozen run sent its solver requests and
executed validly. It runs the 14 rows of registration §10 once each. It writes:

- `$SMOKE/s0/<row>.json`, each tagged `fivebench-execskill-v1-s0-row`.
- `$SMOKE/s0/checks.json`.
- `$SMOKE/s0/sheet-fixture-qualification/`.
- Only if the measurements row passes: `$SMOKE/s0/s0-limits.json`, which is the A5-1 derivation plus the memory guard,
  and `$PRE/s0-pins.json`, which is exactly `{limits, measured}`.

The sheet row passes only if all three hold: the v3 import re-verifies; all 20 SpreadsheetBench fixtures qualify on
this snapshot's engine runtime (`engine_runtime(<v3 block>, $Q23/qualification.json)`); and that engine is the same
as the v3 training qualification's. Its evidence records `qualification_sha256`, `qualification_hash` and
`same_sources_as_v3_training`. The D3 traces default to `s0.D3_TRACES` = `/data/feasibility/D3/r3/lt/traces.json`
(sha256 `4384bbf2…`, 228 trajectories, 7,524 steps).

The rows take these times:

| Row | Time |
|---|---|
| replay (D3 traces) | about 6.5 min |
| sandbox suite | about 20 s |
| equivalence | a few seconds per item |

It exits 0 only if every row passes.

```bash
$CLI smoke-make --items <SET=FILE ...> --selftest $PRE/s0/sandbox-selftest.json --dry-run
$CLI smoke-make --items <SET=FILE ...> --selftest $PRE/s0/sandbox-selftest.json
#   -> $SMOKE/smoke.json (sealed spec: stages S0 S1 S2 S3 SE6, control_cells [], noise_anchor null and its reason)
$CLI smoke --spec $SMOKE/smoke.json --stage S0 --input $SMOKE/s0/checks.json
#   the CLI ANDs the supply row with the persisted exclusion records -> $SMOKE/stages/S0
```

`smoke --stage` records S0 and S1 only (registrar addendum 15:0x): S2, S3 and S-E6 are recorded only by `smoke-run`
(section 6), which runs their units, the GLM projection and the leftovers rows. Anything else is refused.

Give neither `--control-cells` nor `--noise-anchor` (registrar addendum 13:4x). The spec then records
`control_cells: []` (S1-e receipts stay classed by their probe tag), `noise_anchor: null` with the 13:0x addendum as its
reason, and its gating `stages`. If S-N1 runs later on this spec (never gating), it records the measured paired noise
and judges no ratio against an anchor.

## 4. S1 probe (paid, at most 60 calls, own ledger root; plan §10 step 4)

```bash
$CLI probe --spec $SMOKE/smoke.json --env-path $ELUCID --probe-root $PRE/probe
#   prints counts, classes and the judged rows (never a reply or a credential); a complete probe judges rows a-f and
#   records $SMOKE/stages/S1.json itself. The probe root must be the spec's (S2 reads the probe's receipts there).
```

`probe` records S1; do not also run `smoke --stage S1` (it would be refused as already recorded). Never pass `--fake`
here: it is the CLI rehearsal's (section 9) and refuses the registered smoke and probe roots. The first single call
must be confirmed before any concurrency. S1-b sets branch E/N and the `longest` used for B, and
they are written into the smoke manifest in step 5. Neither changes afterwards.

## 5. Smoke manifest (after S1; ticket C6-3)

Pins file `$PRE/smoke-pins.json` has these top-level keys:

- `root`: `/data/execskill-20261021-pre/smoke`.
- `evidence`: `"smoke"`.
- `configuration`: `"main"` (registrar 17:0x). S-E6 projects the configuration the smoke manifest names, and
  main-runbook §2 refuses a smoke of any other configuration.
- `data`: `{"research": {"archive", "index_sha256"}}` only. Write no `pools`, `test_read_estimate` or `pinned`,
  because the smoke's items come from `smoke.json`. The candidate is v3's research block: archive
  `/data/coevo5-20261019-v3-archive`, index_sha256 `7219096cbb7e487439b5598dc12660f639562221c2167744f20c895f8bb2f725`.
  The operator decides.
- `sheet_qualification`: `{"path": "<$V3SHEET>", "record_hash": "<$V3SHEET_HASH>"}`.
- `runtime`: v3's `runtime` with `spreadsheetbench` replaced by `$PRE/sheet-runtime.json` (step 2b). Its `alfworld`
  entry must equal `$IN/alfworld-runtime.json`, because the pre-reset routing views were made with that runtime:

```bash
$PY -B -c "import json, sys; sys.path.insert(0, '$SRC'); from skillopt.continual_eval.core import read_json
r = read_json('$V3', sealed=True)['runtime']; r['spreadsheetbench'] = read_json('$PRE/sheet-runtime.json')
assert r['alfworld'] == read_json('$IN/alfworld-runtime.json'), 'alfworld runtime'; print(json.dumps(r))"
```

- `cards`, `contracts` and `fixtures`, in the shapes of `pilot-runbook.md` §3.1-3.2 (registrar addendum 14:10 row 12):
  - `cards`: `{bench: card text}`, the five texts of `.cards` in `$PRE/texts/texts.json`. They must be texts, not
    hashes: `cells.py` hands `cards[bench]` to the solver as the card, so a hash would replace every task card.
  - `contracts`: `{bench: {"text": guard, "sha": sha256(guard)}}`, the frozen format guards exactly as pilot-runbook
    §3.2 lists them. Recorded only.
  - `fixtures`: `{"sha256": <sha256 of $PRE/fixtures/fixtures.json>}`. Recorded only.
- `provenance`: the output of `verify-snapshot`.
- `clients` must list both solver blocks, the registered roles and route B's pin. `check_clients` requires
  `routes` in every manifest of configuration `main`, this smoke's included (M4), and main-runbook §3.2 asserts
  that the main manifest's `clients` equal the smoke's:

```bash
$PY -B -c "import json, sys; sys.path.insert(0, '$SRC'); from skillopt.execskill import manifest, protocol, routes
from skillopt.continual_eval.core import read_json
s1 = protocol.verified(read_json('$SMOKE/stages/S1.json'), 'smoke-stage')['result']   # S1's branch and longest
d = manifest.solver_block('D', env_path='$ELUCID', branch=s1['branch'], longest=s1['longest'])
print(json.dumps({'solver': {'D': d, 'G': manifest.solver_block('G', env_path='$GREPO')}, 'roles': manifest.ROLES,
                  'routes': {'D': {'B': routes.pin('D', 'B', env_path='<deepseek-credentials-file>',
                                                   solver_block=d)}}}))"
```

This reads no credential. S1 records `longest` on branch N only; on branch E it is `null`, and
`protocol.ledger_bound` accepts no other value there, so take both from S1's record as above rather than by hand.
G is listed because every role is GLM-5.3 with the G block's repository (`manifest.setting_of`). The smoke's solver
is still chain D's deepseek.

```bash
$CLI make-manifest --out $SMOKE/manifest.json --pins $PRE/smoke-pins.json --exclusion-root $SMOKE --s0-pins $PRE/s0-pins.json
#   binds $SMOKE/shared/exclusion into data.exclusion, writes $SMOKE/shared/test-canaries.json once, then the manifest
```

`--s0-pins` provides the `limits` and the `measured` values, which are vsz/rss/view p99 from the self-test plus
native_peak_rss_kib from S0. The operator's pins must give neither. Before anything is written, `make-manifest`
revalidates a v7 `runtime.spreadsheetbench` offline from this checkout and refuses one that does not revalidate (a
stale block would score every SpreadsheetBench cell `unknown`).

## 6. Paid smoke stages, in tmux `execskill-smoke` (background on dl; sparse event-driven monitoring)

Order (registrar addenda 13:0x and 14:3x): S2 ∥ S3 → SE6 → `smoke-summary` (section 7). S2 and S3 run at the same
time in two windows. S-E6 waits until both have recorded and exited.

### 6.1 S2 and S3, in parallel

```bash
tmux new -s execskill-smoke                 # window 1: S2; window 2 (ctrl-b c): S3
# same shell setup as section 1, in each window
RUN="$CLI smoke-run --spec $SMOKE/smoke.json --manifest $SMOKE/manifest.json"
$RUN --stage S2 --env-path $ELUCID --roles-repo $GREPO
#   window 1: the first unit confirms its first reply before any concurrency; records $SMOKE/stages/S2.json
$RUN --stage S3 --env-path $ELUCID --roles-repo $GREPO
#   window 2: one confirmation cell alone (units/S3/confirm-<n>), then S3's own run unit (units/S3/s1-searchqa/run:
#   20 SearchQA items, one run each, parent arm; registry units/S3/history), then the six role pieces in
#   units/S3/roles (8-18 GLM-5.3 calls, notes/C7d.md); records $SMOKE/stages/S3.json
$CLI monitor --root $SMOKE                  # counts and ledgers only, never a score
```

S3 needs nothing of S2 (registrar addendum 14:3x): its engineer and its detector read its own run unit. Running the two
side by side changes this:

- Both charge `smoke:solver` on one ledger (S3 through its run unit and its confirmation cell). S2's ledger row judges
  only S2's own reservations; S3's open ones appear in S2's record as `ledger.others_open`.
- S2's leftovers row lists S3's process (`smoke-run ... --stage S3`) and S3's containers apart, as `concurrent_s3`.
  Anything else of route B still counts as a leftover, so while S2 runs, start nothing else of route B: no S-N1, no
  S4, no other `smoke-run`, no chain.
- The machine-wide slot pools (`protocol.SLOT_ROOT` lock files: deepseek 8, GLM-5.3 10, the sandbox pools) are
  shared, so each stage runs slower. No verdict depends on that.
- If in doubt (a loaded machine), run S3 after S2 has recorded. The order changes no verdict. The registrar
  confirmed the two rows above (addendum 14:4x).

S3's GLM limit is the smoke's GLM cap, 2M (14:3x). Before an endpoint reserves anything, a role call is refused when
S3's spend so far (the sub-scope `smoke:glm:s3`, settled + open, across attempts) plus the call's single-attempt bound
would pass 2M. The unit then pauses `budget`, and `glm.json` names the refused label. The `glm_cap` row judges
against 2M.

### 6.2 S-E6 (zero calls, no credential)

```bash
$RUN --stage SE6
```

It needs the recorded S2 and S3 and a smoke ledger with nothing open on `smoke:solver`, so run it after both processes
have exited. It projects against every cap of both chains of the smoke manifest's `configuration`, which the record
names. For `main`, that is the five steps SearchQA → OfficeQA → LiveMath → SpreadsheetBench → ALFWorld at main's caps
(main-runbook §3.4):

- Every solver scope: the measured tokens per cell × the ledger/actual ratio (over every settled smoke cell, S3's run
  unit included) × the maximum schedule + one full next reservation.
- Every GLM scope (14:3x, 14:4x, R7 decision 16:1x): S3's measured tokens per role call × the maximum role calls per
  step that the code allows (engineer 6, shared by `engineer` and `engineer-2` (R7a); leakage 10 = 2 × 3 first checks
  + 4 checks after fixes; describer 3; examiner 9; examiner research 192; `smoke.MAX_ROLE_CALLS`) + one next
  reservation, 4 × (max(the largest request bytes S3 sent for the scope's roles, `ROLE_INPUT_BYTES` = 220,000) + 512
  + 16,384), so at least 947,584 tokens; on the engineer row the floor also counts the engineer's 5,170-byte system
  prompt (`smoke.ENGINEER_REQUEST_FLOOR`), so at least 968,264 (R7c). The caps are per step 2.5M (engineer), 3.0M
  (examiner) and 4.6M (research) (R7b; registered 1.5M / 2.5M / 4.6M), and 30M per chain (`<chain>:glm`) over both
  steps. Main's are 5M / 5M / 9.2M per step and 288M per chain over its five steps (registrar 17:0x). A role that S3 did not call is priced at the dearest measured role and listed as `assumed`.

If any projection exceeds its cap, S-E6 fails, and the run needs a v1.1 re-registration first. The S-E6 record shows
every row.

### 6.3 A stopped unit

Each stage is recorded once under `$SMOKE/stages/`. `smoke-run` prints `{"stage", "passed"}` and exits 0 if the stage
passed, 3 if it did not. A unit that paused instead (the cap, connectivity, the first reply not confirmed) gives no
verdict: `smoke-run` prints the stopped report (`stage`, `stopped`, `reason`, `unit`) and exits 3
(`chain.EXIT_PAUSED`).

- S3's confirmation cell not confirmed (`first_call_not_confirmed`, unit `smoke/S3/confirm-<n>`): check network and
  TLS (AGENTS.md), then run S3 again. The next process confirms in a new confirmation unit; nothing to recover.
- Any other stopped unit (S2's units; S3's run unit `units/S3/s1-searchqa/run`; S3's roles unit `units/S3/roles`,
  including an unconfirmed first GLM reply) needs the owner's own `recovery.json` in that attempt before the same
  `smoke-run` runs again: `$CLI recover --attempt <attempt dir> --decision '<the owner's decision>'`. Never write one
  without the owner's decision. `smoke-recovery` is only for the S4 drill. `recover` reserves a decision that begins
  with the word `release` for the owner's release of a paused run-root canary scan (a pilot-end matter, registrar
  decision PR-C31-3 (1b)) and refuses it anywhere else.
- A halted smoke ledger (`monitor` shows it) resumes only on the owner's decision:
  `$CLI resume-ledger --root $SMOKE --chain smoke --decision '<the owner's decision>'`.
- C7e-2 (registrar addendum 13:5x): an acceptance round that pauses after its last cell (J5 or J6
  `acceptance_undetermined`, or an error raised by `acceptance.decide`) is final for that round. Write **no**
  `recovery.json` for it: a redo would only reproduce the pause and spend one of the two redos. Report it to the owner
  at once; a fresh round would be a second look at the same items and needs a v1.1 rule with whole-round caps. In this
  smoke only the optional S4 mini-step has an acceptance round, so the rule matters in the pilot (`pilot-runbook.md`).
  `recover` refuses a recovery for it (P2C, 14:10 row 17).

The ledger is `$SMOKE/shared/ledger`, with caps of 14M for the solver and 2M for GLM.

### 6.4 S-N1 and S4 (optional, never gating)

They are not part of this smoke. If either is wanted later, run it only after `smoke-summary` has written its result
(section 7), and alone: never beside S2 or S3, because S4's run unit has the same label as S3's. The commands are
those of `notes/C7c.md`: `$RUN --stage SN1 ...`; `$RUN --stage S4 ...`, then `smoke-recovery` on its drill, then
`$RUN --stage S4 ...` again. Their records appear in `$SMOKE/stages/` and never change the sealed result.

## 7. Exit

```bash
$CLI smoke-summary --spec $SMOKE/smoke.json
#   prints {"stages", "rows", "passed"}; writes $SMOKE/smoke-result.json once S0, S1, S2, S3 and SE6 are all recorded
```

The smoke passes when all five gating stages passed. S-N1 and S4 show `not_required` unless they are recorded, and they
never gate. Until all five are recorded, `smoke-summary` reports the missing ones and writes nothing. If any gating
stage fails, there is no main run: re-register as `fivebench-execskill-v1.1` with new directories, and re-run the
failed rows. On a pass the main agent starts the main experiment (registrar 17:0x; `main-runbook.md`).

## 8. Run data pins (after the smoke has passed; ticket C6-3)

- Main: `main-runbook.md` §3 (all five pools, `data.searchqa_tail`, `clients.routes`, `configuration: "main"`).
  The bullets below describe the default pilot, which is not run.
- `data.pools`: the `pins.pools` block that `export-pools` printed, for the benches of `protocol.ORDER`. For the default
  pilot these are `spreadsheetbench` and `officeqa`. The adapter checks each file's sha256 and orders the items with
  `supply.order`. The SpreadsheetBench file is already the 91 qualified items, and the adapter does not re-qualify.
- ALFWorld (main; registrar 17:0x, closes ticket I1-1): the pool file that `export-pools` builds from the new-game
  supply (`alfworld-xs`) and its views (section 3), not v3's 57-game pool.
- `data.research`, `data.test_read_estimate` and `data.pinned` (the frozen v3 data pins, as in
  `$IN/v3-data-pins.json`), as ticket C6-3 lists them. The test-read estimate is computed from S-E6's measurements
  (pilot-runbook §3.4; registrar addendum 14:10 row 8), and `data.test_read_terms` holds its exact per-bench terms
  for a relaunched read gate (registrar addendum 15:3x, ticket P2C-2; pilot-runbook §3.3).

## 9. Zero-call CLI rehearsal (optional; throwaway roots only; registrar addendum 15:0x)

The trimmed smoke can be rehearsed end to end through the CLI on the plan-§7 fakes, with zero network and no
credential: the scripted elucid gateway behind the real client, FakeDocker running the real sandbox worker, FakeAlfEnv
and FakeNative (`tests/`). The rehearsal never runs on the registered smoke or probe root (`smoke.rehearsal_roots`
refuses both) and refuses any credential argument. S1 to S-E6, the smoke result and a test-read estimate made from it
are labelled `engineering_fixture` (`smoke.REHEARSAL_EVIDENCE`), never `smoke`; S0, recorded by the manual path,
keeps its label, and the result is labelled by its rehearsal stages. Pilot-runbook §3.3 refuses such an estimate.

```bash
R=<a throwaway directory>      # never $PRE, $SMOKE or $PRE/probe
$CLI smoke-make --root $R/smoke --probe-root $R/probe --items <SET=FILE ...> --selftest <self-test record>
$CLI smoke --spec $R/smoke/smoke.json --stage S0 --input <checks>   # S0's supply row reads the exclusion records
$CLI probe --spec $R/smoke/smoke.json --fake                        # S1 on $R/probe: 41 scripted sends, branch E
#   then a smoke manifest of $R/smoke whose chain-D block carries S1's branch (the fakes' credential stand-ins);
#   for main it names "configuration": "main" and carries clients.routes (section 5), and S-E6 then projects main
$CLI smoke-run --spec $R/smoke/smoke.json --manifest $R/manifest.json --stage S2 --fake &   # S2 and S3 side by side
$CLI smoke-run --spec $R/smoke/smoke.json --manifest $R/manifest.json --stage S3 --fake; wait
$CLI smoke-run --spec $R/smoke/smoke.json --manifest $R/manifest.json --stage SE6 --fake
$CLI smoke-summary --spec $R/smoke/smoke.json
$CLI test-read-estimate --smoke $R/smoke --configuration main --out $R/test-read-estimate.json   # a fixture
#   estimate of the configuration S-E6 projected; --configuration refuses an S-E6 of another configuration
```

The supported way to run it is the test
`tests/test_execskill_cli.py::test_cli_rehearsal_runs_the_trimmed_smoke_end_to_end_as_an_engineering_fixture`, which
runs exactly this sequence with synthetic items, a synthetic exclusion unit, and slot and history roots under its
temporary directory (a smoke manifest records the slot and history roots it was made with, so a hand-made one would
name the registered ones). Run it on a fresh copy of the tree: the smoke re-checks the code map before every unit, so
a rehearsal on a tree whose files are changing fails (registrar addendum 15:0x).

The test runs twice. `[default]` rehearses the default projection. `[main]` makes the smoke manifest with
`"configuration": "main"` and `clients.routes`, so S-E6 projects main, runs `test-read-estimate --configuration main`,
and then continues with main-runbook §3.2 and §4 on a throwaway main root (`protocol.RUN_ROOTS["main"]` pointed at
it): a consent file, the main pins, `make-manifest --s0-pins`, a zero-call `manifest.setting_of` of chains G and D
(route A for D), and `consent --root`. It never touches `$MAIN` or `$MM`. The five-step fake end to end of `main` for
both chains (acceptance, freeze, chain D's `balance_exhausted` pause, `switch-route --to B`, `recover`, the redo on
route B, and the five-unit test read) is `tests/test_execskill_e2e_main.py`, an engineering fixture on small slices.
