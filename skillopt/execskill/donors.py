"""The frozen donor corpus of the paired placebo P_y (protocol ``fivebench-execskill-v1``; registration §6.1 "供体语料"
after Codex F4, §3.2 seed tags, §3.4 sealing, §5.1; implementation plan §1 donors.py, §3 "Placebo arms",
T-PLACEBO-1 and T-PLACEBO-6).

Donors are the parent's run-slice trajectories of the bench (§5.1, item x run), which never overlap the acceptance
slice, so their content is of no use on an acceptance item. Before the round is sealed the registrar runs every changed
procedure -- the new or revised version, the original procedure for a deletion or a narrowing (§6.1 edit-type table) --
on every donor in the sandbox, with ZERO model calls and nothing but the stored trajectory:

- ``before_call`` (state None, as the shell calls it) and ``bindings`` on the donor's public view, i.e. the view of its
  first request (the user JSON without ``procedure_notes``);
- ``sheet_feedback`` on the donor's stored pre-check report (a donor without one gives no sheet advice);
- ALFWorld: ``alf_before_step`` step by step along the stored episode, ``alf_after_step`` fed the stored events in order
  (each event rebuilt from the step's action and the next request's observation and admissible commands, as the shell
  builds it), the host keeping the state within the procedure's declared bytes.

Faults follow the shell (§2.3, P1; ``solver._Shell.shaped``): a failed call or a value of the wrong shape is recorded
and the procedure gives no further output on that donor. Every output is screened as the shell screens a note
(``notes.screen``; bindings verified verbatim on the donor's OWN public text, ``notes.check_bindings``), so a sham shown
in the placebo arm never faults there. ALFWorld keeps, per step, the screened fields and the NUMBER of discouraged
admissible commands: the commands themselves are drawn at dispatch (``solver.sham_discouraged``).

The corpus is a sealed ``fivebench-execskill-v1-donor-corpus`` record: per (procedure, donor) the outputs and their
content hash, the sha256 of each donor trajectory (``verify`` refuses a trajectory changed after sealing) and the
faults. ``pair`` gives each acceptance item one donor with the seed ``execskill-v1:yoke:<unit>`` (``router.yoke``,
reuse counted); ``output`` reads one sham output, a step beyond the donor's last giving its last step.

Trajectory contract (plan §2.3; ``trajectories.py`` is A8's): ``{"cell": donor id, "task_id": run-slice item, "bench",
"arm_kind": "parent", "calls": [{"purpose", "user"}, ...], "shell": {"precheck": report or None}, "alfworld_steps":
[{"action"}, ...]}``. A run-slice unit also holds card-arm cells (the descriptive entry reading, §5.1); only the
parent's (``arm_kind`` "parent") are donors. Every SpreadsheetBench trajectory carries its pre-check report: the shell
pre-checks every extracted program (§2.5; ticket A9-1, integration B3).
"""
from __future__ import annotations

import json

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import notes, router
from .errors import ConfigurationError
from .package import default_applies, Package, edits
from .profiles import SUPPORTED_BENCHES as BENCHES, NOTES_KEY, RECORD_HASH, SANDBOX_TIMEOUTS, record, verified

QA_HOOKS = ("before_call", "bindings")
SHEET_HOOK = "sheet_feedback"
STEP_HOOK, AFTER_HOOK = "alf_before_step", "alf_after_step"
SHAM_HOOKS = QA_HOOKS + (SHEET_HOOK, STEP_HOOK)  # the hooks whose content a placebo shows
REPORT_KEYS = ("status", "exc_type", "message", "answer_cells")  # what sheet_feedback sees (solver.REPORT_KEYS)
OBSERVATION_CHARS = 12000  # the shell's event observation (backends.py:756)


def public_text(value):
    """Every text of a public view, joined: the verbatim reference of a binding (the shell's ``_public_text``)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(public_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(public_text(v) for v in value)
    return "" if value is None else str(value)


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


def donor_inputs(trajectory, *, bench):
    """``{"id", "item", "view", "report", "steps"}`` of one stored run-slice trajectory (module docstring): QA and
    SpreadsheetBench the first request's view and the stored pre-check report; ALFWorld per step its view and the event
    after it (None after the last step, whose state no later step reads, and after a last request that got no usable
    reply: the shell sent it, so its view still gets ``alf_before_step``, but it has no action; ticket A10-2)."""
    require(isinstance(trajectory, dict) and trajectory.get("bench") == bench, "A trajectory of the bench")
    donor, item = trajectory.get("cell"), trajectory.get("task_id")
    require(type(donor) is str and donor and type(item) is str and item, "A trajectory names its cell and item")
    calls = trajectory.get("calls") or []
    if bench != "alfworld":
        require(calls and calls[0].get("purpose") == "first", "A QA or sheet trajectory starts with its first call")
        report = (trajectory.get("shell") or {}).get("precheck")
        return {"id": donor, "item": item, "view": _view(calls[0], bench=bench), "report": report, "steps": None}
    views = [_view(c) for c in calls if c.get("purpose") == "step"]
    actions = [s.get("action") for s in trajectory.get("alfworld_steps") or []]
    # the shell logs a step only after a usable reply, so the last request may have none (ticket A10-2)
    require(len(views) in (len(actions), len(actions) + 1), "One request per stored ALFWorld step, at most one more")
    steps = []
    for i, view in enumerate(views):
        event = None
        if i < len(actions) and i + 1 < len(views):
            following = views[i + 1]
            event = {"step": i, "action": actions[i],
                     "observation": str(following["observation"])[:OBSERVATION_CHARS],
                     "admissible_commands": list(following["admissible_commands"])}
        steps.append({"view": view, "event": event})
    return {"id": donor, "item": item, "view": None, "report": None, "steps": steps}


def changed(parent, candidate):
    """``[(edit kind, procedure, side)]`` of the step's edits: the procedure a placebo shams for each edit and the
    package holding it (``candidate`` for a new or revised procedure, ``parent`` for a deletion or a narrowing)."""
    return [(e.kind, e.new, "candidate") if e.kind in ("new", "revision") else (e.kind, e.old, "parent")
            for e in edits(parent, candidate)]


# The shell and diagnostics share these return-shape rules. The tuple is the
# required exact type and, for containers, the required exact item type.
NOTE_SHAPE_EXTRAS = {"before_call": None, "bindings": None,
                     "sheet_feedback": "request_repair", "alf_before_step": "discourage"}
SHAPE_EXTRA_TYPES = {"request_repair": (bool, None), "discourage": (list, str)}


def shape_extra(hook):
    return NOTE_SHAPE_EXTRAS.get(hook)


def expected_shape(hook):
    """Describe the very same types consumed by ``shaped`` and the live shell."""
    extra = shape_extra(hook)
    if extra is None:
        return "None or {<note fields>}"
    outer, item = SHAPE_EXTRA_TYPES[extra]
    suffix = ("[<command strings>]" if outer is list and item is str else "<%s>" % outer.__name__)
    return 'None or {"fields": {<note fields>}, "%s": %s}' % (extra, suffix)


def shaped(value, extra):
    """A hook value in the shell's shapes (``solver._Shell.shaped``): ``(fields, extra value)``; None for a wrong
    shape. ``extra``: None (``before_call``, ``bindings``), ``"request_repair"`` or ``"discourage"``."""
    outer, item = SHAPE_EXTRA_TYPES.get(extra, (list, str)) if isinstance(extra, str) else (list, str)
    default = outer()
    if value is None:
        return {}, default
    if extra is None:
        return (value, None) if isinstance(value, dict) else None
    if isinstance(value, dict) and set(value) <= {"fields", extra}:
        fields, other = value.get("fields") or {}, value.get(extra, default)
        valid = type(other) is outer and (item is None or all(type(c) is item for c in other))
        if isinstance(fields, dict) and valid:
            return fields, other
    return None


class _Run:
    """One procedure's hooks on one donor, with the shell's fault rule."""

    def __init__(self, worker, procedure, donor, bench, faults):
        self.worker, self.procedure, self.donor, self.bench, self.faults = worker, procedure, donor, bench, faults
        self.dead = False

    def fault(self, hook, kind):
        self.faults.append({"procedure": self.procedure.id, "donor": self.donor, "hook": hook, "kind": kind})
        self.dead = True

    def raw(self, fn, args):
        """``(ok, value)`` of one sandbox call; a failed call is a fault."""
        result = self.worker.call(self.procedure.id, fn, list(args), timeout_s=SANDBOX_TIMEOUTS["hook"])
        if result.get("ok") is not True:
            self.fault(fn, result.get("fault"))
            return False, None
        return True, result.get("value")

    def hook(self, fn, args, extra=None):
        """``(fields, extra value)`` of one note hook; None once the procedure has faulted on this donor."""
        if self.dead:
            return None
        ok, value = self.raw(fn, args)
        if not ok:
            return None
        found = shaped(value, extra)
        if found is None:
            self.fault(fn, "output_shape")
        return found

    def fields(self, found, text, hook):
        """The screened fields (bindings checked verbatim on the donor's own public text); {} after a fault."""
        if found is None:
            return {}
        modern = notes.outcome_judged(self.procedure)
        kept, dropped = notes.screen(found[0], bench=self.bench,
                                     **({"outcome_judged": True, "public_text": text, "audited": notes.audited(self.procedure)} if modern else {}))
        if modern:
            _, header_drops = notes.screen_header(self.procedure.header,
                **({"audited": True, "bench": self.bench} if notes.audited(self.procedure) else {}))
            dropped += header_drops
        if "bindings" in kept:
            bindings, unverified = notes.check_bindings(kept.pop("bindings"), text)
            if modern:
                dropped += unverified
            if bindings:
                kept["bindings"] = bindings
        kept = notes.suppress_faulted(kept, dropped, outcome_judged=modern)
        if modern:
            faults = notes.fault_drops(dropped, outcome_judged=True)
            for row in dropped:
                if row in faults:
                    self.fault(hook, "note_" + row["reason"])
                    self.faults[-1].update(row)
                else:
                    self.faults.append({"procedure": self.procedure.id, "donor": self.donor, "hook": hook,
                                        "kind": "note_" + row["reason"], "informational": True, **row})
            if kept:
                text = notes.render(kept, bench=self.bench, header=self.procedure.header)
                if len(text) > self.procedure.max_note_chars:
                    self.fault(hook, "note_over_declared_cap")
                    return {}
        return kept


def _outputs(run, inputs):
    """{hook: content} of one procedure on one donor (module docstring)."""
    hooks, out = run.procedure.hooks, {}
    if inputs["steps"] is None:
        text = public_text(inputs["view"])
        for hook in QA_HOOKS:
            if hook in hooks:
                args = [inputs["view"], None] if hook == "before_call" else [inputs["view"]]
                out[hook] = run.fields(run.hook(hook, args), text, hook)
        if run.dead and notes.outcome_judged(run.procedure):
            out = {hook: {} for hook in out}
        if SHEET_HOOK in hooks and inputs["report"] is not None:
            report = {key: inputs["report"].get(key) for key in REPORT_KEYS}
            out[SHEET_HOOK] = run.fields(run.hook(SHEET_HOOK, [inputs["view"], report, None], shape_extra(SHEET_HOOK)), text,
                                         SHEET_HOOK)
        return out
    if STEP_HOOK not in hooks:
        return out
    state, entries = None, []
    for step in inputs["steps"]:
        view = step["view"]
        found = run.hook(STEP_HOOK, [view, state], shape_extra(STEP_HOOK))
        admissible = view["admissible_commands"] if isinstance(view["admissible_commands"], list) else []
        commands = [c for c in dict.fromkeys(found[1]) if c in admissible] if found is not None else []
        reference = public_text([view["initial_observation"], view["observation"]])
        fields = run.fields(found, reference, STEP_HOOK)
        if run.dead and notes.outcome_judged(run.procedure):
            commands = []
        entries.append({"fields": fields, "discourage": len(commands)})
        if AFTER_HOOK in hooks and step["event"] is not None and not run.dead:
            ok, new = run.raw(AFTER_HOOK, [step["event"], state])
            if ok and len(json.dumps(new, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()) > run.procedure.state_bytes:
                run.fault(AFTER_HOOK, "state_over_declared_bytes")
            elif ok:
                state = new
    out[STEP_HOOK] = entries
    return out


def procedure_outputs(worker, procedure, inputs, *, bench, faults):
    """{hook: screened content} of one procedure on one input (``donor_inputs``' shape) through a started worker;
    faults are appended to ``faults``. The donor corpus runs it on donors, ``placebo.real_lengths`` on the public view
    of an acceptance item (lengths only)."""
    return _outputs(_Run(worker, procedure, inputs["id"], bench, faults), inputs)


def donor_corpus(candidate, parent, trajectories, workers):
    """The sealed corpus of one acceptance round (zero model calls). ``trajectories``: the parent's run-slice
    trajectories of the bench (module docstring), one donor each; ``workers(package, item)``: a context manager
    yielding a started sandbox worker holding ``package`` for the run-slice ``item`` (``router.plan``'s factory)."""
    require(isinstance(candidate, Package) and isinstance(parent, Package)
            and candidate.parent_sha256 == parent.sha256, "A candidate and its parent")
    require(trajectories, "A donor corpus needs the parent's run-slice trajectories")
    require(all(t.get("arm_kind") == "parent" for t in trajectories),
            "Donors are the parent's trajectories (arm kind parent): never a card, placebo, twin or candidate cell")
    bench = trajectories[0].get("bench")
    require(bench in BENCHES, "Trajectories of a known bench")
    procedures = changed(parent, candidate)
    inputs = [donor_inputs(t, bench=bench) for t in trajectories]
    donors = [entry["id"] for entry in inputs]
    require(len(set(donors)) == len(donors), "Donor ids are distinct")
    outputs, faults = {p.id: {} for _, p, _ in procedures}, []
    for entry in inputs:
        for side, package in (("candidate", candidate), ("parent", parent)):
            mine = [p for _, p, s in procedures if s == side]
            if not mine:
                continue
            with workers(package, entry["item"]) as worker:
                for procedure in mine:
                    outputs[procedure.id][entry["id"]] = procedure_outputs(worker, procedure, entry, bench=bench,
                                                                           faults=faults)
    return record("donor-corpus", candidate.evidence, {
        "bench": bench, "candidate_sha256": candidate.sha256, "parent_sha256": parent.sha256,
        "procedures": [{"id": p.id, "edit": kind, "side": side, "sha256": p.sha256} for kind, p, side in procedures],
        "donors": donors, "items": {entry["id"]: entry["item"] for entry in inputs},
        "sources": {t["cell"]: digest(t) for t in trajectories}, "outputs": outputs,
        "hashes": {pid: {d: digest(o) for d, o in per.items()} for pid, per in outputs.items()},
        "faults": faults,
        **({"routing": {p.id: {entry["id"]: {"applies": "default_true"} for entry in inputs}
                         for _, p, _ in procedures if default_applies(p)},
            "keyword_hits": notes.keyword_summary(faults)}
           if any(notes.audited(p) for _, p, _ in procedures) else {})})


def seal(corpus):
    """The corpus hash, after verifying the record (a changed corpus is refused)."""
    return verified(corpus, "donor-corpus")[RECORD_HASH]


def verify(corpus, trajectories):
    """Refuse donor trajectories changed after sealing (a redo re-dispatches with the SAME sealed inputs, §3.4)."""
    corpus = verified(corpus, "donor-corpus")
    found = {t.get("cell"): digest(t) for t in trajectories}
    moved = sorted(d for d, sha in corpus["sources"].items() if found.get(d) != sha)
    if moved:
        raise ConfigurationError("sealed_input_changed: donor trajectories %s" % ", ".join(moved[:5]))


def pair(items, corpus, unit):
    """``{"pairs": {item: donor}, "reuse": {donor: n}}``: one donor per acceptance item by ``yoke_tag(unit)``
    (``router.yoke``: with fewer donors than items the donors rotate, reuse counted)."""
    return router.yoke(items, verified(corpus, "donor-corpus")["donors"], unit)


def output(corpus, procedure_id, donor, hook, step=0):
    """One sham output: the fields of a QA/SpreadsheetBench hook, or ALFWorld's ``{"fields", "discourage"}`` at
    ``step`` (the donor's last step beyond its end; nothing when the donor has no step)."""
    require(hook in SHAM_HOOKS and type(step) is int and step >= 0, "A sham hook and a step")
    content = corpus["outputs"][procedure_id][donor].get(hook)
    if hook != STEP_HOOK:
        return dict(content or {})
    if not content:
        return {"fields": {}, "discourage": 0}
    return dict(content[min(step, len(content) - 1)])


def segments(corpus, procedure_id, donor, hook, step=0):
    """The donor's fields for ``hook`` from ``step`` on, in order: what a short sham is extended with (§6.1, "the same
    donor's next output"). A QA/SpreadsheetBench hook has one segment."""
    if hook != STEP_HOOK:
        return [output(corpus, procedure_id, donor, hook)]
    content = corpus["outputs"][procedure_id][donor].get(hook) or []
    return [entry["fields"] for entry in content[min(step, max(len(content) - 1, 0)):]] or [{}]
