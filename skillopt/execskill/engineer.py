"""The engineer's step: one proposal of procedure changes, the fixed checks C1-C9, one fix, the candidate (registration
§4.2 engineer role, §5.4, §9.2; FA-F6, FA-F12, FA-F13, FA-F17, FE-F7/EE-F1, ME-F2, ME-F3, EE-F12; implementation plan
§1 engineer.py, §2.1, B4).

The engineer (GLM-5.3 through ``roles.plain``, the pinned ``ENGINEER_SYSTEM``) sees the bench's task card, the parent
package, at most 12 failures and 6 successes of the bench's stored run-slice trajectories (whitelisted, in the seeded
order of ``data.ranked``; the reference answers of the shown failures only), detector counts and the previous step's
outcome, fitted to ``ROLE_INPUT_BYTES``. It replies with one ```json manifest ``{"changes": [...]}`` (at most
``MAX_CHANGES``: new, revision, deletion, narrowing) and one ```python block per new or revised procedure. An
unparseable reply gets one new proposal call. The registrar assigns every new or revised procedure its id
(``p-<bench>-<step>-<n>``; ``fx-...`` in engineering-fixture runs) and its lineage (the parent's version, the
engineer call's request hash).

Each change passes the fixed checks; at its first failure the engineer gets one fix call (that change and the failed
check), a second failure drops it. Registered meaning, executed order (each result reported under its registered id):
- C1 parse: the manifest entry's keys and types, its target in the parent, each parent procedure edited once, and a
  ``bindings`` hook only in a procedure whose declared scope leaves out SpreadsheetBench and ALFWorld (``bindings`` is
  QA-only, registration §2.4, §3; registrar addendum 2026-10-22 15:5x R3);
- C2 syntax and banned names (``policy.check`` without the static bans and the size rule);
- C4 static bans on the source (LiveMath meta option, OfficeQA bulletin literals, ALFWorld numbered receptacles), run
  before C3 because a ``Procedure`` refuses any policy violation;
- C3 size and caps: the ``Procedure`` record (``package.Procedure``) and the one-change candidate (``package.with_``);
- C5 sandbox load: a fresh worker loads it and does not reject it (``SandboxUnavailable`` is P4 and propagates);
- C6 zero crash (``replay.zero_crash``) on every stored run trajectory of the route in the procedure's scope;
- C4 leakage and output bans, after C6 because notes exist only after the replay: the description, every string and
  number literal and every replayed note, against each run slice's reference-answer corpus (``leakage.findings``),
  counting only content absent from the item's public view (FA-F12: a note may quote its own item; the description
  and literals may quote the items their replay tests name); any hit goes to ONE adjudication call
  (``leakage.adjudicate``), a veto drops the change. A LiveMath note the meta-option screen dropped, or naming an
  option by its letter, fails without adjudication. The frozen corpus indexes no SpreadsheetBench answer, so the
  answer-cell values the payload discloses (registrar addendum 2026-10-22 15:5x R1) have their own check over the same
  texts and the header (``disclosed``, ``sheet_findings``; Codex review 2026-10-22 #2); its hits join that one
  adjudication, which is then shown the disclosed values (``answer_values``) and the procedure's code;
- C7 replay tests (``replay.run_tests``), C8 format guard (``replay.format_guard``), C9 output screen
  (``replay.output_faults``).
A deletion or a narrowing has no code: C1 and C3 only. ``candidate`` builds S' from the parent and the surviving
changes (dropping, from the last, any whose combination breaks the package caps); no survivor, no candidate. The step
is one sealed ``fivebench-execskill-v1-engineer`` record. At most ``ENGINEER_CALLS`` engineer calls per step: one
count shared by the step's engineer units within an attempt, so ``engineer-2`` gets the calls its first unit left
(``Context.spent``; a redo attempt restarts its own count; registrar addendum 2026-10-22, R7 decision 16:1x, R7a).

v2 (configuration ``main-v2``, learning mode "train"; owner decision 2026-10-23 13:3x; ``run_train``): the engineer
works over training rounds. In round r it sees the incumbent T_{r-1} (``Context.parent``; T_0 is the step's parent S,
``Context.base``), the incumbent's latest trajectories of the run-slice items (``Context.current``), the earlier
rounds (``history``), the last round's training evaluation (``training``: per changed procedure on how many items it
fired and which training items it fixed or broke, with examples) and the last candidate's advisory replay-test
report (``lint``), under the pinned ``ENGINEER_SYSTEM_V2``. The checks are v1's except that the description and the
header are cut to their caps before C3 (recorded as ``truncated``), C7 keeps only the registrar's own checks fatal
(``replay.registrar_checks``) while the engineer's replay tests (0-8) are advice, a change beyond the step's edit
budget fails C3 without a fix call, every other failing change gets up to ``TRAIN_FIXES`` fix calls with the measured
detail of its failure, and a unit makes at most ``TRAIN_ENGINEER_CALLS`` calls. The surviving changes are applied to
T_{r-1} and the result is re-expressed against S (``rebase``), so the step's final candidate is one candidate of S
with at most ``MAX_CHANGES`` edits, whatever the number of rounds. Codex review 2026-10-23: what a round carries to
the next is schema-checked (``Context``; #4), the lint names tests by position only (``_lint``; #3), C4 counts the
table-shape references every round of the step disclosed (``Context.disclosed``; #3), and an oversized proposal
message leaves out trajectories, then training examples, then analyses (``_fit_train``; #5).

v2.1 (configuration ``main-v2-1``; owner decision 2026-10-24 02:22, "好的，那就按照你的说法来，先修，修好之后继续跑"): in
main-v2, LiveMath's round 2 adopted a procedure keyed on the meta option after its fix calls echoed the screen's
matched phrase and the adjudicator's reason, and the next fix reply paraphrased around them. Two train-mode rules,
taken from the run configuration (``protocol.FIX_ECHO``, ``protocol.META_COUNTERFACTUAL``): a fix call shows a failed
C4 or C9 without the flagged texts, the matched terms, the static bans' details and the adjudicator's reason
(``Context.echo`` False, ``_redacted``; the sealed record keeps the full detail), and C4 fails a procedure that behaves
differently on its in-scope LiveMath trajectories when the meta option's text is replaced by a neutral filler
(``Context.counterfactual``, ``replay.meta_counterfactual``; the fix call names the differing aspects and
``COUNTERFACTUAL_RULE``). With echo off, the trajectories the proposal and analyst calls show carry no screen match
either: a lexicon or meta-option fault's message and the detail of a note field dropped for either reason become null
(``_unechoed``; Codex review 2026-10-24 #3). The prompts are main-v2's. In every configuration a model-written value
is type-checked before it is used as a key (``_fix``, ``leak_check``; main-v2's chain G stopped on a mutation written
as an object).

v2.3 (2026-10-25 request E1-E4): configuration-selected proposal output caps, excerpts of shown public text,
pure module constants and structure normalisation. Full trajectories still drive C5-C9. The new pinned prompts and
engineer/procedure records distinguish this behaviour from every frozen earlier configuration. Codex review #4:
single-mode smoke keeps mandatory replay tests under its own prompt; train mode keeps optional advisory tests.
Amendment 2 adds C6b after C6: every new or revised procedure must fire without a predicate fault on at least one
of this round's exact training routing views (run items and admitted generated items). Its counts and public field
names feed the existing repair loop; empty single-mode smoke records a skip. C1-C9 and the call budgets keep their
registered meanings.
"""
from __future__ import annotations

import ast
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from skillopt.coevo5 import leakage
from skillopt.coevo5.data import ranked
from skillopt.coevo5.protocol import LEAK_MIN_SIGNIFICANT_DIGITS, LEAK_MIN_SINGLE_WORD
from skillopt.coevo5.roles import Invalid, fit, message_bytes, parse as parse_reply
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import engineer_payload, notes, policy, profiles as protocol, replay, router
from .donors import public_text
from .errors import PackageInvalid
from .package import EDIT_KINDS, FIXTURE, Package, Procedure, edits, validate, with_
from .profiles import (ANALYST_TAG, BENCHES, ENGINEER_CALLS, ENGINEER_SHOWN, HOOKS, MAX_CHANGES, MAX_DESCRIPTION_CHARS,
                       MAX_TESTS, SANDBOX_TIMEOUTS,
                       MAX_HEADER_CHARS, MAX_PACKAGE_BYTES, MAX_PROCEDURE_BYTES, QA, ROLE_INPUT_BYTES, SEED, SHOWN_TAG,
                       TRAIN_ANALYST_BATCH, TRAIN_ANALYST_CALLS, TRAIN_ENGINEER_CALLS, TRAIN_FINDING_CHARS,
                       TRAIN_EXAMPLES, TRAIN_FINDINGS, TRAIN_FIXES, TRAIN_PROPOSAL_CHARS, TRAIN_ROUNDS,
                       TRAIN_TEXT_CHARS, record, verified)
from .trajectories import HIDDEN, whitelisted

ROLE = "engineer"
STATIC_BANS = ("meta_option", "bulletin_literal", "receptacle_literal")
BLOCK = re.compile(r"```([A-Za-z]*)[ \t]*\n(.*?)\n[ \t]*```", re.S)
RUN_UNIT = re.compile(r"(?P<chain>[^/]+)/s(?P<k>\d+)-(?P<bench>[a-z]+)/run")  # a run unit's label
TRAIN_UNIT = re.compile(r"(?P<chain>[^/]+)/s(?P<k>\d+)-(?P<bench>[a-z]+)/train-r(?P<r>\d+)")  # a v2 training unit
TRAIN = "train"  # v2's learning mode (``protocol.LEARNING``)
LINT_REASONS = ("test_count", "invalid_test", "test_failed", "vacuous_test", "no_fix_claim")  # v2: advice only
MAX_LINT = 10
MAX_DETAIL_CHARS = 300  # v2: a flagged text or a reason in a fix call's detail
# v2.1: what a fix call says of a counterfactual difference (``_redacted``), in place of any flagged text
COUNTERFACTUAL_RULE = ("The procedure must behave the same with or without the option about a stronger result: its "
                       "predicate, notes, bindings and faults on an item may not depend on that option's presence or "
                       "wording.")
# v2.1, Codex review 2026-10-24 #3: the note screens' reasons (``notes.screen``) whose matched texts a shown trajectory
# leaves out when echo is off, and the shell faults they raise (``note_`` + reason)
SCREEN_REASONS = ("lexicon", "meta_option")
SCREEN_FAULTS = tuple("note_" + reason for reason in SCREEN_REASONS)
# v2, Codex review 2026-10-23 #3/#4: the exact fields of what one round carries to the next
LINT_DETAILS = ("keys", "id", "trajectory_not_in_scope", "hook_or_kind", "property_shape", "step", "value",
                "nonvacuity", "mutation", "predicate_needs_mutation")  # replay.validate_test's reasons
LINT_FIELDS = frozenset({"id", "tests", "problems"})
LINT_TEST_FIELDS = frozenset({"test", "holds", "withheld", "mutated", "nonvacuous"})
HISTORY_FIELDS = frozenset({"round", "candidate", "adopted", "items", "generated", "fixed", "broken", "net", "p_sign",
                            "reason", "proposals"})
PROPOSAL_FIELDS = frozenset({"kind", "id", "target", "description", "fate"})
TRAINING_FIELDS = frozenset({"adopted", "reason", "items", "fixed", "broken", "net", "need", "p_sign", "guards",
                             "generated", "procedures"})
GUARD_FIELDS = frozenset({"own_faults", "predicate_faults", "format"})
FEEDBACK_FIELDS = frozenset({"id", "change", "enabled_items", "fixed", "broken", "examples"})
EXAMPLE_FIELDS = frozenset({"task_id", "cell", "outcome", "question", "notes", "current_reply", "candidate_reply",
                            "current_pass", "candidate_pass"})  # and "reference" where ``step._feedback`` shows one
EXAMPLE_TEXTS = (("question", "question"), ("notes", "note"), ("current_reply", "answer"),
                 ("candidate_reply", "answer"))
FRACTION = re.compile(r"-?\d+/\d+")
MAX_REASON_CHARS = 64  # a verdict's reason, a proposal's fate
MAX_ID_CHARS = 64
MAX_FIX_PARSE_CHARS = 600  # v2.7 only: deterministic fix-reply failure details, including their prefix
PREVIOUS_FIELDS = frozenset({"decision", "faults", "format"})  # §4.2: accepted / not accepted + fault, format counts
OPTION_LETTER = re.compile(r"\b(?i:option|choice)\s*\(?[A-E]\)?(?![A-Za-z])|^\s*(?:-\s*)?\(?[A-E]\)?[.)]?\s*$", re.M)
CODED = ("new", "revision")
ALFWORLD_STEP_VIEW_KEYS = ("initial_observation", "observation", "admissible_commands", "recent_history")
PROCEDURE_KEYS = {"description": str, "hooks": list, "header": str, "max_note_chars": int,
                  "requests_second_call": bool, "state_bytes": int, "replay_tests": list, "excluded_benches": list}
OPTIONAL = {"header": "", "max_note_chars": 0, "requests_second_call": False, "state_bytes": 0, "excluded_benches": []}
TARGET_KEYS = {"revision": "revises", "deletion": "id", "narrowing": "id"}
# registration §2.4, §3: ``bindings`` is QA-only, so a new or revised procedure declaring it excludes the benches
# without the <calc> round trip; C1 fails otherwise, with this detail for the fix call (registrar addendum
# 2026-10-22 15:5x R3; the shell runs no bindings hook there either, ``solver.Shell.before``)
NO_CALC_BENCHES = tuple(bench for bench in BENCHES if bench not in QA)
BINDINGS_SCOPE = "bindings_is_qa_only: list %s in excluded_benches" % " and ".join(NO_CALC_BENCHES)
MAX_ADJUDICATED_CHARS = 4000
# Codex review 2026-10-22 #2 (registration §4.2 "参考答案不能进代码", §5.4 C4; registrar addendum 15:5x R1 keeps the
# frozen corpus, which indexes no SpreadsheetBench answer): the C4 check of the answer-cell values the proposal payload
# discloses. A disclosed value counts unless it is trivial -- empty, a boolean (``step._scalar``'s TRUE / FALSE; the
# frozen ``leakage.answer_values`` leaves blanks and booleans out too), a number with fewer than
# LEAK_MIN_SIGNIFICANT_DIGITS significant digits as Python writes it (0-99, 0.5, 1.25: indices, counts and thresholds
# of any program; the registered floor of the OfficeQA value check), or a text whose normalized words carry fewer than
# LEAK_MIN_SINGLE_WORD letters and digits together ("Yes", "N/A", "Q1", "1-2"; the registered floor of a single-word
# answer, applied to the whole value) -- or public: it appears in its own item's instruction, request view or public
# workbook (every cell value and formula, what the sandbox's ``public_workbook()`` reads). A text is matched by its
# normalized word run (frozen ``leakage.normalize``; an ISO date-time's "T" read as a space, a midnight time left
# out), a number by its exact absolute value however written (frozen ``leakage.NUMBER``/``FRACTION``; four-digit years
# are checked here: on SpreadsheetBench a year is a plausible answer, and one the item shows is public). A flagged
# text may also quote its own public context (FA-F12): a note its trajectory's view, workbook and stored pre-check
# report (``sheet_feedback``'s input), the description, header and literals those of the trajectories their replay
# tests name.
SHEET_REASON = "sheet_reference"
MAX_ADJUDICATED_VALUES = 60  # the frozen ``leakage.answer_values`` bound (v3 §6)
ISO_TIME = re.compile(r"(\d{4}-\d{2}-\d{2})T(?=\d{2}:\d{2})")
MIDNIGHT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]00:00(?::00(?:\.0+)?)?$")
BOOLEANS = frozenset({"true", "false"})
WORKBOOK_ERRORS = (OSError, ValueError, KeyError, TypeError, ET.ParseError, zipfile.BadZipFile)
ENGINEER_SYSTEM = """\
You maintain a package of helper programs ("procedures") for a solver model. The shell runs each procedure's hooks in \
a sandbox without network, files or clock, and shows the solver the typed notes they return. You see the bench's task \
card, the current package and stored trajectories of the solver (failures and successes; each failure with its \
reference answer). Propose at most 3 changes that should make the solver right on failures like these without hurting \
the successes.

Hooks (module-level functions; declare every hook you define; "applies" is required):
- applies(view) -> bool: whether the procedure runs on this item. view: QA {"question", "context" or "choices"}; \
SpreadsheetBench {"instruction", "workbook_preview", "input_path", "required_output_path", \
"required_answer_position"}; ALFWorld {"initial_observation", "admissible_commands_at_reset", "task_text"}.
- before_call(view, state) -> fields or None (QA and SpreadsheetBench; state is None).
- bindings(view) -> {"bindings": [{"name", "quote", "value"}]} or None: named numbers quoted verbatim from the task; \
the solver may then compute with <calc> expressions over these names.
- sheet_feedback(view, run_report, state) -> {"fields": fields, "request_repair": bool}: after the solver's program \
ran once on the public input workbook; run_report {"status": "ok", "exception", "missing_output" or "unknown", \
"exc_type", "message", "answer_cells"}. request_repair true asks for one repair call (declare \
"requests_second_call": true).
- alf_before_step(view, state) -> {"fields": fields, "discourage": [admissible commands]}: every ALFWorld step; view \
{"initial_observation", "observation", "admissible_commands", "recent_history"}.
- alf_after_step(event, state) -> the new state (JSON, at most "state_bytes" bytes); event {"step", "action", \
"observation", "admissible_commands"}. A state procedure keeps state["facts"] = {"reached": [receptacles reached or \
opened], "carrying": [objects held], "nothing_happens": the number of actions answered "Nothing happens."}; these \
facts must agree with a fixed reference tracker on at least 97% of the steps.
fields: {"facts": [text <= 200], "table": [[text <= 40]] (<= 20 rows, <= 12 columns), "candidates": [text <= 120], \
"warnings": [text <= 200], "bindings": as above}. Notes give information, never instructions about the reply's form: \
a field with words such as answer, output, return, respond, json, format, round, units, decimal places, only the, \
just the, bare or single letter is dropped and counted as a fault.

Code policy: at most 6000 bytes; module level holds only imports, literal constants (<= 2000 characters) and plain \
functions; importable: bisect, calendar, collections, copy, datetime, decimal, difflib, fractions, functools, heapq, \
itertools, json, math, numpy, openpyxl.utils, operator, pandas, re, statistics, string, sympy, textwrap, \
unicodedata. No classes, globals, I/O, eval, randomness or clock; no dunder names or private attributes. Never write a \
literal naming a specific OfficeQA bulletin issue or page, a numbered ALFWorld receptacle (such as "drawer 3") or the \
LiveMath option about a stronger result, never choose options by their position or letter, and never copy a training \
task's reference answer into code, notes or the description.

Replay tests (1 to 8 per new or revised procedure) show on the stored trajectories that the procedure does what it \
claims: {"id", "trajectory": the "cell" of a trajectory shown to you, "hook", "property", "claims_fix": true or \
false, "nonvacuity": {"withheld_expect": false, "mutation": null or a mutation}}. Properties: {"kind": \
"applies_true"} or "applies_false"; {"kind": "note_contains", "value": text}; {"kind": "note_matches", "value": \
[text fragments in order]}; {"kind": "discourage_contains" or "discourage_excludes", "value": command}; {"kind": \
"binding_equals", "name", "value"}; {"kind": "repair_requested", "value": true or false}; {"kind": "state_equals", \
"key", "value"}; properties of alf_before_step and alf_after_step also give "step" (the step index). Each property \
must hold with the procedure and be false without it (withheld) or under its mutation: strip_digits (any bench), \
drop_exception_message or program_ok (SpreadsheetBench), nothing_happens (ALFWorld); applies properties need a \
mutation. At least one test with "claims_fix": true must hold on a failed trajectory.

Reply with one ```json block {"changes": [...]} and then one ```python block per new or revised procedure, in the \
order of the changes. A change is {"kind": "new", "description" (<= 600 characters, for people), "hooks", "header" \
(<= 200 characters, shown above the notes), "max_note_chars" (1-4000 when a hook writes notes, else 0), \
"requests_second_call", "state_bytes", "replay_tests", optionally "excluded_benches"}; {"kind": "revision", \
"revises": the procedure's id, and the fields of "new"}; {"kind": "deletion", "id"}; or {"kind": "narrowing", "id", \
"benches": the benches it stops running on}. {"changes": []} proposes nothing. When the user message has "request": \
"fix", it names one change and the check it failed: reply in the same format with exactly that change, corrected."""
ENGINEER_PROMPT_SHA256 = digest(ENGINEER_SYSTEM)
# v2 (owner decision 2026-10-23 13:3x): v1's text up to its replay-test paragraph, then the training rounds, the edit
# budget, advisory replay tests and the reply format with optional tests and cut description and header
TRAIN_TAIL = """\
Replay tests (0 to 8 per new or revised procedure; optional) show on the stored trajectories that the procedure does \
what it claims: {"id", "trajectory": the "cell" of a trajectory shown to you, "hook", "property", "claims_fix": true \
or false, "nonvacuity": {"withheld_expect": false, "mutation": null or a mutation}}. Properties: {"kind": \
"applies_true"} or "applies_false"; {"kind": "note_contains", "value": text}; {"kind": "note_matches", "value": \
[text fragments in order]}; {"kind": "discourage_contains" or "discourage_excludes", "value": command}; {"kind": \
"binding_equals", "name", "value"}; {"kind": "repair_requested", "value": true or false}; {"kind": "state_equals", \
"key", "value"}; properties of alf_before_step and alf_after_step also give "step" (the step index). Mutations: \
strip_digits (any bench), drop_exception_message or program_ok (SpreadsheetBench), nothing_happens (ALFWorld). The \
registrar runs them and reports their problems to you as "lint" in the next round; they never block a change. The \
registrar's own checks do block: a passed SpreadsheetBench item must not request a repair, the last action of a won \
ALFWorld game must not be discouraged, an ALFWorld state procedure's facts must agree with the reference tracker, \
and bindings must quote the task verbatim.

Training rounds. This step improves the package over up to 6 rounds on training items: this bench's run batch (the \
trajectories you see) and, when the examiner made them, generated items of this bench. In each round you propose at \
most 3 changes to the current package. The registrar checks them, builds the candidate and runs the solver, several \
times with each package, on every training item where the candidate enables a different set of procedures than the \
current package. The candidate replaces the current package only when it fixes more items than it breaks (a net gain \
of at least one item and of 2% of the items evaluated, one-sided sign test p <= 1/4), with faults of the changed \
procedures in at most 2% of its cells and without more format violations. "round" is this round's number; \
"history" lists the earlier rounds; "training" is the last round's evaluation: per changed procedure on how many \
items it fired, which items it fixed and which it broke, with examples (the question, the notes the solver saw, the \
solver's final replies with the current package and with the candidate, the reference answer); "trajectories" are \
the current package's latest trajectories. Use this evidence: keep what fixes items, repair, narrow or delete what \
breaks them, and try a different idea after a rejected round. A procedure that fires on no item cannot help.

Edit budget. Whatever the number of rounds, the step's final package may differ from the step's starting package by \
at most 3 edits; a new procedure, a revision, a deletion or a narrowing of a starting procedure each count one. \
"edits" lists the edits used so far and the procedures this step created; revising, narrowing or deleting a \
procedure this step created uses no further edit. A change beyond the budget is dropped.

Reply with one ```json block {"changes": [...]} and then one ```python block per new or revised procedure, in the \
order of the changes; never put code into the JSON. A change is {"kind": "new", "description" (at most 600 \
characters, for people; a longer one is cut), "hooks", "header" (at most 200 characters, shown above the notes; cut \
likewise), "max_note_chars" (1-4000 when a hook writes notes, else 0), "requests_second_call", "state_bytes", \
optionally "replay_tests" and "excluded_benches"}; {"kind": "revision", "revises": the procedure's id, and the fields \
of "new"}; {"kind": "deletion", "id"}; or {"kind": "narrowing", "id", "benches": the benches it stops running on}. \
{"changes": []} proposes nothing. When the user message has "request": "fix", it names one change, the check it \
failed and the measured detail: reply in the same format with exactly that change, corrected (the same kind and \
target, its code in a ```python block)."""
ENGINEER_SYSTEM_V2 = ENGINEER_SYSTEM[:ENGINEER_SYSTEM.index("Replay tests (1 to 8")] + TRAIN_TAIL
ENGINEER_PROMPT_V2_SHA256 = digest(ENGINEER_SYSTEM_V2)
ENGINEER_FACTS_V23 = """\

Registered structure and note facts. Canonical hook order: applies, before_call, bindings, sheet_feedback, \
alf_before_step, alf_after_step. bindings is QA-only: exclude spreadsheetbench and alfworld. Before C1 the registrar \
orders hooks and adds those exclusions, recording each normalisation.
All note fields are optional: facts: list[str] (each <=200 characters); table: list[list[str]] (<=20 rows, <=12 \
columns, each cell <=40 characters); candidates: list[str] (each <=120 characters); warnings: list[str] (each \
<=200 characters); bindings: list[dict] with exactly name, quote, value, all strings <=200 characters. A binding \
name is a calculator name, value is numeric text and quote must contain that value verbatim in the item's public \
text. Each note hook uses these same field names and types. Valid minimal examples: before_call(view, state) -> {}; \
bindings(view) -> {"bindings": []}; sheet_feedback(view, run_report, state) -> {"fields": {}, "request_repair": \
False}; alf_before_step(view, state) -> {"fields": {}, "discourage": []}. request_repair is bool; discourage is \
list[str]. No other note fields are allowed.
Module constants may also use these pure expressions over literals: re.compile(str[, re flags joined by |]) after \
import re; set/frozenset(literal iterable); tuple/list/dict/sorted(literal); str.split([str]); str.join(literal \
list/tuple of str); + of same-type literals; a previously defined constant name. The written expression remains \
at most 2000 characters. Move any other call into a function or write its literal value.
"""
ENGINEER_SYSTEM_V23 = ENGINEER_SYSTEM_V2 + ENGINEER_FACTS_V23
ENGINEER_PROMPT_V23_SHA256 = digest(ENGINEER_SYSTEM_V23)
ENGINEER_SYSTEM_SINGLE_V23 = ENGINEER_SYSTEM + ENGINEER_FACTS_V23
ENGINEER_PROMPT_SINGLE_V23_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_V23)
ENGINEER_FACTS_ZPC = """\
ZebraLogic grid-mode addition (zebra-pc-v1): applies(view) and before_call(view, state) both receive exactly
{"question": the puzzle text, "columns": the registered column names}. Use applies and before_call; bindings and
the calculator round trip do not apply. The solver must return the task card's JSON solution grid. A parser and
exact solver may compute a table from the public clues and pass that table in before_call notes. Table cells
quoted verbatim from the public puzzle retain the ordinary screening rule; there is no lexicon exemption.
There is no generator, G_self, or research material on this benchmark. Training uses the run slice only.
"""
ENGINEER_SYSTEM_ZPC = ENGINEER_SYSTEM_V23 + ENGINEER_FACTS_ZPC
ENGINEER_SYSTEM_SINGLE_ZPC = ENGINEER_SYSTEM_SINGLE_V23 + ENGINEER_FACTS_ZPC
ENGINEER_PROMPT_ZPC_SHA256 = digest(ENGINEER_SYSTEM_ZPC)
ENGINEER_PROMPT_SINGLE_ZPC_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ZPC)
ENGINEER_FACTS_V24 = """
Executable feedback (v2.4). Every replay test with claims_fix: true must hold: a failed claim fails C5b and receives
the hook's actual bounded return or exception in the fix call. Tests with claims_fix: false remain advisory lint.
C6c requires a note-writing procedure to produce some non-empty facts, table, candidates, warnings or bindings on
at least one fired training item. Empty output on every fired item fails and enters the fix loop.
What your hooks receive. The user message's hook_views section shows one deterministic run item's exact public
view arguments as JSON, with strings cut to 1500 characters and lists to 20 entries. These are the hook arguments;
the solver prompt wraps the public view in other text. For ALFWorld routing_view is for applies, and hook_view is
the first stored per-step view for alf_before_step. Use these actual keys and text when writing parsers.
Training patience counts only rounds where a candidate survives the checks. The limit remains six rounds.
training.unfixed_examples shows up to four run items the candidate did not fix, with its actual notes, final answer
excerpt and the already-visible run reference. A row marked identical_current reuses an identical incumbent request.
"""
_V24_ADVISORY = ('registrar runs them and reports their problems to you as "lint" in the next round; they never block a change.')
ENGINEER_SYSTEM_V24 = (ENGINEER_SYSTEM_V23.replace("6000", "10000").replace(
    _V24_ADVISORY, 'registrar reports these tests as "lint"; claims_fix: true tests also gate C5b.') + ENGINEER_FACTS_V24)
ENGINEER_SYSTEM_SINGLE_V24 = ((ENGINEER_SYSTEM[:ENGINEER_SYSTEM.index("Replay tests (1 to 8")]
    + TRAIN_TAIL[:TRAIN_TAIL.index("Training rounds.")].replace(
        _V24_ADVISORY, 'registrar reports these tests as "lint"; claims_fix: true tests also gate C5b.')
    + ENGINEER_SYSTEM[ENGINEER_SYSTEM.index("Reply with one ```json block"):] + ENGINEER_FACTS_V23)
    .replace("6000", "10000") + ENGINEER_FACTS_V24)
ENGINEER_FACTS_ZPC_V24 = ENGINEER_FACTS_ZPC.replace("zebra-pc-v1", "zebra-pc-v2") + """
view["question"] is the raw puzzle text beginning "There are N houses, numbered 1 to N ...". The solver's prompt
adds an instruction template with a worked example and headings such as "# Puzzle to Solve"; hooks never see those
headings or that example. Parse the raw question and the public columns directly.
"""
ENGINEER_SYSTEM_ZPC_V24 = ENGINEER_SYSTEM_V24 + ENGINEER_FACTS_ZPC_V24
ENGINEER_SYSTEM_SINGLE_ZPC_V24 = ENGINEER_SYSTEM_SINGLE_V24 + ENGINEER_FACTS_ZPC_V24
ENGINEER_PROMPT_V24_SHA256 = digest(ENGINEER_SYSTEM_V24)
ENGINEER_PROMPT_SINGLE_V24_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_V24)
ENGINEER_PROMPT_ZPC_V24_SHA256 = digest(ENGINEER_SYSTEM_ZPC_V24)
ENGINEER_PROMPT_SINGLE_ZPC_V24_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ZPC_V24)
RENDER_SAMPLE_FIELDS_V25 = {"facts": ["Two attributes are registered.", "Each value is used once."],
                          "table": [["House", "Color"], ["1", "blue"], ["2", "red"]],
                          "warnings": ["Some assignments remain unresolved."]}
RENDER_SAMPLE_HEADER_V25 = "Synthetic rendering example"
RENDER_SAMPLE_V25 = notes.render(RENDER_SAMPLE_FIELDS_V25, bench="zebralogic", header=RENDER_SAMPLE_HEADER_V25)
ENGINEER_FACTS_V25 = """
Rendered-note feedback (v2.5). note_contains and note_matches properties are matched against the rendered note text
below, not against the returned JSON. Failed C5b claims and advisory lint provide rendered_note, cut to 1500
characters, only for verified run trajectories shown to you. This synthetic example uses the ZebraLogic renderer;
other benches render the same way:
""" + RENDER_SAMPLE_V25 + """
training.procedures[].notes_coverage counts enabled run items, items with delivered notes, items with each delivered
field, and items with procedure faults; identical_current rows use the incumbent's delivered notes.
"""
ENGINEER_SYSTEM_V25 = ENGINEER_SYSTEM_V24.replace("10000", "16000") + ENGINEER_FACTS_V25
ENGINEER_SYSTEM_SINGLE_V25 = ENGINEER_SYSTEM_SINGLE_V24.replace("10000", "16000") + ENGINEER_FACTS_V25
ENGINEER_SYSTEM_ZPC_V25 = ENGINEER_SYSTEM_V25 + ENGINEER_FACTS_ZPC_V24.replace("zebra-pc-v2", "zebra-pc-v3")
ENGINEER_SYSTEM_SINGLE_ZPC_V25 = (ENGINEER_SYSTEM_SINGLE_V25
                                + ENGINEER_FACTS_ZPC_V24.replace("zebra-pc-v2", "zebra-pc-v3"))
ENGINEER_PROMPT_V25_SHA256 = digest(ENGINEER_SYSTEM_V25)
ENGINEER_PROMPT_SINGLE_V25_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_V25)
ENGINEER_PROMPT_ZPC_V25_SHA256 = digest(ENGINEER_SYSTEM_ZPC_V25)
ENGINEER_PROMPT_SINGLE_ZPC_V25_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ZPC_V25)
ENGINEER_FACTS_V26 = """
Replay trajectory references (v2.6): copy a replay test's trajectory from a shown trajectory's cell field.
A task_id (or its unique suffix) or a cell id with a small copying slip is resolved only when unambiguous within
the replay scope; trajectory_resolution reports changed or unresolved references. A resolved test must still pass
against the procedure's real replay output. Invalid references include valid_trajectories from shown in-scope cells.
C6 determinism: every in-scope trajectory is replayed in one fresh worker with PYTHONHASHSEED=0 in order and in
another with PYTHONHASHSEED=1 in reverse order. Every hook return must be identical; nothing may crash or time out
(5 s). Mismatches commonly come from iterating over a set/frozenset or anything built from one, wall-clock search
budgets, state carried across items, or id()/hash() ordering. Sort before iterating and use deterministic counters
for limits. mismatch_explanation and shown-cell return examples explain a mismatched C6 result.
"""
ENGINEER_SYSTEM_ZPC_V26 = ENGINEER_SYSTEM_ZPC_V25.replace("zebra-pc-v3", "zebra-pc-v4") + ENGINEER_FACTS_V26
ENGINEER_SYSTEM_SINGLE_ZPC_V26 = (ENGINEER_SYSTEM_SINGLE_ZPC_V25.replace("zebra-pc-v3", "zebra-pc-v4")
                                 + ENGINEER_FACTS_V26)
ENGINEER_PROMPT_ZPC_V26_SHA256 = digest(ENGINEER_SYSTEM_ZPC_V26)
ENGINEER_PROMPT_SINGLE_ZPC_V26_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ZPC_V26)
REPLAY_TEST_LIMITS_V27 = replay.test_format_limits()
FIX_TESTS_V27 = ("The corrected change may also correct its replay tests, remove a test, or set claims_fix to false "
                 "for a claim the procedure cannot satisfy. Every remaining claimed test must hold on the "
                 "procedure's real replay output; an attached actual output is not a verdict on a malformed test.")
ENGINEER_FACTS_V27 = "\n" + REPLAY_TEST_LIMITS_V27 + "\n\nFix requests (v2.7). " + FIX_TESTS_V27 + "\n"
# Keep the frozen v2.6 paragraph distinct while retaining all its reference and determinism instructions.
ENGINEER_SYSTEM_ZPC_V27 = (ENGINEER_SYSTEM_ZPC_V26.replace("zebra-pc-v4", "zebra-pc-v5")
    .replace("Replay trajectory references (v2.6)", "Replay trajectory references (v2.7; inherited v2.6)")
    + ENGINEER_FACTS_V27)
ENGINEER_SYSTEM_SINGLE_ZPC_V27 = (ENGINEER_SYSTEM_SINGLE_ZPC_V26.replace("zebra-pc-v4", "zebra-pc-v5")
    .replace("Replay trajectory references (v2.6)", "Replay trajectory references (v2.7; inherited v2.6)")
    + ENGINEER_FACTS_V27)
ENGINEER_PROMPT_ZPC_V27_SHA256 = digest(ENGINEER_SYSTEM_ZPC_V27)
ENGINEER_PROMPT_SINGLE_ZPC_V27_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ZPC_V27)
_ALF_COVERAGE_PARAGRAPH = ("training.procedures[].notes_coverage counts enabled run items, items with delivered notes, items with each delivered\n"
                           "field, and items with procedure faults; identical_current rows use the incumbent's delivered notes.\n")


def _alf_system(base):
    """ALF-only evidence and output instructions; every inherited prompt remains frozen."""
    replacements = (
        ("stored trajectories of the solver (failures and successes; each failure with its reference answer)",
         "stored game trajectories of the solver (failures and successes): observations, admissible commands, "
         "actions, the notes the solver saw, and the outcome (won/lost, or unknown) and recorded steps"),
        ("never copy a training task's reference answer into code, notes or the description",
         "never encode an expert plan or hidden game state in code, notes or the description"),
        ("with examples (the question, the notes the solver saw, the solver's final replies with the current package "
         "and with the candidate, the reference answer)",
         "with examples (the task text, the notes the solver saw, outcome summaries with the current package and "
         "with the candidate, and their pass shares). Each outcome summary says won/not won and the number of steps"),
        ("C6c requires a note-writing procedure to produce some non-empty facts, table, candidates, warnings or bindings on\n"
         "at least one fired training item. Empty output on every fired item fails and enters the fix loop.",
         "C6c requires a note-writing procedure to produce some screened note text on at least one fired training item.\n"
         "Non-empty facts, table, candidates, warnings or bindings can supply it; for ALFWorld, a non-empty discourage\n"
         "list of admissible commands also counts as output. Empty output on every fired item fails and enters the fix loop."),
        ("training.unfixed_examples shows up to four run items the candidate did not fix, with its actual notes, final answer\n"
         "excerpt and the already-visible run reference.",
         "training.unfixed_examples shows up to four run games the candidate did not fix, with its actual notes and\n"
         "outcome summary (won/not won and steps). Its reference field says reference unavailable; no reference answer is supplied."),
        (_ALF_COVERAGE_PARAGRAPH, ""),
    )
    for old, new in replacements:
        base = base.replace(old, new)
    return base


ENGINEER_FACTS_ALF_V1 = """
ALFWorld single-benchmark configuration alfworld-v1. applies(view) receives exactly initial_observation,
admissible_commands_at_reset, and task_text from the reset. It does not receive observation, recent_history, or
admissible_commands. alf_before_step(view, state) receives initial_observation, observation, admissible_commands,
and recent_history. alf_after_step(event, state) receives exactly step, action, observation, and admissible_commands;
observation and admissible_commands describe the environment AFTER that action. Return the next JSON state.
State starts as None for each game and is kept by the host between steps within that game.
Use the hook_views sample for the exact public arguments. The existing action loop allows at most 50 actions.
No expert plan, hidden game state, reference answer, or solution trajectory is supplied to the engineer.
notes_coverage is not recorded for this configuration; training examples still show actual delivered notes.
"""
_ALF_V26_FACTS = ENGINEER_FACTS_V26.replace("Replay trajectory references (v2.6)",
                                         "Replay trajectory references (ALFWorld v2.6)")
ENGINEER_SYSTEM_ALF_V1 = (_alf_system(ENGINEER_SYSTEM_V25)
                          + _ALF_V26_FACTS + ENGINEER_FACTS_ALF_V1)
ENGINEER_SYSTEM_SINGLE_ALF_V1 = (_alf_system(ENGINEER_SYSTEM_SINGLE_V25)
                                 + _ALF_V26_FACTS + ENGINEER_FACTS_ALF_V1)
ENGINEER_PROMPT_ALF_V1_SHA256 = digest(ENGINEER_SYSTEM_ALF_V1)
ENGINEER_PROMPT_SINGLE_ALF_V1_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ALF_V1)
REFERENCE_TRACKER_ALF_V2 = replay.tracker_format_rules()
ENGINEER_SYSTEM_ALF_V2 = (ENGINEER_SYSTEM_ALF_V1.replace("configuration alfworld-v1", "configuration alfworld-v2")
                        + ENGINEER_FACTS_V27 + "\n" + REFERENCE_TRACKER_ALF_V2 + "\n")
ENGINEER_SYSTEM_SINGLE_ALF_V2 = (ENGINEER_SYSTEM_SINGLE_ALF_V1.replace("configuration alfworld-v1", "configuration alfworld-v2")
                               + ENGINEER_FACTS_V27 + "\n" + REFERENCE_TRACKER_ALF_V2 + "\n")
ENGINEER_PROMPT_ALF_V2_SHA256 = digest(ENGINEER_SYSTEM_ALF_V2)
ENGINEER_PROMPT_SINGLE_ALF_V2_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ALF_V2)
from . import engineer_v28
ENGINEER_SYSTEM_ZPC_V28 = engineer_v28.system(protocol.ZEBRA_PC_V6, train=True)
ENGINEER_SYSTEM_SINGLE_ZPC_V28 = engineer_v28.system(protocol.ZEBRA_PC_V6, train=False)
ENGINEER_SYSTEM_ALF_V3 = engineer_v28.system(protocol.ALFWORLD_V3, train=True)
ENGINEER_SYSTEM_SINGLE_ALF_V3 = engineer_v28.system(protocol.ALFWORLD_V3, train=False)
ENGINEER_PROMPT_ZPC_V28_SHA256 = digest(ENGINEER_SYSTEM_ZPC_V28)
ENGINEER_PROMPT_SINGLE_ZPC_V28_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ZPC_V28)
ENGINEER_PROMPT_ALF_V3_SHA256 = digest(ENGINEER_SYSTEM_ALF_V3)
ENGINEER_PROMPT_SINGLE_ALF_V3_SHA256 = digest(ENGINEER_SYSTEM_SINGLE_ALF_V3)
ENGINEER_PROMPT_FIX_V28_SHA256 = digest(engineer_v28.FIX_SYSTEM)
ENGINEER_PROMPT_FORMAT_RETRY_V28_SHA256 = digest(engineer_v28.FORMAT_RETRY_SYSTEM)
# v2's analysts (owner suggestion 2026-10-23 15:1x; SkillOpt's minibatch reflection): engineer-role calls before each
# round's proposal, on groups of the incumbent's failed run-slice items, whose findings the proposal call is shown
ANALYST_SYSTEM = """\
You analyse failures of a solver model for an engineer who maintains a package of helper programs ("procedures"). The \
shell runs each procedure's hooks in a sandbox without network, files or clock and shows the solver the typed notes \
they return: facts, tables, candidates, warnings and named numbers quoted from the task -- information only, never \
instructions about the reply's form. You see the bench's task card, the current procedures and a group of the \
solver's failed trajectories (on QA and table benches each with its reference answer). Find at most 3 failure \
patterns a procedure could address: what went wrong, on which of the shown items, and what a program could compute, \
look up or check in the item's own text (the question, its context or choices, the workbook, the observations) that \
would have helped the solver. Never quote or restate a reference answer and never suggest rules about the reply's \
form. Reply with one ```json block {"findings": [{"pattern": text of at most 300 characters, "items": [task_id of \
shown trajectories], "helper": text of at most 300 characters}]}; {"findings": []} when no pattern fits."""
ANALYST_PROMPT_SHA256 = digest(ANALYST_SYSTEM)


class Unparseable(ValueError):
    """A reply without exactly one manifest, or whose code blocks do not match its changes."""


@dataclass
class Change:
    """One proposed change: its manifest ``entry``, its code (new, revision), the request hash of the call that wrote
    it, and what the checks built (``procedure``; ``target``: the parent procedure it edits)."""
    n: int
    kind: str
    entry: dict
    source: str | None
    call: str
    procedure: Procedure | None = None
    target: str | None = None
    benches: tuple = ()
    truncated: dict = field(default_factory=dict)  # v2: {field: its length} of a description or header cut to its cap
    normalized: list = field(default_factory=list)  # v2.3 E4: the structural changes made before C1
    trajectory_resolution: list | None = None  # v2.6 only; None leaves every older change record unchanged
    repairs: list | None = None  # v2.8 only: generic reader/system repairs, absent from frozen records

    def to_json(self):
        return {"n": self.n, "kind": self.kind, "target": self.target, "benches": list(self.benches),
                "id": self.procedure.id if self.procedure else None,
                "procedure_sha256": self.procedure.sha256 if self.procedure else None, "engineer_call": self.call,
                **({"truncated": dict(self.truncated)} if self.truncated else {}),
                **({"normalized": list(self.normalized)} if self.normalized else {}),
                **({"trajectory_resolution": list(self.trajectory_resolution)}
                   if self.trajectory_resolution is not None else {}),
                **({"repairs": list(self.repairs)} if self.repairs is not None else {})}


@dataclass
class Context:
    """One engineer step. ``k``: the chain step number in procedure ids; ``step``: the candidate's step label;
    ``trajectories``: the stored run trajectories of the route (this bench and the earlier ones; sealed records);
    ``corpora``: {bench: ``leakage.Corpus``} of the run slices' reference answers; ``workers``: the worker factory of
    ``replay.replay_many``; ``roles``: the GLM-5.3 method roles; ``label``: the unit's label; ``references``:
    {task_id: reference answer} of this bench's run-slice items (shown for failures only); ``inputs_dirs``: {cell:
    public input directory} of SpreadsheetBench trajectories; ``detectors``: detector counts; ``previous``: the previous
    step's outcome {decision: accepted | not_accepted, faults, format} (counts); ``spent``: the engineer calls the
    step's earlier engineer unit made in the attempt that completed it (``ENGINEER_CALLS`` is per step, shared by
    ``engineer`` and ``engineer-2``; registrar addendum 2026-10-22, R7 decision 16:1x, R7a).

    What the engineer may be given is checked here (§4.2; isolation review 5): every trajectory is a sealed record of
    a run unit (``<chain>/s<k>-<bench>/run``) of this chain (the label's first part) at this step or before -- never an
    acceptance or test cell; references only on QA and table benches, only for this bench's run-slice failures, in a
    frozen answer shape (text, list of texts, answer positions to scalars, or ZebraLogic's house/column grid) -- never
    an expert plan or a game path;
    detectors and previous as counts only.

    v2 (``mode`` "train", module docstring): ``round`` (1..``TRAIN_ROUNDS``); ``base``: the step's parent S, against
    which the edit budget counts, ``parent`` being the incumbent T_{r-1} (S itself or one candidate of S);
    ``current``: the incumbent's latest cells of the run-slice items and ``evaluated``: the last training unit's cells
    of run-slice items, both this step's sealed trajectories of its run unit or of an earlier ``train-r<n>`` unit of
    this round's step; ``history``: per earlier round counts and flags only; ``training``: the last round's evaluation
    (its examples name this step's run-slice items and known cells, a reference only as ``references`` gives it,
    never on ALFWorld); ``lint``: the last candidate's advisory replay-test reports; ``reserved``: the procedure ids
    earlier rounds of the step used; ``analysed``: the run-slice items earlier rounds' analysts saw (``analyse``);
    ``disclosed``: the run-slice items whose table-shape reference an earlier round of the step disclosed (C4 counts
    them in every later round; Codex review 2026-10-23 #3). References may then name any run-slice item a shown or
    evaluated cell failed, and every disclosed item. The history, the training feedback and the lint have exactly the
    fields ``step._line``, ``step._feedback`` and ``_lint`` write (#4). ``spent`` is 0 in the train mode:
    each ``engineer-r<r>`` unit has its own ``TRAIN_ENGINEER_CALLS`` and ``TRAIN_ANALYST_CALLS``.

    v2.3 Amendment 2: ``routing_items`` are this round's exact run/admitted-generated (item key, public routing view)
    pairs, independent of stored trajectories; ``routing_workers(package, item)`` mounts that item's public inputs.
    C6b alone consumes them. They never enter the proposal payload; feedback gives counts and field names only."""
    bench: str
    k: int
    step: str
    evidence: str
    parent: object
    trajectories: list
    corpora: dict
    workers: object
    roles: object
    label: str
    card: str = ""
    references: dict = field(default_factory=dict)
    inputs_dirs: dict | None = None
    detectors: dict = field(default_factory=dict)
    previous: dict | None = None
    spent: int = 0
    mode: str = "single"
    round: int = 0
    base: object = None
    current: list = field(default_factory=list)
    evaluated: list = field(default_factory=list)
    history: list = field(default_factory=list)
    training: dict | None = None
    lint: list = field(default_factory=list)
    reserved: frozenset = frozenset()
    analysed: frozenset = frozenset()
    disclosed: frozenset = frozenset()
    echo: bool = True  # v2.1 (``protocol.FIX_ECHO``): False -- fix calls show failed C4 and C9 redacted (``_redacted``)
    counterfactual: bool = False  # v2.1 (``protocol.META_COUNTERFACTUAL``): C4 runs ``replay.meta_counterfactual``
    configuration: str = protocol.PILOT
    # v2.3 Amendment 2: exactly the train unit's (item key, routing view) pairs and per-item sandbox factory.
    routing_items: list = field(default_factory=list)
    routing_workers: object = None
    # The ordinary non-workbook routing factory can hold one worker across pure predicates. Custom factories
    # remain per item unless the caller explicitly declares this capability.
    routing_shared_worker: bool = False
    # v2.9: independent audit-only role objects; never the engineer conversation.
    audit_judges: dict = field(default_factory=dict, repr=False, compare=False)
    # the payload's disclosed SpreadsheetBench values and the public workbooks read for their check (``disclosed``)
    sheet: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    @property
    def calls_cap(self):
        """The engineer calls of one step (v1, ``ENGINEER_CALLS``) or of one ``engineer-r<r>`` unit (v2)."""
        return (protocol.TRAIN_ENGINEER_CALL_BUDGETS[self.configuration] if self.mode == TRAIN
                else protocol.ENGINEER_CALL_BUDGETS[self.configuration])

    def __post_init__(self):
        require(self.bench in protocol.SUPPORTED_BENCHES and type(self.k) is int and 0 <= self.k <= 999,
                "A known bench and step number")
        require(self.mode in ("single", TRAIN), "A known learning mode")
        require(self.configuration in protocol.CONFIGURATIONS, "A known engineer configuration")
        require(isinstance(self.routing_items, list) and all(
            isinstance(entry, (tuple, list)) and len(entry) == 2 and type(entry[0]) is str
            and isinstance(entry[1], dict) and all(type(key) is str for key in entry[1])
            for entry in self.routing_items), "Training routing items hold public view mappings")
        require(len({entry[0] for entry in self.routing_items}) == len(self.routing_items),
                "Training routing items are distinct")
        if self.bench == "zebralogic":
            from .zebralogic import public_view
            require(all(set(view) == {"question", "columns"} and public_view(view) == view
                        for _, view in self.routing_items), "Zebra routing items contain only the exact public view")
        require(not self.routing_items or callable(self.routing_workers), "Training routing items have sandbox workers")
        require(type(self.routing_shared_worker) is bool and not (
            self.bench == "spreadsheetbench" and self.routing_shared_worker), "Workbook routing workers stay per item")
        require(type(self.echo) is bool and type(self.counterfactual) is bool
                and (self.mode == TRAIN or (self.echo and not self.counterfactual)),
                "v2.1's fix-call and counterfactual rules belong to the train mode")
        require(type(self.spent) is int and 0 <= self.spent <= self.calls_cap and (self.mode != TRAIN or not self.spent),
                "The step's engineer calls so far")
        chain = str(self.label).split("/", 1)[0]
        for trajectory in self.trajectories:
            found = RUN_UNIT.fullmatch(str(verified(trajectory, "trajectory")["unit"]))
            require(found is not None and found["chain"] == chain and found["bench"] == trajectory["bench"]
                    and int(found["k"]) <= self.k, "The engineer sees run-slice trajectories of its own chain only")
        failures = {t["task_id"] for t in self.trajectories if t["bench"] == self.bench and t["token"] == "fail"}
        if self.mode == TRAIN:
            failures |= self._training_inputs(chain)
        else:
            require(self.round == 0 and self.base is None and not self.current and not self.evaluated
                    and not self.history and self.training is None and not self.lint and not self.reserved
                    and not self.analysed and not self.disclosed, "Training inputs only in the train mode")
        require(self.bench != "alfworld" or not self.references, "No reference reaches the engineer on ALFWorld")
        require(set(self.references) <= failures and all(
            _answer_shape(v, grid=self.bench == "zebralogic") for v in self.references.values()),
                "References only for this bench's run-slice failures, in a frozen answer shape")
        require(_counts(self.detectors), "The engineer sees detector counts only")
        require(self.previous is None or (
            isinstance(self.previous, dict) and set(self.previous) == PREVIOUS_FIELDS
            and self.previous["decision"] in ("accepted", "not_accepted") and _counts(self.previous["faults"])
            and _counts(self.previous["format"])),
            "The previous step is shown as accepted / not accepted with fault and format counts only")

    def _training_inputs(self, chain):
        """The train mode's own inputs (class docstring); returns the run-slice items a current or evaluated cell
        failed."""
        require(type(self.round) is int and 1 <= self.round <= TRAIN_ROUNDS and isinstance(self.base, Package),
                "A training round of the step's parent")
        require(self.parent.sha256 == self.base.sha256 or self.parent.parent_sha256 == self.base.sha256,
                "The incumbent is the step's parent or one candidate of it")
        if self.parent.sha256 != self.base.sha256:
            validate(self.parent, self.base)
        own = {t["task_id"] for t in self.trajectories if t["bench"] == self.bench
               and int(RUN_UNIT.fullmatch(t["unit"])["k"]) == self.k}
        for trajectory in list(self.current) + list(self.evaluated):
            unit = str(verified(trajectory, "trajectory")["unit"])
            run, train = RUN_UNIT.fullmatch(unit), TRAIN_UNIT.fullmatch(unit)
            found = run or train
            require(found is not None and found["chain"] == chain and found["bench"] == self.bench
                    and int(found["k"]) == self.k and (train is None or int(train["r"]) < self.round)
                    and trajectory["bench"] == self.bench and trajectory["task_id"] in own,
                    "Training trajectories are this step's run-slice cells of its run unit or an earlier training "
                    "unit")
        v24, v25 = protocol.is_v24(self.configuration), protocol.is_v25(self.configuration)
        require(isinstance(self.history, list) and all(_history_line(entry, self.round, v24=v24,
                v28=protocol.is_v28(self.configuration), v29=protocol.is_v29(self.configuration),
                v291=protocol.is_v291(self.configuration),
                v294=protocol.is_v294(self.configuration)) for entry in self.history),
                "The history holds counts and flags only")
        require(isinstance(self.lint, list) and all(_lint_entry(entry, v25=v25,
                **({"v26": True} if protocol.is_v26(self.configuration) else {}),
                **({"v27": True} if protocol.is_v27(self.configuration) else {}),
                **({"v28": True} if protocol.is_v28(self.configuration) else {}),
                **({"v29": True} if protocol.is_v29(self.configuration) else {}),
                **({"v291": True} if protocol.is_v291(self.configuration) else {}),
                **({"v292": True} if protocol.is_v292(self.configuration) else {})) for entry in self.lint),
                "Lint entries are reports")
        require(isinstance(self.reserved, frozenset) and all(type(i) is str for i in self.reserved),
                "Reserved procedure ids")
        require(isinstance(self.analysed, frozenset) and self.analysed <= own, "Analysed items are run-slice items")
        require(isinstance(self.disclosed, frozenset) and self.disclosed <= own
                and (self.bench != "alfworld" or not self.disclosed), "Disclosed items are run-slice items")
        require(all(isinstance(self.references.get(i), dict) for i in self.disclosed),
                "Disclosed items keep their table-shape references")
        evaluated = {t["cell"]: t for t in self.evaluated}
        require(self.training is None or _training_ok(self.training, self.references, own, evaluated, self.bench,
                                                      v24=v24, v25=v25 and not protocol.is_alfworld(self.configuration),
                                                      v28=protocol.is_v28(self.configuration), v29=protocol.is_v29(self.configuration),
                                                      v291=protocol.is_v291(self.configuration),
                                                      v292=protocol.is_v292(self.configuration),
                                                      current={t["cell"]: t for t in self.current}),
                "The training feedback shows this step's run-slice items with their own references only")
        output_refs = {e["task_id"] for e in (self.training or {}).get("unfixed_examples", [])} if v24 else set()
        return ({t["task_id"] for t in list(self.current) + list(self.evaluated) if t["token"] == "fail"}
                | self.disclosed | output_refs)


def _text(value, limit, *, empty=True):
    return type(value) is str and len(value) <= limit and (empty or bool(value.strip()))


def _count(value):
    return type(value) is int and value >= 0


def _verdict_fields(entry):
    """The verdict's counts and flags a history line and the training feedback share: the net as "p/q", the sign
    test's p, the reason."""
    return (all(_count(entry[k]) for k in ("items", "fixed", "broken")) and type(entry["adopted"]) is bool
            and type(entry["net"]) is str and FRACTION.fullmatch(entry["net"]) is not None
            and (entry["p_sign"] is None or (type(entry["p_sign"]) in (int, float) and 0 <= entry["p_sign"] <= 1))
            and (entry["reason"] is None or _text(entry["reason"], MAX_REASON_CHARS)))


def _history_line(entry, before, *, v24=False, v28=False, v29=False, v291=False, v294=False):
    """v2 (Codex review 2026-10-23 #4): a line of an earlier round exactly as ``step._line`` writes it -- counts,
    flags, the net, p and reason -- with its ``proposals`` (the step buffer): kind, registrar id, target, a description
    excerpt and the fate."""
    fields = HISTORY_FIELDS | ({"patience_counted"} if v24 else set())
    if v291:
        fields |= {"own_fault_cells", "format_cells"}
        if not _count(entry.get("own_fault_cells")) or not _format_counts_ok(entry.get("format_cells")):
            return False
    if v29 and "confirm" in entry:
        from .engineer_v29 import confirm_feedback_ok
        if not confirm_feedback_ok(entry["confirm"]):
            return False
        fields |= {"confirm"}
    if v28 and "inert" in entry:
        if not isinstance(entry["inert"], list) or not all(_text(i, MAX_ID_CHARS) for i in entry["inert"]):
            return False
        fields |= {"inert"}
    if not (isinstance(entry, dict) and set(entry) == fields and type(entry["round"]) is int
            and 1 <= entry["round"] < before and type(entry["candidate"]) is bool and _count(entry["generated"])
            and _verdict_fields(entry) and isinstance(entry["proposals"], list)):
        return False
    if v24 and (type(entry["patience_counted"]) is not bool or entry["patience_counted"] != entry["candidate"]):
        return False
    def proposal_fields(proposal):
        fields = PROPOSAL_FIELDS
        if v294 and proposal.get("fate") == "inert":
            from . import inert_feedback
            if not inert_feedback.causes_ok(proposal.get("inert_causes")):
                return False
            fields = fields | {"inert_causes"}
        return set(proposal) == fields

    return all(isinstance(p, dict) and proposal_fields(p) and (p["kind"] is None or p["kind"] in EDIT_KINDS)
               and all(p[k] is None or _text(p[k], MAX_ID_CHARS) for k in ("id", "target"))
               and _text(p["description"], TRAIN_PROPOSAL_CHARS) and _text(p["fate"], MAX_REASON_CHARS, empty=False)
               for p in entry["proposals"])


def _lint_entry(entry, *, v25=False, v26=False, v27=False, v28=False, v29=False, v291=False, v292=False):
    """v2 (Codex review 2026-10-23 #3, #4): an advisory replay-test report exactly as ``_lint`` writes it."""
    if not isinstance(entry, dict):
        return False
    if v28 and "information" in entry:
        from . import fault_feedback
        info = entry["information"]
        if not (isinstance(info, list) and len(info) <= 6 and all(isinstance(row, dict)
                and set(row) == ({"check", "passed", "counts"} | (
                    {"fired_items", "faulted_items", "signatures", "dropped_notes"}
                    | ({"truncated"} if "truncated" in row else set())
                    if v291 and row.get("check") == "C6" else set()))
                and (not v291 or row.get("check") != "C6" or fault_feedback.lint_details_ok(row, v292=v292))
                and row["check"] in ("C5b", "C6", "C6b", "C6c", "C7", "C9")
                and type(row["passed"]) is bool and isinstance(row["counts"], dict)
                and set(row["counts"]) <= engineer_v28.INFORMATION_COUNTS
                and all(_count(v) for v in row["counts"].values()) for row in info)):
            return False
    fields = LINT_FIELDS | ({"information"} if v28 and "information" in entry else set())
    if v29 and "audit" in entry:
        from .engineer_v29 import audit_feedback_ok
        if not audit_feedback_ok(entry["audit"]):
            return False
        fields |= {"audit"}
    if not (isinstance(entry, dict) and set(entry) == fields and _text(entry["id"], MAX_ID_CHARS, empty=False)
            and isinstance(entry["tests"], list) and len(entry["tests"]) <= MAX_TESTS
            and isinstance(entry["problems"], list) and len(entry["problems"]) <= MAX_LINT):
        return False
    tests_ok = all(isinstance(t, dict) and set(t) == LINT_TEST_FIELDS and type(t["test"]) is int
                   and 1 <= t["test"] <= MAX_TESTS and all(type(t[k]) is bool for k in ("holds", "withheld", "nonvacuous"))
                   and (t["mutated"] is None or type(t["mutated"]) is bool) for t in entry["tests"])
    return tests_ok and all(
        isinstance(p, dict) and p.get("reason") in LINT_REASONS
        and set(p) <= (({"reason", "test", "detail", "rendered_note"} if v25 else {"reason", "test", "detail"})
                      | ({"valid_trajectories", "valid_trajectories_total"} if v26 else set())
                      | ({"evaluated", "validation_explanation"} if v27 else set()))
        and (not ({"evaluated", "validation_explanation"} & set(p)) or
             (p["reason"] in ("invalid_test", "test_count") and p.get("evaluated") is False
              and _text(p.get("validation_explanation"), replay.VALIDATION_EXPLANATION_CHARS, empty=False)))
        and (not ({"valid_trajectories", "valid_trajectories_total"} & set(p)) or
             (p.get("reason") == "invalid_test" and p.get("detail") == "trajectory_not_in_scope"
              and replay.valid_trajectories_shape(p)))
        and ("rendered_note" not in p or (_text(p["rendered_note"], 1500)
             and p["reason"] in ("test_failed", "vacuous_test") and type(p.get("test")) is int
             and 1 <= p["test"] <= MAX_TESTS))
        and (p.get("test") is None or (type(p["test"]) is int and p["test"] >= 1))
        and (p.get("detail") is None or p["detail"] in LINT_DETAILS
             or (p["reason"] == "test_count" and _count(p["detail"])))
        for p in entry["problems"])


def _training_ok(training, references, own, evaluated, bench, *, v24=False, v25=False, current=None, v28=False, v29=False,
                 v291=False, v292=False):
    """v2 (Codex review 2026-10-23 #4): the last round's feedback exactly as ``step._feedback`` writes it; each
    example names one of this step's run-slice items (``own``) and that item's candidate-arm cell of the last training
    unit (``evaluated``: {cell: trajectory}), its texts within ``TRAIN_TEXT_CHARS``, and a reference only off ALFWorld
    and only the item's own (``Context.references``)."""
    fields = TRAINING_FIELDS | ({"unfixed_examples", "identical_items"} if v24 else set())
    if v291:
        fields |= {"format"}
    if v29 and "confirm" in training:
        from .engineer_v29 import confirm_feedback_ok
        if not confirm_feedback_ok(training["confirm"]):
            return False
        fields |= {"confirm"}
    if v28:
        fields |= {"informational_guards"}
        if training.get("informational_guards") != ["own_faults", "predicate_faults"]:
            return False
    if not (isinstance(training, dict) and set(training) == fields and _verdict_fields(training)
            and training["p_sign"] is not None and type(training["need"]) is int and training["need"] >= 1
            and isinstance(training["guards"], dict) and set(training["guards"]) == GUARD_FIELDS
            and all(type(v) is bool for v in training["guards"].values())
            and isinstance(training["generated"], dict) and set(training["generated"]) == {"items", "fixed", "broken"}
            and all(_count(v) for v in training["generated"].values()) and isinstance(training["procedures"], list)):
        return False
    for entry in training["procedures"]:
        if not (isinstance(entry, dict) and set(entry) == (FEEDBACK_FIELDS | ({"notes_coverage"} if v25 else set())
                                                        | ({"faults"} if v291 else set()))
                and _text(entry["id"], MAX_ID_CHARS, empty=False)
                and entry["change"] in ("added", "removed", "narrowed")
                and all(_count(entry[k]) for k in ("enabled_items", "fixed", "broken"))
                and isinstance(entry["examples"], list) and len(entry["examples"]) <= 2 * TRAIN_EXAMPLES):
            return False
        if v25 and not _coverage_ok(entry["notes_coverage"], entry["enabled_items"]):
            return False
        if v291 and not _fault_feedback_ok(entry["faults"], own, v292=v292):
            return False
        if not all(_example_ok(example, references, own, evaluated, bench) for example in entry["examples"]):
            return False
    if v24:
        identical = training["identical_items"]
        if (not isinstance(identical, list) or not all(type(key) is str and key in own for key in identical)
                or identical != sorted(set(identical)) or not isinstance(training["unfixed_examples"], list)
                or len(training["unfixed_examples"]) > 4):
            return False
        seen = set()
        for example in training["unfixed_examples"]:
            if (not isinstance(example, dict) or set(example) != {"task_id", "cell", "token", "source", "notes", "answer", "reference"}
                    or type(example["task_id"]) is not str or example["task_id"] not in own
                    or example["task_id"] in seen or type(example["cell"]) is not str
                    or example["source"] not in ("candidate", "identical_current")
                    or not all(_text(example[key], bound) for key, bound in (("notes", 1000), ("answer", 500), ("reference", 1000)))):
                return False
            seen.add(example["task_id"])
            cells = evaluated if example["source"] == "candidate" else current or {}
            cell = cells.get(example["cell"])
            if (cell is None or cell["task_id"] != example["task_id"] or cell["token"] != example["token"]
                    or (example["source"] == "candidate" and cell.get("arm_kind") != "candidate")
                    or (example["source"] == "identical_current" and example["task_id"] not in identical)):
                return False
            reference = (engineer_payload.reference_excerpt(references[example["task_id"]])
                         if example["task_id"] in references else "reference unavailable")
            if example["reference"] != reference:
                return False
    if v291 and not _format_feedback_ok(training["format"], own, evaluated, training["guards"]["format"]):
        return False
    return True


def _format_counts_ok(value):
    return isinstance(value, dict) and set(value) == {"S", "S'"} and all(_count(n) for n in value.values())


def _fault_feedback_ok(value, own, *, v292=False):
    from . import fault_feedback
    if not (isinstance(value, dict) and set(value) == {"cells", "signatures"} and _count(value["cells"])
            and isinstance(value["signatures"], list) and len(value["signatures"]) <= 3):
        return False
    return all(isinstance(row, dict) and set(row) == ({"hook", "kind", "exc_type", "message", "cells", "example_task_id"}
               | ({"expected", "returned"} if v292 and row.get("kind") == "output_shape" else set()))
               and fault_feedback.shape_fields_ok(row, v292=v292)
               and all(row[key] is None or type(row[key]) is str for key in ("hook", "kind", "exc_type"))
               and _text(row["message"], 200) and _count(row["cells"]) and 0 < row["cells"] <= value["cells"]
               and (row["example_task_id"] is None or type(row["example_task_id"]) is str and row["example_task_id"] in own)
               for row in value["signatures"])


def _format_feedback_ok(value, own, evaluated, passed):
    if not (isinstance(value, dict) and set(value) == {"S", "S'", "margin", "blocked", "examples"}
            and all(_count(value[key]) for key in ("S", "S'", "margin")) and type(value["blocked"]) is bool
            and value["blocked"] == (not passed) and value["blocked"] == (value["S'"] - value["S"] > value["margin"])
            and isinstance(value["examples"], list) and len(value["examples"]) <= 2):
        return False
    seen = set()
    from .step import _format_example
    for example in value["examples"]:
        if not (isinstance(example, dict) and set(example) == {"task_id", "cell", "detail", "notes", "candidate_reply"}
                and type(example["task_id"]) is str and example["task_id"] in own and example["task_id"] not in seen
                and type(example["cell"]) is str
                and all(_text(example[key], cap) for key, cap in (("detail", 300), ("notes", 600), ("candidate_reply", 600)))):
            return False
        trajectory = evaluated.get(example["cell"])
        if trajectory is None or trajectory["task_id"] != example["task_id"] or trajectory.get("arm_kind") != "candidate":
            return False
        detail = (trajectory.get("judge") or {}).get("format") or {}
        if not detail.get("violation") or example != _format_example(trajectory, detail):
            return False
        seen.add(example["task_id"])
    return True


def _coverage_ok(value, enabled):
    """v2.5 delivered-note coverage is counts only, once per enabled run item and field."""
    return (isinstance(value, dict) and set(value) == {"items", "with_notes", "fields", "faults"}
            and all(_count(value[key]) for key in ("items", "with_notes", "faults"))
            and value["items"] <= enabled and value["with_notes"] <= value["items"]
            and value["faults"] <= value["items"] and isinstance(value["fields"], dict)
            and set(value["fields"]) == {"facts", "table", "candidates", "warnings", "bindings"}
            and all(_count(count) and count <= value["with_notes"] for count in value["fields"].values()))


def _example_ok(example, references, own, evaluated, bench):
    if not (isinstance(example, dict) and EXAMPLE_FIELDS <= set(example) <= EXAMPLE_FIELDS | {"reference"}
            and type(example["task_id"]) is str and type(example["cell"]) is str):
        return False
    cell = evaluated.get(example["cell"])
    return (example["task_id"] in own and cell is not None and cell["task_id"] == example["task_id"]
            and cell.get("arm_kind") == "candidate" and example["outcome"] in ("fixed", "broken")
            and all(_text(example[k], TRAIN_TEXT_CHARS[cap]) for k, cap in EXAMPLE_TEXTS)
            and all(type(example[k]) is str and FRACTION.fullmatch(example[k]) is not None
                    for k in ("current_pass", "candidate_pass"))
            and ("reference" not in example or (bench != "alfworld"
                                                and example["reference"] == references.get(example["task_id"]))))


def _answer_shape(value, *, grid=False):
    """A frozen reference shape: a text, a list of texts (SearchQA's answers), or answer positions to scalars."""
    if type(value) is str:
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(type(v) is str for v in value)
    if isinstance(value, dict):
        if grid:
            return bool(value) and all(type(k) is str and re.fullmatch(r"House [1-9][0-9]*", k)
                and type(row) is dict and row and all(type(c) is str and c not in HIDDEN and type(v) is str
                                                    for c, v in row.items()) for k, row in value.items())
        return bool(value) and all(type(k) is str and k not in HIDDEN and type(v) in (str, int, float)
                                   for k, v in value.items())
    return False


def _counts(value):
    """Counts only: a non-negative integer, or a mapping of names to counts."""
    if type(value) is int:
        return value >= 0
    return isinstance(value, dict) and all(type(k) is str and _counts(v) for k, v in value.items())


# ------------------------------------------------------------------------------------------------- the payload
def shown(ctx):
    """The trajectories shown to the engineer: at most ``ENGINEER_SHOWN`` failures and successes of the parent's cells
    on the bench, in the seeded order (``data.ranked``, ``SHOWN_TAG`` + the unit label); in the train mode of the
    incumbent's latest cells (``Context.current``)."""
    tag = "%s:%s" % (SHOWN_TAG, ctx.label)
    pool = ctx.current if ctx.mode == TRAIN else [t for t in ctx.trajectories if t.get("arm_kind") == "parent"]
    out = []
    for kind, token in (("failures", "fail"), ("successes", "pass")):
        found = [{"task_id": t["cell"], "trajectory": t} for t in pool
                 if t["bench"] == ctx.bench and t.get("token") == token]
        out += [(kind, entry["trajectory"]) for entry in ranked(found, SEED, tag)[:ENGINEER_SHOWN[kind]]]
    return out


def _shown_view(kind, trajectory, references, echo=True):
    view = whitelisted(trajectory)
    for call in view["calls"]:
        call.pop("system")
    if not echo:
        view["shell"] = _unechoed(view["shell"])
    entry = {"kind": kind, **view}
    if kind == "failures" and trajectory["task_id"] in references:
        entry["reference"] = references[trajectory["task_id"]]
    return entry


def _unechoed(shell):
    """v2.1 (``Context.echo`` False; Codex review 2026-10-24 #3): a shown trajectory's shell without the texts the note
    screens matched -- the message of a lexicon or meta-option fault and the detail of a field dropped for either
    reason become None; every kind, field and reason is kept."""
    out = dict(shell)
    if isinstance(shell.get("faults"), list):
        out["faults"] = [{**f, "message": None} if isinstance(f, dict) and f.get("kind") in SCREEN_FAULTS else f
                         for f in shell["faults"]]
    if isinstance(shell.get("notes"), list):
        out["notes"] = [{**n, "dropped": [{**d, "detail": None} if isinstance(d, dict) and d.get("reason") in
                                          SCREEN_REASONS else d for d in n["dropped"]]}
                        if isinstance(n, dict) and isinstance(n.get("dropped"), list) else n for n in shell["notes"]]
    return out


def _listed(procedure, parent):
    return {"id": procedure.id, "description": procedure.description, "hooks": list(procedure.hooks),
            "header": procedure.header, "max_note_chars": procedure.max_note_chars,
            "requests_second_call": procedure.requests_second_call, "state_bytes": procedure.state_bytes,
            "excluded_benches": list(parent.excluded(procedure.id)), "source": procedure.source}


def payload(ctx, analyses=None):
    """The user message of the proposal call (fitted: the last trajectories are left out first); v2: with the
    round's ``analyses`` (``analyse``), fitted by ``_fit_train``."""
    user = {"request": "propose", "bench": ctx.bench, "card": ctx.card,
            "package": [_listed(p, ctx.parent) for p in ctx.parent.procedures],
            "trajectories": [_shown_view(kind, t, ctx.references, ctx.echo) for kind, t in shown(ctx)],
            "detectors": ctx.detectors, "previous": ctx.previous}
    if protocol.is_v24(ctx.configuration):
        user["hook_views"] = hook_views(ctx)
    if ctx.mode != TRAIN:
        if protocol.TRIM_PAYLOADS[ctx.configuration]:
            user = engineer_payload.trim(user)
        return fit(user, "trajectories", ROLE_INPUT_BYTES)
    # v2: the round, the earlier rounds, the last evaluation and lint, the edit budget
    user.update({"round": ctx.round, "rounds": TRAIN_ROUNDS, "history": ctx.history, "training": ctx.training,
                 "lint": ctx.lint, "edits": budget(ctx), "analyses": list(analyses or [])})
    if protocol.TRIM_PAYLOADS[ctx.configuration]:
        user = engineer_payload.trim(user)
    return _fit_train(user)


def _fit_train(user):
    """v2 (Codex review 2026-10-23 #5): the proposal message within ``ROLE_INPUT_BYTES``, leaving out -- each from
    the last, deterministically -- the trajectories (``fit``), then the training feedback's examples (the last
    procedure's last example first), then the analyses; ``trajectories_omitted``, ``examples_omitted`` and
    ``analyses_omitted`` count them. The context's feedback is never changed (a copy is cut). ValueError (the unit
    pauses, as ``fit``) only when the other fields alone exceed the bound."""
    user["examples_omitted"] = user["analyses_omitted"] = 0
    try:
        return fit(user, "trajectories", ROLE_INPUT_BYTES)
    except ValueError:  # every trajectory is left out; the feedback, then the analyses, go next
        pass
    if user["training"] is not None:
        user["training"] = {**user["training"], "procedures": [
            {**entry, "examples": list(entry["examples"])} for entry in user["training"]["procedures"]]}
        for entry in reversed(user["training"]["procedures"]):
            while entry["examples"] and message_bytes(user) > ROLE_INPUT_BYTES:
                entry["examples"].pop()
                user["examples_omitted"] += 1
        if "unfixed_examples" in user["training"]:
            user["training"]["unfixed_examples"] = list(user["training"]["unfixed_examples"])
            user["unfixed_examples_omitted"] = 0
            while user["training"]["unfixed_examples"] and message_bytes(user) > ROLE_INPUT_BYTES:
                user["training"]["unfixed_examples"].pop()
                user["unfixed_examples_omitted"] += 1
    while user["analyses"] and message_bytes(user) > ROLE_INPUT_BYTES:
        user["analyses"].pop()
        user["analyses_omitted"] += 1
    if message_bytes(user) > ROLE_INPUT_BYTES:
        raise ValueError("A role input exceeds its bound with no example left")
    return user


def analyse(ctx):
    """v2's analysts (owner suggestion 2026-10-23 15:1x; SkillOpt's minibatch reflection, skillopt/gradient/reflect.py):
    the incumbent's failed run-slice items of the bench -- one failed current cell each, in the seeded order
    (``ANALYST_TAG`` + the unit label), items no earlier round analysed (``Context.analysed``) first -- in groups of
    ``TRAIN_ANALYST_BATCH``, at most ``TRAIN_ANALYST_CALLS`` engineer-role calls under ``ANALYST_SYSTEM``, each shown
    the card, the incumbent's procedures (id, description, hooks) and its group as the proposal call shows a failure
    (with its reference). -> ``(findings, [(cell, table-shape reference)] shown, the record)``: a reply's findings that
    name shown items, texts cut to ``TRAIN_FINDING_CHARS``, at most ``TRAIN_FINDINGS`` per reply; an unusable reply
    adds none and is recorded with its reason."""
    tag = "%s:%s" % (ANALYST_TAG, ctx.label)
    failed = [{"task_id": t["cell"], "trajectory": t} for t in ctx.current
              if t["bench"] == ctx.bench and t.get("token") == "fail"]
    first = {}
    for entry in ranked(failed, SEED, tag):
        first.setdefault(entry["trajectory"]["task_id"], entry["trajectory"])
    order = [i for i in first if i not in ctx.analysed] + [i for i in first if i in ctx.analysed]
    chosen = order[:TRAIN_ANALYST_BATCH * TRAIN_ANALYST_CALLS]
    package = [{"id": p.id, "description": p.description, "hooks": list(p.hooks)} for p in ctx.parent.procedures]
    findings, shown_refs, calls = [], [], []
    for n, start in enumerate(range(0, len(chosen), TRAIN_ANALYST_BATCH), 1):
        group = [_shown_view("failures", first[i], ctx.references, ctx.echo)
                 for i in chosen[start:start + TRAIN_ANALYST_BATCH]]
        user = {"request": "analyse", "bench": ctx.bench, "card": ctx.card, "package": package,
                "trajectories": group}
        if protocol.TRIM_PAYLOADS[ctx.configuration]:
            user = engineer_payload.trim(user)
        user = fit(user, "trajectories", ROLE_INPUT_BYTES)
        seen = [t["task_id"] for t in user["trajectories"]]
        shown_refs += [(t["cell"], t["reference"]) for t in user["trajectories"] if isinstance(t.get("reference"), dict)]
        reply = ctx.roles.plain(ROLE, ANALYST_SYSTEM, json.dumps(user, ensure_ascii=False, sort_keys=True),
                                label="analyst/%s/%d" % (ctx.label, n))
        found, reason = _findings(reply, seen)
        findings += found
        calls.append({"call": ctx.roles.calls[-1]["request_sha256"], "items": seen, "findings": len(found),
                      "reason": reason,
                      **({"payload_trimming": user["payload_trimming"]} if "payload_trimming" in user else {})})
    return findings, shown_refs, {"items": [i for c in calls for i in c["items"]], "calls": calls,
                                  "failed_items": len(first)}


def _findings(reply, items):
    """An analyst reply's usable findings (``analyse``) and why it gave none, or None."""
    if type(reply) is not str:
        return [], "no_reply"
    blocks = [body for lang, body in BLOCK.findall(reply) if lang.lower() in ("json", "")]
    try:
        value = json.loads(blocks[0] if blocks else reply.strip())
    except ValueError:
        return [], "not_json"
    entries = value.get("findings") if isinstance(value, dict) else None
    if not isinstance(entries, list):
        return [], "no_findings_list"
    out = []
    for entry in entries:
        if not isinstance(entry, dict) or type(entry.get("pattern")) is not str or not entry["pattern"].strip():
            continue
        named = [i for i in entry.get("items") or [] if type(i) is str and i in items] \
            if isinstance(entry.get("items"), list) else []
        helper = entry.get("helper") if type(entry.get("helper")) is str else ""
        out.append({"pattern": entry["pattern"][:TRAIN_FINDING_CHARS], "items": list(dict.fromkeys(named)),
                    "helper": helper[:TRAIN_FINDING_CHARS]})
        if len(out) == TRAIN_FINDINGS:
            break
    return out, None if out or not entries else "no_usable_finding"


def budget(ctx):
    """v2: the edits the incumbent already makes against the step's parent S (``MAX_CHANGES`` per step) and the
    procedures this step created."""
    made = edits(ctx.base, ctx.parent) if ctx.parent.sha256 != ctx.base.sha256 else []
    return {"max": MAX_CHANGES, "used": len(made), "edits": [{"kind": e.kind, "id": e.id} for e in made],
            "step_procedures": [p.id for p in ctx.parent.procedures if p.id not in ctx.base.order]}


def _ask(ctx, user, purpose):
    """``(reply or None, request sha256)`` of one engineer call; (None, None) once the step's calls are spent: this
    unit's and, for ``engineer-2``, those of the step's first engineer unit (``ctx.spent``; R7a); in the train mode
    the unit's own ``TRAIN_ENGINEER_CALLS`` under ``ENGINEER_SYSTEM_V2``."""
    prefix = "engineer/%s/" % ctx.label
    if ctx.spent + ctx.roles.count(prefix) >= ctx.calls_cap:
        return None, None
    system = ENGINEER_SYSTEM_V2 if ctx.mode == TRAIN else ENGINEER_SYSTEM
    modern = protocol.NORMALIZE_STRUCTURE[ctx.configuration]
    if modern:
        system = ENGINEER_SYSTEM_V23 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_V23
    if ctx.configuration == protocol.ZEBRA_PC_V1:
        system = ENGINEER_SYSTEM_ZPC if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ZPC
    if protocol.is_v24(ctx.configuration):
        if ctx.bench == "zebralogic":
            system = ENGINEER_SYSTEM_ZPC_V24 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ZPC_V24
        else:
            system = ENGINEER_SYSTEM_V24 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_V24
    if protocol.is_v25(ctx.configuration):
        if ctx.bench == "zebralogic":
            system = ENGINEER_SYSTEM_ZPC_V25 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ZPC_V25
        else:
            system = ENGINEER_SYSTEM_V25 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_V25
    if protocol.is_v26(ctx.configuration):
        system = ENGINEER_SYSTEM_ZPC_V26 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ZPC_V26
    if protocol.is_v27(ctx.configuration) and protocol.is_zebra(ctx.configuration):
        system = ENGINEER_SYSTEM_ZPC_V27 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ZPC_V27
    if protocol.is_alfworld(ctx.configuration):
        system = ENGINEER_SYSTEM_ALF_V1 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ALF_V1
    if protocol.is_alfworld_v2(ctx.configuration):
        system = ENGINEER_SYSTEM_ALF_V2 if ctx.mode == TRAIN else ENGINEER_SYSTEM_SINGLE_ALF_V2
    if protocol.is_v28(ctx.configuration):
        system = engineer_v28.system(ctx.configuration, train=ctx.mode == TRAIN)
        if user.get("request") == "fix":
            system += engineer_v28.FIX_SYSTEM
        elif user.get("request") == "format_retry":
            system += engineer_v28.FORMAT_RETRY_SYSTEM
    if protocol.is_v29(ctx.configuration):
        from . import engineer_v29
        system = engineer_v29.system(ctx.configuration, train=ctx.mode == TRAIN)
        suffix = {"fix": engineer_v29.FIX_SYSTEM, "format_retry": engineer_v29.FORMAT_RETRY_SYSTEM,
                  "audit_fix": engineer_v29.AUDIT_FIX_SYSTEM}.get(user.get("request"))
        if suffix:
            system += suffix
    if protocol.is_v291(ctx.configuration):
        from . import engineer_v291
        system = engineer_v291.system(ctx.configuration, train=ctx.mode == TRAIN)
        suffix = {"fix": engineer_v29.FIX_SYSTEM, "format_retry": engineer_v29.FORMAT_RETRY_SYSTEM,
                  "audit_fix": engineer_v29.AUDIT_FIX_SYSTEM,
                  "fault_repair": engineer_v291.FAULT_REPAIR_INSTRUCTION}.get(user.get("request"))
        if suffix:
            system += suffix
    if protocol.is_v292(ctx.configuration) and not protocol.is_v293(ctx.configuration):
        from . import engineer_v292
        system = engineer_v292.system(ctx.configuration, train=ctx.mode == TRAIN)
        suffix = {"fix": engineer_v29.FIX_SYSTEM, "format_retry": engineer_v292.FORMAT_RETRY_SYSTEM,
                  "audit_fix": engineer_v29.AUDIT_FIX_SYSTEM,
                  "fault_repair": engineer_v291.FAULT_REPAIR_INSTRUCTION}.get(user.get("request"))
        if suffix:
            system += suffix
    if protocol.is_v293(ctx.configuration) and not protocol.is_v294(ctx.configuration):
        from . import engineer_v293
        system = engineer_v293.system(ctx.configuration, train=ctx.mode == TRAIN)
        suffix = {"fix": engineer_v29.FIX_SYSTEM, "format_retry": engineer_v293.FORMAT_RETRY_SYSTEM,
                  "audit_fix": engineer_v29.AUDIT_FIX_SYSTEM,
                  "fault_repair": engineer_v291.FAULT_REPAIR_INSTRUCTION}.get(user.get("request"))
        if suffix:
            system += suffix
    if protocol.is_v294(ctx.configuration):
        from . import engineer_v293, engineer_v294
        system = engineer_v294.system(ctx.configuration, train=ctx.mode == TRAIN)
        suffix = {"fix": engineer_v29.FIX_SYSTEM, "format_retry": engineer_v293.FORMAT_RETRY_SYSTEM,
                  "audit_fix": engineer_v29.AUDIT_FIX_SYSTEM,
                  "fault_repair": engineer_v291.FAULT_REPAIR_INSTRUCTION,
                  "inert_repair": engineer_v294.inert_repair_instruction(
                      ctx.configuration, user.get("evidence", {}))}.get(user.get("request"))
        if suffix:
            system += suffix
    options = ({"max_tokens": protocol.ENGINEER_MAX_TOKENS[ctx.configuration]}
               if modern and ctx.mode == TRAIN and purpose in ("propose", "repropose") else {})
    reply = ctx.roles.plain(ROLE, system, json.dumps(user, ensure_ascii=False, sort_keys=True),
                            label=prefix + purpose, **options)
    if protocol.is_v25(ctx.configuration) and purpose in ("propose", "repropose"):
        _remember_shown(ctx, user)
    return reply, ctx.roles.calls[-1]["request_sha256"]


def _verified_run_cells(ctx):
    """Current-step run membership, retaining exact verified original/current cell identities."""
    chain = str(ctx.label).split("/", 1)[0]
    original = {}
    for trajectory in ctx.trajectories:
        verified(trajectory, "trajectory")
        found = RUN_UNIT.fullmatch(str(trajectory["unit"]))
        if (found is not None and found["chain"] == chain and found["bench"] == ctx.bench
                and int(found["k"]) == ctx.k and trajectory["bench"] == ctx.bench):
            original[trajectory["cell"]] = trajectory
    own, cells = {value["task_id"] for value in original.values()}, dict(original)
    for trajectory in ctx.current if ctx.mode == TRAIN else ():
        verified(trajectory, "trajectory")
        unit = str(trajectory["unit"])
        run, train = RUN_UNIT.fullmatch(unit), TRAIN_UNIT.fullmatch(unit)
        found = run or train
        if (found is not None and found["chain"] == chain and found["bench"] == ctx.bench
                and int(found["k"]) == ctx.k and (train is None or int(found["r"]) < ctx.round)
                and trajectory["bench"] == ctx.bench and trajectory["task_id"] in own):
            cells[trajectory["cell"]] = trajectory
    return cells


def _remember_shown(ctx, user):
    """Only complete trajectory entries retained in an actually sent, fitted proposal authorize replay text."""
    verified_cells = _verified_run_cells(ctx)
    shown_cells = ctx.sheet.setdefault("shown_cells_v25", set())
    for entry in user.get("trajectories", []):
        source = verified_cells.get(entry.get("cell"))
        if source is not None and all(entry.get(key) == source[key] for key in ("bench", "task_id", "unit")):
            shown_cells.add(source["cell"])


def _feedback_cells(ctx):
    return frozenset(ctx.sheet.get("shown_cells_v25", ())) & _verified_run_cells(ctx).keys()


# ------------------------------------------------------------------------------------------------------ parsing
def parse(reply, *, lenient=False, fix_change=None, parent_ids=(), normalizations=None, diagnostics=False):
    """``(changes, sources)``: the manifest's change entries and the python blocks, one per new or revised change in
    order. Raises ``Unparseable``. ``lenient`` (v2): a "source" text in a coded entry (the fix request shows the change
    so) is taken out of the entry, and used as its code when the reply has no python block. Only v2.7 fix calls
    supply fix_change and diagnostics; proposal parsing and every older default remain unchanged."""
    def malformed(reason, explanation):
        raise Unparseable((reason + ": " + explanation)[:MAX_FIX_PARSE_CHARS] if diagnostics else reason)

    if type(reply) is not str:
        malformed("no_reply", "expected one JSON manifest and the corrected change's code; received %s" % type(reply).__name__)
    blocks = BLOCK.findall(reply)
    manifests = [body for lang, body in blocks if lang.lower() == "json"]
    sources = [body for lang, body in blocks if lang.lower() in ("python", "py")]
    if len(manifests) != 1:
        malformed("manifest_blocks:%d" % len(manifests), "%d JSON block(s); exactly one ```json manifest block required" % len(manifests))
    try:
        manifest = json.loads(manifests[0])
    except ValueError:
        if diagnostics:
            raise Unparseable("manifest_json: the one JSON block must contain valid JSON; use an object with exactly the changes key") from None
        raise Unparseable("manifest_json") from None
    changes = manifest.get("changes") if isinstance(manifest, dict) and set(manifest) == {"changes"} else None
    if type(changes) is not list or len(changes) > MAX_CHANGES or not all(isinstance(c, dict) for c in changes):
        count = len(changes) if isinstance(changes, (list, tuple)) else None
        malformed("manifest_shape", "expected exactly {\"changes\": [change objects]} with at most %d changes; "
                  "received manifest type %s, changes type %s, change count %s" %
                  (MAX_CHANGES, type(manifest).__name__, type(changes).__name__, count))
    if fix_change is not None and len(changes) == 1:
        _normalize_fix_reply(changes[0], fix_change, parent_ids, normalizations)
    if lenient:
        inline = [c.get("source") for c in changes if c.get("kind") in CODED]
        for c in changes:
            c.pop("source", None)
        if not sources and inline and all(type(s) is str and s.strip() for s in inline):
            sources = inline
    if len(sources) != sum(1 for c in changes if c.get("kind") in CODED):
        malformed("code_blocks", "%d python block(s) for %d coded change(s); keep the change's \"kind\" and put "
                  "its code in exactly one ```python block per new or revised change" %
                  (len(sources), sum(1 for c in changes if c.get("kind") in CODED)))
    return changes, sources


def _normalize_fix_reply(entry, change, parent_ids, normalizations):
    """v2.7: repair only the unambiguous envelope of one reply to one identified change."""
    edits = []
    if "kind" not in entry:
        entry["kind"] = change.kind
        edit = {"rule": "fix_kind_inferred", "kind": change.kind}
        target = TARGET_KEYS.get(change.kind) if type(change.kind) is str else None
        if target is not None and target not in entry:
            entry[target] = change.entry.get(target)
            edit["target_key"] = target
            edit["target"] = str(entry[target])[:MAX_ID_CHARS]
        edits.append(edit)
    elif change.kind == "new" and entry["kind"] == "revision" and entry.get("revises") not in parent_ids:
        given = entry.pop("revises", None)
        entry["kind"] = "new"
        edits.append({"rule": "fix_revision_of_new_mapped", "given_kind": "revision", "kind": "new",
                      "given_revises": json.dumps(given, ensure_ascii=True, sort_keys=True)[:200]})
    if normalizations is not None:
        normalizations.extend(edits)


def changes_of(entries, sources, call):
    """The ``Change`` objects of a parsed reply."""
    out, code = [], iter(sources)
    for n, entry in enumerate(entries, 1):
        kind = entry.get("kind")
        out.append(Change(n, kind, entry, next(code) if kind in CODED else None, call))
    return out


# ------------------------------------------------------------------------------------------------------ checks
def _result(check, passed, detail=None):
    return {"check": check, "passed": bool(passed), "detail": detail}


def _keys(kind, train=False):
    """(required, allowed) keys of a coded entry; v2's replay tests are optional."""
    revises = ("revises",) if kind == "revision" else ()
    return ({"kind", "description", "hooks", *(() if train else ("replay_tests",)), *revises},
            {"kind", *PROCEDURE_KEYS, *revises})


def _structure(change, parent, taken, *, train=False, benches=BENCHES):
    """C1: None when the entry is well formed for its kind, else why not."""
    entry, kind = change.entry, change.kind
    if kind not in EDIT_KINDS:
        return "kind"
    if kind in CODED:
        required, allowed = _keys(kind, train)
        if not required <= set(entry) <= allowed:
            return "keys"
        if not all(type(entry[k]) is t for k, t in PROCEDURE_KEYS.items() if k in entry):
            return "types"
        if not all(type(h) is str and h in HOOKS for h in entry["hooks"]) \
                or not all(type(b) is str and b in benches for b in entry.get("excluded_benches", [])):
            return "unknown_hook_or_bench"
        no_calc = tuple(b for b in benches if b not in QA)
        if "bindings" in entry["hooks"] and not set(no_calc) <= set(entry.get("excluded_benches", [])):
            return "bindings_is_qa_only: list %s in excluded_benches" % " and ".join(no_calc)
    elif set(entry) != {"kind", "id", *(("benches",) if kind == "narrowing" else ())}:
        return "keys"
    if kind == "narrowing" and not (type(entry["benches"]) is list and entry["benches"]
                                    and all(type(b) is str and b in benches for b in entry["benches"])):
        return "benches"
    target = entry.get(TARGET_KEYS.get(kind))
    if kind != "new" and (type(target) is not str or target not in parent.order):
        return "target_not_in_parent"
    if kind != "new" and target in taken:
        return "target_edited_twice"
    return None


def _normalize(change, *, benches=BENCHES):
    """E4, before C1: order valid hooks and extend the scope of a QA-only bindings declaration."""
    entry = change.entry
    if change.kind not in CODED or not isinstance(entry, dict):
        return
    hooks = entry.get("hooks")
    if (isinstance(hooks, list) and all(type(h) is str and h in HOOKS for h in hooks)
            and len(set(hooks)) == len(hooks)):
        ordered = [h for h in HOOKS if h in hooks]
        if hooks != ordered:
            entry["hooks"] = ordered
            change.normalized.append({"field": "hooks", "before": hooks, "after": ordered})
        excluded = entry.get("excluded_benches", [])
        if "bindings" in hooks and isinstance(excluded, list) and all(type(b) is str and b in benches
                                                                        for b in excluded):
            missing = [b for b in benches if b not in QA and b not in excluded]
            if missing:
                entry["excluded_benches"] = [b for b in benches if b in excluded or b in missing]
                change.normalized.append({"field": "excluded_benches", "added": missing,
                                          "reason": "bindings_is_qa_only"})


def _new_id(ctx, n):
    """The registrar's id of the n-th coded change: ``p-<bench>-<k>-<n>`` (``fx-`` for engineering fixtures), the next
    free one."""
    prefix = "fx" if ctx.evidence == FIXTURE else "p"
    if ctx.mode == TRAIN:  # v2: unique across the step's rounds (``reserved``) and the unit; a fixed change keeps its id
        ids = ctx.sheet.setdefault("ids", {})
        if n not in ids:
            taken, m = set(ctx.parent.order) | ctx.reserved | set(ids.values()), 1
            while "%s-%s-%d-%d" % (prefix, ctx.bench, ctx.k, m) in taken:
                m += 1
            ids[n] = "%s-%s-%d-%d" % (prefix, ctx.bench, ctx.k, m)
        return ids[n]
    while "%s-%s-%d-%d" % (prefix, ctx.bench, ctx.k, n) in ctx.parent.order:
        n += 1
    return "%s-%s-%d-%d" % (prefix, ctx.bench, ctx.k, n)


def _edit_distance(left, right, limit=7):
    """Levenshtein distance capped at limit+1; enough to distinguish <=2, 3..7 and >=8."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for n, char in enumerate(left, 1):
        row = [n]
        for m, other in enumerate(right, 1):
            row.append(min(row[-1] + 1, previous[m] + 1, previous[m - 1] + (char != other)))
        if min(row) > limit:
            return limit + 1
        previous = row
    return min(previous[-1], limit + 1)


def _resolve_reference(given, entries, shown, tasks):
    """v2.6 first-match reference rules, with no candidates outside the actual replay scope."""
    if given in entries:
        return given, "exact"
    by_task = {}
    for cell, entry in entries.items():
        by_task.setdefault(entry["item"], []).append(cell)
    task = given if given in by_task else None
    if task is None:
        suffixes = [key for key in tasks if key.rsplit("/", 1)[-1] == given]
        if len(suffixes) == 1 and suffixes[0] in by_task:
            task = suffixes[0]
    if task is not None:
        cells = by_task[task]
        visible = [cell for cell in cells if cell in shown]
        return (visible[0] if len(visible) == 1 else cells[0] if len(cells) == 1 else given), "task_id"
    if re.fullmatch(r"[0-9a-f]{32}", given):
        distances = {cell: _edit_distance(given, cell) for cell in entries}
        close = [cell for cell, distance in distances.items() if distance <= 2]
        if len(close) == 1 and all(distance >= 8 for cell, distance in distances.items() if cell != close[0]):
            return close[0], "near_cell"
    return given, "unresolved"


def _resolve_change(change, ctx):
    """Resolve before any Procedure exists; new/revised procedures have only their declared exclusions.

    package.with_ removes a replaced procedure's narrowing and a new registrar ID cannot have one. Thus this
    excluded-set scope is exactly _scope(ctx, single, procedure), using the same input builder below. No routing,
    generated or evaluated-only trajectory is a candidate. Invalid structure still fails the existing checks.
    """
    if not protocol.is_v26(ctx.configuration) or change.kind not in CODED or change.trajectory_resolution is not None:
        return
    change.trajectory_resolution = []
    tests, excluded = change.entry.get("replay_tests", []), change.entry.get("excluded_benches", [])
    if not (type(tests) is list and type(excluded) is list and all(type(bench) is str for bench in excluded)):
        return
    entries = _scope_entries(ctx, set(excluded))
    shown = _feedback_cells(ctx)
    tasks = {value["task_id"] for value in _verified_run_cells(ctx).values()}
    for index, test in enumerate(tests, 1):
        if not isinstance(test, dict) or type(test.get("trajectory")) is not str:
            continue
        given = test["trajectory"]
        resolved, rule = _resolve_reference(given, entries, shown, tasks)
        if resolved != given:
            tests[index - 1] = {**test, "trajectory": resolved}
        if (resolved != given or resolved not in entries) and len(change.trajectory_resolution) < MAX_TESTS:
            change.trajectory_resolution.append({"test": str(test.get("id", index))[:256], "given": given[:256],
                                                 "resolved": resolved[:256], "rule": rule})


def _build(change, ctx):
    """C3: the procedure record and the one-change candidate."""
    if protocol.is_v26(ctx.configuration):
        _normalize(change, benches=protocol.SUPPORTED_BENCHES if ctx.bench == "zebralogic" else BENCHES)
    _resolve_change(change, ctx)
    entry, parent = change.entry, ctx.parent
    benches = protocol.SUPPORTED_BENCHES if ctx.bench == "zebralogic" else BENCHES
    if change.kind in CODED:
        old = parent.get(entry["revises"]) if change.kind == "revision" else None
        values = {**OPTIONAL, **{k: v for k, v in entry.items() if k in PROCEDURE_KEYS}}
        if ctx.mode == TRAIN:  # v2: optional replay tests; a description or header cut to its cap, recorded
            values.setdefault("replay_tests", [])
            for name, cap in (("description", MAX_DESCRIPTION_CHARS), ("header", MAX_HEADER_CHARS)):
                if len(values[name]) > cap:
                    change.truncated[name] = len(values[name])
                    values[name] = values[name][:cap]
        change.procedure = Procedure(
            id=_new_id(ctx, change.n), origin=ctx.bench, description=values["description"],
            hooks=tuple(h for h in HOOKS if h in values["hooks"]), source=change.source, evidence=ctx.evidence,
            header=values["header"], max_note_chars=values["max_note_chars"],
            requests_second_call=values["requests_second_call"], state_bytes=values["state_bytes"],
            excluded_benches=tuple(b for b in benches if b in values["excluded_benches"]),
            replay_tests=tuple(values["replay_tests"]),
            lineage={"parent": old.sha256 if old else None, "revises": old.id if old else None,
                     "engineer_call": change.call}, policy_version=protocol.POLICY_VERSIONS[ctx.configuration])
        change.target = old.id if old else None
    else:
        change.target = entry["id"]
        change.benches = tuple(b for b in benches if b in entry.get("benches", []))
    return candidate(parent, [change], step=ctx.step)


def candidate(parent, changes, *, step, evidence=None):
    """S': ``parent`` with the ``changes`` (``package.with_``). Raises ``PackageInvalid``."""
    return with_(parent, step=step, add=[c.procedure for c in changes if c.kind == "new"],
                 revise=[c.procedure for c in changes if c.kind == "revision"],
                 remove=[c.target for c in changes if c.kind == "deletion"],
                 narrow={c.target: c.benches for c in changes if c.kind == "narrowing"}, evidence=evidence)


def _literals(source):
    """Every string and number literal of a module, as text."""
    return [str(node.value) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and type(node.value) in (str, int, float) and str(node.value).strip()]


def _has(tokens, phrase):
    return any(tokens[i:i + len(phrase)] == list(phrase) for i in range(len(tokens) - len(phrase) + 1))


def absent_findings(text, corpus, public):
    """``leakage.findings`` restricted to content absent from ``public`` (the item's public text, FA-F12):
    {reason: True, "answer_word": [words]}."""
    tokens, known = leakage.normalize(text).split(), leakage.normalize(public).split()
    found, out = leakage.findings(text, corpus), {}
    if "shared_8gram" in found and (leakage._grams(tokens) & corpus.shared) - leakage._grams(known):
        out["shared_8gram"] = True
    if "answer_text" in found and any(_has(tokens, p) and not _has(known, p) for p in corpus.phrases):
        out["answer_text"] = True
    if "answer_number" in found and {v for v in leakage._numbers(text) if v in corpus.numbers} \
            - set(leakage._numbers(public)):
        out["answer_number"] = True
    if "option_text" in found:
        squeezed, own = "".join(tokens), "".join(known)
        if any(option in squeezed and option not in own for option in corpus.options):
            out["option_text"] = True
    words = sorted(set(found.get("answer_word", [])) - set(known))
    if words:
        out["answer_word"] = words
    return out


# ------------------------------------------------------------- C4 on SpreadsheetBench references (Codex review #2)
def _words(text):
    """The normalized words of a text (frozen ``leakage.normalize``), an ISO date-time's "T" read as a space."""
    return leakage.normalize(ISO_TIME.sub(r"\1 ", text)).split()


def _numbers(text):
    """The exact absolute values of the numbers written in ``text``, as the frozen ``leakage._numbers`` reads them
    (``leakage.NUMBER``, ``leakage.FRACTION``, ``leakage._value``) but with four-digit years kept."""
    text = unicodedata.normalize("NFKC", text)
    found = {leakage._value(match.group()) for match in leakage.NUMBER.finditer(text)}
    found |= {Fraction(int(match.group(1)), int(match.group(2))) for match in leakage.FRACTION.finditer(text)
              if int(match.group(2))}
    found.discard(None)
    return found


def _number_key(written):
    """("number", exact absolute value) of a number as written, None below LEAK_MIN_SIGNIFICANT_DIGITS significant
    digits (sign, point and leading zeros not counted, as the frozen ``leakage._significant``)."""
    try:
        digits = len(Decimal(written.replace(",", "")).as_tuple().digits)
    except InvalidOperation:
        return None
    value = leakage._value(written.lstrip("+-"))
    return ("number", value) if digits >= LEAK_MIN_SIGNIFICANT_DIGITS and value is not None else None


def sheet_key(value):
    """The comparison key of one disclosed reference cell value (``step._scalar``'s shapes), None when it is trivial
    (``SHEET_REASON``'s comment): ("number", its exact absolute value) or ("text", its normalized words)."""
    if value is None or isinstance(value, bool):
        return None
    if type(value) in (int, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return _number_key(str(int(value)) if float(value).is_integer() else repr(float(value)))
    text = str(value).strip()
    if not text or text.lower() in BOOLEANS:
        return None
    numeric = leakage._numeric(text)
    if numeric is not None:
        return _number_key(numeric)
    words = tuple(_words(MIDNIGHT.sub(r"\1", text)))
    return ("text", words) if sum(len(w) for w in words) >= LEAK_MIN_SINGLE_WORD else None


class _Seen:
    """The numbers and word runs of some texts, each text on its own (a word run never spans two texts)."""

    def __init__(self, texts=()):
        self.numbers, self.vocabulary, self.runs = set(), set(), []
        for text in texts:
            words = _words(text)
            self.runs.append(words)
            self.vocabulary.update(words)
            self.numbers |= _numbers(text)

    def extend(self, other):
        self.numbers |= other.numbers
        self.vocabulary |= other.vocabulary
        self.runs += other.runs
        return self

    def has(self, key):
        kind, value = key
        if kind == "number":
            return value in self.numbers
        return set(value) <= self.vocabulary and any(_has(run, value) for run in self.runs)


def _cell_text(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _workbook_texts(path):
    """Every cell value and formula of the public workbook at ``path`` as text, read as the sandbox's
    ``public_workbook()`` reads it (openpyxl read-only, cached values and formulas, dates and times as ISO text); []
    when it cannot be read (nothing is exempted by it)."""
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    out = []
    for data_only in (True, False):
        try:
            book = load_workbook(path, read_only=True, data_only=data_only)
        except WORKBOOK_ERRORS + (InvalidFileException,):
            return []
        try:
            for sheet in book.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    out += [_cell_text(value) for value in row if value is not None]
        except WORKBOOK_ERRORS:
            return []
        finally:
            book.close()
    return out


def _workbook(ctx, cell):
    """The ``_Seen`` of the public workbook a stored SpreadsheetBench trajectory ran on (``ctx.inputs_dirs``), read once
    per context; empty for any other cell."""
    books = ctx.sheet.setdefault("books", {})
    if cell not in books:
        directory = (ctx.inputs_dirs or {}).get(cell)
        books[cell] = _Seen(_workbook_texts(Path(directory) / "input.xlsx") if directory is not None else ())
    return books[cell]


def _shown_references(user):
    """[(cell, reference)] of the table-shape references a proposal payload carries: SpreadsheetBench's answer-cell
    values of the shown failures it kept after fitting (registrar addendum 2026-10-22 15:5x R1) and, in v2, of the
    training feedback's examples."""
    found = [(t["cell"], t["reference"]) for t in user["trajectories"] if isinstance(t.get("reference"), dict)]
    for entry in (user.get("training") or {}).get("procedures", []):
        found += [(e["cell"], e["reference"]) for e in entry.get("examples", []) if isinstance(e.get("reference"), dict)]
    return found


def _output_references(ctx, user):
    """v2.4: track fitted output examples for later C4 checks, including clipped workbook references.
    The full registered run map is checked conservatively when its excerpt was shown."""
    if not protocol.is_v24(ctx.configuration):
        return []
    return [(entry["cell"], ctx.references[entry["task_id"]])
            for entry in (user.get("training") or {}).get("unfixed_examples", [])
            if isinstance(ctx.references.get(entry["task_id"]), dict)]


def disclosed(ctx):
    """Codex review 2026-10-22 #2: {key: the value as written} of the SpreadsheetBench reference values the proposal
    payload disclosed -- exactly those ``run`` sent (``payload`` recomputed, deterministically, for a direct check) --
    that are not trivial and not public in their own item (``SHEET_REASON``'s comment), in payload order. Read once per
    context."""
    if ctx.bench == "zebralogic":
        # Grid reference cells use the ZebraLogic Corpus adapter. The workbook answer-position checker has
        # no workbook, scalar position map, or answer_values interpretation on this text benchmark.
        return {}
    if "disclosed" not in ctx.sheet:
        shown = ctx.sheet.get("shown")
        if shown is None:
            user = payload(ctx)
            shown = ctx.sheet["shown"] = _shown_references(user) + _output_references(ctx, user)
        by_cell, out = {t["cell"]: t for t in list(ctx.trajectories) + list(ctx.current) + list(ctx.evaluated)}, {}
        for cell, reference in shown:
            own = None
            for value in reference.values():
                key = sheet_key(value)
                if key is None or key in out:
                    continue
                if own is None:  # the item's instruction and request view, and its public workbook
                    view = replay.inputs_of(by_cell[cell])["request_view"]
                    own = _Seen([public_text(view)]).extend(_workbook(ctx, cell))
                if not own.has(key):
                    out[key] = str(value)
        ctx.sheet["disclosed"] = out
    return ctx.sheet["disclosed"]


def sheet_findings(ctx, text, public, cited):
    """The disclosed values (``disclosed``) written in ``text`` and absent from its own public context: ``public``
    (the text the note's item or the replay tests' items show) and, of the trajectories ``cited`` (``replay.inputs_of``
    entries), the stored pre-check reports and the public workbooks (FA-F12)."""
    values = disclosed(ctx)
    seen = _Seen([text]) if values else None
    found = [key for key in values if seen.has(key)] if values else []
    if not found:
        return []
    context = _Seen([public] + [public_text(entry["report"]) for entry in cited if entry.get("report")])
    for entry in cited:
        context.extend(_workbook(ctx, entry["cell"]))
    return [key for key in found if not context.has(key)]


def leak_check(change, ctx, outcomes, entries):
    """C4 leakage and output bans (module docstring): ``(passed, detail)``; at most one adjudication call."""
    procedure = change.procedure
    bans = replay.meta_option_faults(outcomes)
    letters = [{"cell": cell, "hook": note["hook"]} for cell, outcome in outcomes.items() if outcome.bench == "livemath"
               for note in outcome.notes if OPTION_LETTER.search(note["text"])]
    if bans or letters:
        return False, {"output_bans": (bans + letters)[:10]}
    if ctx.counterfactual:  # v2.1: the same behaviour with the meta option's text replaced by the filler
        differs = replay.meta_counterfactual(procedure, entries, outcomes, ctx.workers, inputs_dirs=ctx.inputs_dirs)
        if differs:
            return False, {"output_bans": differs[:10]}
    named = [entries[t["trajectory"]] for t in procedure.replay_tests
             if isinstance(t, dict) and type(t.get("trajectory")) is str and t["trajectory"] in entries]
    cited = "\n".join(public_text(e["request_view"] or [s["view"] for s in e["steps"]]) for e in named)
    corpora = list(ctx.corpora.values())
    # (where, text, its public text, the trajectories whose workbook and report it may quote, the corpora); the header
    # is shown above every note, so it is checked on its own too (Codex review 2026-10-22 #2)
    texts = [("description", procedure.description, cited, named, corpora)]
    texts += [("header", procedure.header, cited, named, corpora)] if procedure.header.strip() else []
    texts += [("literal", literal, cited, named, corpora) for literal in _literals(procedure.source)]
    texts += [("note:%s" % cell, note["text"], note["public"], [entries[cell]] if cell in entries else [],
               [corpus for corpus in ctx.corpora.values() if corpus.benchmark == outcome.bench])
              for cell, outcome in outcomes.items() for note in outcome.notes]
    hits, colliding, copied = [], [], []
    for where, text, public, quoted, against in texts:
        for corpus in against:
            found = absent_findings(text, corpus, public)
            if found:
                hits.append({"where": where, "bench": corpus.benchmark, "reasons": sorted(found), "text": text})
                colliding += corpus.evidence(found.get("answer_word", []))
        found = sheet_findings(ctx, text, public, quoted)
        if found:
            hits.append({"where": where, "bench": "spreadsheetbench", "reasons": [SHEET_REASON], "text": text})
            copied += found
    if not hits:
        return True, None
    flagged = "\n".join(dict.fromkeys("- " + h["text"] for h in hits))  # each flagged text once
    text = ("Procedure description: %s\nFlagged content:\n%s" % (procedure.description, flagged))[
        :MAX_ADJUDICATED_CHARS]
    if copied:  # the code tells a value written into it from one it computes on the public workbook (C3: <= 6000 B)
        text += "\nProcedure code:\n" + procedure.source
    values = disclosed(ctx)  # the matched values first, then the other disclosed ones, at most the frozen bound
    matched = set(copied)
    shown = [values[key] for key in dict.fromkeys(copied)] + [v for key, v in values.items() if key not in matched]
    shown = list(dict.fromkeys(shown))[:MAX_ADJUDICATED_VALUES]
    kept = leakage.adjudicate(ctx.roles, text, label="leak/%s/%s" % (ctx.label, procedure.id),
                              colliding=colliding[:3] or None, values=shown or None)
    detail = {"hits": [{k: h[k] for k in ("where", "bench", "reasons")} for h in hits[:10]], "adjudicated": True,
              "kept": kept, "sheet_values": len(shown)}
    if ctx.mode == TRAIN:  # v2: the fix call's detail -- the flagged texts and the adjudicator's reason
        for hit, entry in zip(hits[:10], detail["hits"]):
            entry["text"] = hit["text"][:MAX_DETAIL_CHARS]
        detail["adjudicator_reason"] = _last_reason(ctx.roles)
    return kept, detail


def _last_reason(roles):
    """v2: the leakage adjudicator's reason in the last role call's reply (at most ``MAX_DETAIL_CHARS``), else None."""
    calls = getattr(roles, "calls", None) or []
    if not calls or not isinstance(calls[-1], dict) or calls[-1].get("role") != "leak_adjudicate":
        return None
    receipts = [s["receipt"] for s in calls[-1].get("sends") or () if isinstance(s.get("receipt"), dict)]
    reply = receipts[-1].get("response") if receipts else None
    try:
        reason = parse_reply(reply).get("reason") if type(reply) is str else None
    except Invalid:
        return None
    return reason[:MAX_DETAIL_CHARS] if type(reason) is str else None


def _scope(ctx, candidate_package, procedure):
    """{cell: inputs} of the stored run trajectories on the procedure's benches (v2: and of the incumbent's current
    cells, which the shown trajectories and so the replay tests name)."""
    excluded = set(candidate_package.excluded(procedure.id))
    return _scope_entries(ctx, excluded)


def _scope_entries(ctx, excluded):
    """Shared scope construction for pre-hash reference resolution and the existing replay checks."""
    out = {}
    for trajectory in list(ctx.trajectories) + (list(ctx.current) if ctx.mode == TRAIN else []):
        if trajectory["bench"] not in excluded:
            entry = replay.inputs_of(trajectory)
            if entry is not None:
                out[entry["cell"]] = entry
    return out


def _firing(procedure, ctx):
    """v2.3 Amendment 2, C6b: at least one fault-free True predicate on the exact train routing set. The report
    carries counts and public field names only; predicate error messages and item contents never enter feedback."""
    detail = {"fires_on": 0, "items": len(ctx.routing_items), "predicate_faults": 0,
              "routing_view_keys": sorted({key for _, view in ctx.routing_items for key in view})}
    if ctx.bench == "alfworld":
        detail.update({"step_view_keys": list(ALFWORLD_STEP_VIEW_KEYS),
                       "note": "applies() receives the routing view; hooks receive the step view"})
    if not ctx.routing_items and ctx.mode == "single":
        return True, {**detail, "skipped": True, "reason": "no_training_items"}
    package = replay.solo(procedure)
    def count(view, worker):
        routed = router.route(package, ctx.bench, view, worker)
        detail["fires_on"] += procedure.id in routed.enabled
        detail["predicate_faults"] += bool(routed.faults)
        return routed
    if ctx.routing_items and ctx.routing_shared_worker and protocol.is_v28(ctx.configuration):
        for _ in replay.run_worker_pass(ctx.routing_items, lambda entry: ctx.routing_workers(package, entry[0]),
                                        lambda entry, worker: count(entry[1], worker)):
            pass
    elif ctx.routing_items and ctx.routing_shared_worker:
        with ctx.routing_workers(package, ctx.routing_items[0][0]) as worker:
            for _, view in ctx.routing_items:
                count(view, worker)
    else:
        for item, view in ctx.routing_items:
            with ctx.routing_workers(package, item) as worker:
                count(view, worker)
    return detail["fires_on"] > 0, detail


def _run_entries(ctx, *, membership=None):
    """Every verified public replay input of this step's run slice, in deterministic item/cell order."""
    out = []
    for trajectory in sorted(ctx.trajectories, key=lambda t: (t["task_id"], t["cell"])):
        verified(trajectory, "trajectory")
        found = RUN_UNIT.fullmatch(str(trajectory.get("unit", "")))
        if (trajectory["bench"] != ctx.bench or found is None or int(found["k"]) != ctx.k):
            continue
        if membership is not None:
            membership.add(trajectory["task_id"])
        entry = replay.inputs_of(trajectory)
        if entry is not None:
            out.append(entry)
    return out


def _run_views(ctx):
    """One deterministic public hook input per run item (the prompt and failure samples)."""
    out = {}
    for entry in _run_entries(ctx):
        out.setdefault(entry["item"], entry)
    return out


def hook_views(ctx):
    """v2.4 prompt sample of actual public arguments, never a solver wrapper or a private reference."""
    entries, routed = _run_views(ctx), dict(ctx.routing_items)
    if not entries:
        return {"status": "unavailable", "reason": "no_stored_run_view"}
    key = sorted(entries)[0]
    entry = entries[key]
    routing = routed.get(key, entry["view"])
    hook = entry["steps"][0]["view"] if ctx.bench == "alfworld" else entry["request_view"]
    return {"item": key, "routing_view": engineer_payload.view_excerpt(routing),
            "hook_view": engineer_payload.view_excerpt(hook),
            "string_chars": 1500, "list_entries": 20,
            "meaning": "Exact hook view arguments, truncated only at the stated caps; not the solver prompt."}


def _routing_checks(procedure, ctx, *, outcomes=None, actual=None):
    """v2.4 C6b/C6c on the same views and workers. Callable by the zero-call handoff with a Context-like object."""
    require(len(ctx.routing_items) <= 60, "C6c evaluates at most 60 registered routing items")
    firing = {"fires_on": 0, "items": len(ctx.routing_items), "predicate_faults": 0,
              "routing_view_keys": sorted({key for _, view in ctx.routing_items for key in view})}
    capture_faults = protocol.is_v291(ctx.configuration)
    if capture_faults:
        from . import fault_feedback
        firing["captures"] = []
    hook = "alf_before_step" if ctx.bench == "alfworld" else "before_call"
    run_items = set()
    run_entries = _run_entries(ctx, membership=run_items)
    entries, cells, current_views = {}, {}, {}
    for entry in run_entries:
        entries.setdefault(entry["item"], entry)
        cells.setdefault(entry["item"], []).append(entry["cell"])
    if ctx.bench == "alfworld" and ctx.mode == TRAIN:
        # C6 also replays the incumbent's current trajectories of these same run items. Keep samples anchored to
        # the original run, but allow any already-replayed current cell to demonstrate stateful note output.
        chain = str(ctx.label).split("/", 1)[0]
        for trajectory in ctx.current:
            verified(trajectory, "trajectory")
            unit = str(trajectory["unit"])
            run, train = RUN_UNIT.fullmatch(unit), TRAIN_UNIT.fullmatch(unit)
            found = run or train
            require(found is not None and found["chain"] == chain and found["bench"] == ctx.bench
                    and int(found["k"]) == ctx.k and (train is None or int(train["r"]) < ctx.round)
                    and trajectory["bench"] == ctx.bench and trajectory["task_id"] in run_items,
                    "C6c current trajectories belong to this step's verified run items and prior training rounds")
            item, cell = trajectory["task_id"], trajectory["cell"]
            current = replay.inputs_of(trajectory)
            if cell in (outcomes or {}) and current is not None:
                if cell not in cells.setdefault(item, []):
                    cells[item].append(cell)
                if current["steps"]:
                    current_views.setdefault(item, current["steps"][0]["view"])
    detail = {"hook": hook, "fired": 0, "empty": 0, "exceptions": 0, "nonempty": 0,
              "first_exception": None, "view_keys": [], "sample": None}
    if protocol.is_v294(ctx.configuration):
        detail["empty_task_ids"] = []

    def empty_item(item):
        # Only existing C6c calls that returned no screened note are sampled.
        if (protocol.is_v294(ctx.configuration) and item in entries
                and item not in detail["empty_task_ids"] and len(detail["empty_task_ids"]) < 2):
            detail["empty_task_ids"].append(item)
    applicable = hook in procedure.hooks
    if not applicable:
        detail.update(status="not_applicable", reason="no_note_writing_hook")
    if ctx.bench == "alfworld":
        firing.update(step_view_keys=list(ALFWORLD_STEP_VIEW_KEYS),
                      note="applies() receives the routing view; hooks receive the step view")
    package = replay.solo(procedure)

    def count(item, view, worker):
        capture = fault_feedback.CapturePredicate(worker) if capture_faults else worker
        routed = router.route(package, ctx.bench, view, capture)
        if capture_faults:
            firing["captures"].append(fault_feedback.predicate_capture(procedure, item, view, routed, capture))
        faults = list(routed.faults)
        firing["predicate_faults"] += bool(routed.faults)
        if procedure.id not in routed.enabled:
            return faults
        firing["fires_on"] += 1
        detail["fired"] += 1
        if not applicable:
            return faults
        if ctx.bench == "alfworld":
            entry = entries.get(item)
            step_view = entry["steps"][0]["view"] if entry is not None and entry["steps"] else current_views.get(item)
            if step_view is None:
                detail["empty"] += 1
                detail["missing_step_views"] = detail.get("missing_step_views", 0) + 1
                return faults
            view = step_view
        detail["view_keys"] = sorted(set(detail["view_keys"]) | set(view))
        if detail["sample"] is None and item in entries:
            detail["sample"] = engineer_payload.view_excerpt(view, chars=300)
        if ctx.bench == "alfworld":
            # Use all existing stateful C6 replays of this verified run item. No new step hooks or containers.
            own = [(cell, (outcomes or {}).get(cell)) for cell in cells[item]]
            own = [(cell, outcome) for cell, outcome in own if outcome is not None
                   and outcome.cell == cell and outcome.bench == ctx.bench]
            if not own:
                detail["missing_replays"] = detail.get("missing_replays", 0) + 1
            present = any(note["hook"] == hook and bool(note["text"].strip())
                          for _, outcome in own for note in outcome.notes)
            detail["nonempty" if present else "empty"] += 1
            if not present and any(outcome.applies and not outcome.faults for _, outcome in own):
                empty_item(item)
            for cell, outcome in own:
                failures = [fault for fault in outcome.faults if fault["kind"].startswith("crash:")
                            and fault["hook"] in replay.STEP_HOOKS]
                detail["exceptions"] += len(failures)
                if failures and detail["first_exception"] is None and item in entries:
                    captured = [call for call in (actual or {}).get(cell, ())
                                if call["hook"] in replay.STEP_HOOKS and call.get("status") == "raised"]
                    if captured:
                        detail["first_exception"] = {key: captured[0][key] for key in ("status", "exc_type", "message")}
            return faults
        result = worker.call(procedure.id, hook, [view, None], timeout_s=SANDBOX_TIMEOUTS["hook"])
        if result.get("ok") is not True:
            detail["exceptions"] += 1
            if detail["first_exception"] is None and item in entries:
                detail["first_exception"] = replay.bounded_result(result)
            return faults + [{"kind": result.get("fault")}]
        present = bool(replay.screened_note(procedure, ctx.bench, view, result).strip())
        detail["nonempty" if present else "empty"] += 1
        if not present:
            empty_item(item)
        return faults

    if ctx.routing_items and ctx.routing_shared_worker and protocol.is_v28(ctx.configuration):
        for _ in replay.run_worker_pass(ctx.routing_items, lambda entry: ctx.routing_workers(package, entry[0]),
                                        lambda entry, worker: count(*entry, worker), faults_of=lambda faults: faults):
            pass
    elif ctx.routing_items and ctx.routing_shared_worker:
        with ctx.routing_workers(package, ctx.routing_items[0][0]) as worker:
            for item, view in ctx.routing_items:
                count(item, view, worker)
    else:
        for item, view in ctx.routing_items:
            with ctx.routing_workers(package, item) as worker:
                count(item, view, worker)
    skipped = not ctx.routing_items and ctx.mode == "single"
    if skipped:
        firing.update(skipped=True, reason="no_training_items")
        detail.update(status="not_applicable", reason="no_training_items")
    return {"C6b": (firing["fires_on"] > 0 or skipped, firing),
            "C6c": (not applicable or detail["nonempty"] > 0 or skipped, detail)}


def check(change, ctx, taken=()):
    """The fixed checks of one change (module docstring): ``{"n", "kind", "checks": [...], "passed", "failed"}``
    with the results in executed order, stopping at the first failure."""
    report = {"n": change.n, "kind": change.kind, "checks": [], "passed": False, "failed": None}
    train = ctx.mode == TRAIN
    v24 = protocol.is_v24(ctx.configuration)
    v28 = protocol.is_v28(ctx.configuration)

    def done(check_id, passed, detail=None):
        informational = v28 and check_id in ("C5b", "C6", "C6b", "C6c", "C9")
        report["checks"].append({**_result(check_id, passed, detail),
                                **({"informational": True} if informational else {})})
        if not passed and not informational:
            report["failed"] = check_id
        return passed or informational

    benches = protocol.SUPPORTED_BENCHES if ctx.bench == "zebralogic" else BENCHES
    if v28:
        if protocol.is_v294(ctx.configuration):
            from . import inert_feedback
            inert_feedback.remember_declaration(change, change.entry)
        try:
            report["dropped_tests"] = engineer_v28.prepare(change, ctx)
        except engineer_v28.reader.Unusable as error:
            done("C1", False, {"reason": "unparseable", "detail": str(error)})
            return report
    if protocol.NORMALIZE_STRUCTURE[ctx.configuration]:
        _normalize(change, benches=benches)
    if protocol.is_v26(ctx.configuration):
        _resolve_change(change, ctx)
        if change.trajectory_resolution is not None:
            report["trajectory_resolution"] = list(change.trajectory_resolution)
    problem = _structure(change, ctx.parent, taken, train=train, benches=benches)
    if v28 and problem in ("target_edited_twice", "target_not_in_parent", "benches"):
        done("C1", True, {"system_noop": problem})
        report.update(passed=True, deferred=True)
        return report
    if not done("C1", problem is None, _structure_detail(change, problem,
                **({"configuration": ctx.configuration, "train": train} if protocol.is_v27(ctx.configuration) else {}))
                if (train or protocol.is_v27(ctx.configuration)) and problem else problem):
        return report
    if change.kind in CODED:
        violations = [v.to_json() for v in policy.check(change.source,
                                                       version=protocol.POLICY_VERSIONS[ctx.configuration])]
        banned = [v for v in violations if v["rule"] in STATIC_BANS]
        other = [v for v in violations if v["rule"] not in STATIC_BANS + ("size",)]
        if protocol.NORMALIZE_STRUCTURE[ctx.configuration] and other:
            lines = change.source.splitlines() if isinstance(change.source, str) else []
            other = [{**v, "line_text": lines[v["line"] - 1] if 0 < v["line"] <= len(lines) else "",
                      "fix_hint": "Move the call into a function, or write the literal value."} for v in other]
        if not done("C2", not other, other[:5]) or not done("C4", not banned, {"static_bans": banned[:5]}):
            return report
    try:
        single = _build(change, ctx)
    except PackageInvalid as error:
        if v28 and not any(v.rule == "size" for v in policy.check(change.source,
                version=protocol.POLICY_VERSIONS[ctx.configuration])):
            done("C3", True, {"system_deferred": str(error)[:MAX_DETAIL_CHARS]})
            report.update(passed=True, deferred=True)
            return report
        done("C3", False, _size_detail(change, error, **({"configuration": ctx.configuration} if v24 else {}))
             if train or protocol.is_v25(ctx.configuration) else str(error)[:300])
        return report
    if train:  # v2: the step's edit budget against S (``rebase``); a change beyond it gets no fix call
        try:
            rebase(single, ctx.base, ctx.parent, step=ctx.step)
        except PackageInvalid as error:
            if v28:
                report["system_budget"] = {"deferred": True, "reason": str(error)[:MAX_DETAIL_CHARS]}
            else:
                report["unfixable"] = True
                done("C3", False, {"edit_budget": str(error)[:MAX_DETAIL_CHARS], **budget(ctx)})
                return report
    done("C3", True, {"truncated": dict(change.truncated)} if change.truncated else None)
    if change.kind not in CODED:
        report["passed"] = True
        return report
    procedure = change.procedure
    with ctx.workers(replay.solo(procedure), kind="cell", hashseed=0, inputs_dir=None) as worker:
        worker.ping()
        rejected = worker.rejected.get(procedure.id)
    if not done("C5", rejected is None, rejected):
        return report
    entries = _scope(ctx, single, procedure)
    actual = {} if v24 else None
    crash, outcomes = replay.zero_crash(procedure, list(entries.values()), ctx.workers, inputs_dirs=ctx.inputs_dirs,
                                       **({"capture_faults": True} if protocol.is_v291(ctx.configuration) else {}),
                                       **({"actual": actual} if v24 else {}),
                                       **({"diagnostic_cells": _feedback_cells(ctx)}
                                          if protocol.is_v26(ctx.configuration) else {}))
    if protocol.is_v29(ctx.configuration):
        ctx.sheet.setdefault("audit_replays", {})[procedure.id] = (list(entries.values()), outcomes)
    disclosure = {"shown_cells": _feedback_cells(ctx)} if protocol.is_v25(ctx.configuration) else {}
    if disclosure:
        if not done("C5b", *replay.claimed_tests(procedure, entries, outcomes, actual, **disclosure,
                    **({"reference_feedback": True} if protocol.is_v26(ctx.configuration) else {}),
                    **({"validation_feedback": True} if protocol.is_v27(ctx.configuration) else {}))):
            return report
    else:
        if v24 and not done("C5b", *replay.claimed_tests(procedure, entries, outcomes, actual)):
            return report
    if not done("C6", crash["passed"], crash):
        return report
    if v24:
        routed = _routing_checks(procedure, ctx, outcomes=outcomes, actual=actual)
        if not done("C6b", *routed["C6b"]) or not done("C6c", *routed["C6c"]):
            return report
        if v28:
            from_replay = bool(outcomes) and all(not o.applies or any(
                f["kind"].startswith("crash:") or f["kind"] in replay.CRASH_KINDS for f in o.faults)
                for o in outcomes.values())
            from_routing = bool(ctx.routing_items) and not routed["C6b"][1]["fires_on"]
            empty_notes = bool(ctx.routing_items) and routed["C6c"][1].get("status") != "not_applicable" and not routed["C6c"][1]["nonempty"]
            effect_hooks = (("alf_before_step",) if ctx.bench == "alfworld" else
                            ("before_call", "sheet_feedback") if ctx.bench == "spreadsheetbench" else
                            ("before_call", "bindings") if ctx.bench in QA else ("before_call",))
            if protocol.is_v29(ctx.configuration) and ctx.bench == "alfworld":
                effect_hooks += ("alf_after_step",)
            no_effect = not set(effect_hooks).intersection(procedure.hooks) or ctx.bench in procedure.excluded_benches
            report["inert"] = bool((from_replay and not routed["C6c"][1]["nonempty"])
                                   or from_routing or empty_notes or no_effect)
            if protocol.is_v294(ctx.configuration) and report["inert"]:
                from . import inert_feedback
                report["inert_causes"], report["inert_evidence"] = inert_feedback.describe(
                    change, ctx, report, effect_hooks=effect_hooks, from_replay=from_replay,
                    from_routing=from_routing, outcomes=outcomes)
    elif protocol.CHECK_NON_FIRING[ctx.configuration] and not done("C6b", *_firing(procedure, ctx)):
        return report
    if not done("C4", *leak_check(change, ctx, outcomes, entries)):
        return report
    if train or v24:  # v2.4 adds claimed-test gating above; other replay tests remain advisory in both modes
        tests = replay.registrar_checks(procedure, entries, outcomes)
        if (protocol.is_alfworld_v2(ctx.configuration)
                and any(problem["reason"] == "reference_tracker" for problem in tests["problems"])):
            tests.update(replay.tracker_feedback(procedure, entries, outcomes, _feedback_cells(ctx)))
        if procedure.replay_tests:
            advice = replay.run_tests(procedure, entries, outcomes, ctx.workers, inputs_dirs=ctx.inputs_dirs)
            report["lint"] = _lint(procedure, advice, entries,
                                   **({"outcomes": outcomes, **disclosure} if disclosure else {}),
                                   **({"reference_feedback": True} if protocol.is_v26(ctx.configuration) else {}),
                                   **({"validation_feedback": True} if protocol.is_v27(ctx.configuration) else {}))
    else:
        tests = replay.run_tests(procedure, entries, outcomes, ctx.workers, inputs_dirs=ctx.inputs_dirs)
    if not done("C7", tests["passed"], tests):
        return report
    guard = replay.format_guard(outcomes)
    if v28:
        guard += [{"hook": "header", "marker": marker} for marker in replay.CHANNEL_MARKERS
                  if marker in change.entry.get("header", "").lower()]
    if not done("C8", not guard, guard[:10]):
        return report
    screen = replay.output_faults(outcomes)
    if not done("C9", not screen, screen if v28 else screen[:10]):
        return report
    if v28:
        engineer_v28.advisory_feedback(change, report,
                                       **({"configuration": ctx.configuration} if protocol.is_v291(ctx.configuration) else {}))
    report["passed"] = True
    return report


def _lint(procedure, advice, entries, *, outcomes=None, shown_cells=None, reference_feedback=False,
          validation_feedback=False):
    """v2 (Codex review 2026-10-23 #3): the advisory replay-test report the next round sees -- the tests by position
    (1-based) with their flags, the problems of ``LINT_REASONS`` by reason, position and a registered detail (an
    invalid test's ``replay.validate_test`` reason, the test count) -- never a test's id or property, which no check
    reads for leakage. v2.7 also explains malformed tests using their engineer-authored values and fixed rules,
    never stored item text."""
    tests = list(procedure.replay_tests)
    invalid = iter([n for n, test in enumerate(tests, 1) if replay.validate_test(test, procedure, entries)])
    position = {}
    for n, test in enumerate(tests, 1):
        if isinstance(test, dict) and type(test.get("id")) is str:
            position.setdefault(test["id"], n)
    problems = []
    for problem in advice["problems"]:
        reason, entry = problem["reason"], {"reason": problem["reason"]}
        if reason not in LINT_REASONS:
            continue
        if reason == "invalid_test":
            entry.update(test=next(invalid, None), detail=problem["detail"] if problem["detail"] in LINT_DETAILS else None)
            if reference_feedback and entry["detail"] == "trajectory_not_in_scope":
                entry.update(replay.valid_trajectories(entries, shown_cells or ()))
        elif reason in ("test_failed", "vacuous_test"):
            entry["test"] = position.get(problem["test"]) if type(problem["test"]) is str else None
        elif reason == "test_count":
            entry["detail"] = problem["detail"] if _count(problem["detail"]) else None
        number = entry.get("test")
        if validation_feedback and reason == "invalid_test" and type(number) is int:
            test = tests[number - 1]
            cell = test.get("trajectory") if isinstance(test, dict) else None
            entry.update(replay.test_validation_feedback(test, entry["detail"], procedure=procedure,
                         entry=entries.get(cell) if type(cell) is str else None))
        elif validation_feedback and reason == "test_count":
            entry.update(replay.test_validation_feedback(tests, "test_count"))
        if shown_cells is not None and type(number) is int and 1 <= number <= len(tests):
            test = tests[number - 1]
            if replay.validate_test(test, procedure, entries) is None:
                text = replay.rendered_note(test, entries, outcomes or {}, shown_cells)
                if text is not None:
                    entry["rendered_note"] = text
        problems.append(entry)
    return {"id": procedure.id, "problems": problems[:MAX_LINT], "tests": [
        {"test": n, "holds": bool(result["holds"]), "withheld": bool(result["withheld"]),
         "mutated": None if result["mutated"] is None else bool(result["mutated"]),
         "nonvacuous": bool(result["nonvacuous"])} for n, result in enumerate(advice["tests"], 1)]}


def _structure_detail(change, problem, *, configuration=None, train=True):
    """v2: C1's reason with what it measured, for the fix call."""
    detail, given = {"problem": problem}, sorted(str(k) for k in change.entry)
    if change.kind in CODED and problem in ("keys", "types"):
        required, allowed = _keys(change.kind, train)
        detail.update({"required": sorted(required), "allowed": sorted(allowed), "given": given,
                       "types": {k: t.__name__ for k, t in PROCEDURE_KEYS.items()}})
    elif problem == "keys":
        detail.update({"allowed": sorted({"kind", "id", *(("benches",) if change.kind == "narrowing" else ())}),
                       "given": given})
    if (configuration is not None and protocol.is_v27(configuration) and change.kind in CODED
            and "replay_tests" in change.entry and type(change.entry["replay_tests"]) is not list):
        detail["replay_test_validation"] = replay.test_validation_feedback(change.entry["replay_tests"], "test_list")
    return detail


def _size_detail(change, error, *, configuration=None):
    """v2: C3's error with the measured sizes against their caps, for the fix call."""
    detail, entry = {"error": str(error)[:MAX_DETAIL_CHARS]}, change.entry
    if change.kind in CODED:
        tests = entry.get("replay_tests")
        detail["measured"] = {"description_chars": len(str(entry.get("description", ""))),
                              "header_chars": len(str(entry.get("header", ""))),
                              "source_bytes": len((change.source or "").encode("utf-8")),
                              "max_note_chars": entry.get("max_note_chars", 0),
                              "replay_tests": len(tests) if isinstance(tests, list) else None}
        detail["caps"] = {"description_chars": MAX_DESCRIPTION_CHARS, "header_chars": MAX_HEADER_CHARS,
                          "source_bytes": MAX_PROCEDURE_BYTES, "package_source_bytes": MAX_PACKAGE_BYTES,
                          "max_note_chars": "1-4000 when a hook writes notes, else 0"}
        if configuration is not None and protocol.is_v24(configuration):
            detail["caps"]["source_bytes"] = policy.source_limit(protocol.POLICY_VERSIONS[configuration])
        if configuration is not None and protocol.is_v25(configuration):
            cap, size = detail["caps"]["source_bytes"], detail["measured"]["source_bytes"]
            if size > cap:
                detail.update(bytes_to_remove=size - cap, recommended_source_bytes=cap * 9 // 10,
                              fix_hint="Remove at least %d source bytes; aim to finish at or below 90%% of the cap "
                                       "(%d bytes)." % (size - cap, cap * 9 // 10))
        if configuration is not None and protocol.is_v27(configuration):
            feedback = replay.test_list_feedback(entry.get("replay_tests", []), hooks=entry.get("hooks", ()))
            if feedback is not None:
                detail["replay_test_validation"] = feedback
    return detail


# ------------------------------------------------------------------------------------------------------ the step
def fix(ctx, change, report):
    """The engineer's one fix of ``change`` after its first failure: the corrected ``Change``, or None when the reply
    holds no single change of the same kind and target."""
    return _fix(ctx, change, report)[0]


def _fix(ctx, change, report, *, attempt=None, why=None):
    """``(the corrected Change or None, why not)`` of one fix call. v2 (``attempt``: the change's n-th fix call of
    ``TRAIN_FIXES``) also says why the previous fix reply was not usable (``why``) and reads the reply leniently."""
    if protocol.is_v28(ctx.configuration):
        return engineer_v28.fix(ctx, change, report, attempt=attempt, why=why)
    entry = dict(change.entry, **({"source": change.source} if change.source is not None else {}))
    failed = [c for c in report["checks"] if not c["passed"]]
    last = failed[-1] if failed else None
    user = {"request": "fix", "bench": ctx.bench, "change": entry, "failed": last if ctx.echo else _redacted(last)}
    if protocol.is_v26(ctx.configuration):
        user["trajectory_resolution"] = list(change.trajectory_resolution or ())
    if protocol.is_v27(ctx.configuration):
        user["replay_test_instruction"] = FIX_TESTS_V27
    if protocol.is_v24(ctx.configuration):
        user["hook_views"] = hook_views(ctx)
    if attempt is not None:
        user.update({"attempt": attempt, "attempts": TRAIN_FIXES, **({"previous_reply": why} if why else {})})
    reply, call = _ask(ctx, user, "fix/%d" % change.n if attempt is None else "fix/%d/%d" % (change.n, attempt))
    if reply is None and call is None:
        return None, "no_calls_left"
    normalizations = []
    try:
        entries, sources = parse(reply, lenient=attempt is not None,
            **({"fix_change": change, "parent_ids": ctx.parent.order, "normalizations": normalizations,
                "diagnostics": True} if protocol.is_v27(ctx.configuration) else {}))
    except Unparseable as error:
        reason = "unparseable: %s" % error
        return None, reason[:MAX_FIX_PARSE_CHARS] if protocol.is_v27(ctx.configuration) else reason
    if len(entries) != 1:
        return None, "changes: %d, expected exactly the one change" % len(entries)
    fixed = changes_of(entries, sources, call)[0]
    key = TARGET_KEYS.get(change.kind) if type(change.kind) is str else None  # v2.1: a model-written kind
    if fixed.kind != change.kind or (key is not None and fixed.entry.get(key) != change.entry.get(key)):
        return None, "another kind or target than the change to fix"
    fixed.n = change.n
    if protocol.NORMALIZE_STRUCTURE[ctx.configuration]:
        fixed.normalized = list(change.normalized)
    if protocol.is_v27(ctx.configuration):
        fixed.normalized.extend(normalizations)
    if protocol.is_v26(ctx.configuration):
        _normalize(fixed, benches=protocol.SUPPORTED_BENCHES if ctx.bench == "zebralogic" else BENCHES)
        _resolve_change(fixed, ctx)
        fixed.trajectory_resolution = ((change.trajectory_resolution or []) + (fixed.trajectory_resolution or []))[
            :MAX_TESTS * (TRAIN_FIXES + 1)]
    return fixed, None


def _redacted(result):
    """v2.1 (``Context.echo`` False): a failed check's result as a fix call shows it. C4: the static bans' rules and
    lines; the output bans' cells, hooks, steps and kinds (a letter ban ``option_letter``) with a counterfactual
    difference's aspects and ``COUNTERFACTUAL_RULE``; the leakage hits' places, benches and reason codes and the
    adjudication's outcome -- never a flagged text, a matched term, a ban's detail or the adjudicator's reason. C9:
    each fault's cell, hook, step and kind. Every other result as recorded."""
    if result is None or result["passed"] or result["check"] not in ("C4", "C9") or result["detail"] is None:
        return result
    detail = result["detail"]
    if result["check"] == "C9":
        return {**result, "detail": [{k: f[k] for k in ("cell", "hook", "step", "kind") if k in f} for f in detail]}
    if "static_bans" in detail:
        shown = {"static_bans": [{"rule": v["rule"], "line": v["line"]} for v in detail["static_bans"]]}
    elif "output_bans" in detail:
        bans = [{**{k: b[k] for k in ("cell", "hook", "step", "aspects") if k in b},
                 "kind": b.get("kind", "option_letter")} for b in detail["output_bans"]]
        shown = {"output_bans": bans}
        if any(b["kind"] == replay.COUNTERFACTUAL for b in bans):
            shown["rule"] = COUNTERFACTUAL_RULE
    else:
        shown = {**{k: v for k, v in detail.items() if k not in ("hits", "adjudicator_reason")},
                 "hits": [{k: h[k] for k in ("where", "bench", "reasons")} for h in detail["hits"]]}
    return {**result, "detail": shown}


def _combined(parent, survivors, step):
    """S' from the surviving changes, dropping from the last any whose combination breaks the package."""
    survivors = list(survivors)
    while survivors:
        try:
            return candidate(parent, survivors, step=step), survivors
        except PackageInvalid:
            survivors.pop()
    return None, []


def run(ctx):
    """The engineer's step: ``(candidate package or None, the sealed engineer record)``."""
    if protocol.is_v28(ctx.configuration):
        return engineer_v28.run(ctx)
    user, proposals, changes = payload(ctx), [], []
    ctx.sheet["shown"] = _shown_references(user) + _output_references(ctx, user)
    ctx.sheet.pop("disclosed", None)
    for purpose in ("propose", "repropose"):
        reply, call = _ask(ctx, user, purpose)
        try:
            entries, sources = parse(reply)
        except Unparseable as error:
            proposals.append({"call": call, "parsed": False, "reason": str(error)})
            user = {**user, "unparseable": str(error)}  # the second call says why the first reply was not read
            continue
        proposals.append({"call": call, "parsed": True, "changes": len(entries)})
        changes = changes_of(entries, sources, call)
        break
    survivors, outcomes, taken = [], [], set()
    for change in changes:
        attempts = [check(change, ctx, taken)]
        final = change
        if not attempts[0]["passed"]:
            fixed = fix(ctx, change, attempts[0])
            if fixed is not None:
                attempts.append(check(fixed, ctx, taken))
                final = fixed
        survived = attempts[-1]["passed"]
        if survived:
            survivors.append(final)
            taken.add(final.target)
        outcomes.append({**final.to_json(), "attempts": attempts, "survived": survived})
    package, kept = _combined(ctx.parent, survivors, ctx.step)
    modern = protocol.NORMALIZE_STRUCTURE[ctx.configuration]
    sealed = record(protocol.ENGINEER_RECORDS[ctx.configuration], ctx.evidence, {
        "bench": ctx.bench, "k": ctx.k, "step": ctx.step, "label": ctx.label, "parent_sha256": ctx.parent.sha256,
        "prompt_sha256": (ENGINEER_PROMPT_SINGLE_ALF_V2_SHA256 if protocol.is_alfworld_v2(ctx.configuration) else
                          ENGINEER_PROMPT_SINGLE_ALF_V1_SHA256 if protocol.is_alfworld(ctx.configuration) else
                          ENGINEER_PROMPT_SINGLE_ZPC_V27_SHA256 if protocol.is_v27(ctx.configuration) else
                          ENGINEER_PROMPT_SINGLE_ZPC_V26_SHA256 if protocol.is_v26(ctx.configuration) else
                          (ENGINEER_PROMPT_SINGLE_ZPC_V25_SHA256 if ctx.bench == "zebralogic" else
                           ENGINEER_PROMPT_SINGLE_V25_SHA256) if protocol.is_v25(ctx.configuration) else
                          (ENGINEER_PROMPT_SINGLE_ZPC_V24_SHA256 if ctx.bench == "zebralogic" else
                           ENGINEER_PROMPT_SINGLE_V24_SHA256) if protocol.is_v24(ctx.configuration) else
                          ENGINEER_PROMPT_SINGLE_ZPC_SHA256 if ctx.configuration == protocol.ZEBRA_PC_V1 else
                          ENGINEER_PROMPT_SINGLE_V23_SHA256 if modern else ENGINEER_PROMPT_SHA256),
        "proposals": proposals, "changes": outcomes,
        "kept": [c.n for c in kept], "candidate_sha256": package.sha256 if package else None,
        "procedures": [p.to_json() for p in package.procedures] if package else [],
        "calls": ctx.roles.count("engineer/%s/" % ctx.label), "earlier_calls": ctx.spent,
        **({"payload_trimming": user["payload_trimming"]} if "payload_trimming" in user else {})})
    return package, sealed


# --------------------------------------------------------------------------------------------- v2: a training round
def rebase(package, base, incumbent, *, step):
    """v2: ``package`` -- a candidate built from the round's ``incumbent`` (``candidate``), the incumbent being the
    step's parent ``base`` S or one candidate of it -- re-expressed as one candidate of S: the same procedures, order,
    scopes and describer entries; its parent S; a procedure this round wrote that revises one an earlier round of the
    step wrote is re-linked to S (it revises what that one revises, else it is new); the procedures of S it no longer
    holds are retired. Raises ``PackageInvalid`` when it differs from S by more than ``MAX_CHANGES`` edits
    (``package.validate``)."""
    own, earlier, procedures = set(base.order), set(incumbent.order), []
    for procedure in package.procedures:
        revises = procedure.lineage["revises"]
        if procedure.id in own or procedure.id in earlier or revises is None or revises in own:
            procedures.append(procedure)
            continue
        was = incumbent.get(revises).lineage  # an earlier round's procedure, already relative to S
        procedures.append(replace(procedure, lineage={"parent": was["parent"], "revises": was["revises"],
                                                      "engineer_call": procedure.lineage["engineer_call"]}))
    kept = {p.id for p in procedures}
    rebased = Package(tuple(procedures), step, package.evidence, base.sha256,
                      tuple(base.retired) + tuple(p.sha256 for p in base.procedures if p.id not in kept),
                      package.narrowed, package.describer)
    validate(rebased, base)
    return rebased


def _combined_train(ctx, survivors):
    """v2: the round's candidate -- the surviving changes applied to the incumbent, ``rebase``d on S -- dropping from
    the last any whose combination breaks the package or the step's edit budget."""
    survivors = list(survivors)
    while survivors:
        try:
            return rebase(candidate(ctx.parent, survivors, step=ctx.step), ctx.base, ctx.parent,
                          step=ctx.step), survivors
        except PackageInvalid:
            survivors.pop()
    return None, []


def run_train(ctx):
    """v2's engineer unit of one training round (module docstring): ``(the round's candidate -- one candidate of the
    step's parent S -- or None, the sealed engineer record)``. As ``run`` with up to ``TRAIN_FIXES`` fix calls per
    failing change (none for a change beyond the edit budget) and the record's v2 fields: ``mode``, ``round``,
    ``base_sha256``, ``budget`` (before the round), ``lint`` (the advisory replay-test reports of the final versions),
    each change's ``fix_calls`` and ``fix_replies`` (why a fix reply was not usable; None for a usable one) and the
    surviving changes the budget dropped (``dropped``)."""
    require(ctx.mode == TRAIN, "The engineer unit of a training round")
    if protocol.is_v28(ctx.configuration):
        return engineer_v28.run(ctx)
    findings, analysed_refs, analysis = analyse(ctx)
    user, proposals, changes = payload(ctx, findings), [], []
    # C4 checks exactly the references this (fitted) payload discloses (#2), those the analysts saw, whose findings it
    # shows, and those earlier rounds of the step disclosed (Codex review 2026-10-23 #3)
    ctx.sheet["shown"] = _shown_references(user) + analysed_refs + _earlier_references(ctx) + _output_references(ctx, user)
    ctx.sheet.pop("disclosed", None)
    for purpose in ("propose", "repropose"):
        reply, call = _ask(ctx, user, purpose)
        try:
            entries, sources = parse(reply, lenient=True)
        except Unparseable as error:
            proposals.append({"call": call, "parsed": False, "reason": str(error)})
            user = {**user, "unparseable": str(error)}  # the second call says why the first reply was not read
            continue
        proposals.append({"call": call, "parsed": True, "changes": len(entries)})
        changes = changes_of(entries, sources, call)
        break
    survivors, outcomes, taken, lint = [], [], set(), []
    for change in changes:
        attempts, final, replies = [check(change, ctx, taken)], change, []
        while not attempts[-1]["passed"] and not attempts[-1].get("unfixable") and len(replies) < TRAIN_FIXES:
            fixed, why = _fix(ctx, final, attempts[-1], attempt=len(replies) + 1, why=replies[-1] if replies else None)
            replies.append(why)
            if why == "no_calls_left":
                break
            if fixed is not None:
                final = fixed
                attempts.append(check(fixed, ctx, taken))
        survived = attempts[-1]["passed"]
        if survived:
            survivors.append(final)
            taken.add(final.target)
        if attempts[-1].get("lint"):
            lint.append(attempts[-1]["lint"])
        outcomes.append({**final.to_json(), "attempts": attempts, "survived": survived, "fix_calls": len(replies),
                         "fix_replies": replies, "summary": _summary(final)})
    package, kept = _combined_train(ctx, survivors)
    modern = protocol.NORMALIZE_STRUCTURE[ctx.configuration]
    sealed = record(protocol.ENGINEER_RECORDS[ctx.configuration], ctx.evidence, {
        "bench": ctx.bench, "k": ctx.k, "step": ctx.step, "label": ctx.label, "parent_sha256": ctx.parent.sha256,
        "prompt_sha256": (ENGINEER_PROMPT_ALF_V2_SHA256 if protocol.is_alfworld_v2(ctx.configuration) else
                          ENGINEER_PROMPT_ALF_V1_SHA256 if protocol.is_alfworld(ctx.configuration) else
                          ENGINEER_PROMPT_ZPC_V27_SHA256 if protocol.is_v27(ctx.configuration) else
                          ENGINEER_PROMPT_ZPC_V26_SHA256 if protocol.is_v26(ctx.configuration) else
                          (ENGINEER_PROMPT_ZPC_V25_SHA256 if ctx.bench == "zebralogic" else ENGINEER_PROMPT_V25_SHA256)
                          if protocol.is_v25(ctx.configuration) else
                          (ENGINEER_PROMPT_ZPC_V24_SHA256 if ctx.bench == "zebralogic" else ENGINEER_PROMPT_V24_SHA256)
                          if protocol.is_v24(ctx.configuration) else
                          ENGINEER_PROMPT_ZPC_SHA256 if ctx.configuration == protocol.ZEBRA_PC_V1 else
                          ENGINEER_PROMPT_V23_SHA256 if modern else ENGINEER_PROMPT_V2_SHA256),
        "proposals": proposals, "changes": outcomes,
        "kept": [c.n for c in kept], "dropped": [c.n for c in survivors[len(kept):]],
        "candidate_sha256": package.sha256 if package else None,
        "procedures": [p.to_json() for p in package.procedures] if package else [],
        "calls": ctx.roles.count("engineer/%s/" % ctx.label), "earlier_calls": ctx.spent, "mode": TRAIN,
        "round": ctx.round, "base_sha256": ctx.base.sha256, "budget": budget(ctx), "lint": lint,
        "analysis": analysis, "analyst_prompt_sha256": ANALYST_PROMPT_SHA256, "disclosed": _disclosed_items(ctx),
        **({"payload_trimming": user["payload_trimming"]} if "payload_trimming" in user else {})})
    return package, sealed


def _earlier_references(ctx):
    """v2 (Codex review 2026-10-23 #3): [(cell, reference)] of the table-shape references earlier rounds of the step
    disclosed (``Context.disclosed``), each at a cell of its item in the step's run unit (whose public text and
    workbook ``disclosed`` reads)."""
    cells = {}
    for trajectory in ctx.trajectories:
        if trajectory["bench"] == ctx.bench and int(RUN_UNIT.fullmatch(trajectory["unit"])["k"]) == ctx.k:
            cells.setdefault(trajectory["task_id"], trajectory["cell"])
    return [(cells[item], ctx.references[item]) for item in sorted(ctx.disclosed)]


def _disclosed_items(ctx):
    """v2: the run-slice items whose table-shape reference C4 counted in this round -- this round's and the earlier
    rounds' (``Context.disclosed`` of the next round)."""
    tasks = {t["cell"]: t["task_id"] for t in list(ctx.trajectories) + list(ctx.current) + list(ctx.evaluated)}
    return sorted({tasks[cell] for cell, _ in ctx.sheet.get("shown") or ()})


def _summary(change):
    """v2's step buffer: the change's description, at most ``TRAIN_PROPOSAL_CHARS`` characters ("" without one)."""
    description = change.entry.get("description") if isinstance(change.entry, dict) else None
    return description[:TRAIN_PROPOSAL_CHARS] if type(description) is str else ""
