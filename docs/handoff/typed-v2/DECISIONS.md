# typed-v2: coordinator decisions (binding for the design spec)

2026-11-12, written by the coordinator (the monitoring session). Status: decisions taken; the design spec and the code
are not written yet. Inputs: the owner's approval of three changes (11/12 about 11:0x), the six change maps and
`critic.md` in `<claude-job-tmp>/typed2/maps/`, and practice-side evidence of the typed-v1 run.
Paths are relative to this tree (`<repo-root>`); `T/` = `skillopt/execskill/typed/`,
`X/` = `skillopt/execskill/`.

## 0. Facts every section must respect

- **F1, the bound run.** On the Linux machine every typed process starts through `scripts/run_typed.py
  --machinery-snapshot /data/execskill-code-20261109-main-v10`. `bind_machinery` imports `skillopt` from that frozen
  snapshot and only appends this tree's `X/` directory to `skillopt.execskill.__path__`. So `X/policy.py`,
  `X/package.py`, `X/notes.py`, `X/engineer_reader.py`, `X/v225_cards.py`, `X/v225_writer.py`, `X/profiles.py`,
  `X/chain.py`, `X/v218_lock.py`, `X/sandbox/*` and all of `skillopt/coevo5/` are loaded FROM THE SNAPSHOT. Only `T/*`
  (and module names that exist only in this tree) come from this tree. Local tests and the dl `tests` phase run
  unbound and cannot see the difference.
- **F2, equality checked.** 11/12 13:5x: all 564 `skillopt/**/*.py` files outside `T/` in this tree are byte-identical
  to the dl snapshot (sha256 list: `docs/handoff/typed-v2/machinery-main-v10.sha256`, `LC_ALL=C` sorted by path). Line
  numbers the maps give for route-B files therefore hold for the bound code.
- **F3, typed-v1 stays frozen.** `docs/handoff/typed-v1/DESIGN.md`, the typed-v1 tree
  (`<repo-root>`) and its dl snapshot are not edited. typed-v1 may still be running
  on dl while typed-v2 is built.
- **F4, sealing.** Learners never see test material; test numbers never choose configurations; reads happen only in
  consent-gated sealed read units. Nothing in typed-v2 weakens this.
- **F5, owner rules.** After every learning step all five test panels are really read with fresh calls. Skipping or
  reusing a read, or changing a decision rule to save tokens, is the owner's decision and is NOT designed in here
  (section 3). The static program screen and the sandbox stay strict.
- **F6, practice-side evidence from typed-v1 (12 program candidates, 21 card texts).** Card content lengths 2,349 to
  3,499 characters (mean about 2,883); 9 of 21 over 3,000; 4 card rounds void; the screen counts the newline that
  `coevo5/texts.py` `instruction_text` appends, so a 3,000-character card was rejected as 3,001. 4 of 12 program
  candidates were lost at the static screen (two `frozenset("...".split())` word sets, one regex built by
  concatenation, one `type(e).__name__`); 2 of the 4 fix replies were correct and were lost by the reply reading (top
  level key `change` instead of `changes`; inline `"source": "PLACEHOLDER"` with the real code in the fenced block).
  The engineer prompt inherited from route B does not list the screen rules and carries stale text (J1..J7, "at most
  3 changes"); failure evidence is only rule + line; a third proposal (returned 4 times) is never promoted. Gate: G
  ZebraLogic flips 31 of 100 items between two identical-request runs (tau 11.18); a +11.0 card with 20 better / 9
  worse was rejected by 0.18.

## 1. Decisions

**D1. The machinery stays frozen; every typed-v2 change lives in `T/`, `scripts/`, `tests/`, `docs/`.**
No file loaded from the snapshot (F1) is edited. Consequence for the approved change 2: the two screen relaxations
(nested pure constants; `__name__` on exception types) are NOT implemented in typed-v2. Reason: they need a new
machinery snapshot (a new policy version in `X/policy.py` plus identity branches in package / notes / client / the
in-container worker, and possibly a new qualification of the sheet scorer), while F6 shows the losses came from the
writer not being told the rules and from the reply reading, both fixable in `T/`. The rest of change 2 is kept: the
engineer is told the rules, failure evidence names the rule and the standard rewrite, the reply reading is tolerant,
one format retry, a third proposal is promoted. The relaxation is recorded as a deferred option; the owner is told.
A guard test proves that no file listed in `machinery-main-v10.sha256` differs in this tree, a fresh-interpreter test
runs the new typed code under `bind_machinery`, and a run-start check verifies the bound snapshot against the list
and records snapshot path + list hash in the run manifest.

**D2. Card length, typed side only.** Typed-owned card screen in `T/` (content screens copied from
`X/v225_cards.py` with a drift-guard test against the bound function). The writer is still TOLD 3,000 characters and
12 bullets (the first-attempt request stays byte-identical to typed-v1 unless a section proves this impossible). Hard
reject only above 4,500 content characters; the bullet hard limit stays 12. The count excludes the newline appended by
`instruction_text`; the stored text and every identity derived from it are unchanged in shape (text keeps its
newline). The retry message states the actual length, the target (3,000) and how many characters to cut; retry
sentences are new typed-level constants (route-B `CARD_RETRY` / `RETRY_REASONS` are hash-pinned and stay untouched).
The recorded `chars` field is defined as content characters without the newline (documented change from typed-v1).
Every later consumer of a card text (library load, mount, smoke, describer, readout, any call into the frozen
`card_violation` or `package`) must be shown to accept a card of up to 4,500 characters, or be listed as a blocker.

**D3. Programs: typed-owned engineer prompt, evidence, promotion (screen unchanged).** typed-v2 builds its own
engineer system prompt in `T/` instead of wrapping the stale route-B text: it lists the static-screen rules the bound
`policy` actually enforces for typed programs (module level, constant grammar, attribute rules including dunder
names, imports, size limits) with one legal rewrite per commonly broken rule (word sets, regex constants,
`type(e).__name__`). A test feeds one legal and one illegal example per stated rule to the bound screen so the
prompt cannot drift from the code. Failure evidence given to the fix call: rule name, line, offending source line,
the rule in words, the standard rewrite. One fix call per proposal as in typed-v1. Proposals are screened in the
order given; a proposal that still fails after its fix is dropped and the next proposal (up to three) takes its
place, until two candidates pass or the proposals run out. Promotion happens inside the proposal unit, so unit names
stay `program-1*`, `program-2*` (no `program-3*` units). Promotion is for screen failures only (not for sandbox-smoke
or gate failures). Fix the latent `build_procedure` defect (entry without `max_note_chars` gets cap 1).

**D4. Reply reading: one typed-owned tolerant reader.** New module in `T/`; the frozen `X/engineer_reader.py` may be
called but never edited. Interface for D3: text in, list of proposal records or a typed read problem (reason + what
was unreadable) out; same for a fix reply. General tolerance, not field patches (owner 10/26): accept `change` for
`changes`, a single object for a list, and take the program source from the fenced code block when the inline
`source` is absent or is not real code (does not parse or lacks the required entry point); record which source was
used. One format retry per unit when nothing readable came back, stating exactly what was unreadable. Tolerance never
extends to safety: whatever the reader returns still goes through the unchanged static screen and sandbox.

**D5. Gate: three fresh runs per item per arm, same decision rule.** For every arm run on the gate slice (noise
calibration / incumbent, typing no-harm arm, card rounds, program gates): R = 3 runs per item, each a fresh call
whose identity contains the repeat index (no cache, dedup or resume may return a stored result of another repeat).
Organisation: the R repeats of an arm live inside ONE unit (label suffix that maps back to the arm through the
existing `arm_of` path), not one unit per repeat. Statistics, pre-registered:
  - item mean `m[A,i] = (1/R) * sum_r x[A,i,r]`; `gain = 100 * mean_i(m[K,i] - m[B,i])` for candidate K against
    incumbent B;
  - noise from the incumbent's own repeats: `s2[i] = sum_r (x[B,i,r] - m[B,i])^2 / (R - 1)`,
    `SE = 100 * sqrt(2 * sum_i s2[i] / (R * n^2))`;
  - `tau = max(3.0, 2 * SE)`; accept iff `gain >= tau` and `better > worse`, where better / worse count items with
    `m[K,i] > m[B,i]` / `m[K,i] < m[B,i]` (exact comparison on score sums, tolerance 1e-9 for non-binary scores);
  - a decision needs all `n * R` cells of both arms; a missing cell is an infrastructure failure handled as in
    typed-v1 (pause), never dropped;
  - an arm whose requests are identical to an arm already run in the same step is the same arm: its runs are shared,
    never repeated beyond R (state exactly which arms this covers; the incumbent's R runs are both the calibration
    and the baseline).
Units that are not gate comparisons keep a single run per item (card learn unit, program sandbox-smoke unit).
The typing no-harm rule keeps its typed-v1 form on item means. Record shapes carry R, the per-item sums and the SE
inputs so a decision can be recomputed offline. Readout folds the repeat labels back into one arm.

**D6. One version mechanism: this tree IS typed-v2.** New constants in `T/` (`VERSION = 'typed-v2'`,
`CONFIGURATION = 'typed-v2'`, a bumped library version, new prompt pins); no runtime profile and no typed-v1
compatibility switch inside the chain code. typed-v2 learns from an empty library and refuses a typed-v1 library or
root. New names: code snapshot `/data/execskill-code-<date>-typed-v2`, build dir `/data/execskill-dev-typed2`, run
root `/data/execskill-<date>-typed-v2`, smoke root `...-typed-v2-smoke`, ops dir `/data/typed-v2-ops`. Token caps keep
the typed-v1 values (G 150,000,000; D 170,000,000) unless a section shows they cannot hold the tripled gate cells;
any other value is fixed before `prepare` and never changed afterwards.

**D7. Running beside typed-v1.** Until a section proves that sandbox container names, slot roots and cleanup of two
runs with the same chain letter cannot interfere, a typed-v2 real chain is launched only after the typed-v1 chain of
the same letter has ended or been stopped. The section must settle the question by reading the frozen client code.

**D8. Schedule and memory lock (efficiency; no request, identity or decision content may change).**
(a) Schedule: design a prepare-time manifest field with two values, `interleaved` (typed-v1 order, the default) and
`learn_first` (all learning steps, then every read event in order with the library and typing state frozen at its
step). Same units, same requests, same identities; only the order differs. State what must be stored per step so a
later read mounts exactly the step's library and typing, and how resume behaves. If this is invasive, say so.
(b) Memory lock: only choices among lock functions that already exist in the bound machinery, selected in `T/` call
sites. Default unchanged from typed-v1 unless the section shows with evidence (memory arithmetic for a 15 GiB / 7 CPU
machine, earlier route-B use) that sharing the exclusive lock inside one unit is safe.

## 2. Out of scope for typed-v2

Benches, slices, bench order, models and roles, number of card rounds and attempts, the describer, the typing rule's
form, the read arms (C0, C, S1..S5), the sandbox, the static screen, consent rules. No result number of typed-v1's
sealed reads is used anywhere.

## 3. Waiting for the owner (do not design in; mention as hooks only)

- Read policy for the typed-v2 run (every step reads all five panels fresh, as the binding rule says, versus reading
  only panels whose requests changed plus one full final read; inheriting typed-v1's C0 / C rows after a zero-call
  fingerprint check).
- Whether typed-v1 stops early.

## 4. Deliverables of the design phase

`docs/handoff/typed-v2/spec/<area>.md` per area, a cross-check `spec/critic.md`, then `docs/handoff/typed-v2/DESIGN.md`
(self-contained, same section layout as the typed-v1 DESIGN) and `IMPLEMENTATION-ORDER.md` (areas in sequence, files
and tests per step; `T/chain.py`, `T/writers.py`, `T/smoke.py`, `T/prepare.py`, `T/readout.py` and their tests are
shared by several areas, so areas are implemented one after another).
