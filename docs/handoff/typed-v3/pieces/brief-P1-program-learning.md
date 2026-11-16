# Brief P1: typed-v3 program learning (repair rounds with execution feedback, archive candidate)

You implement ONE piece of the next version of a research codebase. Work in the git tree
`<repo-root>` (branch `research/typed-skills-v3`). Do not touch any other
repository, do not push, do not commit (leave your changes in the working tree; the caller reviews and commits).
No network, no paid model calls: everything is tested with the in-memory fakes the test suite already uses.

## Read first (in this order, only what you need)

1. `docs/handoff/typed-v3/CHAIN-DECISIONS.md`: the owner-approved decisions. You implement T8 and T9, and the part
   of T1 that P1 needs (the version switch below). You do NOT implement T2 to T7 (items, gate list J, card rule,
   screen run, reads): other pieces do.
2. `skillopt/execskill/typed/__init__.py` (constants, sealed manifest options and their defaults).
3. `skillopt/execskill/typed/chain.py`: class `Services` (docstring), `_Run.programs`, `_Run.program`,
   `_Run.program_decision`, `_Run.cells`, `_Run.builder`, `_Run.gate_arm`, `_Run.compare`, `_Run.record`,
   `_Run.finalize`, and how `decisions.json` is built. Mind the conventions: every phase record is write-once
   (`self.record(unit, name, compute)`), a resumed step replays stored records without new calls, every gate arm is
   registered, units are named `s<k>/<name>`.
4. `skillopt/execskill/typed/writers.py`: `propose_programs`, `_fix_once`, `build_procedure`, `program_payload`,
   `engineer_system`; `skillopt/execskill/typed/engineer_prompt.py` and `replies.py` (how a reply is read with one
   format retry per unit, how prompts are verified against the bound static screen).
5. `skillopt/execskill/typed/mount.py`: `mount`, `mount_identity`, `solve`, how a candidate
   `{'procedure': record, 'home_type': tid}` is enabled; `skillopt/execskill/solver.py` docstring (hooks, notes,
   faults; a program acts through a routing predicate and hooks such as `before_call`, whose note is rendered into
   the request).
6. `skillopt/execskill/typed/bank/rejudge.py` `probe()` and `bank/spare.py` `first_request`: how a request is built
   with NO model call (the call function records and answers with a failed receipt).
7. `skillopt/execskill/typed/prepare.py`: how sealed manifest options (`base_card`, `schedule`, `memory_lock`,
   `read_plan`) are set, sealed and read back (`prepare.base_card_of` etc.); `scripts/run_typed.py` for the CLI.
8. The existing chain tests (find them with `ls tests | grep typed`; the chain tests build `Services` from fakes):
   learn how a fake engineer, fake solver and fake worker are scripted before writing new tests.

## What to build

### A. Version switch (minimal, T1)

- `VERSION = CONFIGURATION = 'typed-v3'`, evidence labels `typed_v3_real_run` / `typed_v3_smoke` (test label
  unchanged). Keep every typed-v2 BEHAVIOUR as the default of a sealed manifest option, exactly as typed-v2 kept
  typed-v1's (`BASE_CARD_DEFAULT`, `SCHEDULE_DEFAULT`, `READ_PLAN_DEFAULT`): a manifest without the new options
  behaves as typed-v2 does today. Rename `is_typed_v2` only if nothing outside `typed/` depends on the name (the
  frozen machinery snapshot is NOT in this tree and must not need a change); if in doubt keep the function and add
  what you need beside it.
- New sealed manifest option `program_learning` in `('single', 'repair')`, default `'single'` (typed-v2's flow,
  byte-identical records). New limits with defaults that change nothing under `'single'`:
  `program_repair_rounds = 3`, `program_paid_feedback = 1`.
- New sealed manifest option `archive`: default `{}`. Shape `{bench: {'package': str, 'procedures': [{'id': str,
  'record_sha256': str, 'file': str}]}}` per CHAIN. The archived procedure records live in the tree under
  `skillopt/execskill/typed/archive/<bench>/<package>/<id>.procedure.json` with an index file
  `skillopt/execskill/typed/archive/index.json` (per chain and bench: package name, files, sha256 of each file's
  bytes and each record's own `record_sha256`). Copy the records from
  `<docs-repo>/skill-archive/skills/`:
  chain G ZebraLogic `zebralogic/main-v6-G-s3-p-zebralogic-3-5/procedure.json`; chain D ZebraLogic
  `zebralogic/main-v6-D-s3-p-zebralogic-3-3/procedure.json`; both chains ALFWorld the three files
  `alfworld/alfworld-v11-accepted/p-alfworld-1-{6,14,15}.procedure.json`. NEVER copy or reference
  `oracle-reference`, `zebra-pc-*`, `main-v5-*` or any other folder: only these five records. A loader verifies
  bytes and record hashes against the index and refuses anything else.
- `prepare` gets the two options (CLI flags in `scripts/run_typed.py prepare` in the style of the existing ones),
  seals them, and a real run reads them back only from the manifest.

### B. Program learning under `program_learning == 'repair'` (T8)

Inside `_Run.programs` (keep `'single'` exactly as it is; branch on the manifest option read once at run start):

1. Proposals and static screen: unchanged (`propose_programs`).
2. PROBE (no model call, no ledger charge): for a procedure and a list of items, build the first request of every
   item twice with the solver shell and a probe call function: once with the step's current mount (the snapshot
   the gate would use, arm F) and once with the candidate enabled (arm `cand_program`). Per item record: `fired`
   (the candidate's id in the cell's fired list), `note_chars` (length of the candidate request's user text minus
   the F request's; a note is "shown" when it is above 0), `faults` (the shell's fault records naming this
   procedure, with their kind, e.g. timeout), and for the F side nothing but the length. The probe needs a sandbox
   worker (the program runs in it) and the same memory-lock and drain discipline as a cell unit; give it its own
   unit name `s<k>/program-<slot>-probe-<r>` and write ONE write-once record `probe.json` there:
   `{'items': n, 'fired': n, 'noted': n, 'faults': {kind: n}, 'per_item': [[item_id, fired, note_chars,
   [fault kinds]], ...]}`. A probe must never open the ledger for a charge and never send: prove it in a test with
   a solver client that raises if it is called. Add a `Services` field for the probe call if you need one
   (default None = build it from `bank.rejudge.probe` semantics: answer `{'ok': False, 'response': None,
   'finish_reason': None, 'usage': {}, 'error_type': <a constant>}`); make sure the chain's handling of failed
   receipts does not turn a probe into a pause or an infrastructure retry (do not route the probe through
   `_Run.cells` if that machinery would; call the solve function directly under the same lock and drain).
   ALFWorld: the episode ends at its first step (the first call fails): that first request is the probe.
   SpreadsheetBench: only what runs before the first call is probed. Say so in the record (`scope`).
3. Free repair rounds, at most `limits['program_repair_rounds']` per slot: a new writer function
   `writers.repair_program(...)` sends the engineer its entry and source and the coverage report (counts; for each
   failure class `fired_without_note`, `not_fired`, `fault:<kind>` up to 5 items with the public text the engineer
   already may see for learn items, bounded like the existing examples) and reads ONE revised program with the
   existing tolerant reader and its one format retry. The revision is screened by `build_procedure` (no extra fix
   call: a revision that fails the screen ends the repair with the last good version) and probed. Keep the version
   with the most noted items; ties: fewer faults, then the earlier version. A round that does not strictly
   improve ends the repair. Records: `s<k>/program-<slot>-repair-<r>/repair.json` (write-once: request hash,
   reading, screen, the probe summary, `kept`), and after the loop `s<k>/program-<slot>/refined.json` (which
   version goes on, its procedure record, the history). The engineer's system prompt for this request is a new
   mode `'repair'` beside `'propose'` and `'fix'`; follow how `engineer_prompt` builds and VERIFIES prompts (a test
   keeps the stated static-screen rules equal to the bound screen); state in the prompt the sandbox's wall limit
   per hook call (find the constant in the tree; it showed up as "wall timeout of 5 s" in a real run) and that an
   exhaustive search must prune.
4. One paid feedback round (`limits['program_paid_feedback']`, 0 switches it off): the kept version ONCE on the
   learn items (unit `s<k>/program-<slot>-learn`, arm `cand_program`, through `_Run.cells` like `card-r<j>-learn`).
   Compare per item with the F attempts the writers already use (`current_learned`): `fixed` (F wrong, candidate
   right), `broken` (F right, candidate wrong). If `broken >= fixed` and `fixed + broken > 0`: one more
   `repair_program` call that also shows up to 5 broken items; the revision is screened and probed and replaces
   the kept version only if its probe is not worse (noted items, then faults). No second paid round. Faults in
   these learn cells play the role of typed-v2's smoke: a kept version with a fault or a failure there is refused
   with reason `smoke_fault` (in `'repair'` mode there is no separate `-smoke` unit).
5. Gate and decision: unchanged (`gate_arm` on the gate slice, `compare('program', ...)`, member checks, describe,
   add). The decision record additionally carries `repair` (rounds, kept version, probe summaries) and `learn`
   (fixed / broken counts).

### C. The archive candidate (T9), only under `'repair'`

At the start of `programs` of the bench's step, when the manifest's `archive` names this bench: unit
`s<k>/program-0`. Load the package's procedure records through the verified loader; screen each with the typed
static screen exactly as a new program's source is screened (find the function `build_procedure` uses; a record
that fails is recorded with the screen's evidence and the WHOLE package is refused with reason `archive_screen`:
nothing is fixed). Probe the package on the learn items (record as in B.2). Gate the package as ONE candidate
against the step's current arm: all its procedures enabled together (ALFWorld's package has three; extend the
candidate shape to carry a list, e.g. `{'procedures': [...], 'home_type': tid}`, in `mount.mount`,
`mount.mount_identity` and wherever a candidate is read, keeping `{'procedure': ...}` valid and its identity
unchanged). Decision by the same program rule (fired = any procedure of the package fired). Accepted: every
procedure joins the library as a program skill of the type with `origin: 'archive'` and the package name (describe
each as an accepted program is described), and the step's mount snapshot for the engineer's proposals and gates is
taken AFTER it, so the engineer's `parent` holds the archive programs and its candidates are judged against the
incumbent that holds them (the current arm for later candidates is the archive package's gate arm, in the way an
accepted card's `cand_card` runs become the current arm). Refused: recorded, nothing joins, the engineer proceeds
as without an archive. `decisions.json` keeps the archive decision as its own row (`kind: 'program', 'origin':
'archive'`).

## Rules that are not negotiable

- Frozen behaviour: with the default options every existing test passes unchanged and every record of a typed-v2
  style run is byte-identical. Do not edit tests to make them pass unless the test pins the VERSION string or an
  evidence label that part A changes; list every such edit.
- Write-once records, resume safety: a step interrupted anywhere in B or C resumes without repeating a model call
  whose record exists and without changing a stored record. Add tests that kill and resume inside a repair loop,
  after the probe and before the repair record, and after an accepted archive candidate.
- No test-side data: nothing here reads a test panel. The repository has a path-word guard
  (`FORBIDDEN_PATH_WORDS`): do not create paths containing `test`, `holdout`, `held_out`, `final`, `sealed`,
  `reserve`, `verifier_calibration`, `testaccess` inside run roots (unit names, record names). Python test files
  under `tests/` keep their usual names.
- A writer never sees a gate item or a reference answer: the repair report shows only learn items' public text and
  outcome labels, as the existing examples do. Check how `outcomes_for_writer` bounds and screens examples and
  reuse it.
- Deterministic: no wall-clock, random or hash-order dependence in any stored record.
- Style: follow the file's existing style (docstrings that say what and why, `require(...)` for invariants).
- Do not weaken the static screen, the sandbox, the ledger, or any `require`.

## Tests to add (pytest, fakes only) and how to run

Run the typed test files with a TMPDIR whose name has no forbidden word, e.g.
`TMPDIR=/tmp/typed3-neutral python3 -m pytest tests -q -p no:cacheprovider -x -k "typed"` (find the right selection;
the full suite is large: run at least every test file whose name contains `typed`, and say exactly what you ran
and the counts).
New tests must show, each with expected values computed independently of the code under check:
1. `'single'` is unchanged (an existing golden test still passes; add nothing here).
2. The probe sends nothing and charges nothing; its record counts fired / noted / faults correctly for a scripted
   program that notes on some items, stays silent on others and times out on one.
3. The repair loop keeps the best version (most noted items), stops at the first round without improvement, ends on
   a revision that fails the screen, and never exceeds the limit; every round's record is written once.
4. The paid feedback round: `broken >= fixed` triggers exactly one more repair; a fault in the learn cells refuses
   the candidate with `smoke_fault`.
5. The archive package: verified against the index (a changed byte is refused before anything runs); gated first;
   accepted -> its procedures are in the library with origin `archive`, later candidates are compared with the
   incumbent that holds them; refused -> the library is unchanged; a package that fails the static screen is
   refused whole.
6. Resume: kill at the three points named above, resume, compare all records with an uninterrupted run.

## Report back (your final message)

Plain text: (a) the files you changed and created, one line each on what changed; (b) the exact test commands and
their pass/fail counts; (c) every existing test you edited and why; (d) anything in this brief you could not do or
decided differently, with the reason; (e) open risks you see. Do not claim something is tested if it is not.
