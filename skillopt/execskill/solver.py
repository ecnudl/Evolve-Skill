"""The route-B shell: the frozen solvers copied with the procedure hooks (protocol ``fivebench-execskill-v1``;
registration §2.1-§2.5, §4.4 P1/P2/P4/P5, §6.1, §6.5, §8.1; implementation plan §1 solver.py row, §3; T-SOLVER-1..9).

``solve`` is a copy of ``continual_eval/backends.solve`` (backends.py:364-455) and ``_solve_alfworld`` (:715-783) for
the five benches, with the hooks of plan §3. With a package that holds no procedure for the bench it sends the frozen
requests byte for byte and returns the frozen prediction plus one key, ``shell`` (T-SOLVER-1); on ALFWorld this holds
for episodes whose every reply is exactly an admissible command (``how == tag_exact``), because the level-1
canonicaliser executes the canonical command where the frozen loop executes the raw text (plan §3).

What the shell adds, and nothing else (no interface edits the system prompt, the format sentence or a delivered reply):
- routing (``router.route``) once per item -- on ALFWorld on the registered pre-reset view, whose sha256 is asserted
  against the items file and the live reset view -- and the enable log in ``shell.route``;
- typed notes of the enabled procedures, screened and rendered by ``notes`` under the fixed headers, as the LAST key
  ``procedure_notes`` of the user JSON (absent when empty; at most 4,000 characters, ALFWorld 1,500 per step); a
  procedure's table cells and binding quotes found verbatim in the item's public text are not screened (registrar
  decision 2026-10-22, ticket A3-1), a sham's content is screened whole;
- QA: the ``<calc>`` round trip (§2.4): when the invitation was shown and the first reply is delivered, untruncated and
  carries ``<calc>`` tags, ONE second call whose user JSON is the first one plus ``first_reply``, ``computed`` and
  ``instruction`` (``COMPUTE_FOLLOWUP``); the second reply is final when delivered and untruncated, else the first
  (``second_call_fallback``);
- SpreadsheetBench: the pre-check of the extracted program on the public input (``precheck``, its container named
  with the worker's unit tag; a stored report is read back on replay), ``sheet_feedback`` and at most ONE repair call
  whose user JSON is the first one plus
  ``previous_program``, ``repair_instruction`` (``REPAIR_FRAME``), ``run_report`` and ``repair_notes`` (when any); the
  repaired program is used when delivered and extractable, else the original (§2.5). The ``spreadsheet-native``
  slot is held around each container run only, never across a model call;
- SpreadsheetBench's no-workbook mode (``shortcut="no_workbook"``; registration §7.2 shortcut gate, §9.2 shortcut
  probe; registrar decision 2026-10-22 row C1-2): the frozen request view without ``workbook_preview``, so neither the
  preview nor any other sheet content reaches the model, while the program is still pre-checked and executed on the
  real input files. Only a package without a procedure for SpreadsheetBench runs it (the probe is the card arm's):
  procedure hooks read the mounted workbook and the pre-check report. The shell record carries ``shortcut``;
- ALFWorld: ``alf_before_step`` notes and the discouraged commands (``NOT_RECOMMENDED_PREFIX``; the shown admissible
  list is unchanged), the level-1 canonical action (``canonical``), ``alf_after_step`` with the state kept by the host;
  every stop of ``errors.STOP_KINDS`` is re-raised before the frozen catch-all (backends.py:774-776).

Faults (§2.3, §4.4): a predicate fault leaves the procedure disabled (P2); a hook fault -- a failed sandbox call, a
value of the wrong shape, a dropped note field or binding, a repeated binding name, a note over its declared cap, a
state over its declared bytes, an undeclared repair request -- drops the procedure for the rest of the cell or episode
(P1).
Both are logged in ``shell.faults``; neither pauses. ``SandboxUnavailable``, ``CleanupUnconfirmed`` and the other stops
propagate. Stops raised by the call function itself become frozen reasons in ``_response`` (``model_call_exception:``)
and are recorded per call in ``shell.calls[i].reason``, where ``outcomes_ext`` finds them.

Arms (one per call of ``solve``): ``withhold`` (a withholding twin: the predicate still runs, ``shadow_fired``),
``restore`` (a restoration twin: the restored procedures are marked; the package is ``package.restore``'s), ``placebo``
(the sealed donor content of registration §6.1: same predicates and slots, sham content; every computation ``not
evaluated``; the repair trigger is the shammed procedure's own ``sheet_feedback`` run as a shadow on this arm's run
report, its content never shown; the ALFWorld discouragement drawn at dispatch by ``sham_discouraged``) and ``text``
(T_F, registration §8.1 table: the frozen description in the procedure's slot where the procedure has output on the
item -- decided for ``before_call``/``bindings`` by its hook run as a shadow, nothing of it shown; ``bindings``: the
description and the invitation, no names or values; ``sheet_feedback``: the description, the shell's own error message
and one repair call when the program fails on the public input; ALFWorld: the description every step, no discouraged
list, no state).

The worker is the caller's unstarted ``sandbox.client.Worker`` (None only when the package holds no procedure for the
bench): ``solve`` starts it for the package (kind ``cell``, or ``episode`` on ALFWorld, where it is pinged at once so
every arm takes the same slot path, §6.2; SpreadsheetBench mounts the public workbook read-only as /input/input.xlsx)
and closes it at the end.

Prediction = the frozen shape + ``shell``, a sealed ``fivebench-execskill-v1-shell`` record: {route, calls [{purpose,
request_sha256, receipt_index, reason}], procedure_events, faults, notes, notes_chars, compute, precheck, fallback,
deciding_receipt, worst_delivery, arm, sandbox, alfworld_steps (ALFWorld)}. ``sandbox`` (ticket C5-4; safety review 3,
5): the worker's ``restarts`` (containers replaced without dropping a procedure) and ``cleanups`` (confirmed removals
with their latency), taken after the worker closed, so the last removal is in it; None without a worker.
``deciding_receipt`` indexes the logical receipts the
call function returned (one per call that returned): the one whose reply the prediction carries. Every ALFWorld
prediction carries ``alfworld_steps``, empty when the episode ended before its first step (the judge's J4 share reads
it, ticket A7-1).
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tempfile
import zipfile
from contextlib import nullcontext
from pathlib import Path

from skillopt.coevo5.calls import _request_hash
from skillopt.continual_eval import backends
from skillopt.continual_eval.backends import (ALFWORLD_TRACE_VERSION, ANSWER_TAG_BENCHMARKS, CODE_EXTRACTION_VERSION,
                                              CONTRACT_FIRST_LAYOUT_V2, CONTRACT_FIRST_LAYOUTS, LIVEMATH_CONTRACT,
                                              SHEET_CONTRACT_V2, SHEET_PREVIEW_VERSION, _alf_post_observation, _code,
                                              _completed_without_text, _layout_supported, _prediction_unknown,
                                              _public_view as _legacy_public_view, _response, _sheet_preview, _unknown, _xlsx_bytes)
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import compute, donors, notes, profiles, router, zebralogic
from .code_delivery import VERSION as CODE_EXTRACTION_V23
from . import precheck as prechecks
from .canonical import canonical
from .errors import STOP_KINDS, CleanupUnconfirmed, ConfigurationError
from .outcomes_ext import worst_delivery
from .package import Package
from .profiles import (SUPPORTED_BENCHES as BENCHES, COMPUTE_FOLLOWUP, COMPUTE_INVITE, NOT_EVALUATED, NOT_RECOMMENDED_PREFIX, NOTES_KEY, QA,
                       REPAIR_FRAME, SANDBOX_TIMEOUTS, TRUNCATION_MARGIN, record)
from .supply import routing_view as alfworld_routing_view

STOPS = tuple(STOP_KINDS)  # the one exception set plus the route-B stops (errors.py)
FALLBACK = "second_call_fallback"
QA_SYSTEM = "Solve the supplied task using only the supplied public information."  # backends.py:379
ALF_SYSTEM = "Act in the text environment. Return a single action inside <action>...</action>."  # backends.py:731
GUIDANCE = "Frozen skill guidance (use only where applicable):\n"
MAX_ACTION_CHARS = 1000  # backends.py:754
OBSERVATION_CHARS = 12000  # backends.py:756
PROGRAM_ERRORS = ("exception", "missing_output")  # T_F's repair trigger: the program fails on the public input
REPORT_KEYS = ("status", "exc_type", "message", "answer_cells")  # what a sheet_feedback hook sees of the pre-check
SHOWN_REPORT_KEYS = ("status", "exc_type", "message")  # the shell's own error message (§2.5)
REPAIR_KEY = "repair_instruction"  # the sheet view already has an "instruction" key: the task's own
UNCLOSED_TAGS = ("answer", "action", "calc")
NOTE_HOOKS = ("before_call", "bindings")
NO_WORKBOOK = "no_workbook"  # SpreadsheetBench's shortcut-probe mode (registration §7.2; ticket C1-2)


def _unclosed(text):
    """An unclosed answer, action or calc tag, or an odd number of code fences (§4.1's margin truncation rule)."""
    lowered = text.lower()
    return text.count("```") % 2 == 1 or any(lowered.count("<%s>" % t) > lowered.count("</%s>" % t)
                                             for t in UNCLOSED_TAGS)


def sham_discouraged(admissible, count, seed, step):
    """The ALFWorld discouragement sham of a placebo arm (§6.1), drawn at dispatch: the ``count`` admissible commands
    first in the sha256 order of (seed, step, command) -- the way ``data.ranked`` orders items -- in admissible order.
    ``seed``: the cell's registered tag ``protocol.discourage_tag(unit, cell)``."""
    require(type(count) is int and count >= 0 and type(seed) is str and type(step) is int, "Invalid sham draw")
    unique = list(dict.fromkeys(admissible))
    keyed = sorted(unique, key=lambda c: hashlib.sha256(json.dumps([seed, step, c]).encode()).hexdigest())
    chosen = set(keyed[:count])
    return [c for c in unique if c in chosen]


def _public_text(value):
    """Every text of a public view, joined (the verbatim reference of a binding's value and quote)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_public_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(_public_text(v) for v in value)
    return "" if value is None else str(value)


def _system(bench, card_text, runtime):
    """The frozen system prompt (backends.py:379-394) with the active bench card as the skill text."""
    if bench == zebralogic.BENCH:
        return QA_SYSTEM  # the official format and examples live only in the USER message
    guidance = ("\n\n" + GUIDANCE + card_text) if card_text.strip() else ""
    if bench in {"searchqa", "officeqa"}:
        contract = "\nReturn the concise final answer inside <answer>...</answer>."
    elif bench == "livemath":
        contract = LIVEMATH_CONTRACT
    elif bench == "spreadsheetbench" and runtime.get("prompt_layout") == CONTRACT_FIRST_LAYOUT_V2:
        contract = SHEET_CONTRACT_V2
    elif bench in {"spreadsheetbench", "alfworld"}:
        contract = "\nReturn one complete Python program in a ```python code block."
    else:
        raise ValueError("Unknown text-solver benchmark")
    if runtime.get("prompt_layout") in CONTRACT_FIRST_LAYOUTS:
        return QA_SYSTEM + contract + guidance
    return QA_SYSTEM + guidance + contract  # the historical order



def _user(bench, view, text=""):
    """Exact benchmark USER transport; hooks always receive the separate public view."""
    if bench == zebralogic.BENCH:
        return zebralogic.render_user(view, text)
    request = dict(view)
    if text:
        request[NOTES_KEY] = text
    return json.dumps(request, ensure_ascii=False)


def _sheet_view(view, runtime, *, shortcut=None):
    """The frozen SpreadsheetBench request view (backends.py:403-409); in the no-workbook mode (registration §7.2,
    ticket C1-2) the same keys in the same order without ``workbook_preview``: the workbook is not even opened."""
    shown = {"instruction": view["instruction"]}
    if shortcut != NO_WORKBOOK:
        shown["workbook_preview"] = _sheet_preview(view["input_files"][0],
                                                   version=runtime.get("spreadsheet_preview_version"))
    shown.update({"input_path": "input.xlsx", "required_output_path": "output.xlsx",
                  "required_answer_position": view["answer_position"]})
    return shown


def _registered_view(public):
    """The ALFWorld item's registered routing view (``routing_view`` / ``routing_view_sha256`` of the items file, as
    ``supply.prereset`` writes them), None when the item carries none; ConfigurationError when its hash is wrong."""
    view = public.get("routing_view")
    if view is None:
        return None
    if not isinstance(view, dict) or digest(view) != public.get("routing_view_sha256"):
        raise ConfigurationError("alfworld_routing_view_hash_mismatch: the items file's view")
    return view


def _public_view(bench, public):
    """Versioned public adapter; frozen backend admission remains unchanged."""
    return zebralogic.public_view(public) if bench == zebralogic.BENCH else _legacy_public_view(bench, public)


def routing_view(bench, public, *, runtime=None):
    """The view an item is routed on (§2.3; the router's ``views``), from public data only: the frozen public view on
    QA, the frozen request view on SpreadsheetBench, the registered pre-reset view on ALFWorld."""
    runtime = runtime or {}
    view = _public_view(bench, public)
    if bench == "spreadsheetbench":
        require(view["input_files"], "A SpreadsheetBench item has a public workbook")
        return _sheet_view(view, runtime)
    if bench == "alfworld":
        registered = _registered_view(public)
        require(registered is not None, "An ALFWorld item carries its registered routing view")
        return registered
    return view


def _extract(response, extraction, *, multiple="refuse"):
    """``(program or None, delivery)``: the frozen extraction (backends.py:427-436)."""
    if extraction == CODE_EXTRACTION_V23:
        from .code_delivery import extract_python

        extracted = extract_python(response, multiple=multiple)
        delivery = {"code_delivery": {key: value for key, value in extracted.items() if key != "code"}}
        return (extracted["code"] if extracted["status"] == "available" else None), delivery
    if extraction == CODE_EXTRACTION_VERSION:
        from skillopt.continual_eval.code_delivery import extract_python

        extracted = extract_python(response)
        delivery = {"code_delivery": {key: value for key, value in extracted.items() if key != "code"}}
        return (extracted["code"] if extracted["status"] == "available" else None), delivery
    return _code(response), {}


def _two_calls(first, second, second_decides):
    """The costs of a cell with a second call: the frozen keys for the deciding call plus both calls' usage."""
    return {"calls": first.get("calls", 0) + second.get("calls", 0),
            "usage": (second if second_decides else first).get("usage", {}),
            "usage_by_call": [first.get("usage", {}), second.get("usage", {})]}


class _Shell:
    """One cell's (or episode's) hooks, calls and logs."""

    def __init__(self, bench, package, call, worker, *, withhold, restore, placebo, text, native, nominal,
                 shortcut=None, configuration=None):
        require(bench in BENCHES and isinstance(package, Package), "A known bench and a package")
        require(shortcut is None or (shortcut == NO_WORKBOOK and bench == "spreadsheetbench"),
                "The one shortcut mode is SpreadsheetBench's no-workbook probe (registration §7.2)")
        require(shortcut is None or not package.for_bench(bench),
                "The no-workbook probe is the card arm's: no procedure may run on its item (registration §7.2, §9.2)")
        require(placebo is None or text is None, "One arm: a placebo or a text twin, not both")
        if placebo is not None:
            require(isinstance(placebo, dict) and set(placebo) == {"procedures", "seed"}
                    and type(placebo["seed"]) is str and isinstance(placebo["procedures"], dict)
                    and set(placebo["procedures"]) <= set(package.order)
                    and all(isinstance(v, dict) for v in placebo["procedures"].values()),
                    "A placebo is {procedures: {id: sham content}, seed} over the package's procedures")
        require(text is None or (isinstance(text, dict) and set(text) <= set(package.order)
                                 and all(type(v) is str and v for v in text.values())),
                "A text twin maps procedures of the package to their frozen descriptions")
        require(native is None or hasattr(native, "hold"), "The native slot pool has hold()")
        require(nominal is None or (type(nominal) is int and nominal > TRUNCATION_MARGIN), "Invalid nominal M")
        if package.for_bench(bench) and worker is None:
            raise ConfigurationError("execskill_worker_missing: a package with procedures for %s runs in the sandbox"
                                     % bench)
        self.bench, self.package, self.worker, self._call = bench, package, worker, call
        self.withhold, self.restore = frozenset(withhold), frozenset(restore)
        self.placebo, self.text, self.native, self.nominal = placebo, dict(text or {}), native, nominal
        self.shortcut = shortcut
        self.configuration = configuration
        self.effects = []
        self.shams = frozenset(placebo["procedures"]) if placebo else frozenset()
        self.receipts, self.calls, self.events, self.faults, self.notes = [], [], [], [], []
        self.dropped, self.route, self.started = set(), None, False
        self.compute = self.precheck = self.fallback = self.deciding = None
        self.steps = [] if bench == "alfworld" else None
        self.notes_chars = 0

    # ------------------------------------------------------------------------------------------- sandbox and route
    def start(self, sandbox_kind, inputs_dir=None):
        if self.worker is not None:
            self.worker.start(self.package, kind=sandbox_kind, inputs_dir=inputs_dir)
            self.started = True

    def close(self):
        if self.worker is not None:
            self.worker.close()

    def route_on(self, view):
        self.route = router.route(self.package, self.bench, view, self.worker if self.started else None,
                                  withhold=self.withhold, restore=self.restore)
        self.faults.extend(dict(f) for f in self.route.faults)

    def enabled(self, hooks):
        """The enabled, not dropped procedures declaring one of ``hooks``, in package order."""
        on = set(self.route.enabled) if self.route is not None else set()
        return [p for p in self.package.procedures
                if p.id in on and p.id not in self.dropped and any(h in p.hooks for h in hooks)]

    def fault(self, procedure_id, hook, fault_kind, exc_type=None, message=None):
        """P1: logged, and the procedure is dropped for the rest of the cell or episode."""
        self.faults.append({"procedure": procedure_id, "hook": hook, "kind": fault_kind, "exc_type": exc_type,
                            "message": None if message is None else str(message)[:500]})
        self.dropped.add(procedure_id)

    def hook(self, procedure, fn, args):
        """``(ok, value)`` of one hook call in the sandbox; a failed call is a fault of the procedure."""
        args = list(args)
        result = self.worker.call(procedure.id, fn, args, timeout_s=SANDBOX_TIMEOUTS["hook"])
        ok = result.get("ok") is True
        self.events.append({"id": procedure.id, "fn": fn, "args_sha256": digest(args),
                            "value_sha256": result.get("value_sha256") if ok else None,
                            "fault": None if ok else result.get("fault"), "cpu_ms": result.get("cpu_ms")})
        if not ok:
            self.fault(procedure.id, fn, result.get("fault"), result.get("exc_type"), result.get("message"))
            return False, None
        return True, result["value"]

    def shaped(self, procedure, fn, value, extra=None):
        """A hook's value as ``(fields, extra value)``: ``before_call``/``bindings`` return the typed fields (None: no
        output); ``sheet_feedback`` {fields, request_repair: bool}; ``alf_before_step`` {fields, discourage: [command]}.
        None, and a fault, for any other shape."""
        found = donors.shaped(value, extra)
        if found is not None:
            return found
        self.fault(procedure.id, fn, "output_shape", None, type(value).__name__)
        return None

    # --------------------------------------------------------------------------------------------------- notes
    def render(self, procedure, hook, fields, *, public_text):
        """``(text, bindings)``: one procedure's screened note (§2.2) and the bindings it shows. With ``public_text``
        every binding must quote it verbatim (§2.4 item 1); sham content (``public_text`` None) was checked on its
        donor. Each dropped field or binding is a fault."""
        modern = notes.outcome_judged(procedure)
        kept, dropped = notes.screen(fields, bench=self.bench, public_text=public_text,
                                     **({"outcome_judged": True, "audited": notes.audited(procedure)} if modern else {}))
        if modern:
            _, header_drops = notes.screen_header(procedure.header,
                **({"audited": True, "bench": self.bench} if notes.audited(procedure) else {}))
            dropped += header_drops
        bindings = kept.pop("bindings", [])
        if bindings and public_text is not None:
            bindings, unverified = notes.check_bindings(bindings, public_text)
            dropped = dropped + unverified
        if bindings:
            kept["bindings"] = bindings
        kept = notes.suppress_faulted(kept, dropped, outcome_judged=modern)
        bindings = kept.get("bindings", [])
        text = notes.render(kept, bench=self.bench, header=procedure.header) if kept else ""
        self.notes.append({"id": procedure.id, "hook": hook, "fields": kept, "rendered_chars": len(text),
                           "dropped": dropped,
                           **({"procedure_sha256": procedure.sha256,
                               "source_sha256": hashlib.sha256(procedure.source.encode()).hexdigest(),
                               "step": len(self.steps) if self.steps is not None else None,
                               "delivered_text": ""} if notes.audited(procedure) else {})})
        for entry in notes.fault_drops(dropped, outcome_judged=modern):
            self.fault(procedure.id, hook, "note_" + entry["reason"], None, entry["detail"])
        return text, bindings

    def assemble(self, entries):
        """The notes of one request: ``entries`` [(label "id/hook", text, max_note_chars)] joined in package order
        within the caps (``notes.assemble``); a note over its declared cap is a fault. Returns (text, shown labels)."""
        text, skipped = notes.assemble(entries, bench=self.bench)
        gone = set()
        for entry in skipped:
            gone.add(entry["procedure"])
            if entry["reason"] == "over_declared_cap":
                self.fault(entry["procedure"].split("/")[0], "notes", "note_over_declared_cap", None, entry["chars"])
        modern_dropped = {p.id for p in self.package.procedures if p.id in self.dropped and notes.outcome_judged(p)}
        if modern_dropped:
            # A cap fault discovered during assembly also suppresses this procedure's other pending notes.
            entries = [entry for entry in entries if entry[0].split("/")[0] not in modern_dropped]
            text, skipped = notes.assemble(entries, bench=self.bench)
            gone = {entry["procedure"] for entry in skipped}
        shown = [label for label, note, _ in entries if note and label not in gone]
        for label, rendered, _ in entries:
            pid, hook = label.split("/", 1)
            procedure = self.package.get(pid)
            if not notes.audited(procedure):
                continue
            step = len(self.steps) if self.steps is not None else None
            found = next((row for row in reversed(self.notes)
                          if row["id"] == pid and row["hook"] == hook and row.get("step") == step), None)
            if found is None:
                found = {"id": pid, "hook": hook, "fields": {}, "rendered_chars": len(rendered), "dropped": [],
                         "procedure_sha256": procedure.sha256, "source_sha256": hashlib.sha256(procedure.source.encode()).hexdigest(),
                         "step": step, "delivered_text": ""}
                self.notes.append(found)
            found["delivered_text"] = rendered if label in shown else ""
        return text, shown

    def sham(self, procedure_id, hook, step=0):
        """A placebo procedure's sealed content for ``hook`` (ALFWorld: the donor's step, its last one beyond)."""
        content = self.placebo["procedures"][procedure_id]
        if hook == "alf_before_step":
            steps = content.get(hook) or []
            entry = steps[min(step, len(steps) - 1)] if steps else {}
            return entry.get("fields") or {}, entry.get("discourage", 0)
        return content.get(hook) or {}

    def note(self, procedure, hook, args, public_text):
        """``(text, bindings)`` this arm shows for one QA/SpreadsheetBench note hook of ``procedure``."""
        if procedure.id in self.shams:
            return self.render(procedure, hook, self.sham(procedure.id, hook), public_text=None)
        ok, value = self.hook(procedure, hook, args)
        shaped = self.shaped(procedure, hook, value) if ok else None
        if shaped is None:
            return "", []
        text, bindings = self.render(procedure, hook, shaped[0], public_text=public_text)
        if procedure.id in self.text:  # T_F: the description where the procedure has output, no names
            return (self.text[procedure.id] if text else ""), []
        return text, bindings

    def before(self, view, public_text):
        """The first request's notes (QA, SpreadsheetBench) and the calculator's names: (notes text, the bindings of
        the shown ``bindings`` notes, or None when no invitation is shown). A binding name another shown procedure
        already binds is a fault of the later procedure, whose bindings note is then not shown. ``bindings`` is
        QA-only (registration §2.4, §3): on SpreadsheetBench the hook is not run, so no bindings note and no compute
        invitation are shown, in every arm (registrar addendum 2026-10-22 15:5x R3)."""
        entries, offered = [], {}
        for procedure in self.enabled(NOTE_HOOKS):
            for hook in NOTE_HOOKS:
                if hook not in procedure.hooks or procedure.id in self.dropped or (hook == "bindings"
                                                                                   and self.bench not in QA):
                    continue
                text, bindings = self.note(procedure, hook, [view, None] if hook == "before_call" else [view],
                                           public_text)
                label = procedure.id + "/" + hook
                if hook == "bindings" and text:
                    taken = {b["name"] for names in offered.values() for b in names}
                    repeated = sorted({b["name"] for b in bindings} & taken)
                    if repeated:
                        self.fault(procedure.id, hook, "note_duplicate_name", None, repeated[0])
                        continue
                    offered[label] = bindings
                entries.append((label, text, procedure.max_note_chars))
        # v2.8: another hook of this procedure can fault after its first note was prepared.
        modern_dropped = {p.id for p in self.package.procedures if p.id in self.dropped and notes.outcome_judged(p)}
        entries = [entry for entry in entries if entry[0].split("/")[0] not in modern_dropped]
        text, shown = self.assemble(entries)
        invited = [label for label in shown if label in offered]
        if invited:
            text += notes.SEPARATOR + COMPUTE_INVITE
        self.notes_chars = max(self.notes_chars, len(text))
        return text, ([b for label in invited for b in offered[label]] if invited else None)

    def calculate(self, tags, names):
        """The evaluated ``<calc>`` tags shown in the second request: the fixed evaluator on the shown names; in a
        placebo arm with an enabled shammed ``bindings`` procedure every value is ``not evaluated`` (§6.1)."""
        if any(p.id in self.shams for p in self.enabled(("bindings",))):
            results = [{"expr": tag, "value": NOT_EVALUATED} for tag in tags]
        else:
            results = compute.evaluate_tags(tags, names)
        self.compute = {"tags": tags, "results": results}
        return [{"expr": r["expr"], "value": r["value"]} for r in results]

    # -------------------------------------------------------------------------------------------- model calls
    def request(self, purpose, system, user):
        """One logical call through the frozen ``_response`` (backends.py:90-113): ``(reply, costs, reason, receipt
        index)``. Answer-tag benches keep the frozen completed-without-text rule (backends.py:418-422); with a nominal
        M the §4.1 margin rule marks a reply truncated."""
        before = len(self.receipts)

        def recorded(system_, user_):
            self.receipts.append(self._call(system_, user_))
            return self.receipts[-1]

        response, costs, reason = _response(recorded, system, user)
        index = len(self.receipts) - 1 if len(self.receipts) > before else None
        receipt = self.receipts[index] if index is not None else None
        if response is None and self.bench in (*ANSWER_TAG_BENCHMARKS, zebralogic.BENCH) and _completed_without_text(receipt):
            response, reason = "", "model_response_completed_without_text"
        if response and self._margin_truncated(receipt, response):
            response, reason = None, "model_response_truncated"
        self.calls.append({"purpose": purpose, "request_sha256": _request_hash(system, user), "receipt_index": index,
                           "reason": reason})
        return response, costs, reason, index

    def _margin_truncated(self, receipt, response):
        if self.nominal is None or not isinstance(receipt, dict):
            return False
        visible = receipt.get("visible_completion_tokens")
        return type(visible) is int and visible >= self.nominal - TRUNCATION_MARGIN and _unclosed(response)

    def native_slot(self):
        return self.native.hold() if self.native is not None else nullcontext()

    def sandbox(self):
        """The sandbox lifecycle of the cell's worker (ticket C5-4): copies of its ``restarts`` and ``cleanups``
        (container names, procedure ids and numbers only); None without a worker. A worker without these lists (the
        tests' FakeSandbox) has had neither. Opted-in start measurements accompany the same evidence."""
        if self.worker is None:
            return None
        return {"restarts": [dict(r) for r in getattr(self.worker, "restarts", ())],
                "cleanups": [dict(c) for c in getattr(self.worker, "cleanups", ())],
                **({"starts": [dict(s) for s in self.worker.starts]} if getattr(self.worker, "starts", ()) else {})}

    # ------------------------------------------------------------------------------------------- predictions
    def record(self):
        deciding = self.deciding
        if deciding is None and self.receipts:
            deciding = len(self.receipts) - 1
        fields = {"route": self.route.to_json() if self.route is not None else None, "calls": self.calls,
                  "procedure_events": self.events, "faults": self.faults, "notes": self.notes,
                  "notes_chars": self.notes_chars, "compute": self.compute, "precheck": self.precheck,
                  "fallback": self.fallback, "deciding_receipt": deciding,
                  "worst_delivery": worst_delivery(self.receipts),
                  "arm": {"withheld": sorted(self.withhold), "restored": sorted(self.restore),
                          "placebo": sorted(self.shams), "text": sorted(self.text)},
                  "sandbox": self.sandbox()}
        if profiles.uses_v211(self.configuration, self.bench):
            fields['effects'] = list(self.effects)
        if any(notes.audited(p) for p in self.package.procedures):
            fields["keyword_hits"] = notes.keyword_summary([row for entry in self.notes for row in entry["dropped"]])
        if self.steps is not None:
            fields["alfworld_steps"] = self.steps
        if self.shortcut is not None:
            fields["shortcut"] = self.shortcut
        return record("shell", self.package.evidence, fields)

    def unknown(self, reason, **extra):
        return {**_prediction_unknown(reason, **extra), "shell": self.record()}

    def available(self, output, costs, reason, **extra):
        return {"status": "available", "output": output, "costs": costs, "reason": reason, **extra,
                "shell": self.record()}

    # -------------------------------------------------------------------------------------- SpreadsheetBench
    def run_precheck(self, program, workbook, position, runtime, stored):
        """The stored report on replay, else one pre-check run under the native slot (§2.5), its container named with
        the worker's unit tag when the worker has one (ticket C5-2), so the unit's drain finds it."""
        if stored is not None:
            return stored
        tag = getattr(self.worker, "tag", None)
        options = {"tag": tag} if tag is not None else {}
        with self.native_slot():
            return prechecks.precheck(program, workbook, position, runtime, evidence=self.package.evidence, **options)

    def feedback(self, view, run_report):
        """``(notes text, repair requested)`` of the enabled ``sheet_feedback`` procedures after the pre-check."""
        report = {key: run_report.get(key) for key in REPORT_KEYS}
        failed = report["status"] in PROGRAM_ERRORS
        entries, requests = [], []
        for procedure in self.enabled(("sheet_feedback",)):
            if procedure.id in self.text:  # T_F: no procedure code; the same trigger RULE on the shell's report
                text, trigger = (self.text[procedure.id] if failed else ""), failed and procedure.requests_second_call
            else:
                ok, value = self.hook(procedure, "sheet_feedback", [view, report, None])
                shaped = self.shaped(procedure, "sheet_feedback", value, donors.shape_extra("sheet_feedback")) if ok else None
                if shaped is None:
                    continue
                if procedure.id in self.shams:  # the shadow decides the trigger; the donor's content is shown
                    text, _ = self.render(procedure, "sheet_feedback", self.sham(procedure.id, "sheet_feedback"),
                                          public_text=None)
                else:
                    text, _ = self.render(procedure, "sheet_feedback", shaped[0], public_text=_public_text(view))
                if notes.outcome_judged(procedure) and procedure.id in self.dropped:
                    continue
                trigger = shaped[1]
                if trigger and not procedure.requests_second_call:
                    self.fault(procedure.id, "sheet_feedback", "undeclared_second_call")
                    continue
            if trigger:
                requests.append(procedure)
            entries.append((procedure.id + "/sheet_feedback", text, procedure.max_note_chars))
        text, _ = self.assemble(entries)
        if profiles.uses_v211(self.configuration, self.bench):
            self.effects.extend({'procedure': p.id, 'hook': 'sheet_feedback',
                'kind': 'request_repair', 'permitted': not (notes.outcome_judged(p) and p.id in self.dropped),
                'source_sha256': hashlib.sha256(p.source.encode()).hexdigest()} for p in requests)
        self.notes_chars = max(self.notes_chars, len(text))
        return text, any(not (notes.outcome_judged(p) and p.id in self.dropped) for p in requests)

    # ------------------------------------------------------------------------------------------------ ALFWorld
    def before_step(self, view, states, step):
        """``(notes text, discouraged commands)`` of one ALFWorld step."""
        admissible = view["admissible_commands"] if isinstance(view["admissible_commands"], list) else []
        reference = _public_text([view["initial_observation"], view["observation"]])
        entries, discouraged = [], {}
        for procedure in self.enabled(("alf_before_step",)):
            label = procedure.id + "/alf_before_step"
            if procedure.id in self.shams:
                fields, count = self.sham(procedure.id, "alf_before_step", step)
                text, _ = self.render(procedure, "alf_before_step", fields, public_text=None)
                commands = sham_discouraged(admissible, count, self.placebo["seed"], step)
            elif procedure.id in self.text:
                text, commands = self.text[procedure.id], []
            else:
                ok, value = self.hook(procedure, "alf_before_step", [view, states.get(procedure.id)])
                shaped = self.shaped(procedure, "alf_before_step", value, donors.shape_extra("alf_before_step")) if ok else None
                if shaped is None:
                    continue
                text, _ = self.render(procedure, "alf_before_step", shaped[0], public_text=reference)
                commands = [c for c in dict.fromkeys(shaped[1]) if c in admissible]
            if notes.outcome_judged(procedure) and procedure.id in self.dropped:
                continue
            line = NOT_RECOMMENDED_PREFIX + ", ".join(commands) if commands else ""
            entries.append((label, "\n".join(part for part in (text, line) if part), procedure.max_note_chars))
            discouraged[label] = commands
        text, shown = self.assemble(entries)
        self.notes_chars = max(self.notes_chars, len(text))
        return text, [c for label in shown for c in discouraged[label]]

    def after_step(self, event, states):
        """``alf_after_step`` of the enabled procedures (real content only); the host keeps each new state within the
        procedure's declared bytes. Returns {procedure: state sha256}."""
        for procedure in self.enabled(("alf_after_step",)):
            if procedure.id in self.shams or procedure.id in self.text:
                continue
            ok, value = self.hook(procedure, "alf_after_step", [event, states.get(procedure.id)])
            if not ok:
                continue
            size = len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
            if size > procedure.state_bytes:
                self.fault(procedure.id, "alf_after_step", "state_over_declared_bytes", None, size)
                continue
            states[procedure.id] = value
        return {pid: digest(state) for pid, state in sorted(states.items()) if pid not in self.dropped}


def solve(bench, public, card_text, package, call, *, runtime=None, worker=None, withhold=frozenset(),
          restore=frozenset(), placebo=None, text=None, native=None, nominal_tokens=None, precheck_report=None,
          shortcut=None, configuration=None):
    """One item through the shell (module docstring). ``card_text``: the active bench card only (§2.2);
    ``call(system, user) -> receipt``: the cell's call function (the frozen Recorder); ``worker``: an unstarted sandbox
    worker, started and closed here; ``native``: the ``spreadsheet-native`` slot pool (its ``hold()``);
    ``nominal_tokens``: the nominal M of chain D's margin truncation rule (§4.1; None: the finish reason only);
    ``precheck_report``: the stored SpreadsheetBench pre-check report of the replayed cell; ``shortcut``: None, or
    ``NO_WORKBOOK`` for a SpreadsheetBench shortcut-probe cell of a package without procedures for the bench (§7.2)."""
    require(type(card_text) is str, "The card text is text")
    runtime = runtime or {}
    shell = _Shell(bench, package, call, worker, withhold=withhold, restore=restore, placebo=placebo, text=text,
                   native=native, nominal=nominal_tokens, shortcut=shortcut, configuration=configuration)
    try:
        prediction = _solve(shell, bench, public, card_text, runtime, precheck_report)
    finally:
        shell.close()
    return {**prediction, "shell": shell.record()}  # sealed again once the worker closed (ticket C5-4)


def _solve(shell, bench, public, card_text, runtime, stored):
    """Copy of the checks of ``backends.solve`` (backends.py:366-376)."""
    extraction = runtime.get("code_extraction_version")
    if extraction is not None and (extraction not in (CODE_EXTRACTION_VERSION, CODE_EXTRACTION_V23) or bench != "spreadsheetbench"):
        return shell.unknown("invalid_code_extraction_version")
    if not _layout_supported(bench, runtime):
        return shell.unknown("invalid_prompt_layout")
    try:
        view = _public_view(bench, public)
    except (KeyError, ValueError, TypeError):
        return shell.unknown("invalid_public_contract")
    if bench == "alfworld":
        return _solve_alfworld(shell, public, view, card_text, runtime)
    if bench == "spreadsheetbench":
        return _solve_sheet(shell, public, view, card_text, runtime, stored)
    require(bench in (*QA, zebralogic.BENCH), "Unknown text-solver benchmark")
    return _solve_qa(shell, view, card_text, runtime)


def _solve_qa(shell, view, card_text, runtime):
    """Copy of ``backends.solve`` for SearchQA, OfficeQA and LiveMath (backends.py:377-455) with the notes and the
    ``<calc>`` round trip (§2.4)."""
    system = _system(shell.bench, card_text, runtime)
    costs = {}
    try:
        shell.start("cell")
        shell.route_on(view)
        text, names = shell.before(view, _public_text(view))
        request = dict(view)
        if text:
            request[NOTES_KEY] = text
        response, costs, reason, first = shell.request("first", system, _user(shell.bench, view, text))
        if response is None:
            return shell.unknown(reason, costs=costs)
        shell.deciding = first
        tags = compute.parse_tags(response) if names is not None else []
        if tags:
            follow = {**request, "first_reply": response, "computed": shell.calculate(tags, names),
                      "instruction": COMPUTE_FOLLOWUP}
            second, costs2, reason2, index = shell.request("second", system, json.dumps(follow, ensure_ascii=False))
            if second is not None:
                response, reason, costs, shell.deciding = second, reason2, _two_calls(costs, costs2, True), index
            else:
                shell.fallback, costs = FALLBACK, _two_calls(costs, costs2, False)
        # Historical profiles retain their exact extraction behavior: the reply itself.
        return shell.available(response, costs, reason)
    except STOPS:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        return shell.unknown("public_input_or_runtime_error:" + type(exc).__name__, costs=costs)


def _inputs_dir(workbook):
    """A directory holding the public workbook as ``input.xlsx`` (the sandbox's read-only /input mount, §2.5)."""
    directory = Path(tempfile.mkdtemp(prefix="execskill-input-"))
    (directory / "input.xlsx").write_bytes(_xlsx_bytes(workbook))
    (directory / "input.xlsx").chmod(0o444)
    directory.chmod(0o755)
    return directory


def _solve_sheet(shell, public, view, card_text, runtime, stored):
    """Copy of ``backends.solve`` for SpreadsheetBench (backends.py:377-455) with the notes, the pre-check and one
    repair call (§2.5); the native slot is held around each container run only. In the no-workbook mode the view has
    no preview (``_sheet_view``); the pre-check and the per-case runs still read the real input files."""
    system = _system("spreadsheetbench", card_text, runtime)
    extraction = runtime.get("code_extraction_version")
    costs, inputs = {}, None
    try:
        preview_version = runtime.get("spreadsheet_preview_version")
        if preview_version not in (None, SHEET_PREVIEW_VERSION):
            return shell.unknown("invalid_spreadsheet_preview_version")
        files = view.get("input_files", [])
        if not files:
            return shell.unknown("missing_public_workbook")
        sheet_view = _sheet_view(view, runtime, shortcut=shell.shortcut)
        if shell.worker is not None and shell.package.for_bench("spreadsheetbench"):
            inputs = _inputs_dir(files[0])
        shell.start("cell", inputs)
        shell.route_on(sheet_view)
        text, _ = shell.before(sheet_view, _public_text(sheet_view))
        request = dict(sheet_view)
        if text:
            request[NOTES_KEY] = text
        response, costs, reason, first = shell.request("first", system, json.dumps(request, ensure_ascii=False))
        if response is None:
            return shell.unknown(reason, costs=costs)
        shell.deciding = first
        output, delivery = _extract(response, extraction, multiple=runtime.get("multiple_python_blocks", "refuse"))
        if output is None:
            return shell.unknown("code_delivery:" + delivery["code_delivery"]["reason"], costs=costs, **delivery)
        # §2.5: every extracted program is pre-checked once on the public input, whether or not a sheet_feedback
        # procedure is enabled, and the report is stored with the cell: the run slice's stored reports feed the
        # sheet_feedback sham of P_y (§6.1 donors) and the mechanical category program_exception_on_public_input
        # (§5.2) (ticket A9-1, integration B3). Without an enabled sheet_feedback procedure nothing reads it here.
        report = shell.run_precheck(output, files[0], sheet_view["required_answer_position"], runtime, stored)
        shell.precheck = report
        notes_text, requested = shell.feedback(sheet_view, report)
        if requested:
            repair = {**request, "previous_program": output, REPAIR_KEY: REPAIR_FRAME,
                      "run_report": {key: report.get(key) for key in SHOWN_REPORT_KEYS}}
            if notes_text:
                repair["repair_notes"] = notes_text
            second, costs2, _, index = shell.request("repair", system, json.dumps(repair, ensure_ascii=False))
            program, repaired = _extract(second, extraction, multiple=runtime.get("multiple_python_blocks", "refuse")) if second is not None else (None, {})
            if program is not None:
                output, delivery, costs, shell.deciding = program, repaired, _two_calls(costs, costs2, True), index
            else:
                shell.fallback, costs = FALLBACK, _two_calls(costs, costs2, False)
        cases = []
        for index, path in enumerate(public["input_files"]):
            with shell.native_slot():
                case = backends._native({"operation": "spreadsheet_generate", "code": output,
                                         "input_base64": base64.b64encode(_xlsx_bytes(path)).decode()}, runtime)
            cases.append(case)
            if runtime.get("_stop_on_cleanup_failure") is True and (
                    case.get("cleanup_confirmed") is False or "cleanup_unconfirmed" in str(case.get("reason", ""))):
                cases.extend(_unknown("not_executed_after_cleanup_failure") for _ in public["input_files"][index + 1:])
                break
        return shell.available({"code": output, "cases": cases}, costs, "generated_once_executed_per_public_case",
                               **delivery)
    except STOPS:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        return shell.unknown("public_input_or_runtime_error:" + type(exc).__name__, costs=costs)
    finally:
        if inputs is not None:
            shutil.rmtree(inputs, ignore_errors=True)


def _solve_alfworld(shell, public, view, card_text, runtime):
    """Copy of ``backends._solve_alfworld`` (backends.py:715-783) with the routing view checks, the per-step notes and
    discouraged commands, the level-1 canonical action, ``alf_after_step`` and the stops re-raised before the catch-all
    (a stop that meets an unconfirmed environment close becomes CleanupUnconfirmed)."""
    env, calls, usages, trace = None, 0, [], []
    trace_version = runtime.get("alfworld_trace_version")
    if trace_version not in (None, ALFWORLD_TRACE_VERSION):
        return shell.unknown("invalid_alfworld_trace_version")
    transitions = trace_version == ALFWORLD_TRACE_VERSION
    # Logging must not change the solver's history keys, content, or window.
    prompt_history = []

    def trace_fields():
        return {"trace": trace, **({"trace_version": trace_version} if transitions else {})}

    def spent():
        return {"calls": calls, "usage_by_call": usages}

    max_steps = runtime.get("max_steps", 50)
    if type(max_steps) is not int or not 1 <= max_steps <= 150:
        return shell.unknown("invalid_alfworld_step_budget")
    system = ALF_SYSTEM
    if card_text.strip():
        system += "\n" + GUIDANCE + card_text
    registered = _registered_view(public)
    if registered is None and shell.package.for_bench("alfworld"):
        raise ConfigurationError("alfworld_routing_view_missing: an item with procedures routes on its registered view")
    shell.start("episode")
    if shell.worker is not None:
        shell.worker.ping()  # every arm takes the same slot path (§6.2)
    if registered is not None:
        shell.route_on(registered)

    def episode():
        nonlocal env, calls
        env = backends._new_alfworld(view, runtime)
        observations, _, infos = env.reset()
        # The task instruction is part of the public reset observation, but
        # subsequent observations generally omit it. Keep it throughout the
        # episode, independently of the bounded recent-action history.
        initial_observation = str(observations[0])
        if registered is not None and digest(alfworld_routing_view(
                initial_observation, list(infos[0].get("admissible_commands", [])))) != public["routing_view_sha256"]:
            raise ConfigurationError("alfworld_routing_view_hash_mismatch: the live reset view differs")
        states, won = {}, False
        for step in range(max_steps):
            # No expert plan, won/score, extra metadata, task identifiers, or
            # reference trajectory enters the model-visible view.
            step_view = {"initial_observation": initial_observation,
                         "observation": observations[0], "admissible_commands": infos[0].get("admissible_commands", []),
                         "recent_history": prompt_history[-5:]}
            text, discouraged = shell.before_step(step_view, states, step)
            request = dict(step_view)
            if text:
                request[NOTES_KEY] = text
            response, costs, reason, _ = shell.request("step", system, json.dumps(request, ensure_ascii=False))
            calls += 1
            usages.append(costs.get("usage", {}))
            if response is None:
                return shell.unknown(reason, costs=spent(), **trace_fields())
            admissible = step_view["admissible_commands"]
            action, how = canonical(response, admissible if isinstance(admissible, list) else [])
            entry = {"i": step, "view_sha256": digest(step_view), "notes": text, "discouraged": discouraged,
                     "action": action, "how": how, "state_sha256": {}}
            shell.steps.append(entry)
            if not action or len(action) > MAX_ACTION_CHARS:
                return shell.unknown("invalid_action_format", costs=spent(), **(trace_fields() if transitions else {}))
            history_item = {"observation": str(observations[0])[:OBSERVATION_CHARS], "action": action}
            prompt_history.append(history_item)
            trace.append({**history_item, "post_observation": None, "post_observation_status": "missing",
                          "post_observation_characters": None, "post_observation_reason": "step_result_unavailable"}
                         if transitions else history_item)
            observations, _, _, dones, infos = env.step([action])
            if transitions:
                trace[-1].update(_alf_post_observation(observations))
            if "won" not in infos[0]:
                return shell.unknown("native_won_signal_missing", costs=spent(),
                                     **(trace_fields() if transitions else {}))
            event = {"step": step, "action": action,
                     "observation": str(observations[0])[:OBSERVATION_CHARS] if observations else None,
                     "admissible_commands": list(infos[0].get("admissible_commands", []))}
            entry["state_sha256"] = shell.after_step(event, states)
            won = bool(infos[0]["won"])
            if won or dones[0]:
                break
        return {"status": "available", "output": {"won": won, "steps": step + 1},
                "reason": "fresh_native_episode_completed", "costs": spent(), **trace_fields(),
                "shell": shell.record()}

    try:
        result = episode()
    except STOPS as stop:
        if env is not None:
            try:
                env.close()
            except Exception:
                raise CleanupUnconfirmed("alfworld_cleanup_unconfirmed after %s" % type(stop).__name__) from stop
        raise
    except Exception as exc:
        result = shell.unknown("alfworld_environment_error:" + type(exc).__name__, costs=spent(), **trace_fields())
    if env is not None:
        try:
            env.close()
        except Exception:
            return shell.unknown("alfworld_cleanup_unconfirmed", costs=spent(), **trace_fields())
    return result
