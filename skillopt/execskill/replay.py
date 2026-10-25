"""Replay of one procedure on the stored run trajectories: the engineer's checks C6-C9 (registration §5.4 C6 zero
crash, C7 replay tests, C8 format guard, C9 output screen; FA-F6, FA-F17, MA-M12, EA-E9; implementation plan §1
replay.py, §2.1 replay tests, T-REPLAY-1..4).

Everything here is fixed registrar code over sandbox outputs: the procedure's hooks run only in the sandbox
(``sandbox.client.Worker``), on the whitelisted inputs of stored trajectories, with ZERO model calls, exactly as the
shell would call them (``solver._Shell``): QA and SpreadsheetBench ``before_call`` (state None) and ``bindings`` on the
first request's view, ``sheet_feedback`` on the stored pre-check report; ALFWorld ``alf_before_step`` step by step and
``alf_after_step`` fed the stored events (the action and the next request's observation and admissible commands; the
last step has no event, as in ``donors.donor_inputs``), the host keeping the state within its declared bytes. Every
note is screened as the shell screens it (``notes.screen``; bindings verbatim on the item's own public text,
``notes.check_bindings``); the first fault ends the procedure's run on that trajectory, as the shell drops it.

- ``zero_crash`` (C6): every in-scope trajectory in two fresh workers (PYTHONHASHSEED 0 and 1) in two item orders
  (forward, reversed): no crash-type fault and identical value hashes.
- ``run_tests`` (C7): the procedure's replay tests, of the fixed property kinds ``PROPERTY_KINDS`` only (no model-
  written judgement runs anywhere); each test must hold with the procedure and be non-vacuous -- false with the
  procedure withheld (the differential test) or under its declared input mutation (``MUTATIONS``; required for the
  predicate kinds, whose value withholding cannot change) -- and at least one must hold on a failed trajectory it
  claims to fix. The registrar's negative tests (a passed ALFWorld episode's last action never discouraged at its step,
  a passed SpreadsheetBench item never asked for a repair), the reference-tracker agreement of an ALFWorld state
  procedure (>= ``TRACKER_AGREEMENT`` of its steps, ``ReferenceTracker``) and the verbatim bindings belong to C7.
- ``format_guard`` (C8): no shown note carries an answer-channel marker. The system prompt is not an input of any hook
  (the shell builds it from the card and the runtime) and the notes stay the last key of the request, so the answer
  channel is what a procedure could touch.
- ``output_faults`` (C9): the note faults of the lexicon screen and the caps (declared, and the bench's per-request cap
  a single note may never exceed).
- ``meta_counterfactual`` (C4, v2.1 ``protocol.META_COUNTERFACTUAL``): the procedure on its in-scope LiveMath
  trajectories whose view holds the meta option, with that option's text replaced by ``protocol.META_FILLER``: any
  difference from its run on the real views -- predicate, notes, bindings, repair request, ALFWorld steps or fault
  kinds, the filler mapped back to the option -- is a C4 failure. A procedure that never reads the option, or quotes
  it verbatim, behaves the same; one keyed on it does not. Steps before LiveMath have no such trajectory (the check is
  vacuous there); acceptance's options-only probe J7 stays the backstop.

Every value a model wrote (a replay test, its property, its mutation) is type-checked before it is used as a key
(v2.1: main-v2's chain G stopped on a mutation written as an object, 2026-10-24 00:01).

ALFWorld state contract (registrar-defined; ticket A10-1): a state procedure keeps ``state["facts"]``, a mapping of at
least one of ``STATE_FACTS`` -- ``reached`` (receptacles reached or opened), ``carrying`` (objects held),
``nothing_happens`` (rejected actions so far) -- compared with the fixed port of the D3 hand tracker
(/data/feasibility/D3/r3/lt/tracker_ref.py = pilot_alf_glm.py:107-163; the comparison of lt_replay.py ``agree_all``:
receptacle sets, sorted objects, the count).
"""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import notes
from .donors import public_text, shaped
from .package import Package
from .protocol import MUTATIONS  # historical exported registration remains unchanged
from .profiles import (SUPPORTED_BENCHES, BENCHES, LIVEMATH_META_OPTION, MAX_FRAGMENTS, MAX_NOTE_CHARS, MAX_PROPERTY_TEXT, MAX_TESTS,
                       META_FILLER, MUTATIONS as SUPPORTED_MUTATIONS, NOT_RECOMMENDED_PREFIX, NOTES_KEY, PROPERTY_KINDS, SANDBOX_TIMEOUTS,
                       STATE_FACTS, TRACKER_AGREEMENT)
from .supply import routing_view as alfworld_routing_view

OBSERVATION_CHARS = 12000  # the shell's event observation (backends.py:756)
REPORT_KEYS = ("status", "exc_type", "message", "answer_cells")  # what sheet_feedback sees (solver.REPORT_KEYS)
SANDBOX_KINDS = {"alfworld": "episode"}  # the sandbox kind of a bench's worker; every other bench runs a cell's
TEST_KEYS = ("claims_fix", "hook", "id", "nonvacuity", "property", "trajectory")
TEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}")
STEP_HOOKS = ("alf_before_step", "alf_after_step")
NOTHING = "Nothing happens."
CRASH_KINDS = ("predicate:not_bool", "output_shape", "state_over_declared_bytes", "undeclared_second_call")
BINDING_KINDS = ("note_name", "note_duplicate_name", "note_value", "note_not_verbatim")
META_KINDS = ("note_meta_option",)
COUNTERFACTUAL = "meta_counterfactual"  # v2.1: C4's output ban of a procedure keyed on the LiveMath meta option
CHANNEL_MARKERS = ("<answer", "</answer", "<action", "</action", "<calc", "</calc", "```")


# ------------------------------------------------------------------------------------------- the reference tracker
ARTICLE = re.compile(r"^(?:a|an|the)\s+")


def names(text):
    """The object or receptacle names of an observation's list ("a drawer 1, a cabinet 2, and a desk 1")."""
    out = []
    for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", text.strip().rstrip(".")):
        part = ARTICLE.sub("", part.strip())
        if part and part != "nothing":
            out.append(part)
    return out


class ReferenceTracker:
    """The fixed D3 hand tracker (/data/feasibility/D3/r3/lt/tracker_ref.py, pilot_alf_glm.py:107-163), ported
    verbatim as registrar code; ``facts`` is the comparison of lt_replay.py ``agree_all``."""

    def __init__(self, initial):
        match = re.search(r"you see (.*?)\.\s*(?:\n|$)", initial, re.S)
        self.receptacles = names(match.group(1)) if match else []
        self.visited, self.inventory, self.rejected = {}, [], 0

    @staticmethod
    def _summary(observation):
        match = re.search(r"you see (.*?)\.", observation, re.S)
        if match:
            found = names(match.group(1))
            return ", ".join(found) if found else "nothing"
        if "is closed" in observation:
            return "closed (not opened yet)"
        return "reached"

    def update(self, action, observation):
        action, observation = action.strip(), (observation or "").strip()
        if observation.startswith("Nothing happens"):
            self.rejected += 1
            return
        for pattern, prefix in ((r"go to (.+)$", "You arrive at"), (r"open (.+)$", "You open")):
            match = re.match(pattern, action)
            if match and observation.startswith(prefix):
                self.visited[match.group(1).strip()] = self._summary(observation)
                return
        match = re.match(r"take (.+?) from (.+)$", action)
        if match and observation.startswith("You pick up"):
            obj, receptacle = match.group(1).strip(), match.group(2).strip()
            self.inventory.append(obj)
            if receptacle in self.visited:
                rest = [n for n in names(self.visited[receptacle]) if n != obj]
                self.visited[receptacle] = ", ".join(rest) if rest else "nothing"
            return
        match = re.match(r"move (.+?) to (.+)$", action) or re.match(r"put (.+?) (?:in/on|in|on) (.+)$", action)
        if match and observation.startswith(("You move", "You put")):
            obj, receptacle = match.group(1).strip(), match.group(2).strip()
            self.inventory = [o for o in self.inventory if o != obj]
            seen = [n for n in names(self.visited.get(receptacle, "")) if n not in ("nothing", "reached")]
            self.visited[receptacle] = ", ".join(seen + [obj])

    def facts(self):
        return {"reached": sorted(self.visited), "carrying": sorted(self.inventory), "nothing_happens": self.rejected}


def facts_agree(state, reference):
    """Whether a state's ``facts`` agree with the reference tracker's: at least one registered key, each one equal
    (``reached`` as a set, ``carrying`` sorted, ``nothing_happens`` the count)."""
    facts = state.get("facts") if isinstance(state, dict) else None
    if not isinstance(facts, dict) or not facts or not set(facts) <= set(STATE_FACTS):
        return False
    for key, value in facts.items():
        if key == "nothing_happens":
            if type(value) is not int or value != reference[key]:
                return False
        elif type(value) is not list or not all(type(v) is str for v in value):
            return False
        elif (sorted(set(value)) if key == "reached" else sorted(value)) != reference[key]:
            return False
    return True


# ------------------------------------------------------------------------------------------------------ inputs
def _view(call, *, bench=None):
    """The view a request showed: its user JSON without the procedure notes."""
    if bench == "zebralogic":
        from .zebralogic import parse_user
        view = parse_user(call["user"])
    else:
        view = json.loads(call["user"])
    require(isinstance(view, dict), "A request's user content is a JSON object")
    view.pop(NOTES_KEY, None)
    return view


def _commands(view):
    value = view.get("admissible_commands")
    return list(value) if isinstance(value, list) and all(type(c) is str for c in value) else []


def inputs_of(trajectory):
    """What the hooks of one stored trajectory see (whitelisted keys only), or None when it holds no request:
    ``{"cell", "bench", "item", "token", "view"`` (the routing view), ``"request_view", "report", "steps"}``. QA and
    SpreadsheetBench: the first request's view and the stored pre-check report; ALFWorld: per step request its view, the
    stored action (None when the request got no reply) and the event after it (None after the last step)."""
    bench = trajectory["bench"]
    require(bench in SUPPORTED_BENCHES, "A trajectory of a known bench")
    calls = trajectory.get("calls") or []
    base = {"cell": trajectory["cell"], "bench": bench, "item": trajectory["task_id"], "token": trajectory.get("token")}
    if bench != "alfworld":
        first = [call for call in calls if call.get("purpose") == "first"]
        if not first:
            return None
        view = _view(first[0], bench=bench)
        report = (trajectory.get("shell") or {}).get("precheck") if bench == "spreadsheetbench" else None
        return {**base, "view": view, "request_view": view, "report": report, "steps": None}
    views = [_view(call) for call in calls if call.get("purpose") == "step"]
    if not views:
        return None
    stored = sorted(trajectory.get("alfworld_steps") or [], key=lambda s: s["i"])
    actions = [s.get("action") for s in stored]
    steps = []
    for i, view in enumerate(views):
        action = actions[i] if i < len(actions) else None
        event = None
        if type(action) is str and i + 1 < len(views):
            following = views[i + 1]
            event = {"step": i, "action": action,
                     "observation": str(following.get("observation"))[:OBSERVATION_CHARS],
                     "admissible_commands": _commands(following)}
        steps.append({"view": view, "action": action, "event": event})
    routing = alfworld_routing_view(str(views[0].get("initial_observation")), _commands(views[0]))
    return {**base, "view": routing, "request_view": None, "report": None, "steps": steps}


def _strip_digits(value):
    if isinstance(value, str):
        return re.sub(r"[0-9]", "", value)
    if isinstance(value, dict):
        return {k: _strip_digits(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_digits(v) for v in value]
    return value


def mutate(inputs, mutation):
    """A perturbed copy of ``inputs`` (``MUTATIONS``): every digit removed from the item's texts; the pre-check
    report's exception message dropped, or the report made a clean run; every observation after an action replaced by
    the environment's rejection text."""
    require(mutation in SUPPORTED_MUTATIONS and inputs["bench"] in SUPPORTED_MUTATIONS[mutation], "A registered mutation of this bench")
    out = copy.deepcopy(inputs)
    if mutation == "strip_digits":
        for key in ("view", "request_view", "report", "steps"):
            out[key] = _strip_digits(out[key])
    elif mutation in ("drop_exception_message", "program_ok"):
        if out["report"] is not None:
            out["report"].update(exc_type=None, message="", **({"status": "ok"} if mutation == "program_ok" else {}))
    else:
        for i, step in enumerate(out["steps"]):
            if i:
                step["view"]["observation"] = NOTHING
            if step["event"] is not None:
                step["event"]["observation"] = NOTHING
    return out


# ------------------------------------------------------------------------------------------------------ replay
@dataclass
class Outcome:
    """One procedure on one trajectory. ``notes``: [{hook, step, text, public}] (the shown note and the public text
    it may quote); ``steps``: ALFWorld [{note, discouraged, state, after}] (``after``: alf_after_step ran);
    ``faults``: [{hook, step, kind, detail}]; ``values``: [[hook, step, value sha256 or "fault:<kind>"]]."""
    cell: str
    bench: str
    applies: bool | None = None
    notes: list = field(default_factory=list)
    bindings: list = field(default_factory=list)
    repair: bool = False
    steps: list = field(default_factory=list)
    faults: list = field(default_factory=list)
    values: list = field(default_factory=list)

    def note(self, hook, step=None):
        found = [n["text"] for n in self.notes if n["hook"] == hook and n["step"] == step]
        return found[0] if found else ""

    def summary(self):
        return {"cell": self.cell, "applies": self.applies, "notes": len(self.notes), "faults": self.faults,
                "values_sha256": digest(self.values)}


class _Run:
    """One procedure's hooks on one trajectory, with the shell's fault rule."""

    def __init__(self, worker, procedure, inputs, actual=None):
        self.worker, self.procedure, self.inputs = worker, procedure, inputs
        self.actual = actual
        self.outcome = Outcome(inputs["cell"], inputs["bench"])
        self.dead = False

    def fault(self, hook, step, kind, detail=""):
        self.outcome.faults.append({"hook": hook, "step": step, "kind": kind, "detail": str(detail)[:200]})
        self.dead = True

    def call(self, hook, args, step=None):
        """``(ok, value)`` of one sandbox call; a failed call is a crash fault."""
        timeout = SANDBOX_TIMEOUTS["predicate" if hook == "applies" else "hook"]
        result = self.worker.call(self.procedure.id, hook, list(args), timeout_s=timeout)
        if self.actual is not None:
            self.actual.append({"hook": hook, "step": step, **bounded_result(result)})
        if result.get("ok") is not True:
            self.outcome.values.append([hook, step, "fault:%s" % result.get("fault")])
            self.fault(hook, step, "crash:%s" % result.get("fault"), result.get("message") or "")
            return False, None
        self.outcome.values.append([hook, step, result["value_sha256"]])
        return True, result["value"]

    def hook(self, hook, args, extra=None, step=None):
        """``(fields, extra value)`` of one note hook, None after a fault."""
        if self.dead:
            return None
        ok, value = self.call(hook, args, step)
        if not ok:
            return None
        found = shaped(value, extra)
        if found is None:
            self.fault(hook, step, "output_shape", type(value).__name__)
        return found

    def render(self, hook, fields, reference, step=None):
        """``(text, bindings)``: the screened note and its verbatim bindings (the shell's ``render``)."""
        bench = self.inputs["bench"]
        kept, dropped = notes.screen(fields, bench=bench, public_text=reference)  # verbatim quotes kept (C6b-2)
        bindings = kept.pop("bindings", [])
        if bindings:
            bindings, unverified = notes.check_bindings(bindings, reference)
            dropped = dropped + unverified
        if bindings:
            kept["bindings"] = bindings
        for entry in dropped:
            self.fault(hook, step, "note_" + entry["reason"], entry["detail"])
        text = notes.render(kept, bench=bench, header=self.procedure.header) if kept else ""
        return text, bindings

    def show(self, hook, text, reference, step=None):
        """Whether the shell would show the note; one over its caps is a fault and is not shown."""
        if not text:
            return False
        if len(text) > self.procedure.max_note_chars:
            self.fault(hook, step, "note_over_declared_cap", len(text))
            return False
        if len(text) > MAX_NOTE_CHARS[self.inputs["bench"]]:
            self.fault(hook, step, "note_over_bench_cap", len(text))
            return False
        self.outcome.notes.append({"hook": hook, "step": step, "text": text, "public": reference})
        return True

    def cell(self):
        view, report = self.inputs["request_view"], self.inputs["report"]
        reference = public_text(view)
        for hook in ("before_call", "bindings"):
            if hook in self.procedure.hooks and not self.dead:
                found = self.hook(hook, [view, None] if hook == "before_call" else [view])
                if found is not None:
                    text, bindings = self.render(hook, found[0], reference)
                    if self.show(hook, text, reference) and hook == "bindings":
                        self.outcome.bindings = bindings
        if "sheet_feedback" in self.procedure.hooks and report is not None and not self.dead:
            shown = {key: report.get(key) for key in REPORT_KEYS}
            found = self.hook("sheet_feedback", [view, shown, None], "request_repair")
            if found is not None:
                text, _ = self.render("sheet_feedback", found[0], reference)
                if found[1] and not self.procedure.requests_second_call:
                    self.fault("sheet_feedback", None, "undeclared_second_call")
                else:
                    self.show("sheet_feedback", text, reference)
                    self.outcome.repair = found[1]

    def episode(self):
        state = None
        for i, step in enumerate(self.inputs["steps"]):
            if self.dead:
                break
            view, entry = step["view"], {"note": "", "discouraged": [], "state": None, "after": False}
            self.outcome.steps.append(entry)
            if "alf_before_step" in self.procedure.hooks:
                found = self.hook("alf_before_step", [view, state], "discourage", i)
                if found is not None:
                    reference = public_text([view.get("initial_observation"), view.get("observation")])
                    text, _ = self.render("alf_before_step", found[0], reference, i)
                    admissible = _commands(view)
                    commands = [c for c in dict.fromkeys(found[1]) if c in admissible]
                    line = NOT_RECOMMENDED_PREFIX + ", ".join(commands) if commands else ""
                    note = "\n".join(part for part in (text, line) if part)
                    if self.show("alf_before_step", note, reference, i):
                        entry.update(note=note, discouraged=commands)
            if "alf_after_step" in self.procedure.hooks and step["event"] is not None and not self.dead:
                ok, value = self.call("alf_after_step", [step["event"], state], i)
                if ok:
                    size = len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
                    if size > self.procedure.state_bytes:
                        self.fault("alf_after_step", i, "state_over_declared_bytes", size)
                    else:
                        state = value
                        entry.update(state=value, after=True)


def replay(worker, procedure, inputs, *, mutation=None, actual=None):
    """The ``Outcome`` of ``procedure`` on one trajectory's ``inputs`` (``inputs_of``) through a started worker holding
    it: its predicate on the routing view, then -- where it applies -- its hooks as the shell calls them."""
    if mutation is not None:
        inputs = mutate(inputs, mutation)
    run = _Run(worker, procedure, inputs, actual)
    ok, value = run.call("applies", [inputs["view"]])
    if ok and type(value) is not bool:
        run.fault("applies", None, "predicate:not_bool", type(value).__name__)
    elif ok:
        run.outcome.applies = value
        if value and inputs["bench"] == "alfworld":
            run.episode()
        elif value:
            run.cell()
    return run.outcome


def solo(procedure):
    """The one-procedure package a check loads into its workers."""
    return Package((procedure,), "replay", procedure.evidence)


def replay_many(procedure, entries, workers, *, hashseed=0, inputs_dirs=None, mutation=None, actual=None):
    """{cell: Outcome} of ``procedure`` on ``entries`` (``inputs_of`` values), in their order within each worker group:
    one worker per bench kind and input directory, opened by ``workers(package, kind=, hashseed=, inputs_dir=)`` (a
    context manager yielding a started worker, e.g. ``sandbox.client.with_worker`` with its options bound).
    ``inputs_dirs``: {cell: the SpreadsheetBench item's public input directory}."""
    groups = defaultdict(list)
    for entry in entries:
        groups[(SANDBOX_KINDS.get(entry["bench"], "cell"), (inputs_dirs or {}).get(entry["cell"]))].append(entry)
    out, package = {}, solo(procedure)
    for (kind, directory), group in groups.items():
        with workers(package, kind=kind, hashseed=hashseed, inputs_dir=directory) as worker:
            for entry in group:
                captured = None if actual is None else actual.setdefault(entry["cell"], [])
                out[entry["cell"]] = replay(worker, procedure, entry, mutation=mutation,
                                          **({"actual": captured} if captured is not None else {}))
    return out


def _faults(outcomes, kinds=None, prefix=None):
    return [dict(f, cell=cell) for cell, outcome in outcomes.items() for f in outcome.faults
            if (kinds is not None and f["kind"] in kinds) or (prefix is not None and f["kind"].startswith(prefix))]


def crash_faults(outcomes):
    return _faults(outcomes, CRASH_KINDS, "crash:")


MISMATCH_EXPLANATION = (
    "C6 replays every in-scope trajectory in a fresh worker with PYTHONHASHSEED=0 in order and another with "
    "PYTHONHASHSEED=1 in reverse order. Every hook return must be identical; nothing may crash or time out (5 s). "
    "Sort unordered collections before iterating and use deterministic counters for limits."
)


def zero_crash(procedure, entries, workers, *, inputs_dirs=None, actual=None, diagnostic_cells=None):
    """C6: ``(report, outcomes of the first worker)``. Every in-scope trajectory runs in a fresh worker with
    PYTHONHASHSEED 0 in the given order and in one with PYTHONHASHSEED 1 in the reverse order; the check passes when
    there is at least one trajectory, no crash-type fault and every hook value hash is identical. v2.6's optional
    ``diagnostic_cells`` captures bounded results from these same two passes and permits one shown mismatch example;
    None preserves historical reports and capture behavior."""
    diagnosing = diagnostic_cells is not None
    first_actual = actual if actual is not None else {} if diagnosing else None
    second_actual = {} if diagnosing else None
    first = replay_many(procedure, entries, workers, hashseed=0, inputs_dirs=inputs_dirs,
                        **({"actual": first_actual} if first_actual is not None else {}))
    second = replay_many(procedure, entries[::-1], workers, hashseed=1, inputs_dirs=inputs_dirs,
                         **({"actual": second_actual} if diagnosing else {}))
    crashes = crash_faults(first) + crash_faults(second)
    mismatched = [cell for cell in first if first[cell].values != second[cell].values]
    report = {"check": "C6", "passed": bool(entries) and not crashes and not mismatched,
              "trajectories": len(entries), "fault_count": len(crashes), "faults": crashes[:10],
              "mismatched": mismatched[:10], "applied": sum(1 for o in first.values() if o.applies)}
    if diagnosing and mismatched:
        report.update(_mismatch_diagnostics(entries, mismatched, first, second, first_actual, second_actual,
                                            diagnostic_cells))
    return report, first


def _mismatch_diagnostics(entries, mismatched, first, second, first_actual, second_actual, shown):
    """v2.6 report metadata and at most one already-captured, shown cell's first differing hook."""
    by_cell = {entry["cell"]: entry for entry in entries}
    ordered = sorted(mismatched, key=lambda cell: (by_cell[cell]["item"], cell))
    detail = {"mismatch_explanation": MISMATCH_EXPLANATION,
              "mismatched_task_ids": sorted({by_cell[cell]["item"] for cell in mismatched})[:20],
              "mismatched_total": len(mismatched)}
    eligible = [cell for cell in ordered if cell in shown]
    if not eligible:
        return detail
    cell = eligible[0]
    left, right = first[cell].values, second[cell].values
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        if a == b:
            continue
        # A missing or differently located hook has no pair of actual returns to display.
        if a is None or b is None or a[:2] != b[:2]:
            return detail
        hook, step = a[:2]
        pair = []
        for captured in (first_actual, second_actual):
            found = [call for call in captured.get(cell, ()) if call["hook"] == hook and call["step"] == step]
            if not found:
                return detail
            pair.append({key: value for key, value in found[-1].items() if key not in ("hook", "step")})
        detail["mismatch_example"] = {"cell": cell, "task_id": by_cell[cell]["item"], "hook": hook, "step": step,
                                      "first": pair[0], "second": pair[1]}
        return detail
    return detail


def bounded_result(result):
    """v2.4 repair evidence from an actual worker call, never a re-execution or inferred return."""
    if result.get("ok") is not True:
        return {"status": "raised", "exc_type": str(result.get("exc_type") or result.get("fault") or "unknown")[:300],
                "message": str(result.get("message") or "")[:300]}
    value = result.get("value")
    text = ("returned nothing ({})" if value == {} else
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:1500])
    return {"status": "returned", "value": text}


def screened_note(procedure, bench, view, result):
    """v2.4 C6c: the shell-visible note from one existing before_call response, without another hook call.

    _Run.render uses the shell's notes.screen/type/lexicon and check_bindings/render path. The final assembly is
    notes.assemble itself, so both the procedure's declared cap and the benchmark request cap apply.
    """
    if result.get("ok") is not True:
        return ""
    fields = shaped(result.get("value"), None)
    if fields is None:
        return ""
    run = _Run(None, procedure, {"cell": "routing-output", "bench": bench})
    text, _ = run.render("before_call", fields[0], public_text(view))
    visible, _ = notes.assemble([(procedure.id + "/before_call", text, procedure.max_note_chars)], bench=bench)
    return visible


NO_RENDERED_NOTE = "no rendered note (nothing survived screening and rendering)"


def rendered_note(test, entries, outcomes, shown_cells):
    """v2.5: the exact original-outcome text tested by holds, only for a shown, verified run cell."""
    if not isinstance(test, dict) or not isinstance(test.get("property"), dict):
        return None
    prop, cell = test["property"], test.get("trajectory")
    if (prop.get("kind") not in ("note_contains", "note_matches") or type(cell) is not str
            or cell not in shown_cells or cell not in entries):
        return None
    outcome = outcomes.get(cell)
    if outcome is None or outcome.cell != cell or outcome.bench != entries[cell]["bench"]:
        return None
    text = outcome.note(test.get("hook"), prop.get("step"))
    return text[:1500] if text else NO_RENDERED_NOTE


def valid_trajectories(entries, shown_cells):
    """v2.6 reference help: IDs already shown, filtered by the exact procedure replay scope."""
    allowed = set(shown_cells) & entries.keys()
    ordered = sorted(allowed, key=lambda cell: (entries[cell]["item"], cell))
    return {"valid_trajectories": [{"trajectory": cell, "task_id": entries[cell]["item"]} for cell in ordered[:20]],
            "valid_trajectories_total": len(ordered)}


def valid_trajectories_shape(problem):
    """Bounded, counts-and-IDs-only shape of the persisted v2.6 lint reference help."""
    values, total = problem.get("valid_trajectories"), problem.get("valid_trajectories_total")
    if not (isinstance(values, list) and len(values) <= 20 and type(total) is int and total >= len(values)):
        return False
    if not all(isinstance(row, dict) and set(row) == {"trajectory", "task_id"}
               and all(type(row[key]) is str and 0 < len(row[key]) <= 512 for key in row) for row in values):
        return False
    keys = [(row["task_id"], row["trajectory"]) for row in values]
    return keys == sorted(set(keys)) and len({row["trajectory"] for row in values}) == len(values)


def claimed_tests(procedure, entries, outcomes, actual, *, shown_cells=None, reference_feedback=False):
    """v2.4 C5b: every declared fix claim holds under the same validation/property evaluator as lint."""
    claimed, failed = 0, []
    for test in procedure.replay_tests:
        if not isinstance(test, dict) or test.get("claims_fix") is not True:
            continue
        claimed += 1
        why = validate_test(test, procedure, entries)
        if why is None and holds(test["property"], test["hook"], outcomes.get(test["trajectory"])):
            continue
        prop = test.get("property") if isinstance(test.get("property"), dict) else {}
        cell = test.get("trajectory")
        disclose = shown_cells is None or (type(cell) is str and cell in shown_cells and cell in entries)
        calls = actual.get(cell, ()) if type(cell) is str and disclose else ()
        found = [call for call in calls if call["hook"] == test.get("hook") and call["step"] == prop.get("step")]
        failure = {"id": test.get("id"), "hook": test.get("hook"), "property": prop,
                       "reason": why or "test_failed", "actual":
                       {k: v for k, v in found[0].items() if k not in ("hook", "step")} if found else
                       {"status": "not_called", "reason": "hook_not_reached"}}
        if not disclose:
            failure["actual"] = {"status": "withheld", "reason": "trajectory_not_shown"}
        if shown_cells is not None and why is None:
            text = rendered_note(test, entries, outcomes, shown_cells)
            if text is not None:
                failure["rendered_note"] = text
        if reference_feedback and why == "trajectory_not_in_scope":
            failure.update(valid_trajectories(entries, shown_cells or ()))
        failed.append(failure)
    return not failed, {"claimed": claimed, "failed": failed}


# ------------------------------------------------------------------------------------------------- replay tests
def _text(value):
    return type(value) is str and 0 < len(value) <= MAX_PROPERTY_TEXT


def validate_test(test, procedure, entries):
    """None when ``test`` is a well-formed replay test of ``procedure`` on one of ``entries`` ({cell: inputs}), else
    why not."""
    if not isinstance(test, dict) or tuple(sorted(test)) != TEST_KEYS:
        return "keys"
    if type(test["id"]) is not str or TEST_ID.fullmatch(test["id"]) is None:
        return "id"
    entry = entries.get(test["trajectory"]) if type(test["trajectory"]) is str else None
    if entry is None:
        return "trajectory_not_in_scope"
    hook, prop = test["hook"], test["property"]
    if type(hook) is not str or hook not in procedure.hooks or not isinstance(prop, dict) \
            or type(prop.get("kind")) is not str or prop["kind"] not in PROPERTY_KINDS:
        return "hook_or_kind"
    hooks, keys = PROPERTY_KINDS[prop["kind"]]
    stepped = hook in STEP_HOOKS
    if hook not in hooks or set(prop) != {"kind", *keys, *(("step",) if stepped else ())}:
        return "property_shape"
    if stepped and (entry["bench"] != "alfworld" or type(prop["step"]) is not int or prop["step"] < 0):
        return "step"
    kind = prop["kind"]
    if kind in ("note_contains", "discourage_contains", "discourage_excludes") and not _text(prop["value"]):
        return "value"
    if kind == "note_matches" and not (type(prop["value"]) is list and 0 < len(prop["value"]) <= MAX_FRAGMENTS
                                       and all(_text(v) for v in prop["value"])):
        return "value"
    if kind == "binding_equals" and not (_text(prop["name"]) and _text(prop["value"])):
        return "value"
    if kind == "repair_requested" and type(prop["value"]) is not bool:
        return "value"
    if kind == "state_equals" and not (_text(prop["key"]) and len(json.dumps(prop["value"])) <= MAX_PROPERTY_TEXT):
        return "value"
    nonvacuity = test["nonvacuity"]
    if type(test["claims_fix"]) is not bool or not isinstance(nonvacuity, dict) \
            or sorted(nonvacuity) != ["mutation", "withheld_expect"] or nonvacuity["withheld_expect"] is not False:
        return "nonvacuity"
    mutation = nonvacuity["mutation"]
    if mutation is not None and (type(mutation) is not str or mutation not in SUPPORTED_MUTATIONS
                                 or entry["bench"] not in SUPPORTED_MUTATIONS[mutation]):
        return "mutation"
    if kind in ("applies_true", "applies_false") and mutation is None:
        return "predicate_needs_mutation"
    return None


def _fragments(text, fragments):
    position = 0
    for fragment in fragments:
        found = text.find(fragment, position)
        if found < 0:
            return False
        position = found + len(fragment)
    return True


def holds(prop, hook, outcome):
    """Whether the property holds on ``outcome`` (None: the procedure withheld -- no predicate, no output)."""
    outcome = outcome or Outcome("withheld", "withheld")
    kind, step = prop["kind"], prop.get("step")
    entry = outcome.steps[step] if step is not None and step < len(outcome.steps) else None
    if kind in ("applies_true", "applies_false"):
        return outcome.applies is (kind == "applies_true")
    if kind in ("note_contains", "note_matches"):
        text = outcome.note(hook, step)
        return prop["value"] in text if kind == "note_contains" else _fragments(text, prop["value"])
    if kind in ("discourage_contains", "discourage_excludes"):
        found = entry is not None and prop["value"] in entry["discouraged"]
        return found if kind == "discourage_contains" else not found
    if kind == "binding_equals":
        return any(b["name"] == prop["name"] and b["value"] == prop["value"] for b in outcome.bindings)
    if kind == "repair_requested":
        return outcome.repair is prop["value"]
    state = entry["state"] if entry is not None and entry["after"] else None
    return isinstance(state, dict) and prop["key"] in state and digest(state[prop["key"]]) == digest(prop["value"])


def negative_tests(entries, outcomes):
    """The registrar's negative tests: [{cell, test}] violated. A passed ALFWorld episode's last action is not
    discouraged at its step; a passed SpreadsheetBench item does not request a repair."""
    out = []
    for cell, entry in entries.items():
        outcome = outcomes.get(cell)
        if entry["token"] != "pass" or outcome is None:
            continue
        if entry["bench"] == "alfworld":
            acted = [i for i, step in enumerate(entry["steps"]) if type(step["action"]) is str]
            if acted and acted[-1] < len(outcome.steps) \
                    and entry["steps"][acted[-1]]["action"] in outcome.steps[acted[-1]]["discouraged"]:
                out.append({"cell": cell, "test": "winning_action_discouraged"})
        elif entry["bench"] == "spreadsheetbench" and outcome.repair:
            out.append({"cell": cell, "test": "repair_on_passed_item"})
    return out


def reference_tracker_agreement(entries, outcomes):
    """``(agreeing steps, compared steps)`` of an ALFWorld state procedure: every step after which its
    ``alf_after_step`` ran, its state's facts against the reference tracker fed the same events."""
    agree = total = 0
    for cell, entry in entries.items():
        outcome = outcomes.get(cell)
        if entry["bench"] != "alfworld" or outcome is None or not outcome.applies:
            continue
        tracker = ReferenceTracker(str(entry["steps"][0]["view"].get("initial_observation")))
        for i, step in enumerate(entry["steps"]):
            if step["event"] is None:
                continue
            tracker.update(step["event"]["action"], step["event"]["observation"])
            if i < len(outcome.steps) and outcome.steps[i]["after"]:
                total += 1
                agree += facts_agree(outcome.steps[i]["state"], tracker.facts())
    return agree, total


def run_tests(procedure, entries, outcomes, workers, *, inputs_dirs=None):
    """C7: the report of ``procedure``'s replay tests on ``entries`` ({cell: inputs}, the in-scope trajectories) with
    ``outcomes`` (``zero_crash``'s first-worker outcomes); mutated inputs replay in a fresh worker."""
    problems, results = [], []
    tests = list(procedure.replay_tests)
    if not tests or len(tests) > MAX_TESTS:
        problems.append({"reason": "test_count", "detail": len(tests)})
    invalid = [(t.get("id") if isinstance(t, dict) else None, validate_test(t, procedure, entries)) for t in tests]
    problems += [{"reason": "invalid_test", "test": i, "detail": why} for i, why in invalid if why]
    if problems:
        return {"check": "C7", "passed": False, "problems": problems, "tests": []}
    mutated = {}
    for mutation in sorted({t["nonvacuity"]["mutation"] for t in tests} - {None}):
        cells = sorted({t["trajectory"] for t in tests if t["nonvacuity"]["mutation"] == mutation})
        found = replay_many(procedure, [entries[c] for c in cells], workers, inputs_dirs=inputs_dirs,
                            mutation=mutation)
        mutated.update({(mutation, cell): outcome for cell, outcome in found.items()})
    fixed = False
    for test in tests:
        prop, hook, cell = test["property"], test["hook"], test["trajectory"]
        mutation = test["nonvacuity"]["mutation"]
        real = holds(prop, hook, outcomes.get(cell))
        withheld = holds(prop, hook, None)
        perturbed = holds(prop, hook, mutated[(mutation, cell)]) if mutation is not None else None
        predicate = prop["kind"] in ("applies_true", "applies_false")
        nonvacuous = (not withheld and not predicate) or perturbed is False
        results.append({"id": test["id"], "holds": real, "withheld": withheld, "mutated": perturbed,
                        "nonvacuous": nonvacuous})
        if not real:
            problems.append({"reason": "test_failed", "test": test["id"]})
        elif not nonvacuous:
            problems.append({"reason": "vacuous_test", "test": test["id"]})
        elif test["claims_fix"] and entries[cell]["token"] == "fail":
            fixed = True
    if not fixed:
        problems.append({"reason": "no_fix_claim"})
    problems += [{"reason": "negative_test", **n} for n in negative_tests(entries, outcomes)]
    agreement = None
    if "alf_after_step" in procedure.hooks:
        agree, total = reference_tracker_agreement(entries, outcomes)
        agreement = [agree, total]
        if not total or Fraction(agree, total) < TRACKER_AGREEMENT:
            problems.append({"reason": "reference_tracker", "detail": agreement})
    problems += [{"reason": "bindings_not_verbatim", **f} for f in _faults(outcomes, BINDING_KINDS)][:10]
    return {"check": "C7", "passed": not problems, "problems": problems, "tests": results,
            "tracker_agreement": agreement}


def registrar_checks(procedure, entries, outcomes):
    """v2's fatal part of C7 (owner decision 2026-10-23 13:3x, spec-v2): the registrar's own checks of ``run_tests``
    without the engineer's replay tests, which v2 runs as advice only -- the negative tests (``negative_tests``), the
    reference tracker's agreement of an ALFWorld state procedure and the bindings that are not verbatim. The same
    report shape: {"check": "C7", "passed", "problems", "tracker_agreement"}."""
    problems = [{"reason": "negative_test", **n} for n in negative_tests(entries, outcomes)]
    agreement = None
    if "alf_after_step" in procedure.hooks:
        agree, total = reference_tracker_agreement(entries, outcomes)
        agreement = [agree, total]
        if not total or Fraction(agree, total) < TRACKER_AGREEMENT:
            problems.append({"reason": "reference_tracker", "detail": agreement})
    problems += [{"reason": "bindings_not_verbatim", **f} for f in _faults(outcomes, BINDING_KINDS)][:10]
    return {"check": "C7", "passed": not problems, "problems": problems, "tracker_agreement": agreement}


# ------------------------------------------------------------------------------------------------ C8, C9, C4 faults
def format_guard(outcomes):
    """C8: [{cell, hook, step, marker}] of the shown notes carrying an answer-channel marker."""
    out = []
    for cell, outcome in outcomes.items():
        for note in outcome.notes:
            lowered = note["text"].lower()
            hits = [marker for marker in CHANNEL_MARKERS if marker in lowered]
            if hits:
                out.append({"cell": cell, "hook": note["hook"], "step": note["step"], "marker": hits[0]})
    return out


def output_faults(outcomes):
    """C9: the note faults of the lexicon screen and the caps."""
    return [f for f in _faults(outcomes, prefix="note_") if f["kind"] not in BINDING_KINDS + META_KINDS]


def meta_option_faults(outcomes):
    """C4's static ban on outputs: notes the LiveMath meta-option screen dropped."""
    return _faults(outcomes, META_KINDS)


def _texts(value, old, new):
    """``value`` with ``old`` replaced by ``new`` in every text it holds (mapping keys kept)."""
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, dict):
        return {key: _texts(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_texts(item, old, new) for item in value]
    return value


def _holds(value, text):
    """Whether a text in ``value`` contains ``text``."""
    if isinstance(value, str):
        return text in value
    if isinstance(value, dict):
        return any(_holds(item, text) for item in value.values())
    if isinstance(value, list):
        return any(_holds(item, text) for item in value)
    return False


def _behaviour(outcome, mapped=False):
    """{aspect: value} of an ``Outcome`` the counterfactual compares; ``mapped``: the counterfactual's, its texts with
    ``META_FILLER`` mapped back to the meta option."""
    back = (lambda value: _texts(value, META_FILLER, LIVEMATH_META_OPTION)) if mapped else (lambda value: value)
    return {"applies": outcome.applies,
            "notes": [[n["hook"], n["step"], back(n["text"])] for n in outcome.notes],
            "bindings": back(outcome.bindings), "repair": outcome.repair,
            "steps": [[back(s["note"]), back(s["discouraged"]), digest(s["state"]), s["after"]] for s in outcome.steps],
            "faults": [[f["hook"], f["step"], f["kind"]] for f in outcome.faults]}


def meta_counterfactual(procedure, entries, outcomes, workers, *, inputs_dirs=None):
    """C4's meta-option counterfactual (module docstring; v2.1 ``protocol.META_COUNTERFACTUAL``):
    [{cell, kind: "meta_counterfactual", aspects}] of the in-scope LiveMath trajectories of ``entries`` ({cell:
    inputs}) whose view holds the meta option (``LIVEMATH_META_OPTION``) on which ``procedure``, replayed in a fresh
    worker (PYTHONHASHSEED 0) with every occurrence of the option's text replaced by ``META_FILLER``, behaves otherwise
    than in ``outcomes`` (``zero_crash``'s first-worker outcomes); ``aspects``: the differing ones of ``_behaviour``,
    in its order. Zero model calls."""
    present = [entry for cell, entry in entries.items() if entry["bench"] == "livemath" and cell in outcomes
               and _holds([entry["view"], entry["request_view"]], LIVEMATH_META_OPTION)]
    if not present:
        return []
    replaced = [_texts(entry, LIVEMATH_META_OPTION, META_FILLER) for entry in present]
    found = replay_many(procedure, replaced, workers, hashseed=0, inputs_dirs=inputs_dirs)
    out = []
    for entry in present:
        real, counter = _behaviour(outcomes[entry["cell"]]), _behaviour(found[entry["cell"]], mapped=True)
        aspects = [aspect for aspect in real if real[aspect] != counter[aspect]]
        if aspects:
            out.append({"cell": entry["cell"], "kind": COUNTERFACTUAL, "aspects": aspects})
    return out
