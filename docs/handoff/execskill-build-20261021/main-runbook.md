# Route-B main-run runbook (dl, fivebench-execskill-v1, configuration `main`)

Builder M1 wrote this on 2026-10-22 (dl clock 19:0x) from the dev tree `/data/execskill-dev`. It is for the five-bench
main experiment of the owner's instructions of 17:0x and 17:3x (`../execskill-registrar-decisions-20261022.md`, section
"Owner instructions 2026-10-22 17:0x and 17:3x"). It covers the steps from "the trimmed smoke of configuration `main`
passed" to "chains G and D are running and monitored", and on to the end of the run and the readout.

**The operator is the main agent. None of the commands below has been run.** The pins file and the manifest do not
exist yet.

This runbook is `pilot-runbook.md` with the main configuration's differences. Where a step is unchanged, this
runbook names the pilot-runbook section and gives the commands with the main paths. Read `$PILOT` as `$MAIN`, `$PM` as
`$MM` and `pilot-run.sh` as `main-run.sh` there. These parts of the pilot runbook apply as written:

- the P1–P7 outcomes (§6.2);
- the operator actions (§6.3) and cap raises (§6.4);
- the canary-scan rules (§7.4).

The main root holds exactly one file: the owner's read consent `$MAIN/shared/consent.json`. The owner wrote it at
18:06 (registrar: 290 bytes, sha256 prefix `d3c89a8f70ff249d`). Never modify, move or rewrite it.

## 0. What `main` changes

| Item | Pilot (`default`) | Main (`main`) | Code |
|---|---|---|---|
| Steps | SpreadsheetBench → OfficeQA | **SearchQA → OfficeQA → LiveMath → SpreadsheetBench → ALFWorld**, five steps (`protocol.BENCHES`) | `protocol.PILOTS["main"]["order"]`. The manifest's `configuration` becomes `setting.extra["configuration"]`, and `protocol.order_of` reads it in chain, step and evaluation. |
| Root, manifest | `/data/execskill-20261021-pilot`, `…-pilot-manifest.json` | `/data/execskill-20261022-main` (`protocol.MAIN_ROOT`), `/data/execskill-20261022-main-manifest.json` (`protocol.MAIN_MANIFEST`) | `protocol.RUN_ROOTS`. `make-manifest` refuses a main real run with any other root. |
| Evidence label | `pilot_real_run` | `main_real_run`. The run is exploratory: no label is confirmatory. | `protocol.REAL_RUN_EVIDENCE`. `manifest.check` refuses the other real-run label. |
| Caps | 1.5 × the need | ≥ 3 × the computed maximum need of every scope, with 16 full chain-G reservations held at once (section 3.4) | `protocol.MAIN_STEP_CAPS`, `MAIN_ROLE_CAPS`, `MAIN_GLM_CAP`, `PILOTS["main"]`; `budgets.chain_caps(c, "main")` |
| First-call confirmation | on SpreadsheetBench's settings | On SearchQA's settings, the first step's bench. Chain D on route B makes its own confirmation (`confirm-route-B.json`). | `protocol.first_call_bench("main")`; `chain.first_call` |
| Chain G's cost check | A breach pauses chain G (pilot row 18). | It runs after G's first run unit (SearchQA, step 1). It records `ok`, the factor and `pauses: false`, and **never pauses**. The read gate still prices G's read at ⌈part × max(1, factor_G)⌉. | `protocol.COST_CHECK_PAUSES["main"]` = False; `chain.cap_check`, `latest_cap_check`. `step.cost_projection` divides each cap by 3 (`CONFIG_CAP_FACTOR`). |
| Test-read estimate | f = 1 / 0.7 / 0.5 (home / similar / other) | f = 1 on every bench: after its step, each bench is a home bench. | `protocol.TEST_READ_CELLS["main"]`, `fired_share(b, "main")`; `test-read-estimate --configuration main` |
| SearchQA step | — | Run: 300 × 1 from the pool. Accept: 1,000 × 1 in 4 blocks from the kept fresh tail. | `data.searchqa_tail` + `data.exclusion.searchqa_test_exclusion`; `manifest._searchqa_tail`, `step._tail` (M2b) |
| LiveMath step | — | Run: 119. Accept: 100 × 2. J7 probe: 64 items, options only. 283 = 119 + 100 + 64, so there is no slack. | `step._options_only` (M2b) |
| ALFWorld pool | v3's 57 games (no step) | The fresh supply `$HIST/supply/alfworld-xs.json`, with its views reset on the pinned runtime. `export-pools` exports it. Run: 60. Accept: 150 in 4 room blocks. | `supply.alfworld_pool`; `step._alfworld_views` (M2b) |
| Chain D's provider | elucid | Route A is elucid. After a `balance_exhausted` pause, `switch-route` moves chain D to route B (northgate, `deepseek-v4-flash`, branch-N bound). | `clients.routes.D.B` (`routes.pin`); `routes.py`, `client.py` (M4) |
| Memory lock | SpreadsheetBench units, exclusive | Exclusive: SpreadsheetBench units and every unit with an SB set among its cells (the self-tests of steps 4 and 5). Shared: ALFWorld units. | `chain.heavy_mode` |
| Continuation file, addendum | the owner's continue/stop file, and for "continue" the formal addendum, before the unseal | No formal addendum (exploratory run). The code still needs `shared/owner-continuation.json` before `report` unseals (section 9, open item 2). | `evaluation.continuation` |

Former open items, answered by the registrar (19:1x, "M1 questions 19:1x (main configuration)"):

1. **An `above_high` flag in main's S-E6** (a bench's measured card cell above 1.25 × its high anchor, plan §10 step
   6) is recorded and reported. It does not stop main's launch as long as S-E6 passed, that is, every projected need
   fits main's caps; a projection above a main cap fails S-E6 and still stops the launch (section 2). The flag stays
   a stop rule for `default` and `recommended`.
2. **The continuation file at the readout.** Unsealing still requires `$MAIN/shared/owner-continuation.json`, written
   by the owner. At the readout the main agent gives the owner a one-line command, as for the consent (section 9).

## 1. Shell setup (every tmux window)

Use pilot-runbook §1 (`PY`, `SRC`, `PRE`, `IN`, `SMOKE`, `HIST`, `V3`, `V3SHEET`, `V3SHEET_HASH`, `Q23`, `OPS`,
`ELUCID`, `GREPO`, `ALFWORLD_DATA`, `CLI`; no `proxy_on`; never print `.env`, a key or a proxy credential), plus these:

```bash
MAIN=/data/execskill-20261022-main                  # protocol.MAIN_ROOT; shared/consent.json is the owner's: NEVER modify
MM=/data/execskill-20261022-main-manifest.json      # protocol.MAIN_MANIFEST; written once (section 4)
NORTHGATE=/root/.config/weak-solver/northgate.env   # chain D's route B credentials: path only, never read or printed
```

`$OPS` stays `protocol.OPS_ROOT`. Every main file in it starts with `main-`.

## 2. Go checks (zero model calls)

The main run starts only from a passed trimmed smoke (S0, S1, S2, S3, S-E6) **of configuration `main`** on the final
snapshot. Its smoke manifest names `"configuration": "main"` and carries `clients.routes` (smoke-runbook §5). So S-E6
projected main's five steps at main's caps, together with both chains' GLM scopes (`smoke.se6_projection`), and
`test-read-estimate` prices main's read.

```bash
mkdir -p $OPS && chmod 700 $OPS
test ! -e $MM && echo "no main manifest yet"                     # make-manifest refuses an existing file
# the owner's consent (18:06) is the root's only file; plus shared/test-canaries.json on a retry of section 4
found=$(cd $MAIN && find . -type f | LC_ALL=C sort | tr '\n' ' ')
case "$found" in
  "./shared/consent.json "|"./shared/consent.json ./shared/test-canaries.json ") echo "main root ok: $found";;
  *) echo "STOP, ask: $MAIN holds $found";;
esac
$CLI consent --root $MAIN           # {"test_read": "valid"}: the owner's read consent
$PY -B - <<EOF
import json, sys; sys.path.insert(0, '$SRC')
from skillopt.continual_eval.core import read_json
from skillopt.execskill import manifest, protocol
r = protocol.verified(read_json('$SMOKE/smoke-result.json'), 'smoke-result')
s1 = protocol.verified(read_json('$SMOKE/stages/S1.json'), 'smoke-stage')['result']
se6 = protocol.verified(read_json('$SMOKE/stages/SE6.json'), 'smoke-stage')['result']
sm = manifest.load('$SMOKE/manifest.json', verify=False)
print(json.dumps({'stages': r['stages'], 'required': r['required'], 'passed': r['passed'], 'branch': s1['branch'],
                  'longest': s1['longest'], 'se6_passed': se6['passed'], 'ratio': se6['ratio'],
                  'configuration': [sm['configuration'], se6.get('configuration')],
                  'above_high': {b: a['above_high'] for b, a in se6['anchors'].items()}}))
assert r['passed'] is True and sorted(r['required']) == ['S0', 'S1', 'S2', 'S3', 'SE6'] and all(
    r['stages'][s] == 'pass' for s in r['required'])   # 'stages' also lists SN1 and S4 (not_required)
assert sm['configuration'] == se6.get('configuration') == 'main', 'the smoke did not project main: stop'
assert 'routes' in sm['clients'], 'the smoke manifest carries no route-B pin: stop'
EOF
$CLI consent --root $SMOKE          # {"exclusion": "valid"}
$CLI leftovers                      # "clean" or "cannot_judge" (D3/D14 workers excluded by command line): pass
$CLI monitor --root $SMOKE          # the smoke ledger: no "halted", nothing open
$CLI verify-snapshot --list $PRE/source-sha256.txt --root $SRC --git-head "$(cat $PRE/build-head.txt)" \
     > $OPS/main-provenance.json    # 3.2 requires it to equal the smoke manifest's provenance
```

Stop and ask instead of continuing in any of these cases:

- **A required stage is not `pass`.** There is no main run. Re-register the failed rows as `fivebench-execskill-v1.1`
  with new directories (§10 exit).
- **The smoke or its S-E6 is not of configuration `main`.** A default-configuration smoke never priced main's caps,
  GLM scopes or test read. Ask the registrar which stages to run again.
- **S1 chose branch N and a completion above B was seen** (the smoke ledger shows `halted`; plan §11).
- **`leftovers` prints `leftovers`**, or the main root holds anything other than the consent (and the canaries on a
  retry).

A true `above_high` flag alone is not a stop in `main` (section 0, item 1): report it to the owner with the go-check
output. A projection above a main cap fails S-E6, which the first case covers.

## 3. The main pins file `$OPS/main-pins.json`

### 3.1 Keys that differ from pilot-runbook §3.1

Every other key (`data.research`, `data.pinned`, `sheet_qualification`, `cards`, `contracts`, `runtime`,
`clients.solver`, `clients.roles`, `fixtures`, `provenance`) is as in pilot-runbook §3.1–3.2, and equal to the smoke
manifest's.

| Key | Value | Exact source |
|---|---|---|
| `root` | `/data/execskill-20261022-main` | `protocol.MAIN_ROOT`. `make-manifest` refuses a `main_real_run` with any other root. |
| `evidence` | `"main_real_run"` | `protocol.REAL_RUN_EVIDENCE["main"]` |
| `configuration` | `"main"` | Registrar 17:0x. `make-manifest` takes it from the pins, and `manifest.make` stamps it with `caps` = `budgets.caps("main")`. |
| `data.pools` | `{bench: {path, sha256}}` for **all five** benches | `supply.pool_pins($PRE/pools/pools.json)`, which is the `pins.pools` that `export-pools` printed (smoke-runbook §3). ALFWorld's entry comes from the fresh supply. `manifest.setting_of` refuses pools that are not main's order. |
| `data.searchqa_tail` | `{"path": "/data/execskill-history/supply/searchqa-tail.json", "sha256": <file sha256>}` | The tail supply that `make-items --bench searchqa` wrote once (smoke-runbook §3). `setting_of` joins it with the bound `data.exclusion.searchqa_test_exclusion`. `step._tail` re-hashes the file and applies that exclusion record only. |
| `data.test_read_estimate`, `data.test_read_terms` | `{"G": …, "D": …}` | `test-read-estimate --configuration main` (3.2, 3.3) |
| `clients.routes` | `{"D": {"B": routes.pin("D", "B", env_path=$NORTHGATE, solver_block=clients.solver.D)}}` | M4. Required in a `main` manifest (`routes.check_pins`). It records the credential file by path only and reads nothing. Its `longest` is S1's on branch N, else 256. |

### 3.2 Build the pins (zero calls, written once)

```bash
$CLI test-read-estimate --smoke $SMOKE --configuration main --out $OPS/main-test-read-estimate.json
#   prints {"out", "test_read_estimate": {"D": n, "G": n}, "configuration": "main", "record_sha256"}; refuses an
#   existing file, a smoke whose result or S-E6 did not pass, and an S-E6 of another configuration
$PY -B - <<EOF
import hashlib, json, sys
sys.path.insert(0, '$SRC')
from skillopt.continual_eval.core import read_json
from skillopt.execskill import manifest, protocol, routes, supply
sha = lambda path: hashlib.sha256(open(path, 'rb').read()).hexdigest()
smoke = manifest.load('$SMOKE/manifest.json', verify=False)      # the sealed smoke manifest (record and fields checked)
v3 = read_json('$V3', sealed=True)
s1 = protocol.verified(read_json('$SMOKE/stages/S1.json'), 'smoke-stage')['result']
se6 = protocol.verified(read_json('$SMOKE/stages/SE6.json'), 'smoke-stage')['result']
# fields a main unit reads: rebuilt from their sources, and equal to the smoke's (else stop)
runtime = {**v3['runtime'], 'spreadsheetbench': read_json('$PRE/sheet-runtime.json')}
cards = read_json('$PRE/texts/texts.json')['cards']
solver = {'G': manifest.solver_block('G', env_path='$GREPO'),
          'D': manifest.solver_block('D', env_path='$ELUCID', branch=s1['branch'], longest=s1['longest'])}
clients = {'solver': solver, 'roles': manifest.ROLES,
           'routes': {'D': {'B': routes.pin('D', 'B', env_path='$NORTHGATE', solver_block=solver['D'])}}}
pinned = read_json('$IN/v3-data-pins.json')
assert runtime['alfworld'] == read_json('$IN/alfworld-runtime.json'), 'alfworld runtime'
assert pinned == v3['data'], 'data.pinned must be the v3 data block'
for key, value in (('runtime', runtime), ('cards', cards), ('clients', clients)):
    assert smoke[key] == value, key + ': the smoke manifest differs, stop'
assert smoke['configuration'] == 'main', 'not a smoke of configuration main, stop'
assert smoke['provenance']['snapshot_root'] == '$SRC' and smoke['provenance']['env_files_absent'] is True
assert json.load(open('$OPS/main-provenance.json')) == smoke['provenance'], 'the snapshot changed since the smoke'
# section 3.3: main's estimate, of this smoke, recomputed
found = protocol.verified(read_json('$OPS/main-test-read-estimate.json'), 'test-read-estimate')
spec = protocol.verified(read_json('$SMOKE/smoke.json'), 'smoke-spec')
assert found['smoke']['spec'] == spec[protocol.RECORD_HASH], 'the estimate of another smoke, stop'
assert found['pilot'] == 'main', 'not main estimate, stop'
assert found['value'] == protocol.estimate_test_read(se6['per_cell'], se6['ratio'], 'main'), 'the estimate differs, stop'
assert found['evidence'] == 'smoke', 'the estimate of a rehearsal (an engineering fixture), stop'
pools = supply.pool_pins(read_json('$PRE/pools/pools.json'))
assert sorted(pools) == sorted(protocol.BENCHES), 'export-pools must have exported all five pools'
tail = '$HIST/supply/searchqa-tail.json'
pins = {'root': protocol.MAIN_ROOT, 'evidence': 'main_real_run', 'configuration': 'main',
        'data': {'pools': {b: pools[b] for b in protocol.BENCHES}, 'research': smoke['data']['research'],
                 'pinned': pinned, 'searchqa_tail': {'path': tail, 'sha256': sha(tail)},
                 'test_read_estimate': {'G': found['value'], 'D': found['value']},
                 'test_read_terms': {'G': found['terms'], 'D': found['terms']}},
        'runtime': runtime, 'cards': cards, 'clients': clients,
        **{k: smoke[k] for k in ('sheet_qualification', 'contracts', 'fixtures', 'provenance')}}
assert set(pins) == manifest.GIVEN | {'evidence', 'configuration'}
with open('$OPS/main-pins.json', 'x') as out:                      # 'x': written once, never overwritten
    json.dump(pins, out, indent=1, sort_keys=True, ensure_ascii=False)
print(json.dumps({'pins': '$OPS/main-pins.json', 'sha256': sha('$OPS/main-pins.json'), 'branch': s1['branch'],
                  'longest': s1['longest'], 'ratio': se6['ratio'], 'test_read_estimate': found['value'],
                  'route_b': {k: clients['routes']['D']['B'][k] for k in ('model', 'url_host', 'branch', 'longest')},
                  'pools': {b: pools[b]['sha256'][:16] for b in protocol.BENCHES},
                  'searchqa_tail': pins['data']['searchqa_tail']['sha256'][:16]}, indent=1))
EOF
```

The pins hold paths, hashes, the card texts and the runtime. They hold no credential. If an `assert` fails, stop: the
main run would differ from what the smoke ran.

### 3.3 The test-read estimate of main

The formula is pilot-runbook §3.4's: estimate = ⌈ratio × Σ_b n_b × (card_b + 4 × f_b × proc_b)⌉. Main changes two
inputs:

- **f_b = 1 on all five benches** (`fired_share(b, "main")`).
- **n_b** comes from `TEST_READ_CELLS["main"]`: SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 279,
  ALFWorld 134.

At the §9.1 high anchors (procedure = 1.6 × card, ratio 1) the estimate is **77,268,847**; the pilot's is 54,409,087.
The start rule needs 1.3 × the estimate left on both `<c>:solver` and `<c>:test`:

- chain D: 100.4M;
- chain G: ⌈1.3 × estimate × max(1, factor_G)⌉. At factor_G = 3, the most the cost check tolerates before it flags a
  breach, that is 301.3M, inside the 407M test cap.

A relaunched read is priced by its units still to run (`data.test_read_terms`, ticket P2C-2), as in the pilot.

### 3.4 Caps (stamped by `make` as `budgets.caps("main")`, not in the pins)

The rule (registrar 17:0x): every cap is ≥ 3 × its computed maximum need. A scope's need is its maximum-schedule cells
(`protocol.MAIN_SCHEDULE_CELLS`, calc T4s) at the high anchors, plus 16 full chain-G reservations held at once
(4 × (request bytes + 512 + 65,536)). Chain D's B never exceeds 65,536, on route B either, so the same caps serve both
chains. The arithmetic of every scope is in `notes/M-M1.md` and `tests/test_execskill_protocol.py`.

| Scope (per chain) | Cap |
|---|---|
| `overall` | 1,808M = solver 1,520M + GLM 288M |
| `<c>:solver` | 1,520M |
| `<c>:test` | 407M |
| `<c>:redo` | 72M |
| `<c>:glm` | 288M |
| `<c>:confirm` | 1.1M (`protocol.FIRST_CALL_CAP`, inside `<c>:solver`) |
| `<c>:xs:searchqa:1:{run,examiner,selftest,accept}` | 29.9 / 26.5 / 28.2 / 110.7M |
| `<c>:xs:officeqa:2:{…}` | 28.7 / 38.7 / 34.2 / 83.0M |
| `<c>:xs:livemath:3:{…}` | 29.6 / 36.3 / 35.7 / 56.1M |
| `<c>:xs:spreadsheetbench:4:{…}` | 27.6 / 33.3 / 39.1 / 43.8M |
| `<c>:xs:alfworld:5:{…}` | 44.8 / 38.3 / 72.0 / 201.1M |
| `…:<kind>:attempt-2`, `…:attempt-3` | min(step cap, 72M) |
| `<c>:xs:<bench>:<k>:role:{engineer,examiner,examiner:research}` | 5 / 5 / 9.2M per step |

For both chains together, the manifest's `overall` is 3,616M.

## 4. Main manifest (zero model calls)

```bash
$CLI make-manifest --out $MM --pins $OPS/main-pins.json --exclusion-root $SMOKE --s0-pins $PRE/s0-pins.json
#   as pilot-runbook §4: revalidates runtime.spreadsheetbench offline; verifies the S0 exclusion records under $SMOKE
#   and binds data.exclusion; writes $MAIN/shared/test-canaries.json once; writes the sealed manifest (code map of $SRC,
#   image inspect + one sandbox ping). Prints {"manifest", "run", "root", "exclusion", "configuration": "main"}
$PY -B - <<EOF
import json, sys; sys.path.insert(0, '$SRC')
from skillopt.execskill import budgets, manifest, protocol
mm = manifest.load('$MM')                                       # verified: code map, interpreter, image (zero calls)
sm = manifest.load('$SMOKE/manifest.json', verify=False)
same = {k: mm[k] == sm[k] for k in ('code', 'environment', 'sandbox', 'clients', 'runtime', 'cards', 'contracts',
                                    'fixtures', 'provenance', 'prompt_sha', 'lexicon_sha', 'templates', 'configuration')}
print(json.dumps({'run': mm[protocol.RECORD_HASH], 'evidence': mm['evidence'], 'root': mm['root'],
                  'configuration': mm['configuration'], 'same_as_smoke': same,
                  'exclusion': sorted(mm['data']['exclusion']), 'pools': sorted(mm['data']['pools']),
                  'test_read_estimate': mm['data']['test_read_estimate'],
                  'caps': {k: v for k, v in sorted(mm['caps'].items()) if k.count(':') == 1 or k == budgets.ROOT}},
                 indent=1))
assert all(same.values()) and mm['caps'] == budgets.caps('main') and mm['evidence'] == 'main_real_run'
assert mm['configuration'] == 'main' and sorted(mm['data']['pools']) == sorted(protocol.BENCHES)
EOF
$CLI consent --root $MAIN           # {"test_read": "valid"}: the owner's consent of 18:06, unchanged
```

If any `same_as_smoke` value is false, stop and ask the registrar. If `make-manifest` fails after it wrote the
canaries, rerun it: the canaries write is idempotent for identical content.

## 5. Launch (two tmux sessions on dl)

### 5.1 Network and TLS check (no model call, no credential)

This checks the route apart from authorization (AGENTS.md), for chain G, chain D's route A and its route B:

```bash
for H in $($PY -B -c "import json; c = json.load(open('$MM'))['clients']
print(c['solver']['G']['url_host'], c['solver']['D']['url_host'], c['routes']['D']['B']['url_host'])"); do
  curl -sS -o /dev/null --max-time 30 --proxy http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 \
       -w "$H http=%{http_code} connect=%{time_connect}s tls=%{time_appconnect}s\n" "https://$H/"
done
#   any HTTP status (401/404 included) shows that the gateway route and TLS work; a timeout is a network fault
```

### 5.2 Launcher and sessions: chain G first, chain D alongside

```bash
cat > $OPS/main-run.sh <<'EOF'
#!/bin/bash
# One main chain (G or D) of fivebench-execskill-v1, configuration main. No proxy_on: the clients carry protocol.GATEWAY.
set -u
C=${1:?chain G or D}
OPS=/data/execskill-20261021-ops
export ALFWORLD_DATA=/root/continual-alf-prep-20260928/data PYTHONDONTWRITEBYTECODE=1
unset OPENAI_API_KEY OPENAI_BASE_URL HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
cd /data/execskill-20261021-source || exit 2
n=1; while [ -e "$OPS/main-$C-run-$n.log" ]; do n=$((n+1)); done
log="$OPS/main-$C-run-$n.log"
echo "START $(date -u +%FT%TZ) chain $C" > "$log"
/root/continual-alf-prep-20260928/env/bin/python -B scripts/run_execskill.py run \
    --manifest /data/execskill-20261022-main-manifest.json --chain "$C" >> "$log" 2>&1
echo "EXIT $? $(date -u +%FT%TZ)" >> "$log"
EOF
chmod 700 $OPS/main-run.sh
tmux new-session -d -s execskill-main-G "$OPS/main-run.sh G; exec bash"   # chain G first (owner 17:3x: GLM-5.3 first)
#   ... until $MAIN/G/confirm.json exists (5.3) or G's log has an EXIT line, then chain D alongside:
tmux new-session -d -s execskill-main-D "$OPS/main-run.sh D; exec bash"
```

Chain D waits only for chain G's first reply to be confirmed: confirm one actual model response before any
concurrency. After that the two chains run side by side. Each `run` prints its summary JSON into its log, and the
launcher appends `EXIT 0` (complete), `EXIT 3` (paused or terminated) or another code, which is a crash outside a
unit: report it, and relaunch only once the cause is known (pilot-runbook §5.2).

One `run` does this, in order:

1. It verifies the manifest: code map, interpreter, image and pinned files. A changed pinned file terminates the chain
   (`manifest_mismatch`), so never edit `$SRC`, `$PRE/pools/`, `$HIST/supply/` or the smoke's exclusion records.
2. It writes `$MAIN/<c>/chain.json`, with `order` = the five benches and `configuration: "main"`, and declares
   `chain_caps(c, "main")` and `<c>:confirm` on `$MAIN/shared/ledger-<c>`.
3. The first-call confirmation: one solver call alone on SearchQA's settings, then `confirm.json` (chain D on route B:
   `confirm-route-B.json`). A relaunch reuses it.
4. Step 1, SearchQA (`s1-searchqa`): run, diagnose, generate, engineer, selftest, [engineer-2, selftest-2], accept and
   freeze. It takes no memory lock.
5. Chain G only: the cost check after its first run unit, `cap-check-G.json` with `pauses: false`. It never pauses.
6. Step 2 OfficeQA (`s2-officeqa`), step 3 LiveMath (`s3-livemath`; the J7 probe goes options-only), step 4
   SpreadsheetBench (`s4-spreadsheetbench`), step 5 ALFWorld (`s5-alfworld`). Acceptance blocks and their spacing are
   as registered (`protocol.SLICES`).
7. The test read, if anything was accepted: the consent check, the read gate and five read units.
8. It writes `chain-complete.json`.

**The memory lock.** `/data/execskill-slots/memory-heavy.lock` (`chain.heavy_mode`) serializes the two chains'
SpreadsheetBench units and every self-test that runs an SB set, so steps 4 and 5 of G and D never overlap there. ALFWorld
units share it. Nothing else is needed: never hold, remove or touch the lock file, and never start a second `run` of a
chain while its first is alive (`.runner.lock`).

### 5.3 First-call confirmations

```bash
for f in $MAIN/G/confirm.json $MAIN/D/confirm.json $MAIN/D/confirm-route-B.json; do
  test -e $f || continue
  $PY -B -c "import sys; sys.path.insert(0, '$SRC')
from skillopt.continual_eval.core import read_json; from skillopt.execskill import protocol
r = protocol.verified(read_json('$f'), 'first-call')
print('$f', {k: r.get(k) for k in ('passed', 'model', 'returned_model', 'route', 'charged', 'seconds', 'checks')})"
done
```

On `first_call_unconfirmed` (`EXIT 3`, `confirm-failed-<n>.json`, or route B's `confirm-route-B-failed-<n>.json`), do
as in pilot-runbook §5.3: rerun 5.1, and relaunch `run` once the network or TLS cause is known. No owner decision and
no `recovery.json` are needed.

### 5.4 After the launch

Update `docs/project-status.md` with the launch times, the manifest's record hash, the sessions and what is running
(AGENTS.md). Report to the owner in plain Chinese. Do not commit or push. Say in that report:

- the main run is exploratory (`main_real_run`);
- chain G's cost check only records, it never pauses;
- the read consent of 18:06 is in place;
- chain D runs on route A, and moves to route B only after a balance-exhaustion pause (7, 8.1).

## 6. Monitoring

Watch for each chain's `EXIT` line. A pause in one chain never stops the other: each chain has its own ledger and its
own runner. Poll sparsely, every 15–30 min, with one ssh call (or a Monitor until-loop on these lines). Do not watch
continuously.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=20 dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn \
  'grep -H "^EXIT" /data/execskill-20261021-ops/main-[GD]-run-*.log; tmux ls 2>/dev/null | grep execskill-main'
```

On an `EXIT` line, and otherwise every few hours, take pilot-runbook §6.1's snapshot with `$MAIN`: `monitor --root
$MAIN`, the `LEDGERS` view and the paused-attempt listing. None of them shows a score. Files to watch, beyond pilot §6.1's:

| File | Meaning |
|---|---|
| `$OPS/main-<c>-run-<n>.log` | `START`/`EXIT` lines, the run's final JSON, stderr diagnostics |
| `$MAIN/<c>/s<k>-<bench>/…` | k = 1–5: `s1-searchqa`, `s2-officeqa`, `s3-livemath`, `s4-spreadsheetbench`, `s5-alfworld` |
| `$MAIN/G/cap-check-G.json` | the cost check: `ok`, `per_cell`, the projection per scope, `configuration: "main"`, `pauses: false` |
| `$MAIN/D/route-<n>.json` | chain D's route history, written once per `switch-route` |
| `$MAIN/D/confirm-route-B.json` | route B's own first call |
| `$HIST/supply/searchqa-tail.json`, `$HIST/supply/alfworld-xs*.json`, `$PRE/pools/*.json` | pinned inputs. Never touch them: the steps re-hash them, and the read re-hashes the pools. |

Keep every attempt directory, log and receipt. Never delete or move them.

## 7. Pause outcomes specific to main

Every row of pilot-runbook §6.2 that is not listed here applies unchanged.

| Kind (where) | Cause | Operator |
|---|---|---|
| `balance_exhausted` (a chain-D unit, route A) | Elucid refused a call for exhausted balance (HTTP 402, or 403/429 with balance text). The client raises at once, never retries, and sends nothing more on that route. The call is charged its full reservation. | The owner's standing instruction of 17:3x ("如果第一个余额不足了", registrar row "deepseek route B") covers this case: switch chain D to route B and recover. Follow 8.1. |
| `balance_exhausted` (route B) | Northgate refused for exhausted balance (HTTP 429 `insufficient_quota`). | Report it to the owner, and let chain D wait. The options are to terminate, or to top up a route; going back to route A needs `switch-route --to A --reason "<the owner's words>"`. Chain G is unaffected. |
| cost-check breach (chain G; **not** a pause) | G's ledger tokens per SearchQA run cell exceed 3 × 3,400 = 10,200 (`ok: false`) | Chain G continues. Tell the owner, as information only. At the read, G's part is priced at ⌈part × factor_G⌉. If that does not fit, the chain pauses with `test_read_budget` there (pilot §6.2, §6.4). |
| `budget` | A scope reached its cap. | Main's caps are 3 × the need, so this means at least a threefold overrun. Report it. A raise needs the owner's written decision (pilot §6.4, with `$MAIN`). |
| `configuration` at a cut (steps 1, 3, 5) | A slice could not be cut: the SearchQA tail ran short after the exclusion, LiveMath's 283 = 119 + 100 + 64 left no slack, or ALFWorld's room groups ran short. | Registrar 18:4x: "A loud cut failure is the correct behaviour." Report it. The owner decides: terminate, or a v1.1 rule. |
| `first_call_unconfirmed` (chain level, including route B's) | as in the pilot | 5.3 |
| `consent_missing` | as in the pilot | The owner's consent exists, so check `consent --root $MAIN` and ask. Never rewrite the file. |
| `acceptance_undetermined` | as in the pilot: the round is final | No `recovery.json` (`recover` refuses it). Report it at once. |

The owner decides from infrastructure facts only, never from scores (§9.4). Report each pause in plain Chinese: what
stopped, the facts, the options and what a redo would cost.

## 8. Operator actions

### 8.1 Chain D ran out of balance: switch to route B (M4)

1. Wait for chain D's `EXIT 3` line with `{"status": "paused", "kind": "balance_exhausted", …}`. Check that no
   chain-D process is alive: no `run --chain D`, and no `step-unit` or `evaluate-unit` child of chain D.
   `switch-route` refuses to switch unless chain D's runner lock and every unit lock under `$MAIN/D` are free.
2. Switch the route:
   ```bash
   $CLI switch-route --manifest $MM --chain D --to B
   ```
   It checks the manifest's route-B pin and the credential file offline (no request, nothing printed). It writes
   `$MAIN/D/route-<n>.json` once and prints `next`: one `recover` command per open paused attempt (latest first),
   then the `run` command. A pause already used by an earlier switch needs `--reason`.
3. Recover each attempt that `switch-route` printed:
   ```bash
   $CLI recover --attempt <attempt> --decision "redo on route B: owner instruction 2026-10-22 17:3x, second deepseek provider when the first runs out of balance"
   ```
4. Relaunch chain D:
   ```bash
   tmux send-keys -t execskill-main-D "$OPS/main-run.sh D" Enter
   ```
   The new process binds route B (`setting_of`; a running unit never switches routes). It makes route B's own first
   call (`confirm-route-B.json`). Then it redoes the paused unit whole on route B. That redo counts as one of the
   unit's two redos and is charged to `D:redo`.

Report the switch to the owner with the time, the paused unit and the route record's hash. From then on, chain D's
cells record `solver_route: {"route": "B", "model": "deepseek-v4-flash"}` (route A's cells: route `"A"`; chain G's:
route `null`). The test read's sealed cells keep it, and analyses report chain D by route. The two routes' model
identity cannot be verified; this is a recorded caveat.

### 8.2 Everything else

Use pilot-runbook §6.3 (`recover`, `resume-ledger`, `terminate`) and §6.4 (cap raises, on the owner's written
decision). Substitute `$MAIN`, `$MM`, `execskill-main-<c>` and `main-run.sh`. Never act from a loop. Act only on an
idle chain, after its `EXIT` line.

## 9. End of the run and the readout

**The read** (automatic, per chain, after step 5's freeze): as pilot-runbook §7.2, with the main estimate (3.3). The
read units re-hash all five `$PRE/pools/*.json` files to skip test texts that also occur on the training side, so never
touch them.

**Continuation and unseal.** Registrar 17:0x: the main run is exploratory. It has no confirmatory label, so no formal
addendum is sealed. The code still refuses to unseal until every chain of `$MAIN` has ended (complete or terminated)
and `$MAIN/shared/owner-continuation.json` exists (`evaluation.continuation`: exactly `by` = `owner`, `date`,
`decision` ∈ {`continue`, `stop`}, `note`). With `stop`, the label is `read_after_stop_decision`; it is never
confirmatory. Registrar 19:1x (section 0, item 2): the owner writes it; at the readout the main agent gives the owner
a one-line command, as for the consent. It is written once, verbatim, never edited (pilot-runbook §7.3). No chain
reaches its read before the owner is back. Check it without writing anything:

```bash
$CLI continuation-check --manifest $MM --chain G; $CLI continuation-check --manifest $MM --chain D
```

**The canary scan and the report:**

```bash
LOG=$OPS/main-report-$(date -u +%Y%m%dT%H%M%SZ).log
tmux new-session -d -s "execskill-main-report-$(date -u +%H%M%S)" \
  "$CLI report --manifest $MM --out $OPS/main-readout > $LOG 2>&1; echo EXIT \$? >> $LOG; exec bash"
```

Follow pilot-runbook §7.4 with `$MAIN`: the whole-root scan before each chain's first unseal, hits, the owner's
"scan again" or `release <scan record_sha256>`, and `readout-<c>.json` with `unsealed.json`. A five-step root is larger
than the pilot's, so allow an hour or more per chain's scan.

Then update `docs/results-and-lessons.md`, `docs/current-workflow.md` (if the workflow changed) and
`docs/project-status.md`. Give the actual denominators, costs, models, chain D's split by route, the provenance and the
label `main_real_run` (exploratory). Negative or pending results stay negative or pending.
