# typed-v2 spec: version, identity, machinery guard, operations

Status: complete draft, 2026-11-12 (design only; nothing in the tree is edited). Area: D1, D6, D7; F1, F2, F3.
Paths relative to `<repo-root>`; `T/` = `skillopt/execskill/typed/`,
`X/` = `skillopt/execskill/`, `OPS/` = `<claude-job-tmp>/typed/ops/` (typed-v1 helpers, read
only). Marks: [V] opened and read, [I] inferred. "List" = `docs/handoff/typed-v2/machinery-main-v10.sha256`
(564 lines; its own sha256 is `3c37fdd90de0e6b51013af7fd4f166f3fa9a1fead5836b335111a4775202599f` [V, computed]).

## 0. Blockers

No blockers. Three readings of DECISIONS for the coordinator to confirm:
- D1 "records ... in the run manifest": the manifest is sealed at `prepare` (`T/prepare.py:239-251` [V]), so the
  bound `prepare` process (`OPS/run-typed.sh:15, :35, :47` [V]) writes the record and every later start must equal it.
- F2 covers 564 `.py` files only; `skillopt/` also holds 64 non-`.py` files (policy JSONs, prompt texts) [V,
  counted] that the bound run reads from the snapshot and local tests from this tree. No list covers them (Q2).
- D7: with the call sites unchanged, interference IS possible (1.13). Two changed lines in `T/` remove it (Q1).

## 1. Behaviour

Identity
1. `typed.VERSION == typed.CONFIGURATION == 'typed-v2'`; evidence labels `typed_v2_real_run`, `typed_v2_smoke`,
   `engineering_fixture`. `MACHINERY`, `MACHINERY_SNAPSHOT`, `MACHINERY_MANIFEST`, `ROUTE_B_EVIDENCE`, `SEED`,
   `SLICES`, `CAPS`, `READ_ARMS` keep their typed-v1 values. No `is_typed_v1`, no profile, no compatibility switch.
2. `prepare` accepts only a NEW directory `/data/execskill-<8 digits>-typed-v2[-smoke]`; names ending `-typed-v1`,
   `-typed-v1-smoke`, `-typed-v3` are refused by name.
3. Every entry that takes a root (`run`, resume, `smoke` real and fake, `readout`, `status`, `load_manifest`) first
   calls `prepare.own_root`. It refuses, before anything else is read or written, when (a) a path component names
   another typed version (`typed-v<n>`, n not 2), (b) `<root>/manifest.json` carries another `version` or
   `configuration`, (c) `<root>/<chain>/state.json` carries another `version`. The directory is left unchanged.
   Today `readout.build` writes `<root>/readout/<stamp>/` with no version check (`T/readout.py:619-643` [V]).
4. A library or type map whose `version` is not `typed-v2-library` / `typed-v2-typemap`, or whose `module` is not
   `typed-v2`, is refused at load. A new chain starts from the empty library (`skills: []`, `T/library.py:91` [V]).
5. `bind_machinery` refuses a snapshot that contains `skillopt/execskill/typed/`. Reason: the tree path is APPENDED
   (`scripts/run_typed.py:48-50` [V]), so such a snapshot (for example the typed-v1 code snapshot) would shadow this
   tree's typed package and run typed-v1 code under the typed-v2 launcher.
6. The draw keys keep their typed-v1 literal values: `SEED = 20261110`, `SLICE_TAG = 'typed-v1:%s:slices'`,
   `EXAMPLE_TAG = 'typed-v1:writer-examples'`. With the same pool pins the learn / gate items and the order of the
   writer examples equal typed-v1's (needed for D2's byte-identical first request; slices are out of scope) (Q3).

Machinery guard
7. Guard test: every file in the List exists in this tree with the listed hash, AND the set of `skillopt/**/*.py`
   outside `T/` equals the listed set. A module added outside `T/`, or a machinery file edited or removed, fails.
8. `bind_machinery` verifies after binding, always: the List's own sha256 equals `machinery.LIST_SHA256`; the 564
   files under the snapshot equal the List; no unlisted `.py` under `<snapshot>/skillopt/`; `skillopt` was loaded
   from the snapshot and `typed` from the tree; every symbol in `machinery.REQUIRED` exists. Any failure exits
   before a command runs. Unbound starts (local tests, `smoke --fake`) are not checked here.
9. `prepare` writes `machinery_code` (snapshot path, `bound`, List name, List sha256, 564, symbol count) into the
   sealed manifest. Every real start (`chain.real_services`: run, resume, real smoke) recomputes it and requires
   `bound`, snapshot path `== MACHINERY_SNAPSHOT`, equality with the manifest's record, and that the typed tree's
   hash equals `provenance.typed_tree.sha256_list_sha256`. The chain state stores the record; a resume compares it.
10. A manifest prepared unbound (`bound: false`) is refused by every real start; the `prepare` command prints the
    record so the launcher can stop at once.
11. Provenance stays truthful: `typed_tree` (whole tree, `T/prepare.py:226-236` [V], unchanged) is true of the code
    that ran because 7-9 prove the tree's 564 machinery files equal the bound ones; the new `typed_code` entry
    hashes only what this tree contributes to a bound run (`T/**`, `scripts/run_typed.py`).

Caps
12. `CAPS` stays G 150,000,000 / D 170,000,000 (`T/__init__.py:26` [V]). Today the run takes the CONSTANT
    (`T/chain.py:973`; `real_services` passes no cap, `:1127-1138`; `Services.cap` is None, `:159`) [V]; the manifest
    field (`T/prepare.py:273` [V]) is unread. On resume `Ledger.__init__` raises `ValueError('Ledger cap changed')`
    for a different cap (`T/units.py:114-115` [V]; the map's `:118-119` is off). typed-v2: constant fixed in the
    code snapshot before `prepare` -> sealed in the manifest -> `load_manifest` requires `caps == CAPS` ->
    `real_services` passes `cap=manifest['caps'][chain]` -> ledger compare on resume. No command line option.
    Sufficiency [I, coordinator's practice-side ledger note of 11/12 11:15, not in this tree]: typed-v1 had charged
    G 33.7M (learning 7.5M, reads 26.2M) and D 45.1M (7.5M, 37.6M) after about 3.5 steps per chain; tripling ALL
    learning tokens and doubling the reads gives about 85M (G) and 107M (D). The gate area confirms per unit.

Running beside typed-v1 (D7)
13. Finding, unchanged call sites. Container names are `execskill-sbx-<chain lower>-<sha256(unit)[:12]>-<uuid4>`
    (`X/sandbox/client.py:80, :138-143, :658` [V]); typed passes the chain letter and the chain-relative unit string
    (`s2/noise`, `s3/program-1`, ...; `T/chain.py:1155` [V]): no version, no root. Names never collide (uuid), but
    the unit drain does. `drain_unit` (`client.py:316-325` [V]) lists `^/execskill-sbx-<g|d>-<sha12>-` and, because
    typed drains with grace 120 s (`T/chain.py:1115, :1164`; `X/profiles.py:150-153, :206-208` [V]), force-removes
    EVERY listed container (`client.py:292-303` [V]), then raises `CleanupUnconfirmed` if one is listed again
    (`:306-313` [V]), which pauses the chain (`T/chain.py:514-530` [V]). So when a typed-v2 chain ends unit U while
    the typed-v1 chain of the same letter is inside its own unit U, typed-v2 removes typed-v1's live sandboxes
    (one retry, `RETRIED`, `client.py:100` [V]; then a failed cell [I]) and may pause itself. A typed-v2 SMOKE with
    that letter is the likelier case: it shares the unit names `s<k>/...` and sweeps all step numbers in hours.
    Only read units differ (`practice-read-*` vs `test-read-*`, `T/reads.py:64-68` [V]).
14. Shared by design, no corruption: slot pools and `memory-heavy.lock` under the common `slot_root` are flock
    files for every process on the machine (`X/slots.py`, `X/chain.py:84-86, :126-144` [V]): contention and lock
    starvation only. `history_root` is never read in `T/`; the embedder is a stdin / stdout subprocess
    (`T/embed_service.py:4, :18`); `T/` names no temp path [V, grep]. Ledgers, call records and libraries live under
    the run root. TMPDIR, tmux and log names are fixed by ops (2b).
15. With Q1, typed-v2 passes `'typed-v2:<root name>:' + unit` to both `unit_tag` and `drain_unit`: its prefixes are
    disjoint from typed-v1's and from its own smoke's. `tag` is used only in the container name
    (`client.py:481, :658` [V]); no request or cell identity contains it [I].
16. Operating rule. Without Q1: no typed-v2 process (real chain OR real smoke) with chain letter L while a typed-v1
    process with letter L runs. With Q1: correctness-safe side by side; default still one real chain per letter at
    a time for throughput (pools sized for two chains; the heavy lock has no fairness).

Operations
17. Names (D6): snapshot `/data/execskill-code-<date>-typed-v2`, build `/data/execskill-dev-typed2`, run root
    `/data/execskill-<date>-typed-v2`, smoke root `...-typed-v2-smoke`, ops `/data/typed-v2-ops`; TMPDIR
    `/tmp/typed2run-<phase>-<chain>`; test scratch `/tmp/typed2-neutral`; tmux `typed2-run-G|D`, `typed2-smoke-G|D`.
    No typed-v2 helper names, removes or lists a typed-v1 path. `/data/typed-v1-ops` and `OPS/` are not edited.
18. Consent (rules out of scope, unchanged): `<root>/shared/consent.json` with EXACTLY six fields
    (`T/reads.py:91-109` [V]; the set is `profiles.CONSENT_FIELDS`, named in `X/evaluation.py:14` [V] and in the
    fixture `tests/test_typed_reads.py:32-35` [V]): `test_evaluation: true`, `sheet_test_qualification: true`,
    `multi_arm_arms: ["C0","C","S1","S2","S3","S4","S5"]` (this order), `by: "owner"`, `date` and `note` nonblank
    strings. No version or root field exists, so a copied typed-v1 consent would pass (Q5).

## 2. Change list

2a. Tree

| File, lines today | Change |
|---|---|
| `T/__init__.py:1-6, :9, :10, :63, :72-73` [V] | docstring; `VERSION = 'typed-v2'`; `CONFIGURATION = 'typed-v2'`; `EVIDENCE` values `typed_v2_real_run`, `typed_v2_smoke`, `engineering_fixture`; delete `is_typed_v1` (no caller [V, grep]). `:13, :26, :56-58, :62` unchanged |
| `T/machinery.py` NEW | `LIST = 'docs/handoff/typed-v2/machinery-main-v10.sha256'`; `LIST_SHA256`; `LIST_FILES = 564`; `REQUIRED = {module: (names,)}`; `listed(tree)`; `compare(root) -> [(path, 'missing'/'differs'/'unlisted')]`; `loaded() -> {snapshot, bound, typed_from}` from `skillopt.__file__` and its own `__file__`; `require_symbols() -> int`; `check(*, real) -> record` (real: bound and `snapshot == MACHINERY_SNAPSHOT`). Reads bytes; stdlib only |
| `T/prepare.py:34` [V] | `ROOT_NAME = re.compile(r'^execskill-\d{8}-typed-v2(-smoke)?$')` |
| `T/prepare.py:39`, `T/writers.py:36` [V] | values kept; comment "draw key, frozen literal, not a version label" |
| `T/prepare.py` NEW beside `check_root :46-59` | `OTHER_TYPED = re.compile(r'typed-v(\d+)')`; `own_root(root) -> Path` (1.3); `check_root` calls it; messages `:50, :54, :56, :58, :69` say typed-v2 |
| `T/prepare.py:226-236` [V] | `tree_provenance` unchanged; NEW `typed_code(tree) -> {files, sha256_list_sha256}` over the `prelaunch.sha256_list` lines under `skillopt/execskill/typed/` plus `scripts/run_typed.py` |
| `T/prepare.py:239-251, :269-285, :293-302` [V] | messages; fields + `machinery_code = machinery.check(real=False)`, + `draw_keys`, `provenance` + `typed_code`; `load_manifest`: `own_root` first, 'A typed-v2 manifest', + `caps == dict(CAPS)`, + `machinery_code` present |
| `T/library.py:1, :15, :177-178`; `T/tasktypes.py:1, :22, :263-264` [V] | `LIBRARY_VERSION = 'typed-v2-library'`; `TYPEMAP_VERSION = 'typed-v2-typemap'`; both loads also require `module == VERSION` |
| `T/chain.py:150-162, :944-950, :953-963` [V] | `Services` + `machinery_code: object = None`; `run` calls `prepare.own_root(root)` first; a new state stores `machinery_code` and `container_scope`; a reopened state must equal both |
| `T/chain.py:1084-1138` [V] | NEW `start_checks(root, manifest, *, check=machinery.check, provenance=prepare.tree_provenance) -> record` (1.9), called after `load_manifest`; `Services(..., cap=manifest['caps'][chain], machinery_code=record)` |
| `T/chain.py:1155, :1164` [V] (Q1) | `scope = '%s:%s:' % (VERSION, Path(root).name)`; `sandbox.unit_tag(chain, scope + unit)`; `sandbox.drain_unit(chain, scope + unit, ...)` |
| `T/smoke.py:126-131` [V] | `prepare.own_root(root)` after `smoke_root(root)`; `:218-228` unchanged (constants follow) |
| `T/readout.py:1, :619-623, :645-647, :868` [V] | `build` and `status` call `prepare.own_root(root)`; title built from `VERSION`; `:49` follows `VERSION` -> `typed-v2-readout-v1` |
| `T/reads.py:83-124` [V] | message texts only (`:86, :98, :101, :104, :106, :108, :124`); `consent` logic untouched |
| docstrings `T/units.py:1`, `T/gates.py:1`, `T/mount.py:1, :6`, `T/embed_service.py:2`, `T/writers.py:1, :361`, `T/chain.py:1`, `T/smoke.py:1` [V] | text only |
| `scripts/run_typed.py:2, :35-54, :213, :249, :275-283` [V] | text; `bind_machinery`: at `:39-42` refuse `<snapshot>/skillopt/execskill/typed`, after `:52` `binding['machinery_code'] = machinery.check(real=False)`, no switch to skip it; `prepare` also prints `machinery_code`; `main` keeps the binding (discarded today, `:277-278`) |

2b. Operations (new copies for `/data/typed-v2-ops`, staged in a new local directory; `OPS/` is never edited)

| Helper, lines today [V] | Change |
|---|---|
| `run-typed.sh:7-13` | `OPS=/data/typed-v2-ops`; `DATE=<snapshot date>`; `BUILD=/data/execskill-dev-typed2`; `SNAP=/data/execskill-code-$DATE-typed-v2`; `SMOKE_ROOT=/data/execskill-$DATE-typed-v2-smoke`; `RUN_ROOT=/data/execskill-$DATE-typed-v2`; `:11, :15` unchanged |
| `run-typed.sh:26-29` | after the copy: `(cd $MACHINERY && sha256sum --quiet -c $SNAP/<List>)`, the same inside `$SNAP` (the List is in `sha256sum` format) |
| `run-typed.sh:30-33` | `TMPDIR=/tmp/typed2run-a`; add the new test files (section 4); cleanup removes only `/tmp/typed2run-a /tmp/typed2-neutral` |
| `run-typed.sh:39, :45` | `T=/tmp/typed2run-$phase-$chain`. Today's `/tmp/typedrun-$phase-$chain` is `rm -rf`-ed before and after each chain process: reusing it would delete the running typed-v1 chain's TMPDIR |
| `run-typed.sh:35, :47`, run phase | after `prepare`: stop unless the printed `machinery_code.bound` is true; before `run`: stop unless the consent `note` contains `$(basename $RUN_ROOT)` (Q5) |
| `watch.sh:8`; `watch-probe.sh:3, :4, :7`; `smoke-status.py:8`; `stall_probe.sh:7`, `stall_probe2.sh:6` | `/data/typed-v2-ops/...`; `ROOT=/data/execskill-$DATE-typed-v2`; tmux `=typed2-run-$c`; `pgrep -f run_typed.py` matches typed-v1 processes too: match `code-[0-9]*-typed-v2/scripts/run_typed.py` |
| `fault_probe.py:7, :9, :11`; `selection_check.py:8-11` | v2 snapshot, smoke root, ops dir, scratch `...-typed-v2-smoke-selcheck`; `fault_probe.py:23-25` follows D3's `build_procedure` signature |
| `reuse.py` (`mode same`) | today pairs cells `C0a` / `C0b` of `s<k>/noise` by the last 3 tag characters; rewrite for D5's R = 3 repeat labels inside one unit (needs the gate area's label format) |
| `attdump.py:23`; `cost.py`, `decdump.py` (path-free) | split on `"typed-v2/"`; print D3 / D4 fields (source used, format retry), D5 fields (R, per-item sums, SE inputs), promotion records; `cost.py` adds `charged / cap` |
| `snapshot_provenance.py:38` | note text; also record the List sha256 and the `sha256sum -c` result for `$MACHINERY` |
| `diag.py`, `mounts.py`, `mounts2.py`, `qa3.py`, `stepdump.py` | not opened [I]: grep for `typed-v1`, `typedrun`, `typed-run` when copied |

## 3. Records and identity

| Record | Field | typed-v2 value |
|---|---|---|
| `manifest.json` | `version`, `configuration`, `evidence`, `root` | `typed-v2`, `typed-v2`, `typed_v2_real_run` / `typed_v2_smoke`, new root name |
| `manifest.json` | `machinery_code` NEW | `{snapshot, bound, typed_from, list, list_sha256, files: 564, symbols}` |
| `manifest.json` | `draw_keys` NEW | `{seed: 20261110, slices: 'typed-v1:%s:slices', examples: 'typed-v1:writer-examples'}` |
| `manifest.json` | `provenance.typed_code` NEW; `caps` | `{files, sha256_list_sha256}`; same numbers, now the value the run uses |
| `<chain>/state.json` | `version`, `evidence`; NEW `machinery_code`, `container_scope` | compared on resume |
| `library.json`, type map | `version`, `module` | `typed-v2-library` / `typed-v2-typemap`, `typed-v2`; record hashes differ from typed-v1 for equal content |
| `confirm.json` `T/chain.py:550`, `decisions.json` `:924`, read aggregate / status `T/reads.py:449, :462` [V] | `version` (+ `evidence` at `:924`) | `typed-v2`, `typed_v2_*` |
| readout documents | `version`; title | `typed-v2-readout-v1`; `# typed-v2 readout: ...` |
| `ledger.json` | none (no version field, `T/units.py:101-127` [V]) | `cap` now comes from the manifest |
| `consent.json`, `recovery.json` | none | unchanged |

Requests and pins. This area changes NO model request text. How I know: `VERSION` and `CONFIGURATION` occur only
in record stamps and checks ([V] grep: `T/prepare.py:270, :297`, `T/chain.py:550, :924, :944, :948`, `T/reads.py:449,
:462`, `T/library.py:91`, `T/tasktypes.py:150`, `T/smoke.py:222`, `T/readout.py:49`). Typed evidence labels go to
typed records; machinery calls get `ROUTE_B_EVIDENCE` (`T/chain.py:865`, `T/reads.py:54, :82-87` [V]) and the
configuration `MACHINERY` (`T/chain.py:1154` [V]); `POLICY_VERSION` (`T/writers.py:37` [V]) is unchanged. The step
label `typed/<chain>/s<k>` (`T/chain.py:436-438` [V]) is unchanged, harmless because every stored call lives under
its own run root. No 64-hex prompt pin exists in `T/` or `tests/test_typed_*.py` today [V, grep]; D6's "new prompt
pins" are the new typed-level constants of D2 / D3 / D4, pinned in their own areas. Which typed-v1 files a change
touched is checked against `docs/handoff/typed-v2/typed-v1-source-manifest.txt` [V].

## 4. Tests

New, `tests/test_typed2_machinery.py`:
- `test_list_is_pinned` (own sha256, 564 sorted unique lines, none in `T/`); `test_tree_equals_list` (behaviour 7).
- `test_bind_refuses_altered_snapshot`: stand-in with one byte changed / one file missing / one extra
  `skillopt/x.py` / a `skillopt/execskill/typed/` directory: each refused, the message names the path.
- `test_real_check_needs_bound_snapshot_path`: `check(real=True)` unbound, and bound to the stand-in, both refuse.
- `test_start_checks`: `chain.start_checks` with injected `check` / `provenance`: equal passes; changed List hash,
  snapshot path, typed tree hash, or a `bound: false` manifest each refuse. (No test calls `real_services` [V, grep].)
- `test_bound_fresh_interpreter` (pattern `tests/test_typed_cli.py:80-105` [V]: `sys.executable -I -c`, no
  PYTHONPATH). Snapshot on the Mac: a stand-in built in `/tmp/typed2-neutral/<id>/snap` by copying exactly the 564
  listed files (plus the 64 data files) from this tree; it has no `typed/`, so anything typed-v2 needs outside the
  List fails as on dl. Where `MACHINERY_SNAPSHOT` exists (dl) the test runs a second time against it. The child
  runs `tests/typed2_bound_driver.py` (not collected), one case per area: (i) origins: every loaded `skillopt.*`
  module outside typed has its file under the snapshot, every `typed.*` under the tree, `machinery_code.bound`;
  (ii) every `T/*.py` imported; (iii) `require_symbols()` plus an AST pass over `T/*.py` showing each attribute used
  on a machinery module alias is in `REQUIRED`; (iv) D2: typed card screen against the bound `v225_cards` function,
  a 4,500-character card through library, mount, describer; (v) D3: each legal / illegal prompt example through
  the bound `policy` screen; (vi) D4: the two F6 reply shapes; (vii) the CLI itself, bound: `run_typed.py
  --machinery-snapshot <snap> smoke --fake --chain G`, then `readout` and `status` on that root (covers D5 labels
  through the bound `arm_of` path and D8's default schedule).

New, `tests/test_typed2_identity.py`:
- `test_other_version_roots_refused`: for `run`, fake `smoke`, `readout.build`, `readout.status`, `load_manifest`
  x (typed-v1-named directory, typed-v2-named directory with a typed-v1 manifest, with a typed-v1 `G/state.json`):
  refusal, and the directory listing with sizes and mtimes is unchanged.
- `test_other_version_library_refused` (library and type map; wrong `version`, and right `version` + wrong `module`).
- `test_draw_keys_frozen`: the three literals, and `draw_slices` of a fixture pool equals a stored typed-v1 draw.
- `test_cap_from_sealed_manifest`: `caps != CAPS` manifest refused; ledger opened with the manifest value.
- `test_container_scope`: prefix for (`G`, `s2/noise`) differs from `sandbox.unit_tag('G', 's2/noise')`; the
  worker tag and the drain prefix agree; two root names give two prefixes.

Existing tests that must change:
- `tests/test_typed_cli.py:80-103` [V]: the two-file MARKER snapshot can no longer bind (behaviour 8); use the
  stand-in and assert on `skillopt.__file__`; `:99, :116, :126` -> `'typed-v2'`. Refusal cases `:105, :107` stay.
- `tests/test_typed_reads.py:555-575` [V]: root-name cases flip (`:560` lists `...-typed-v2` as refused today);
  version / evidence pins at `:253, :301, :317, :325, :351, :354, :374, :392, :424, :459, :583, :587-588, :608,
  :630, :634, :644` [V, grep]; `tests/test_typed_chain.py:681`; `tests/test_typed_mount.py:350, :443`.
- `/tmp/typed-neutral` -> `/tmp/typed2-neutral` at `tests/test_typed_{writers:18, units:16, chain:21, chain:765,
  readout:20, cli:23, e2e:26, core:18, mount:23, reads:19}` [V, grep], so test runs of the two trees never share
  or delete each other's scratch. Consent note fixtures `test_typed_reads.py:34`, `test_typed_e2e.py:111`: text.

## 5. Interfaces to other areas

- All areas: add each machinery symbol you call to `machinery.REQUIRED` and one case to
  `tests/typed2_bound_driver.py`. New modules go under `T/` only; behaviour 7 fails otherwise.
- Card (D2): the first-attempt request stays byte-identical only with the draw keys of 1.6 unchanged.
- Programs / reader (D3, D4): each new prompt constant carries its own sha256 pin and test; `fault_probe.py` and
  `attdump.py` follow your signatures and record fields.
- Gate (D5): give the repeat label format (for `reuse.py`, `cost.py`) and the per-step cell counts to close 1.12.
- Schedule (D8): your manifest field goes into the same `fields` dict (`T/prepare.py:269-285`) and is validated in
  `load_manifest`; `own_root` and `start_checks` run before any schedule logic.
- Owner hooks (DECISIONS section 3): none designed here. A read-policy change would touch `T/reads.py`.

## 6. Risks and open questions

Q1. Scope the container tag by version and root (`T/chain.py:1155, :1164`, two lines)? Recommended: yes. It is the
    only way inside `T/` to make D7's condition true; a typed-v2 smoke may then run beside typed-v1. Without it,
    rule 1.16 "no same letter, smoke included" is binding.
Q2. The 64 non-`.py` machinery files are unchecked, and nothing shows the dl snapshot holds no further `.py`.
    Recommended: the coordinator lists ALL files under `skillopt/` of the main-v10 snapshot once on dl (read-only);
    a second file `machinery-main-v10-data.sha256` then extends the guard test, `compare` and the stand-in.
Q3. Keep `SEED`, `SLICE_TAG`, `EXAMPLE_TAG` at typed-v1 values (same practice items as typed-v1)? Recommended: yes
    (slices are out of scope; D2 needs it); the manifest's `draw_keys` states it openly.
Q4. Typed code or machinery changed between `prepare` and a resume: refuse with no override? Recommended: yes; a fix
    means a new snapshot and a new root ("never patch mid-run"). Cost: no hotfix for a running chain.
Q5. Consent is not bound to version or root. Recommended: leave the rule as it is (out of scope) and add the
    launcher check of 2b (the `note` must contain the run root's name); the coordinator writes the note that way.

## NOT DONE

- Not verifiable from here (no ssh): that the dl snapshot has no `typed/` package, no `.py` beyond the 564 and the
  same non-`.py` files; the value of `slot_root` in the machinery manifest.
- `profiles.CONSENT_FIELDS` definition line not located (field set taken from `X/evaluation.py:14` and the fixture).
- Five ops helpers not opened (last row of 2b). The cap arithmetic in 1.12 is an estimate, not a proof.
