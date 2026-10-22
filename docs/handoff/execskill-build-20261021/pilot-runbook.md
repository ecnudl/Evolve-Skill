# Route-B pilot runbook (dl, fivebench-execskill-v1)

Written by the pilot-runbook workflow agent on 2026-10-22 (dl clock 12:5x–13:1x) from read-only checks of the dev tree
`/data/execskill-dev` on dl, and checked for completeness and corrected at 13:4x (section 9). It covers the steps from "the trimmed smoke passed" to "chains G and D are running and
monitored", and on to the end of the pilot. It follows:

- registration §3.3, §3.4, §4.1, §4.4, §8.1, §9.2–§9.4, §11 and §21;
- plan §10 step 8;
- the registrar decisions of 2026-10-22, including the 13:0x smoke trim, the 13:2x owner authorization and the 13:4x,
  13:5x and 14:1x addenda. The owner said "不用，你直接开试点就行": the main agent makes the pilot manifest and starts both chains as soon as
  `smoke-summary` records a pass;
- `execskill-owner-checklist-20261022.md`;
- `smoke-runbook.md` (merged by I1 at 12:55), whose shell setup and paths it reuses.

**The operator is the main agent.** None of the commands below has been run. The pins file and the manifest do not
exist yet. The pilot root holds one file: the owner's read consent `$PILOT/shared/consent.json`, written by the owner
at 15:01 (registrar 15:1x: 252 bytes, sha256 prefix `2748d886fcb1b207`, `consent --root` → valid). Never touch it. While this was written and checked, other agents were editing
`acceptance`, `step`, `units`, `cells`, `evaluation`, `readout`, `smoke`, `smoke_roles`, `engines`, `solver`,
`examiner`, `manifest`, `budgets`, `generators/sheet.py` and `scripts/run_execskill.py`. Every step that depends on
unfinished work says "after <agent/ticket>".

**The owner does exactly one step by hand: the read consent `$PILOT/shared/consent.json` (section 7.1; registrar 13:2x,
owner checklist).** It is done: the owner wrote it at 15:01 (registrar 15:1x). Every other owner input is a decision. The main agent asks for it in plain Chinese, on
infrastructure facts and learning-side records only, records the owner's words verbatim, and never makes such a
decision itself: a `recover`, `resume-ledger` or `terminate` (6.3), a cap raise (6.4), and the continue/stop file and
the formal addendum (7.3).

**Status (dl 13:4x).** The runbook cannot be executed yet:

- The smoke: S3 is built (C7d), and the 13:0x trim and the 13:4x smoke-make defaults are in the code (rows 1–2). The
  smoke-runbook still describes the seven-stage smoke (row 1). Then come the main agent's steps: the whole-suite pass,
  the single Codex round, the commit, the final snapshot and `$Q23`.
- The pilot-readiness pieces landed in the dev tree between 13:35 and 13:45 and are still being tested by their
  builders (rows 3–6 and 13). They must all be in the final snapshot before smoke step 2.
- Rows 7, 8, 9 and 17 are closed in the dev tree by P2C (registrar addendum 14:10; `notes/P2C.md`): the
  first-call confirmation of each chain, the test-read estimate and chain G's corrected read gate, the chain-level
  wait for the read consent, and `recover`'s refusal of a finished acceptance round. Like rows 3–6 and 13, they must
  be in the final snapshot.
- A cap raise cannot clear a pause of chain G's cost check (row 18): chain G then ends, or waits for a v1.1 rule.

Every row of section 0 names the agent or ticket that closes it.

## 0. Blockers and open items

| # | What | Effect on the pilot | Closer | Needed by |
|---|---|---|---|---|
| 1 | S3 and the 13:0x trim. Built: `smoke_roles.py` and `smoke.run_stage(..., "S3")` (C7d; whole suite run at 13:41, notes/C7d.md); `smoke.SMOKE_STAGES` = S0, S1, S2, S3, SE6 is the spec's default `stages`; `summary` requires exactly the spec's stages and lists S-N1 and S4 as `not_required`; `SE6_STAGES` = S2, S3. Open: `smoke-runbook.md` (13:01) still lists S3 and the two smoke-make inputs as open and gives the old order S2 → SN1 → S4 → SE6 → S3; tickets C7d-1 (S3 in the rehearsal, then in `BUILT_STAGES`; `run_stage` already admits S3) and C7d-3 (`smoke-run --fake` passes a credential path by default). | An operator who follows the smoke-runbook as written would run the dropped S-N1 and S4 stages. | I1 phase 2 (smoke-runbook, C7d-1, C7d-3) | the smoke |
| 2 | `smoke-make --control-cells` and `--noise-anchor`: closed in the code at 13:39. Both are optional in the parser; `smoke.make` defaults to `control_cells=()` and `noise_anchor=None` and records the 13:0x reason when S-N1 is not a stage. | None, once the smoke-runbook stops passing the two flags (row 1). | registrar 13:4x; I1 phase 2 | the smoke |
| 3 | C6-1, the production SpreadsheetBench engines. PR-C61-1 landed: `manifest.services_of` binds `engines.sheet_engines` (13:35). The LiveMath checker half is still a TODO there (ticket C7d-2); the default pilot has no LiveMath step. PR-C61-2 landed in `generators/sheet.py` at 13:40 (P2-A1: `asset_sha256` binds the generated input and answer, and both workbooks are the qualified engine's recalculation; its tests pass on dl). Ticket P2-A1-1: an engines test still counts one recalculation per generated item instead of three. | Without both, step 1 of both chains pauses at `<c>/s1-spreadsheetbench/generate` (kind `configuration`): no generated SpreadsheetBench item passes the engine qualification. | P2-A1 (done 13:43); I1 phase 2 (P2-A1-1, C7d-2) | the final snapshot |
| 4 | C1-2, the SpreadsheetBench no-workbook shortcut probe. PR-C12 (`solver.py`, `cells.py`, `examiner.py`) is done. PR-C12-1 landed: `step._probe_shortcut` runs SpreadsheetBench's probe cells in `examiner.probe_mode` (P2-A2, 13:45, tests running). PR-C12-2 (two mutation entries, an e2e docstring) changes tests only. | Without PR-C12-1, the SpreadsheetBench shortcut gate stays `not_run` and no SpreadsheetBench set is admitted. | P2-A2 (PR-C12-1); I1 phase 2 (PR-C12-2) | the final snapshot |
| 5 | C3-1 (b), the read canaries and the run-root scan. PR-C31 is built (`make_read_canaries`, `root_scan`, `_root_scanned`). PR-C31-1 landed: one canary selection; `report` prints a paused scan and exits 3 or 5; `recover` accepts root-scan attempts; `monitor` lists `root_scans`. PR-C31-3 is landing (P2-A3, `evaluation.py` 13:41): the read record skips test texts that occur verbatim on the training side; the owner's release `release <scan record_sha256>` (`evaluation.release_check`, also checked by `recover`); a process pool for the scan. PR-C31-2: the e2e fixture must register the canary records. Until then the e2e errors at its unseal (C7d's suite run at 13:41: 12 failures and errors, all from this). | Without it, the read has no OfficeQA, LiveMath or SpreadsheetBench canaries, and a coincidental hit could block the unseal for good. | P2-A3 (PR-C31-3); I1 phase 2 (PR-C31-2) | the final snapshot |
| 6 | C7c-2, redo one acceptance block: closed (C7e, 13:16). Follow-ups: C7e-1, the G_acc cells charged to the examiner scope as registered, landed at 13:45 (P2-A2: `units.solver_endpoint(..., g_acc=True)`; registrar 13:5x). C7e-2 is decided (row 17). | Without C7e-1, OfficeQA's maximum-schedule accept margin is about 1.32× instead of 1.53×. | C7e; P2-A2 (C7e-1) | the final snapshot |
| 7 | **Closed by P2C (registrar addendum 14:10, row 7).** Was: the pilot path had no first-call confirmation (only the smoke's `smoke._confirm`), and chain G's solver settings (M = B = 65,536, read timeout 2,400 s) first run in the pilot. Now `chain.run` makes ONE solver call alone (`chain.first_call`) after `chain.json` and the ledger declaration and before step 1: the chain's own client and registered settings (chain G: M = B = 65,536; chain D: SpreadsheetBench's M and read timeout, S1's ledger bound), the fixture prompt `protocol.FIRST_CALL_SYSTEM` / `FIRST_CALL_USER` (no pool item, nothing consumed), charged to `<c>:solver` and its sub-scope `<c>:confirm` (cap `protocol.FIRST_CALL_CAP` = 1.1M). It passes when the reply is delivered (`ok`), the echoed model is the registered one, the ledger settled > 0 tokens and, for chain D, the receipt has no reasoning tokens or text. A pass is written once to `$PILOT/<c>/confirm.json` (counts, model, latency, hashes; no reply text) and every relaunch reuses it. A failure writes `confirm-failed-<n>.json` and pauses the chain (`first_call_unconfirmed`, unit `<c>/confirm`) before its first unit, with no unit attempt opened. Ticket P2C-1 (registrar 15:3x; I1 2b (c)): `step-unit` (`step.run_unit_spec`) refuses to start unless `$PILOT/<c>/confirm.json` is a verified, passed record of this run and chain (`chain.confirmation`), before anything is written, so no entry point skips the confirmation. | The rule "confirm the first actual model response before any concurrency" (plan §10 step 4, AGENTS.md) is met in code. Section 5.3 keeps the staggered start as the fallback. | P2C (done; tests in `test_execskill_chain.py`, mutation entries 37–43); I1 (P2C-1: mutation entries 56–57) | the final snapshot |
| 8 | **Closed by P2C (registrar addendum 14:10, row 8).** Was: `data.test_read_estimate` had no producer and no registered formula. Now `protocol.estimate_test_read` is the formula of section 3.4 (exact arithmetic; 54,409,087 at the §9.1 high anchors with ratio 1), and `run_execskill.py test-read-estimate --smoke $SMOKE --out $OPS/test-read-estimate.json` (zero calls) writes it once from the passed smoke's S-E6 record, as the sealed record `test-read-estimate` with its inputs. Section 3.3 copies its value into `data.test_read_estimate` for both chains. At the read gate chain G uses ⌈estimate × max(1, factor_G)⌉, factor_G = the per-cell factor of its latest passed `cap-check-G*.json` (S-E6 never prices GLM-5.3 solving); chain D uses the estimate. `test-read.json` records the gate: `estimate`, `units`, `part`, `factor`, `cap_check`, `used`, `need`. Ticket P2C-2 (registrar 15:3x; I1 2b (c)): the gate needs 1.3 × the estimate of the read units not yet complete; a relaunch after some read units completed prices the rest by the record's exact per-bench `terms`, which section 3.3 copies into `data.test_read_terms` for both chains. | `make-manifest` needs `$OPS/test-read-estimate.json` first (section 3.3). | P2C (done; mutation entries 44–49); I1 (P2C-2: mutation entries 58–59) | `make-manifest` |
| 9 | **Closed by P2C (registrar addendum 14:10, row 9).** Was: a missing consent made each read child fail, leaving a paused `attempt-1` (`child_failed_before_its_attempt`) in all five read units. Now `chain.run` checks the consent once before the read (`chain.read_consent` → `evaluation.consent` on `shared/consent.json`). Missing or invalid: no read attempt is opened, `$PILOT/<c>/read-waiting.json` is written (kind `consent_missing`, counts only; rewritten only with the same content), and `run` exits 3 with `{"status": "paused", "kind": "consent_missing", "unit": "<c>/test"}`. After the owner writes the consent, the main agent relaunches `run`: no `recovery.json`. The check inside each read child stays (PR-C31-3 (4)). | A late consent is a clean wait. The owner already wrote it at 15:01 (registrar 15:1x; section 7.1). | P2C (done; mutation entry 51) | the end of step 2 |
| 10 | No CLI for `Budget.raise_cap`. | Only a direct ledger call (section 6.4) can lift these: a second redo (attempt-3, which needs the owner's cap decision, §9.2), a `budget` pause and a `test_read_budget` pause. No raise lifts chain G's `cap_check` pause (row 18). | I1 (no ticket yet) | only if such a pause occurs |
| 11 | No learning-side report exists for the owner's continue/stop decision. `report` unseals test scores, and it needs that decision first. | The owner decides from the raw records (section 7.3). | I1 / main agent (no ticket yet) | the end of the pilot |
| 12 | The code does not fix the shapes of `contracts`, `fixtures` and `sheet_qualification`. They are recorded and never read, and the tests use other shapes. Plan §2.9 says `cards{bench: sha}`, but `cells.py:143` passes `cards[bench]` to the solver as the card text. Smoke-runbook §5 only says "as for the pilot". | Section 3.1 fixes the shapes. A smoke manifest built differently is copied unchanged, and the builder reports the mismatch. Hashes in `cards` would silently replace every task card. | I1: adopt section 3.1 in smoke-runbook §5 (no ticket yet) | the smoke manifest |
| 13 | PR-F2-1, the §6.2 per-15-minute series in every acceptance round (short-answer share, format share, reply length per arm): landed at 13:45 (`acceptance.series` in `decide`, P2-A2; registrar 14:1x), tests running. | Descriptive only. If it misses the snapshot, the series is missing from this pilot's records; disclose that. | P2-A2 | not blocking |
| 14 | The LiveMath checker is built (`generators.livemath.WorkerChecker`, C7d) but not bound in `services_of` (ticket C7d-2; a TODO in `manifest.py`). The v3 ALFWorld pool has only 57 games (I1-1: deferred to the formal chain's ALFWorld step, registrar 13:4x). | The default pilot uses neither: it has no LiveMath or ALFWorld step. | I1 phase 2b (C7d-2); the formal-chain addendum (I1-1) | not blocking |
| 15 | On the real test sets, the route-B read path has run only on fakes. That path is the frozen `coevo5.data.test_panel` (OfficeQA and LiveMath rendered from upstream) plus the SpreadsheetBench test qualification. The smoke opens no test set except in the two exclusion runs. | Its first real run is the pilot's read, after the learning side has been spent. A failure pauses that read unit (`configuration`) for the owner. | none (disclosed) | — |
| 16 | Every `recovery.json`, and the budget for a second redo, are owner decisions. | The main agent writes `recovery.json` (`recover`) only on an explicit owner instruction, never from a loop. | rule | always |
| 17 | C7e-2 (registrar 13:5x, choice 1): an acceptance round that pauses after its last cell is final. That is `acceptance_undetermined` (J5 or J6), or an error raised by `acceptance.decide` once every block is done. **Enforced by P2C (registrar addendum 14:10, row 17):** `recover` refuses such an attempt (`acceptance.finished_round`: every block complete, and the status kind `acceptance_undetermined`, an undetermined `decision.json`, or a `decide` frame in `diagnostics.log`) with "A finished acceptance round is final ...: no recovery.json is written, report the pause to the owner". | A `recover` can no longer spend a redo here. A fresh round needs a v1.1 rule. | P2C (done; mutation entries 52–55); rule (section 6.2): the main agent reports the pause to the owner at once | always |
| 18 | Chain G's cost check cannot be cleared by a cap raise. `step.cost_projection` projects every chain-G scope as ⌈cap ÷ 1.5 × factor⌉, where factor = ledger tokens per SpreadsheetBench run cell ÷ 4,273. So every scope breaches at once when chain G spends more than 6,409.5 ledger tokens per run cell, whatever the caps. The ledger charges each failed try of a call (a timeout or a server error; a refused request costs nothing) at its full bound, request bytes + 512 + 65,536, so a few timeouts count heavily. GLM-5.3 cells are likely dearer than the deepseek anchors (registration §4.1). Ticket C2-2's re-check after a raise never ends the pause. | A breach ends chain G: the owner terminates it or orders a v1.1 re-registration of its caps in new directories (registration §9.3). Chain D is unaffected. | rule (§9.3; section 6.2); the main agent tells the owner at the launch (5.4) | step 1, chain G |

The smoke and the pilot run on one snapshot. Rows 3–6 and 13, and P2C's code for rows 7, 8, 9 and 17, must therefore be in `$SRC`
before smoke step 2. Section 4 asserts that the pilot manifest's code map equals the smoke manifest's. If a pilot-readiness change
lands after the snapshot, it needs a new snapshot and so a new smoke (v1.1 directories): ask the registrar.

The steps each row blocks:

| Step | Blocked by |
|---|---|
| the smoke, and so everything after it | row 1 (the smoke-runbook), plus the main agent's sequence: the whole-suite pass, the Codex round, the commit, the final snapshot, `$Q23` |
| the final snapshot | rows 3–6 and 13 (landed; their tests and I1's follow-ups) and P2C's code for rows 7, 8, 9 and 17 (landed in the dev tree) |
| `make-manifest` | `test-read-estimate` (section 3.3; row 8 closed) and the go checks of section 2 |
| the launch | nothing more (row 7 closed: each `run` confirms its chain's first call; 5.3 is the fallback) |
| step 1 | row 3; for chain G, row 18 |
| step 2 (and step 1) | row 17: an acceptance round that pauses after its last cell is final |
| the test read | rows 5 and 15 (row 9 closed: a missing consent is a clean wait) |
| the owner's decision and the report | rows 10 and 11 |

## 1. Shell setup (every tmux window)

```bash
PY=/root/continual-alf-prep-20260928/env/bin/python                  # 3.11.16
SRC=/data/execskill-20261021-source        # protocol.SNAPSHOT_ROOT; never edited (a change terminates both chains)
PRE=/data/execskill-20261021-pre           # protocol.PRE_ROOT
IN=$PRE/inputs                             # OPS1's input files
SMOKE=$PRE/smoke                           # protocol.SMOKE_ROOT; shared/exclusion-consent.json: NEVER modify
HIST=/data/execskill-history               # protocol.HISTORY_ROOT: consumption/<G|D>/<bench>.jsonl
V3=/data/coevo5-20261019-v3-run-manifest.json
V3SHEET=/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json
V3SHEET_HASH=acc5c07f76a088969181cf45e8224fae2d4d033aa49385713802cba5338827a1   # record hash, not the file sha256
Q23=/data/execskill-20261021-sheet-q23     # this snapshot's v7 engine qualification (smoke-runbook §2b)
PILOT=/data/execskill-20261021-pilot       # protocol.PILOT_ROOT; make-manifest creates it
PM=/data/execskill-20261021-pilot-manifest.json   # protocol.PILOT_MANIFEST; written once
OPS=/data/execskill-20261021-ops           # protocol.OPS_ROOT: pins, launcher, run logs, readout (never inside $PILOT)
ELUCID=/root/.config/weak-solver/elucid.env          # chain D credentials: path only, never read or printed
GREPO=/root/continual-noskill-bcb-20260928-a         # chain G solver and every GLM role: credential repository, path only
export ALFWORLD_DATA=/root/continual-alf-prep-20260928/data
unset OPENAI_API_KEY OPENAI_BASE_URL; export PYTHONDONTWRITEBYTECODE=1
CLI="$PY -B $SRC/scripts/run_execskill.py"
cd $SRC
```

Log in with `ssh dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn` (there is no `dl` alias).

Proxy: do not run `proxy_on`, and do not export `HTTP(S)_PROXY`. Every pilot client uses `trust_env=False` and the
explicit gateway `protocol.GATEWAY` = `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128` (`client.py`,
`manifest.services_of`). That covers:

- chain D's elucid client;
- the frozen BigModel client, which serves chain G's solver and the GLM-5.3 roles;
- the research Wikipedia source.

Never print `.env`, a key or a proxy credential.

## 2. What the smoke must have produced

The pilot starts only from a passed, trimmed smoke (S0, S1, S2, S3, S-E6). The smoke outputs below feed it, and the
pilot never produces any of them a second time.

| Output | Path | Made by (smoke-runbook step) | Used in the pilot as |
|---|---|---|---|
| Smoke verdict | `$SMOKE/smoke-result.json`: `passed: true`; `required` = S0, S1, S2, S3, SE6, each `pass` in `stages` (which also lists S-N1 and S4, `not_required` unless they were run) | `smoke-summary` (§7) | the go condition (13:2x) |
| S0 pins | `$PRE/s0-pins.json`, exactly `{limits, measured}` | `s0-collect` (§3) | `make-manifest --s0-pins`. The operator's pins give neither key. |
| S1 branch and longest | `$SMOKE/stages/S1.json` → `result.branch` (`E` or `N`) and `result.longest` (an int on N, else null) | `probe` + `smoke --stage S1` (§4) | chain D's solver block. B = 2 × M on E and max(4 × M, ⌈1.5 × longest⌉) on N, M being the bench's nominal max_tokens (`protocol.ledger_bound`). |
| Exclusion records and canaries | `$SMOKE/shared/exclusion/{searchqa_test_exclusion,alfworld_test_identity_check,test-canaries}.json` | `exclude-tests`, under the owner's exclusion consent (§3) | `make-manifest --exclusion-root $SMOKE` verifies them and binds `data.exclusion` = {name: {path, record_sha256}}. It writes the canaries record once, as `$PILOT/shared/test-canaries.json` (ticket fixer-4). No second exclusion run and no second exclusion consent. |
| SpreadsheetBench runtime | `$PRE/sheet-runtime.json`: the v3 block, with `recalculation.{qualification_path, qualification_sha256, qualification_hash}` taken from `$Q23/qualification.json` | step 2b + `sheet-runtime` (C7b1-3) | `runtime.spreadsheetbench`. `make-manifest` revalidates it offline. |
| Texts import | `$PRE/texts/texts.json` (`cards` = the five card texts, plus `card_sha256`) | `import-texts` (§3) | `cards` |
| Sheet-qualification import | `$PRE/sheet/` (the re-verified v3 training qualification: 120 items, 91 qualified) | `import-sheet-qualification` (§3) | S0 evidence. `sheet_qualification` names the same source, and the SpreadsheetBench pool is its 91 qualified items. |
| Pools | `$PRE/pools/{spreadsheetbench,officeqa}.json` + the sealed `$PRE/pools/pools.json` | `export-pools` (§3) | `data.pools` for `protocol.ORDER`. SpreadsheetBench 91 items = run 31 + accept 60. OfficeQA 74 = run 24 + accept 50. |
| Fixtures record | `$PRE/fixtures/fixtures.json` | `make-fixtures` (§3) | `fixtures` |
| Snapshot provenance | the `verify-snapshot` output (= `.provenance` of `$SMOKE/manifest.json`) | §2 | `provenance` |
| S-E6 | `$SMOKE/stages/SE6.json` → `result.per_cell`, `.ratio`, `.scopes`, `.anchors` | `smoke-run --stage SE6` (§6). With the trim it reads the S2 and S3 records (`smoke.SE6_STAGES`). | `data.test_read_estimate` (§3.4) and the cost report |
| Smoke manifest | `$SMOKE/manifest.json` | `make-manifest` (§5) | the given fields the pilot shares with the smoke (section 3) |

Go checks. They make zero model calls, and each must pass before section 3.

```bash
mkdir -p $OPS && chmod 700 $OPS
test ! -e $PM && echo "no pilot manifest yet"                        # make-manifest refuses an existing file
# registrar 15:1x: $PILOT already holds the owner's read consent. Exactly shared/consent.json, plus
# shared/test-canaries.json on a retry of section 4; anything else: stop and ask
found=$(cd $PILOT && find . -type f | LC_ALL=C sort | tr '\n' ' ')
case "$found" in
  "./shared/consent.json "|"./shared/consent.json ./shared/test-canaries.json ") echo "pilot root ok: $found";;
  *) echo "STOP, ask: $PILOT holds $found";;
esac
$CLI consent --root $PILOT          # {"test_read": "valid"}: the owner's read consent (never edit or rewrite it)
$PY -B - <<EOF
import json, sys; sys.path.insert(0, '$SRC')
from skillopt.continual_eval.core import read_json
from skillopt.execskill import protocol
r = protocol.verified(read_json('$SMOKE/smoke-result.json'), 'smoke-result')
s1 = protocol.verified(read_json('$SMOKE/stages/S1.json'), 'smoke-stage')['result']
se6 = protocol.verified(read_json('$SMOKE/stages/SE6.json'), 'smoke-stage')['result']
print(json.dumps({'stages': r['stages'], 'required': r['required'], 'passed': r['passed'], 'branch': s1['branch'], 'longest': s1['longest'],
                  'se6_passed': se6['passed'], 'ratio': se6['ratio'],
                  'above_high': {b: a['above_high'] for b, a in se6['anchors'].items()}}))
assert r['passed'] is True and sorted(r['required']) == ['S0', 'S1', 'S2', 'S3', 'SE6'] and all(
    r['stages'][s] == 'pass' for s in r['required'])   # 'stages' also lists SN1 and S4 (not_required)
EOF
$CLI consent --root $SMOKE          # {"exclusion": "valid"}
$CLI leftovers                      # "clean" or "cannot_judge" (D3/D14 workers excluded by command line): pass
$CLI monitor --root $SMOKE          # the smoke ledger: no "halted", nothing open
$CLI verify-snapshot --list $PRE/source-sha256.txt --root $SRC --git-head "$(cat $PRE/build-head.txt)" \
     > $OPS/pilot-provenance.json   # the builder (3.3) requires it to equal the smoke manifest's provenance
```

Stop and ask instead of continuing in any of these cases:

- **A required stage is not `pass`.** Then there is no pilot. Re-register the failed rows as `fivebench-execskill-v1.1` with new
  directories (§10 exit; unchanged at 13:2x).
- **An `above_high` flag is true.** That bench's measured cost per card cell is more than 1.25 × its high anchor. Plan
  §10 step 6 requires a written pre-pilot amendment from the registrar first.
- **S1 chose branch N and a completion above B was seen in S1 or S2** (the smoke ledger shows `halted`). Plan §11:
  stop, and the main agent asks the owner for a decision.
- **`leftovers` prints `leftovers`.**

## 3. The pilot pins file `$OPS/pilot-pins.json`

`manifest.make` requires exactly `GIVEN` = {root, data, sheet_qualification, cards, contracts, runtime, clients,
fixtures, provenance}. `make-manifest` also takes `evidence` from the pins and `limits` + `measured` from `--s0-pins`.
It stamps everything else: `caps` = `budgets.caps()`, the code map of `$SRC`, the prompt and lexicon hashes, and the
sandbox and environment blocks.

### 3.1 Keys and their sources

| Key | Value | Exact source |
|---|---|---|
| `root` | `/data/execskill-20261021-pilot` | `protocol.PILOT_ROOT` |
| `evidence` | `"pilot_real_run"` | `protocol.EVIDENCE`. `setting_of` refuses to run chains G and D on a `smoke` manifest. |
| `data.pools` | `{"spreadsheetbench": {path, sha256}, "officeqa": {path, sha256}}` | `supply.pool_pins($PRE/pools/pools.json)`, restricted to `protocol.ORDER`. These are the `pins.pools` that `export-pools` printed. |
| `data.research` | `{"archive": "/data/coevo5-20261019-v3-archive", "index_sha256": "7219096c…f2725"}` | the smoke manifest's `data.research` (v3's archive). `services_of` requires exactly these two keys and re-hashes the index. |
| `data.pinned` | v3's `data` block (16 pins) | `$IN/v3-data-pins.json` (sha256 `0f07ad48…`), asserted equal to the `data` of `$V3`. The read's test panels (`data.test_panel`) and the read canaries use it. |
| `data.test_read_estimate` | `{"G": int, "D": int}` | the `value` of `$OPS/test-read-estimate.json` (`run_execskill.py test-read-estimate`, sections 3.3 and 3.4; row 8) |
| `data.exclusion` | — (do not write it) | bound by `make-manifest --exclusion-root $SMOKE` |
| `sheet_qualification` | `{"path": "$V3SHEET", "record_hash": "$V3SHEET_HASH"}` | smoke-runbook §5. Recorded only. |
| `cards` | `{bench: card text}`, five texts | `.cards` of `$PRE/texts/texts.json`: 1,846 / 2,926 / 2,068 / 2,907 / 2,301 characters (`CARD_IDENTITY`). These must be texts, not hashes: `cells.py:143` hands `cards[bench]` to the solver as the card. |
| `contracts` | `{bench: {"text": guard, "sha": sha256(guard)}}` | the frozen format guards (registration §2.2, `continual_eval/backends.py`): SearchQA and OfficeQA, the literal at l. 381–382; LiveMath, `LIVEMATH_CONTRACT` (l. 35); SpreadsheetBench, `SHEET_CONTRACT_V2` (l. 53–56); ALFWorld, the system line at l. 730. Recorded only. The texts and hashes are in 3.2. |
| `runtime` | v3's `runtime`, with `spreadsheetbench` replaced | `.runtime` of `$V3` + `$PRE/sheet-runtime.json`. Its `alfworld` entry must equal `$IN/alfworld-runtime.json`. |
| `clients` | `{"solver": {"G": …, "D": …}, "roles": …}` | `manifest.solver_block('G', env_path=$GREPO)`; `manifest.solver_block('D', env_path=$ELUCID, branch=<S1>, longest=<S1>)`; `manifest.ROLES`. `solver_block` reads no credential, and `check_clients` re-derives every field, B included. |
| `fixtures` | `{"sha256": <sha256 of $PRE/fixtures/fixtures.json>}` | the fixture set of S0 and S2. Recorded only. |
| `provenance` | `{build_tree, git_head, snapshot_root, sha256_list_sha256, env_files_absent: true}` | `verify-snapshot` (= the smoke manifest's) |

The solver blocks fix the client of each chain:

| Field | Chain G | Chain D |
|---|---|---|
| backend | `bigmodel` (frozen client) | `elucid` |
| model | `glm-5.3` | `deepseek-v4.1-flash-1017` |
| M (nominal `max_tokens`) | 65,536 on every bench | 8,192 on the QA benches, 16,384 on SpreadsheetBench, 1,024 per ALFWorld step |
| B (ledger bound) | = M | 2 × M on S1's branch E; max(4 × M, ⌈1.5 × longest⌉) on branch N |
| read timeout | 2,400 s | 600 s (QA), 900 s (SpreadsheetBench), 180 s (ALFWorld) |
| slots | 10 glm-5.3, one machine-wide pool shared with both chains' GLM-5.3 roles | 8 elucid, chain D only |
| `reasoning_effort` | `low` | `none` |
| `proxy` | the gateway | the gateway |

The method roles of both chains are GLM-5.3 through chain G's credential repository (`manifest.setting_of`).

Machine-wide pools, shared by both chains (`protocol.SLOTS`, `protocol.SANDBOX_SLOTS`; plan §5): `spreadsheet-native` 3
(2 when S0's native peak RSS exceeds 2 GiB, `NATIVE_SLOTS_LOW_MEMORY`), `alfworld-episode` 6, live sandboxes 6 (at most
2 per SpreadsheetBench unit), per-call sandboxes 4. A unit runs up to 16 cell threads (`units.Setting.workers`;
ALFWorld 6).

### 3.2 JSON template

`<smoke: …>` marks a value that a smoke output fills. `<file: …>` marks the verbatim contents of an existing file that is
too long to inline. Every other value is literal.

````json
{
  "root": "/data/execskill-20261021-pilot",
  "evidence": "pilot_real_run",
  "data": {
    "pools": {
      "spreadsheetbench": {"path": "/data/execskill-20261021-pre/pools/spreadsheetbench.json",
                           "sha256": "<smoke: export-pools pins.pools.spreadsheetbench.sha256>"},
      "officeqa": {"path": "/data/execskill-20261021-pre/pools/officeqa.json",
                   "sha256": "<smoke: export-pools pins.pools.officeqa.sha256>"}
    },
    "research": {"archive": "/data/coevo5-20261019-v3-archive",
                 "index_sha256": "7219096cbb7e487439b5598dc12660f639562221c2167744f20c895f8bb2f725"},
    "pinned": "<file: the object in /data/execskill-20261021-pre/inputs/v3-data-pins.json>",
    "test_read_estimate": {"G": "<smoke: test-read-estimate value, int>", "D": "<smoke: the same value>"},
    "test_read_terms": {"G": "<smoke: test-read-estimate terms, {bench: \"p/q\"}>", "D": "<smoke: the same terms>"}
  },
  "sheet_qualification": {"path": "/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json",
                          "record_hash": "acc5c07f76a088969181cf45e8224fae2d4d033aa49385713802cba5338827a1"},
  "cards": "<smoke: .cards of /data/execskill-20261021-pre/texts/texts.json>",
  "contracts": {
    "searchqa": {"text": "\nReturn the concise final answer inside <answer>...</answer>.",
                 "sha": "f8daf424a4bc76b780b0c3228b8976962078daae51a1a880c795bd266be1b935"},
    "officeqa": {"text": "\nReturn the concise final answer inside <answer>...</answer>.",
                 "sha": "f8daf424a4bc76b780b0c3228b8976962078daae51a1a880c795bd266be1b935"},
    "livemath": {"text": "\nChoose exactly one of the listed options and return only its letter inside <answer>...</answer>.",
                 "sha": "97e1b962ad224d2f94cf97eb9e836c3b93c45858921a192daab562d946e30f80"},
    "spreadsheetbench": {"text": "\nReturn one complete Python program in a ```python code block whose opening fence starts its own line. The program reads input.xlsx and saves output.xlsx with the answer at the required answer position. A formula alone is not an answer: when the task asks for a formula, the program writes it into the answer cells.",
                         "sha": "6dbedf61afdbc571804acbc95bdd8c7dd57ba4e9ce0e1c9c1c154b2a506b120f"},
    "alfworld": {"text": "Act in the text environment. Return a single action inside <action>...</action>.",
                 "sha": "844c8c18ec0c0ee417247a4135c15c8f861a7782e39177b0cdd4fd197696429e"}
  },
  "runtime": "<file: .runtime of /data/coevo5-20261019-v3-run-manifest.json, with spreadsheetbench = <smoke: /data/execskill-20261021-pre/sheet-runtime.json>>",
  "clients": {
    "solver": {"G": "<smoke: solver_block('G', env_path='/root/continual-noskill-bcb-20260928-a') on the final snapshot>",
               "D": "<smoke: solver_block('D', env_path='/root/.config/weak-solver/elucid.env', branch=<S1 branch>, longest=<S1 longest>)>"},
    "roles": {"model": "glm-5.3", "max_tokens": 16384, "read_timeout": 900, "reasoning": "low"}
  },
  "fixtures": {"sha256": "<smoke: sha256 of /data/execskill-20261021-pre/fixtures/fixtures.json>"},
  "provenance": "<smoke: the verify-snapshot block>"
}
````

The contract hashes were computed from the frozen `backends.py` source on 10/22. The solver blocks are smoke outputs
because their `client_source_sha` hashes the final snapshot's `client.py`.

### 3.3 Build the pins (zero calls, written once)

```bash
# section 3.4 (registrar addendum 14:10, row 8): the S-E6-corrected test-read estimate, a sealed record, written once
$CLI test-read-estimate --smoke $SMOKE --out $OPS/test-read-estimate.json
#   prints {"out", "test_read_estimate": {"D": n, "G": n}, "record_sha256"}; refuses an existing file, and a smoke
#   whose result or S-E6 stage did not pass. The record also holds the per-bench terms (ticket P2C-2) and the smoke's
#   evidence label (a rehearsal smoke's estimate is an engineering fixture, registrar 15:0x)
$PY -B - <<EOF
import hashlib, json, math, sys
sys.path.insert(0, '$SRC')
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json
from skillopt.execskill import manifest, protocol, supply
sha = lambda path: hashlib.sha256(open(path, 'rb').read()).hexdigest()
smoke = manifest.load('$SMOKE/manifest.json', verify=False)      # the sealed smoke manifest (record and fields checked)
v3 = read_json('$V3', sealed=True)
s1 = protocol.verified(read_json('$SMOKE/stages/S1.json'), 'smoke-stage')['result']
se6 = protocol.verified(read_json('$SMOKE/stages/SE6.json'), 'smoke-stage')['result']
# fields a pilot unit reads: rebuilt from their sources, and equal to the smoke's (else stop)
runtime = {**v3['runtime'], 'spreadsheetbench': read_json('$PRE/sheet-runtime.json')}
cards = read_json('$PRE/texts/texts.json')['cards']
clients = {'solver': {'G': manifest.solver_block('G', env_path='$GREPO'),
                      'D': manifest.solver_block('D', env_path='$ELUCID', branch=s1['branch'], longest=s1['longest'])},
           'roles': manifest.ROLES}
pinned = read_json('$IN/v3-data-pins.json')
assert runtime['alfworld'] == read_json('$IN/alfworld-runtime.json'), 'alfworld runtime'
assert sorted(cards) == sorted(protocol.BENCHES) and all(isinstance(t, str) and len(t) > 1000 for t in cards.values())
assert pinned == v3['data'], 'data.pinned must be the v3 data block'
for key, value in (('runtime', runtime), ('cards', cards), ('clients', clients)):
    assert smoke[key] == value, key + ': the smoke manifest differs, stop'
assert smoke['provenance']['snapshot_root'] == '$SRC' and smoke['provenance']['env_files_absent'] is True
assert json.load(open('$OPS/pilot-provenance.json')) == smoke['provenance'], 'the snapshot changed since the smoke'
# recorded-only fields: the smoke's value is kept (one value per field); the output says whether it is section 3.1's
qa = '\nReturn the concise final answer inside <answer>...</answer>.'
guards = {'searchqa': qa, 'officeqa': qa, 'livemath': backends.LIVEMATH_CONTRACT,
          'spreadsheetbench': backends.SHEET_CONTRACT_V2,
          'alfworld': 'Act in the text environment. Return a single action inside <action>...</action>.'}
defined = {'contracts': {b: {'text': t, 'sha': hashlib.sha256(t.encode('utf-8')).hexdigest()} for b, t in guards.items()},
           'fixtures': {'sha256': sha('$PRE/fixtures/fixtures.json')},
           'sheet_qualification': {'path': '$V3SHEET', 'record_hash': '$V3SHEET_HASH'}}
# section 3.4 (registrar addendum 14:10, row 8): the estimate test-read-estimate wrote, of this smoke, recomputed
found = protocol.verified(read_json('$OPS/test-read-estimate.json'), 'test-read-estimate')
spec = protocol.verified(read_json('$SMOKE/smoke.json'), 'smoke-spec')
assert found['smoke']['spec'] == spec[protocol.RECORD_HASH], 'the estimate of another smoke, stop'
assert found['value'] == protocol.estimate_test_read(se6['per_cell'], se6['ratio']), 'the estimate differs, stop'
assert found['evidence'] == 'smoke', 'the estimate of a rehearsal (an engineering fixture), stop'
estimate = found['value']
pools = supply.pool_pins(read_json('$PRE/pools/pools.json'))
pins = {'root': protocol.PILOT_ROOT, 'evidence': 'pilot_real_run',
        'data': {'pools': {b: pools[b] for b in protocol.ORDER}, 'research': smoke['data']['research'],
                 'pinned': pinned, 'test_read_estimate': {'G': estimate, 'D': estimate},
                 'test_read_terms': {'G': found['terms'], 'D': found['terms']}},   # ticket P2C-2
        'runtime': runtime, 'cards': cards, 'clients': clients,
        **{k: smoke[k] for k in ('sheet_qualification', 'contracts', 'fixtures', 'provenance')}}
assert set(pins) == manifest.GIVEN | {'evidence'}
with open('$OPS/pilot-pins.json', 'x') as out:                     # 'x': written once, never overwritten
    json.dump(pins, out, indent=1, sort_keys=True, ensure_ascii=False)
print(json.dumps({'pins': '$OPS/pilot-pins.json', 'sha256': sha('$OPS/pilot-pins.json'), 'branch': s1['branch'],
                  'longest': s1['longest'], 'ratio': se6['ratio'], 'test_read_estimate': estimate,
                  'research': pins['data']['research'], 'pools': {b: pools[b]['sha256'][:16] for b in protocol.ORDER},
                  'as_defined': {k: smoke[k] == v for k, v in defined.items()}}, indent=1))
EOF
```

The pins hold paths, hashes, the card texts and the runtime. They hold no credential.

- If an `assert` fails, stop: the pilot would differ from what the smoke ran.
- If `as_defined` shows `false`, the pilot keeps the smoke's value of that field, which is recorded only. Note it for
  I1 (row 12).

### 3.4 The test-read estimate (registrar addendum 14:10, row 8; built by P2C)

estimate = ⌈ ratio × Σ_b n_b × (card_b + 4 × f_b × proc_b) ⌉, in ledger tokens, where:

- **n_b** is the number of test items, `protocol.TEST_READ_CELLS["default"][b][0]`: SearchQA 400, OfficeQA 172,
  LiveMath 125, SpreadsheetBench 279, ALFWorld 134.
- **card_b and proc_b** are S-E6's measured tokens per card cell and per procedure cell (`result.per_cell`). A bench with
  no measured procedure cell is priced at 1.6 × its card cell.
- **f_b** is the high fired share of §9.2: 1.0 for the home benches (SpreadsheetBench, OfficeQA), 0.7 for the similar
  ones (SearchQA, LiveMath), 0.5 for the other one (ALFWorld).
- **4** counts F, P_F and T_F on a fired item plus one twin. Calc T5 takes one twin per fired item at the high end; the
  maximum schedule takes 2.
- **ratio** is S-E6's ledger/actual ratio (`result.ratio`), because `chain.read_budget` compares the estimate with what
  is left on the ledger.

`protocol.estimate_test_read` computes it exactly (every input as a Fraction, one ceiling at the end), and
`run_execskill.py test-read-estimate` writes it once from the passed smoke (section 3.3). With the §9.1 high anchors
(card = the high anchor, procedure = 1.6 × card, ratio 1), the formula gives 54,409,087 (= 272,045,432 / 5, rounded
up). That is calc T5's high estimate with twins, 54.4M. The start rule then needs 1.3 × 54.4 = 70.7M left on both
`<c>:solver` and `<c>:test` (cap 99M).

Both chains carry the same number in the manifest. S-E6 prices chain G at the elucid per-cell tokens, a placeholder,
and GLM-5.3 cells are likely dearer (calc T11). So at the read gate (`chain.read_budget`) chain G uses
⌈estimate × max(1, factor_G)⌉, where factor_G is the per-cell factor of its latest passed cost check
(`cap-check-G.json`, or `cap-check-G-<n>.json`: ledger tokens per SpreadsheetBench run cell ÷ 4,273); chain D uses
the estimate. `test-read.json` records the gate (`estimate`, `units`, `part`, `factor`, `cap_check`, `used`, `need`).
The cost check itself may pause chain G after its first run unit, and a cap raise cannot clear that pause (row 18). The
estimate in the manifest cannot change after `make-manifest`.

A relaunched read (ticket P2C-2, registrar 15:3x) is priced by what is still to read. On a first start all five read
units are still to run, so `part` = the estimate. After some read units completed (a `unit.json`) and one paused,
`part` = ⌈Σ of the per-bench `terms` of the units still to run⌉, from `data.test_read_terms[<c>]`, the record's exact
terms (`protocol.read_estimate_terms`; their sum rounds up to the estimate, and `manifest.setting_of` refuses terms that
do not). Chain G's `used` = ⌈part × max(1, factor_G)⌉, chain D's `used` = part, and `need` = ⌈1.3 × used⌉ on both
`<c>:solver` and `<c>:test`. So the read already spent is not charged again, and a resume after a paused read unit
needs a raise only when what is left cannot cover the units still to run.

### 3.5 Caps (stamped by `make`, not in the pins)

`make` stamps `budgets.caps()`. Each chain's ledger, `$PILOT/shared/ledger-<c>`, declares `budgets.chain_caps(c)` and
`budgets.first_call_caps(c)` at every `run`, and the frozen ledger keeps a cap the owner raised (registration §9.3;
calc T6, T11). The caps per chain:

| Scope | Cap | §9.3 row |
|---|---|---|
| `overall` | 210M | solver + GLM of the chain |
| `<c>:solver` | 180M | steps 61.3 + test read 99 + redo reserve 14.8 = 175.1, rounded up |
| `<c>:test` | 99M | the test read (1.5 × its maximum 65.4M + one reservation) |
| `<c>:redo` | 14.8M | redo reserve = the largest single acceptance block (one OfficeQA block) |
| `<c>:glm` | 30M | GLM-5.3 roles |
| `<c>:confirm` | 1.1M | the first-call confirmation, charged inside `<c>:solver` (registrar addendum 14:10, row 7): four full reservations at B = 65,536, rounded up. Not in `chain_caps`, S-E6 or chain G's cost projection. |
| `<c>:xs:spreadsheetbench:1:{run,examiner,selftest,accept}` | 1.2 / 3.5 / 2.6 / 8.3M | step 1 |
| `<c>:xs:officeqa:2:{run,examiner,selftest,accept}` | 2.3 / 7.3 / 6.6 / 29.5M | step 2 |
| `…:<kind>:attempt-2` and `…:<kind>:attempt-3` | min(step cap, 14.8M) | redo sub-scopes |
| `<c>:xs:<bench>:<k>:role:{engineer,examiner,examiner:research}` | 2.5 / 3.0 / 4.6M per step (10.1M; 20.2M for the two steps) | roles; registrar R7 decision 16:1x (R7b) raised engineer 1.5 → 2.5M and examiner 2.5 → 3.0M (registered 1.5 / 2.5 / 4.6M, calc T11). The engineer scope also carries the leakage adjudications and the describer; `ENGINEER_CALLS` = 6 is per step, shared by `engineer` and `engineer-2` (R7a). |

For both chains together: solver 360M, GLM 60M. The manifest's `caps` lists both chains, with `overall` = 420M.

The first-call confirmation (5.3) is an ordinary solver call (registrar addendum 15:0x): its reservation (about 264,596
ledger tokens at chain G's B = 65,536) and its settlement count against `<c>:solver` and the root (`overall`) like any
cell, besides `<c>:confirm`. No cap changes for it, and S-E6 does not model it.

## 4. Pilot manifest (zero model calls)

```bash
$CLI make-manifest --out $PM --pins $OPS/pilot-pins.json --exclusion-root $SMOKE --s0-pins $PRE/s0-pins.json
#   1. revalidates runtime.spreadsheetbench offline from $SRC (C7b1-3); nothing is written if that fails
#   2. verifies the three S0 records under $SMOKE/shared/exclusion and binds data.exclusion
#   3. writes $PILOT/shared/test-canaries.json once
#   4. writes the sealed manifest: code map of $SRC, docker image inspect + one sandbox ping
#   prints {"manifest", "run", "root", "exclusion"}
$PY -B - <<EOF
import json, sys; sys.path.insert(0, '$SRC')
from skillopt.execskill import budgets, manifest, protocol
pm = manifest.load('$PM')                                       # verified: code map, interpreter, image (zero calls)
sm = manifest.load('$SMOKE/manifest.json', verify=False)
same = {k: pm[k] == sm[k] for k in ('code', 'environment', 'sandbox', 'clients', 'runtime', 'cards', 'contracts',
                                    'fixtures', 'provenance', 'prompt_sha', 'lexicon_sha', 'templates')}
print(json.dumps({'run': pm[protocol.RECORD_HASH], 'evidence': pm['evidence'], 'root': pm['root'],
                  'same_as_smoke': same, 'exclusion': sorted(pm['data']['exclusion']),
                  'test_read_estimate': pm['data']['test_read_estimate'],
                  'test_read_terms': pm['data']['test_read_terms'],   # ticket P2C-2
                  'caps': {k: v for k, v in sorted(pm['caps'].items()) if k.count(':') == 1 or k == budgets.ROOT}},
                 indent=1))
assert all(same.values()) and pm['caps'] == budgets.caps() and pm['evidence'] == 'pilot_real_run'
EOF
$CLI consent --root $PILOT          # {"test_read": "valid"}: the owner's consent of 15:01 (registrar 15:1x), unchanged
```

If any `same_as_smoke` value is false, stop. The pilot would run code, an environment or settings that the smoke did not
exercise; ask the registrar. If `make-manifest` fails after step 3, rerun it: the canaries write is idempotent for
identical content.

## 5. Launch (two tmux sessions on dl)

### 5.1 Network and TLS check (no model call, no credential)

AGENTS.md: check the route separately from authorization.

```bash
for C in D G; do
  H=$($PY -B -c "import json; print(json.load(open('$PM'))['clients']['solver']['$C']['url_host'])")
  curl -sS -o /dev/null --max-time 30 --proxy http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 \
       -w "$C http=%{http_code} connect=%{time_connect}s tls=%{time_appconnect}s\n" "https://$H/"
done
#   any HTTP status (401/404 included) shows that the gateway route and TLS work; a timeout is a network fault, not a key problem
```

### 5.2 Launcher and sessions

```bash
cat > $OPS/pilot-run.sh <<'EOF'
#!/bin/bash
# One pilot chain (G or D) of fivebench-execskill-v1. No proxy_on: the clients carry protocol.GATEWAY, trust_env=False.
set -u
C=${1:?chain G or D}
OPS=/data/execskill-20261021-ops
export ALFWORLD_DATA=/root/continual-alf-prep-20260928/data PYTHONDONTWRITEBYTECODE=1
unset OPENAI_API_KEY OPENAI_BASE_URL HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
cd /data/execskill-20261021-source || exit 2
n=1; while [ -e "$OPS/pilot-$C-run-$n.log" ]; do n=$((n+1)); done
log="$OPS/pilot-$C-run-$n.log"
echo "START $(date -u +%FT%TZ) chain $C" > "$log"
/root/continual-alf-prep-20260928/env/bin/python -B scripts/run_execskill.py run \
    --manifest /data/execskill-20261021-pilot-manifest.json --chain "$C" >> "$log" 2>&1
echo "EXIT $? $(date -u +%FT%TZ)" >> "$log"
EOF
chmod 700 $OPS/pilot-run.sh
tmux new-session -d -s execskill-pilot-D "$OPS/pilot-run.sh D; exec bash"     # chain D first
#   ... until $PILOT/D/confirm.json exists (section 5.3) or D's log has an EXIT line, then:
tmux new-session -d -s execskill-pilot-G "$OPS/pilot-run.sh G; exec bash"
```

At the end, each `run` prints its summary into its log as indented JSON: `{"status": "complete"}`, or
`{"status": "paused", "kind", "reason", "unit"}`, or `{"status": "terminated", "reason"}`. The launcher then appends
`EXIT 0` (complete) or `EXIT 3` (paused or terminated). Any other code, usually `EXIT 1`, is a crash outside a unit (for
example, a manifest that no longer verifies), with its traceback in the log: report it, and relaunch only once the cause
is known. The session stays open (`exec bash`).

One `run` does this, in order:

1. It verifies the manifest: code map, interpreter and image.
2. It writes `$PILOT/<c>/chain.json` and declares `chain_caps` and `<c>:confirm` on `$PILOT/shared/ledger-<c>`.
3. The first-call confirmation (row 7, section 5.3): one solver call alone, then `confirm.json`; a relaunch reuses
   it. A failure pauses the chain here (`first_call_unconfirmed`, 6.2).
4. Step 1, SpreadsheetBench: the units are run, diagnose, generate, engineer, selftest, [engineer-2, selftest-2],
   accept and freeze. Every SpreadsheetBench unit holds the machine-wide lock `/data/execskill-slots/memory-heavy.lock`
   exclusively, so G's and D's SpreadsheetBench units run one at a time.
5. Chain G only: the cost check after its first run unit (`cap-check-G.json`). A breach pauses chain G, and a cap
   raise cannot clear it (6.2, row 18).
6. Step 2, OfficeQA. It takes no memory lock, and acceptance runs in two blocks of 25 items at least 2 h apart.
7. The test read, if anything was accepted (section 7): the consent check (row 9), the read gate (row 8), the five
   read units.
8. It writes `chain-complete.json`.

The pinned files are verified before every unit. A change terminates the chain (`chain-terminated.json`,
`manifest_mismatch`). Never edit `$SRC`, and never start a second `run` of a chain while its first is alive
(`.runner.lock`).

### 5.3 First-call confirmation (built by P2C, row 7; the staggered start below is the fallback)

Each `run` confirms its own chain's first call before its first unit (row 7): `$PILOT/<c>/confirm.json` appears
before `$PILOT/<c>/s1-spreadsheetbench/`. Check it (no reply text is stored):

```bash
for C in D G; do $PY -B -c "import sys; sys.path.insert(0, '$SRC')
from skillopt.continual_eval.core import read_json; from skillopt.execskill import protocol
r = protocol.verified(read_json('$PILOT/$C/confirm.json'), 'first-call')
print('$C', {k: r[k] for k in ('passed', 'model', 'returned_model', 'charged', 'seconds', 'checks')})"; done
```

On `first_call_unconfirmed` (`EXIT 3`; `$PILOT/<c>/confirm-failed-<n>.json` holds the failed checks, the error type
and the counts): no unit attempt was opened and nothing was consumed. Rerun 5.1 (network and TLS apart from
authorization), and relaunch `run` once the cause is known. That needs no owner decision and no `recovery.json`
(addendum 14:10). Each relaunch makes one new call charged to `<c>:confirm`; a `BudgetStop` there means the
confirmations have used up their 1.1M cap: report it to the owner.

Fallback, only for a snapshot without row 7's code (needs the registrar's OK):

1. **Smoke evidence.** S1 confirmed one elucid reply alone through chain D's client and the gateway (row f). S3 ran the
   GLM-5.3 roles through the same frozen BigModel client and credential repository that chain G's solver uses, at the
   roles' 16,384 tokens; chain G's solver settings (65,536 tokens, read timeout 2,400 s) first run in the pilot.
   Neither is a fresh confirmation for the pilot.
2. **Staggered start.** Launch chain D alone. About 5 minutes after `D/s1-spreadsheetbench/run/attempt-1/` appears,
   run `LEDGERS` (6.1). It must show `D:solver` settled > 0 and no `halted`, and `$OPS/pilot-D-run-1.log` must have no
   `EXIT` line. Only then launch chain G. G's first unit waits for the memory lock while a D SpreadsheetBench unit runs.
   Confirm `G:solver` settled > 0 at the first poll after `G/s1-spreadsheetbench/run/attempt-1/` appears.
3. **Safety net, already in the code.** A round pauses with `infrastructure_incomplete` when more than 10 % of an arm's
   cells are infrastructure-unknown (J5, `protocol.INFRA_UNKNOWN_MAX`). Failed calls are therefore not scored as model
   failures.
4. **If a first check shows settled = 0 and a pause, stop.** Rerun 5.1, report to the owner, and relaunch only on the
   owner's decision (section 6.3).

### 5.4 After the launch

Update `docs/project-status.md` with the launch time, the manifest's record hash, the sessions and what is running
(AGENTS.md), and report to the owner in plain Chinese. Do not commit or push. In that report, say that chain G's cost
check comes after its first SpreadsheetBench run unit and that a breach ends chain G or needs a v1.1 rule (row 18), and
that the read consent the owner wrote at 15:01 is in place (7.1, registrar 15:1x).

## 6. Monitoring

### 6.1 Sparse and event-driven

The event to watch for is a chain's `EXIT` line. Each chain's `run` exits on completion, a pause or a termination. A pause
in one chain never stops the other, because each chain has its own ledger and its own runner. Poll from the Mac every
15–30 min with one ssh call that prints only the `EXIT` lines and the sessions:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=20 dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn \
  'grep -H "^EXIT" /data/execskill-20261021-ops/pilot-[GD]-run-*.log; tmux ls 2>/dev/null | grep execskill-pilot'
```

On an `EXIT` line, and otherwise every few hours, take one snapshot on dl. None of these shows a score.

```bash
$CLI monitor --root $PILOT          # complete units, open attempts, every ledger of the root with any "halted"
$CLI monitor --root $PILOT | $PY -B -c "import json, sys
m = json.load(sys.stdin)
for name, snap in sorted(m['ledgers'].items()):
    print(name, json.dumps({k: v for k, v in snap.items() if k == 'halted' or k.endswith((':solver', ':test', ':redo', ':glm'))}))
print('open attempts', len(m['open']), 'complete units', len(m['complete']))"        # = LEDGERS
$PY -B - <<EOF
# paused attempts waiting for the owner: status.json, no recovery.json, the unit not complete
# (an acceptance round paused after its last cell is final, row 17; a root-scan attempt is decided as in 7.4)
import sys; from pathlib import Path; sys.path.insert(0, '$SRC')
from skillopt.continual_eval.core import read_json
root = Path('$PILOT')
for status in sorted(root.rglob('attempt-*/status.json')):
    attempt = status.parent
    if not (attempt / 'recovery.json').exists() and not (attempt.parent / 'unit.json').exists():
        found = read_json(status)
        print(attempt.relative_to(root), found.get('kind'), found.get('reason'), found.get('cell'))
EOF
```

If a chain's `run` has exited, any open attempt without a `status.json` was interrupted (a crash, a kill or a reboot).
The next attempt of that unit waits for the owner's decision as well (`awaiting_owner_decision`).

Files to watch:

| File | Meaning |
|---|---|
| `$OPS/pilot-<c>-run-<n>.log` | `START`/`EXIT` lines, the run's final JSON, stderr diagnostics |
| `$PILOT/<c>/chain.json` | the chain started (identity, order) |
| `$PILOT/<c>/confirm.json`, `confirm-failed-<n>.json` | the first-call confirmation passed (once), or a failed one (row 7, 5.3) |
| `$PILOT/<c>/s<k>-<bench>/<unit>/unit.json` | the unit is complete |
| `$PILOT/<c>/s<k>-<bench>/step.json` | the step is sealed (write-once; names every unit's record) |
| `…/<unit>/attempt-<N>/status.json`, `diagnostics.log` | a paused attempt: its kind and reason; the traceback |
| `…/attempt-<N>/recovery.json` | the owner's decision for that attempt |
| `$PILOT/G/cap-check-G.json` (`cap-check-G-<n>.json` when a relaunch finds other caps) | chain G's cost check after its first run unit: `ok`, `per_cell`, the projection per scope |
| `$PILOT/shared/ledger-G`, `$PILOT/shared/ledger-D` | the ledgers of each chain (read them with `monitor`) |
| `$PILOT/shared/host_only/diagnostics/child-*.log` | the logs of the `step-unit` and `evaluate-unit` children |
| `$PILOT/<c>/test-read.json`, `$PILOT/<c>/test/<bench>/` | the read (`read` with its gate, or `not_read`) and the read units |
| `$PILOT/<c>/read-waiting.json` | the read waited for the owner's consent (`consent_missing`, counts only; row 9) |
| `$PILOT/<c>/root-scan/attempt-<N>/scan.json`, `status.json` | the run-root canary scan before the chain's unseal (7.4); `monitor` lists its hits under `root_scans` |
| `$PILOT/<c>/chain-complete.json`, `chain-terminated.json` | the chain ended |
| `$PILOT/<c>/unsealed.json`; `$PILOT/shared/owner-continuation.json`; `shared/formal-addendum.md`, `.json` | the unseal marker; the owner's continue/stop decision; the formal addendum (7.3, 7.4) |
| `$PILOT/shared/consent.json`, `shared/test-read-canaries.json` | the owner's read consent; the read canaries (after PR-C31) |
| `/data/execskill-history/consumption/<c>/<bench>.jsonl` | consumption in namespaces G and D. Both chains see the same items: a replication, not independent evidence. |
| `$PILOT/shared/research/<c>/` | the research store |

Keep every attempt directory, log and receipt. Never delete or move them (AGENTS.md).

### 6.2 Pause outcomes

Registration §4.4:

| Row | What | What the code does | Operator |
|---|---|---|---|
| P1 | Procedure fault (crash, timeout, memory, format, cap, banned name, lexicon hit, worker death) | The cell continues without that procedure. The fault is counted; no pause. | nothing |
| P2 | Applies-condition fault | The procedure is not enabled. Counted; no pause. | nothing |
| P3 | The request hash does not match on re-execution | Recorded as `unknown_fault` (wrong for the candidate, right for the control), outside the infrastructure share. Counted; no pause. | nothing |
| P4 | Sandbox unavailable: image missing, docker down, a container that cannot be removed, or a per-call slot not obtained after 600 s and one retry | `SandboxUnavailable` pauses the unit (`status.json` kind `sandbox`). Unremoved containers pause it as `cleanup`. Waiting for the episode or native locks is not P4: those waits are untimed and only logged. | Gather infrastructure facts: `docker ps` for the unit's tag, `diagnostics.log`, whether the image is present, free memory. The owner decides: redo or terminate (6.3). |
| P5 | The second or modified call was not delivered, or was truncated | The final answer falls back to the first reply. Both usages are recorded, plus `worst_delivery`. | nothing |
| P6 | Reasoning mismatch (chain D) | The `thinking_mismatch` resend path, counted. A completion above B halts that chain's ledger; the other chain continues. | On a halt, the unit pauses (kind `assumption`) and `monitor` shows `"halted"` on `ledger-<c>`. The owner decides. To resume: `resume-ledger` + `recover` + relaunch. Otherwise terminate. |
| P7 | M < reply ≤ B | Scored as usual; `over_nominal` is counted. | nothing |

Other pauses and stops:

| Kind (where) | Cause | Operator |
|---|---|---|
| `budget` | A scope's cap was reached. | The owner raises it (6.4) and redoes, or terminates. |
| `infrastructure_incomplete` (round or read unit) | More than 10 % of an arm's cells are infrastructure-unknown (J5). | Check 5.1, the gateway and the slots. The owner decides on a redo. |
| `acceptance_undetermined` (accept), or `configuration`/`exception` in an accept attempt whose traceback in `diagnostics.log` comes from `acceptance.decide` | The round finished every block, and J5 or J6 left the decision undetermined, or `decide` raised (for example, too few answered items). | Registrar decision C7e-2 (row 17): the round is final. Write NO `recovery.json` (`recover` refuses it: `acceptance.finished_round`): a redo would reuse every block, pause again and use up one of the two redos. Report it to the owner at once. The owner's options: terminate the chain (6.3), or a v1.1 rule for a fresh round (a second look at the same A* items, with whole-round caps). |
| `cap_check` (chain G, after `G/s1-spreadsheetbench/run`; chain level) | Chain G's ledger tokens per SpreadsheetBench run cell exceed 1.5 × the high anchor 4,273 = 6,409.5 (`step.cost_projection`; `cap-check-G.json`). Every chain-G scope breaches together at that point, and failed tries count at their full bound (row 18). | Report it to the owner at once. A cap raise does not clear it: the projection scales with the cap, and a relaunch re-reads the completed run unit, writes `cap-check-G-<n>.json` and pauses again. The owner's options (§9.3): terminate chain G (6.3), or a v1.1 re-registration of chain G's caps in new directories. Chain D is unaffected. |
| `first_call_unconfirmed` (chain level, unit `<c>/confirm`) | The chain's one call before its first unit did not pass (row 7): no delivered reply, another echoed model, nothing settled, or (chain D) reasoning in the receipt; or a configuration or ledger error before the send. `confirm-failed-<n>.json` keeps the checks, the error type and the counts. No unit attempt was opened. | Rerun 5.1. Relaunch `run` once the network or TLS cause is known: no owner decision, no `recovery.json` (5.3). A `BudgetStop` on `<c>:confirm` goes to the owner. |
| `consent_missing` (chain level, unit `<c>/test`) | The owner's read consent is missing or invalid at the read (row 9). `read-waiting.json` holds counts only. No read attempt was opened. | Ask the owner for the consent (7.1). Once `$CLI consent --root $PILOT` prints `"test_read": "valid"`, relaunch `run`: no `recovery.json`. |
| `test_read_budget` (chain level) | What is left on `<c>:solver` or `<c>:test` is less than 1.3 × the estimate of the read units still to run (all five on a first start; ticket P2C-2, section 3.4; chain G: ⌈part × max(1, factor_G)⌉, row 8). | The owner raises (6.4; both scopes if needed, and `overall`) or terminates. The relaunch checks again; the read is not run until the check passes. |
| `canary_hit` (a read unit, or the root scan) | A canary's text window was found in an artifact. | The owner decides. Report the counts and paths, never text. For the root scan, the two options are in 7.4: a new scan after the files were dealt with, or the release of that scan. |
| `awaiting_owner_decision` | A paused or interrupted attempt has no `recovery.json`. | The owner's decision → `recover`. |
| `redo_limit` | A fourth attempt, i.e. more than two redos (§3.4). | Terminate, or ask for a registrar decision. |
| `configuration`, `exception`, `package`, `consumption`, `containment` | Checks and crashes. The traceback is in `diagnostics.log`. | Never patch code mid-run: a patch terminates the chain (`manifest_mismatch`). The owner redoes (a deterministic defect will repeat) or terminates. |
| `no_qualified_test_items`, `qualification_paused` (SpreadsheetBench read) | The test-reference qualification qualified nothing, or paused. | The owner decides. |
| `child_failed_before_its_attempt` (read units; kind `exception`) | A read child ended before it opened its attempt (a missing consent now stops the chain before any child starts: `consent_missing`, row 9). | The owner decides: a `recover` per read unit, or terminate. |
| terminated: `manifest_mismatch` | A pinned file changed. | Nothing resumes. Report it. A new manifest needs a registrar decision. |

The owner decides on infrastructure information only, never on scores (§9.4). Report each pause in plain Chinese: what
stopped, the infrastructure facts, the options (redo or terminate), and what a redo would cost. The pilot's first pause
is its first live recovery, because the smoke's S4 drill was dropped at 13:0x.

### 6.3 Operator actions (only after the owner's decision; never from a loop)

```bash
# Redo a paused unit attempt. Writes the owner-format {"by": "owner", "date", "decision"} once.
# The first redo is paid from <c>:redo; the second one also needs 6.4. Never for an acceptance round that paused after
# its last cell (6.2, row 17: recover refuses it); chain G's cap_check leaves no attempt to recover (row 18). The
# chain-level pauses first_call_unconfirmed and consent_missing have no attempt either: relaunch only (5.3, 7.1).
# Only while the chain is idle (after its EXIT line, no step-unit or evaluate-unit child alive): recover does not yet
# tell a running attempt from an interrupted one (ticket I1-3).
$CLI recover --attempt $PILOT/<c>/s<k>-<bench>/<unit>/attempt-<N> --decision "<the owner's decision, verbatim>"
tmux send-keys -t execskill-pilot-<c> "$OPS/pilot-run.sh <c>" Enter       # only after that chain's EXIT line
# A halted ledger (a P6 breach or a quarantined settlement): resume, then recover the paused attempt and relaunch.
$CLI resume-ledger --root $PILOT --chain <c> --decision "<the owner's decision>"
# Termination: only an idle chain (after its EXIT line; refused while its runner or a read child runs).
# The chain ends, and its read, if not yet made, is not run.
$CLI terminate --manifest $PM --chain <c> --decision "<the owner's decision>"
```

`step-unit` is not an entry point for a chain without its first-call confirmation: it refuses unless
`$PILOT/<c>/confirm.json` is a passed record of this run and chain (ticket P2C-1). Start or relaunch a chain with `run`
(5.2), which makes the confirmation.

Read units are recovered the same way: `--attempt $PILOT/<c>/test/<bench>/attempt-<N>`. A run-root scan attempt,
`$PILOT/<c>/root-scan/attempt-<N>`, takes one of the two decisions of 7.4. A decision text that begins with the word
`release` is reserved for that case.

### 6.4 Raising a cap (on the owner's written cap decision; no CLI until row 10 is closed)

Raise a cap only after the owner's written cap decision. The raise is a deviation: it is recorded in the ledger journal
and must also go into the docs.

```bash
$PY -B -c "import sys; sys.path.insert(0, '$SRC'); from skillopt.coevo5.budget import Budget; from skillopt.execskill import budgets
Budget(budgets.ledger_root('$PILOT', '<c>')).raise_cap('<scope>', <new cap, int tokens>, deviation='<owner decision, date>')"
```

A second redo (attempt-3) usually needs `<c>:redo` raised. The owner states that decision in the attempt's
`recovery.json` decision text (§9.2).

Every solver call also names `overall` and `<c>:solver`, and a redo also names `<c>:redo`. Before a raise, check with
`LEDGERS` (6.1) that those still have room, and ask the owner to cover them in the same decision if they do not. A raise
survives a relaunch: `run` declares `chain_caps` again, and the frozen ledger keeps the raised cap. No raise clears
chain G's `cap_check` pause (row 18).

## 7. End of the pilot

### 7.1 The read consent (owner only; ask for it while step 2 runs)

**Already written** (registrar 15:1x): the owner wrote `$PILOT/shared/consent.json` at 15:01 on 2026-10-22 (252
bytes, sha256 prefix `2748d886fcb1b207`; `consent --root` → valid). Nobody edits, moves or rewrites it; the block below
only records the format (its `test -e` makes it a no-op now). If a v1.1 moves the pilot to new directories, the owner
writes the consent again there.

The read waits for `$PILOT/shared/consent.json`. Its key set must be exactly `protocol.CONSENT_FIELDS`, as checked by
`evaluation.consent`: `test_evaluation` true, `sheet_test_qualification` true, `multi_arm_arms` = the five
`protocol.TEST_ARMS`, `by` = `owner`, `date`, and a non-empty `note`. This is the owner's only hands-on step, and the
main agent never writes this file. The owner pastes this on dl (after `ssh dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn`):

```bash
F=/data/execskill-20261021-pilot/shared/consent.json      # written once: if it exists, leave it alone
test -e $F && echo "consent.json already exists" || echo '{"test_evaluation": true, "sheet_test_qualification": true, "multi_arm_arms": ["F", "C", "P_F", "T_F", "twins"], "by": "owner", "date": "<YYYY-MM-DD>", "note": "<one sentence of yours>"}' > $F
```

The operator checks it with `$CLI consent --root $PILOT`, which must print `{"test_read": "valid"}`. Do not edit the
file afterwards: the read-canaries record stores its hash.

Tell the owner, when they sign, what the consent authorizes (registrar row C3-1):

- the multi-arm read: F, C, P_F, T_F and twins;
- qualifying the SpreadsheetBench test references (with `false`, the SpreadsheetBench read unit pauses);
- after PR-C31: opening the OfficeQA, LiveMath and SpreadsheetBench test sets once, at the start of the read, to make
  canaries. Only lengths and sha256 prefixes are kept.

If the consent is late, the chain waits at the read (row 9): `consent_missing`, `read-waiting.json`, `EXIT 3`, and
no read attempt. Relaunch `run` once the consent is valid.

### 7.2 The read (automatic)

The read begins after step 2's freeze:

- If nothing was accepted (F = C), `test-read.json` says `not_read` and no read happens.
- Otherwise the chain checks the owner's consent (row 9; else `consent_missing`). Then `chain.read_budget` requires
  1.3 × the estimate of the read units still to run to be left on `<c>:solver` and on `<c>:test`, else the chain
  pauses with `test_read_budget`: the whole estimate on a first start, the per-bench terms of the rest on a relaunch
  (ticket P2C-2). Chain G's part is ⌈part × max(1, factor_G)⌉ (row 8, section 3.4).
- Then five `evaluate-unit` children start, one per bench. The SpreadsheetBench child holds the memory lock exclusively
  and the ALFWorld child holds it shared.

The first read unit makes `shared/test-read-canaries.json` (C3-1 (b)), under a lock, after its consent check and
before its attempt. It re-reads and re-hashes the pinned pool files `$PRE/pools/{spreadsheetbench,officeqa}.json` to
skip test texts that also occur on the training side (PR-C31-3, after P2-A3), so never touch `$PRE/pools/`. Every
attempt is canary-scanned before its first call and on every exit: the unit root, `shared/host_only/diagnostics` and
`shared/test`. Scores stay sealed until 7.4.

### 7.3 Continue or stop (the owner's decision), and the formal addendum

After both chains have ended (complete or terminated), the owner decides from the learning-side records only, with no
test score. A summary command does not exist yet (row 11). The records are:

- `$PILOT/<c>/chain-complete.json` (`steps`, the final `package_sha256`), and each step's `step.json`;
- the decision in each step's `accept/unit.json`;
- `$CLI show-package --package $PILOT/<c>/packages/<sha>.json` (procedure ids and hooks).

The main agent reports these records to the owner in plain Chinese and asks for the decision. It then records the
owner's decision once, verbatim, in `$PILOT/shared/owner-continuation.json`, with exactly these keys
(`evaluation.continuation` requires `by` = `owner`): `{"by": "owner", "date": "<YYYY-MM-DD>", "decision": "continue",
"note": "<the owner's words>"}`, or `"decision": "stop"`. Write it once (`test -e` first) and never edit it. This is the
pattern `recover` follows, and it keeps the read consent the owner's only hands-on step (13:2x). If the registrar reads
registration §8.1 (负责人……写下"继续 / 停止"的决定) as requiring the owner's own hand, this becomes a second
owner-only step: ask the registrar before the end of the pilot.

For "continue", owner decision #32 applies: the full formal-chain addendum (bench order, slice sizes, allowed
adjustments, caps; registration §8.1) is written and sealed before any unseal. The main agent, as registrar, drafts it.
Once the owner approves its content, the main agent writes it to `$PILOT/shared/formal-addendum.md` and runs
`$CLI seal-addendum --manifest $PM`, before `report`. It seals the file once, with this code's clock, into
`shared/formal-addendum.json`. The unseal label then depends on the order:

| Case | Label of the unseal | Later reads |
|---|---|---|
| continue, addendum sealed first | `interim_read_addendum_before_unseal` | `confirmatory` |
| continue, no addendum first | `interim_read_without_prior_addendum` | `repeated_test_development` |
| stop | `read_after_stop_decision` | `repeated_test_development` |

To check without writing anything, run `$CLI continuation-check --manifest $PM --chain G` and the same with `--chain D`.

### 7.4 The canary scan and the report

```bash
LOG=$OPS/pilot-report-$(date -u +%Y%m%dT%H%M%SZ).log
tmux new-session -d -s "execskill-report-$(date -u +%H%M%S)" \
  "$CLI report --manifest $PM --out $OPS/pilot-readout > $LOG 2>&1; echo EXIT \$? >> $LOG; exec bash"
```

`report` refuses until every chain has ended and the continuation file exists; for "continue", seal the addendum first
(7.3). It prints its result and exits 0; or it prints `{"paused", "reason", "at"}` and exits 3 when a scan paused, or 5
when a paused scan still awaits the owner's decision (PR-C31-1). Before the first unseal of each chain, it scans the
whole run root: every unit with every attempt, the packages, the research store, the ledgers, the logs and the shared
test files. It searches for every canary, both S0's (SearchQA, ALFWorld) and the read's (OfficeQA, LiveMath,
SpreadsheetBench), and writes `$PILOT/<c>/root-scan/attempt-<N>/scan.json`. Hence tmux: one scan may take minutes or
hours (ticket PR-C31-3: one process hashed a 25.5 MB tree in 105 s; v3's run root was 1.5 GB; the scan now uses five
processes, 2.7× measured on dl, so about 30-40 minutes per chain for a 1.5 GB root), and each chain gets one.

- **On a hit:** the attempt pauses (`canary_hit`) with paths and canary indices only, never text, and nothing more is
  unsealed. Report it to the owner, who chooses one of two decisions. The main agent records it with
  `$CLI recover --attempt $PILOT/<c>/root-scan/attempt-<N> --decision "<...>"`:
  - **Scan again**, after the files were dealt with: the owner's words, not beginning with `release`. The next
    `report` runs a new scan.
  - **Release** a hit that is not a leak: exactly `release <scan record_sha256>`, the hash in that attempt's
    `scan.json` (its `status.json` names it as `scan_sha256`). `recover` checks it. The next `report` scans the whole
    root again in a new attempt (as long as the first scan) and passes only if it finds exactly the released hits; then
    `unsealed.json` names that scan and the release (registrar decision PR-C31-3 (1b), after P2-A3). Any other hit
    pauses again in the new attempt, where the owner decides anew. Never release without the owner's decision; each
    chain's scan needs its own release.

  Then run the same two `report` lines again: nothing is written after a refusal, so `--out` is still new, and a chain
  unsealed before the refusal keeps its `unsealed.json`.
- **On a clean scan:** it writes `readout-<c>.json` for each chain that read, and the unseal marker
  `$PILOT/<c>/unsealed.json`.

Then update `docs/results-and-lessons.md`, `docs/current-workflow.md` (if the workflow changed) and
`docs/project-status.md`. Give the actual denominators, controls, costs, models, the provenance and the label
`pilot_real_run`. Negative or pending results stay negative or pending.

## 8. Estimates per chain (estimates, not measurements)

These come from the calc `docs/handoff/execskill-calc-20261021.py` (T4, T5, T11; identical to registration Appendix A).
The anchors per cell are deepseek measurements, and chain G reuses them as a placeholder. After S-E6, quote its
`result.scopes`, which hold the maximum-schedule projections with the measured ratio and one reservation, next to these
numbers.

| Part | Solver tokens, estimate | Registered maximum schedule | Cap |
|---|---|---|---|
| Step 1, SpreadsheetBench (run 0.16–0.42, accept 1.23–4.10, examiner 0.65–1.97, selftest 0.35–0.67) | 2.38–7.17M | 8.86M | 15.6M over its four step scopes |
| Step 2, OfficeQA (run 0.50–1.22, accept 5.15–16.17, examiner 1.46–4.55, selftest 1.04–2.07) | 8.16–24.01M | 29.25M | 45.7M |
| Learning side | 10.5–31.2M | 38.1M | — |
| Test read with twins (SearchQA 1.42–7.45, OfficeQA 3.27–10.09, LiveMath 0.47–2.72, SpreadsheetBench 2.59–8.82, ALFWorld 4.82–25.32) | 12.6–54.4M | 65.4M | 99M |
| Solver total | 23.1–85.6M | 103.5M | 180M |
| GLM-5.3 roles (examiner research 0.26–5.76M included) | 3.3–13.8M | — | 30M |

For both chains: solver 46.2–171.2M (maximum 207.0M, caps 360M), GLM 6.5–27.5M (caps 60M).

Chain G disclosure (calc T11): with chain G's own reservation (B = 65,536), its OfficeQA step caps would be 2.4 / 7.4 /
6.8 / 29.6M. The registered caps are 2.3 / 7.3 / 6.6 / 29.5M, so a chain-G cap pause is plausible. The owner rule is
that the registered caps are not recomputed. Separately, chain G's cost check pauses chain G when its ledger tokens per
SpreadsheetBench run cell exceed 6,409.5, and no raise clears that pause (row 18).

Wall clock: about 1–2 days for the default pilot. That is registration §9.2's estimate, written for one chain. Running two
chains in parallel adds contention that no one has estimated:

- **Step 1.** Every SpreadsheetBench unit of both chains holds the memory lock exclusively, so the two chains' step 1 runs
  one unit at a time: about double one chain's step 1.
- **Step 2.** OfficeQA acceptance runs in two blocks at least 2 h apart (`BLOCK_GAP_SECONDS` 7,200), so each acceptance
  round takes at least 2 h, and redoing a block adds its own gap. No memory lock applies, so the chains overlap. Chain
  G's OfficeQA cells and both chains' GLM roles share 10 glm-5.3 slots.
- **Worst cases per call.** GLM solver read timeout 2,400 s. Elucid 600 s (QA), 900 s (SpreadsheetBench), 180 s (one
  ALFWorld step). GLM roles 900 s.
- **Read.** ALFWorld runs 134–402 episodes per chain: C on all 134 items, plus F, P_F, T_F and one twin on the 0–50 % of
  items where a procedure fires. At the registered median of 290–348 s per episode on 6 machine-wide episode slots, that
  is about 1.8–6.5 h per chain alone (this runbook's arithmetic; p90 episodes reach 1,929 s). Each chain's
  SpreadsheetBench read unit excludes every ALFWorld unit.
- **The owner's waits:** the read consent (7.1) and the continue/stop decision (7.3).

## 9. Checked (completeness check, dl 13:4x)

Read-only checks of `/data/execskill-dev` at 13:3x–13:4x, zero model calls. The `--help` runs and the cap listing ran
on dl with `$PY`.

| Check | Result |
|---|---|
| (a) pins vs `manifest.make` | `GIVEN` (nine keys) plus `evidence` come from the pins, and `limits` + `measured` from `--s0-pins`. All are in 3.1–3.3 with their sources. The C6-3 data contract (`manifest.py` docstring, `setting_of`, `services_of`, `_pools`): `data.pools` for `protocol.ORDER`, `data.research` {archive, index_sha256}, `data.test_read_estimate` {G, D} > 0, `data.pinned`; `make-manifest` binds `data.exclusion`. The four contract hashes were recomputed from `backends.py`. |
| (b) every step reachable | `run` → `chain.run_manifest` → `step.run_step` for SpreadsheetBench, then OfficeQA, through `step.UNITS` (the §5 sub-steps); chain G's cost check; `read_budget` → five `evaluate-unit` children (§8); `continuation-check`, `seal-addendum`, `report`. `--help` exits 0 for all 17 subcommands used here, and their arguments match this runbook. |
| (c) caps and slots | `budgets.chain_caps` and `budgets.caps()` on dl equal 3.5 and registration §9.3. `protocol.SLOTS`, `SANDBOX_SLOTS`, `ELUCID_MAX_TOKENS`, `ELUCID_READ_TIMEOUT` and `ledger_bound` equal 3.1 and registration §4.1. |
| (d) safety | No step reads a test pool or a credential file, prints a credential, writes under `/data/coevo5-*` (the v3 files and the research archive are only read), or resumes a paid cell by itself. |
| (e) owner-only steps | Exactly the read consent (7.1). |
| (f) open items | Section 0 matches the code and the agents' notes as of 13:45, and each row names its closer. |

Changed in this check:

- Header and status: the owner-only rule; the state at 13:4x.
- Section 0: rows 1–14 brought up to date with what landed and who closes the rest; new rows 17 (C7e-2) and 18 (chain
  G's cost check); the table of blocked steps.
- Section 2: the go check's assertion. `stages` lists all seven stages, so the old set comparison would have refused a
  passing smoke. B is now written as 2 × M and max(4 × M, …), not "2M". The plan §11 item is an owner decision.
- 3.1: chain D's ALFWorld M (1,024), the B rule, the model pools and the machine-wide pools. 3.4, 3.5 and section 8:
  the cost check and raised caps.
- 5.2: the run's summary is indented JSON, plus other exit codes and the cost check. 5.3: chain G's untested solver
  settings. 5.4: what to tell the owner at the launch.
- 6.1: new files to watch, and the note on paused attempts. 6.2: `cap_check` (terminate or v1.1, never a raise),
  `acceptance_undetermined` (final, no `recovery.json`), `test_read_budget`, `canary_hit`. 6.3: what is never
  recovered; terminate only an idle chain. 6.4: the scopes a call names; a raise survives a relaunch.
- 7.1: a write-once guard. 7.2: never touch `$PRE/pools/`. 7.3: the main agent records the owner's continue/stop
  decision and drafts the addendum. 7.4: tmux, exit codes, scan time, and the two decisions on a hit (scan again or
  release).

Still blocking the launch: row 1 (the smoke-runbook); rows 3–6 and 13 (tests and I1 follow-ups, then the final
snapshot); row 7 (no first-call confirmation and no ticket); row 8 (no `test_read_estimate` producer or registered
formula); and the main agent's sequence (whole suite, Codex round, commit, snapshot, `$Q23`, smoke). Row 9 must be
handled before the end of step 2. Row 18 is a standing risk for chain G.
