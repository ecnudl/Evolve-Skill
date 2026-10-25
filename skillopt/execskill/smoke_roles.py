"""The smoke's S3, the method roles (registration §10 S3 row, §7.2, §21 owner rule (b); implementation plan §10 step
7; notes/C7d.md; registrar addendum 2026-10-22 14:3x). S3 needs nothing of another stage, so it runs beside S2
(order S0 -> S1 -> S2 || S3 -> S-E6 -> summary):

0. Its own run unit first (``own_run``): the S4 mini-step's run sub-step only -- SearchQA step 1 of chain "smoke"
   from the smoke's empty parent on the 60 S4 smoke items (its run slice, the first ``S4_SLICES["run"]``, as the
   parent arm, ``SLICES`` runs each), no accept, no freeze, no drill -- under ``<root>/units/S3`` (``s1-searchqa/run``,
   its sealed slices and its own consumption registry ``history`` in the smoke namespace), charged to the smoke
   ledger's one solver scope after this process's single confirmation cell (``smoke._confirm``, unit
   ``<root>/units/S3/confirm-<n>``; plan §10 step 4). Its run trajectories are the only ones ``engineer.Context``
   admits (``engineer.RUN_UNIT``); S4, whose run unit C7d's S3 read, is not a stage of the trimmed smoke (13:0x).

Then one copied unit ``<root>/units/S3/roles`` (``units.run_unit``) on the Setting of the verified smoke manifest
makes the six registered GLM-5.3 role calls once each and judges whether each flow ran through -- its result need not
pass -- into the one write-once stage record ``<root>/stages/S3.json`` (``smoke.record``, judged by
``smoke.s3_roles``). The roles unit makes zero solver calls.

1. The leakage adjudication (``coevo5.leakage.adjudicate``) of a registrar-fixed rule text (the description of the
   engineering fixture fx-note) is the FIRST call; its first send must come back as a confirmed reply of the
   registered model (``ok`` and an echo in the role client's ``response_model_ids``) before anything else is sent --
   the guard refuses every later send (a resend included) of an attempt whose first reply was not confirmed and the
   unit pauses ``first_call_not_confirmed``.
2. One engineer step (``engineer.run``: proposal, the fixed checks C1-C9, at most one fix per change) on the stored
   run trajectories of S3's own run unit ``<root>/units/S3/s1-searchqa/run`` (label ``smoke/s1-searchqa/run``, a run
   unit's); references of its failed items, the run items as the leakage corpus, detector counts of its parent cells.
3. One detector write and its hold-half validation (``examiner.detector_payload`` / ``detector_write``,
   ``detectors.seal_candidates`` before the hold half is read, ``detectors.validate`` in the sandbox) on the parent-arm
   trajectories of the same run unit, split by item -- the input of a step's diagnose unit (``step._diagnose``), so
   S3 waits for no S2 unit.
4. One LiveMath generation THROUGH research (§21 (b)): one ``family_material`` request for the definition of
   "derivative" (``research.Researcher``: screened by the frozen mechanical leakage checks of the LiveMath smoke
   items, at most 8 calls, Wikipedia through the explicit gateway ``protocol.GATEWAY`` with ``trust_env=False``, the
   frozen archive of the manifest's data pins opened read-only with its index hash checked, every fetched page archived
   write-once under the attempt's ``research/sources/``, the quote checked verbatim). Generation consumes only that
   finding: before the generator call its provenance is re-checked (the request's calls were made through this
   attempt's roles, its page is archived here under its own digest, the quote is verbatim on it) and a material of
   any other origin raises ``ConfigurationError`` (``generation_without_research``) -- no fallback; a request that
   finds nothing leaves the generation unrun. The examiner's specs are built by the registered families with the
   registrar's checker (``livemath.WorkerChecker``: ``CHECKER_SOURCE`` in a generator sandbox, sympy only in the
   pinned image); at least ``MIN_CHECKED`` items must be kept with a checker-solved truth.
5. The describer (``describer.describe``, one call) on the engineer's first surviving procedure with a note hook,
   else on the fixture fx-note; its note lengths replayed on the run unit's parent cells (zero model calls).

Money (§9.3; registrar addendum 14:3x: S3's GLM limit is the smoke's registered GLM cap, 2M, not §10's estimate
"GLM <= 0.5 M"): every call is GLM-5.3 through the frozen client on ``smoke:glm``
(``budgets.glm_scopes("smoke", role, None, None)``, ``setting.clients(ROLE_MODEL, None)``, B = ``ROLE_MAX_TOKENS``, as
``step._Step.roles`` in smoke mode), plus the accounting sub-scope ``METER_SCOPE`` (declared at the smoke GLM cap, so it
never binds before ``smoke:glm``) that keeps S3's settled spend across attempts. Before an endpoint reserves anything,
the guard refuses (``BudgetStop``: the unit pauses ``budget``, nothing reserved or sent) a send whose single-attempt
bound (``coevo5.ledger.attempt_bound``) would take S3's spend over ``S3_GLM_CAP``; a reservation-based sub-scope
cannot, since one 220 KB request reserves four attempt bounds (~0.95M) by itself. The spend -- before this attempt,
charged in it, per role -- is recorded, and the stage's row ``glm_cap`` fails if retries took it over the cap.

Real mode reuses ``smoke._backends`` (the smoke solver's credential -- the elucid env path, or in a chain-G smoke chain
G's credential repository, registrar addendum 2026-10-23 02:3x -- and the roles' credential repository must be the
manifest's, the code map and image are verified); fake mode (``S3Rehearsal`` of
``tests/execskill_fakes_s3.py``, imported only there) names no credential.
"""
from __future__ import annotations

import contextlib
import functools
import re
from dataclasses import replace

from skillopt.coevo5 import leakage
from skillopt.coevo5.calls import Recorder
from skillopt.coevo5.ledger import attempt_bound, request_bytes
from skillopt.coevo5.roles import Roles
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import (budgets, describer, detectors, engineer, examiner, fixtures, manifest, protocol, replay, research,
               rounds, slots, smoke, solver, step, trajectories, units)
from .cells import Pause
from .errors import BudgetStop, ConfigurationError
from .generators import livemath
from .package import empty
from .registry import Registry
from .sandbox import client as sandbox

STAGE = "S3"
UNIT_NAME = "roles"  # <root>/units/S3/roles, label "smoke/S3/roles"
S3_GLM_CAP = protocol.SMOKE_CAPS["glm"]  # registrar addendum 14:3x: the smoke GLM cap 2M (§10's 0.5M was an estimate)
METER_SCOPE = budgets.SMOKE + ":glm:s3"  # S3's accounting sub-scope of smoke:glm
ROLES_USED = ("leakage", "engineer", "examiner", "examiner_research", "describer")
BENCH = "searchqa"  # the engineer's and the detector's bench: S3's own run unit (the S4 mini-step's run sub-step)
K = 1  # the mini-step's step number (its run unit is s1-searchqa)
RULE_PROCEDURE = "fx-note"  # the adjudicated rule: this engineering fixture's description (registrar text)
LIVEMATH = "livemath"
CONCEPT = "derivative"  # the family_material request (livemath.derivative's concept)
GENERATOR = "g-livemath-1-1"
SET_NAME = "G_self"
MIN_CHECKED = 5  # §10 S3 row: the truth checker on >= 5 generated items
CATEGORY = re.compile(r"[a-z][a-z0-9_]{0,39}")


def _unit_label(name):
    return "smoke/%s/%s" % (STAGE, name)


def unit_root(spec, name=UNIT_NAME):
    return safe_path(spec["root"]) / smoke.UNITS_DIR / STAGE / name


def run_root(spec):
    """S3's own run unit ``<root>/units/S3/s1-searchqa/run`` (registrar addendum 14:3x)."""
    return units.unit_path(safe_path(spec["root"]) / smoke.UNITS_DIR / STAGE, K, BENCH, "run")


def own_run(spec, m, manifest_path, *, fake=False, env_path=None, roles_repo=None):
    """Piece 0 (module docstring; registrar addendum 14:3x): S3's own run unit -- ``step._run`` of the S4 mini-step
    (``step.SmokeStep`` without a drill and with the smoke's empty parent; nothing after its run sub-step) on the
    smoke backends (``smoke._backends``: real, the named credentials must be the manifest's; fake, the S2 rehearsal's
    plan-§7 fakes). Before a run unit that is not complete, this process's single confirmation cell
    (``smoke._confirm``). A completed run unit is read back (same run and identity) and nothing is sent. Returns the
    run unit's record, or the stopped report {"stage", "complete": False, "stopped", "reason", "unit"} of a unit
    that paused (its attempt kept; the owner's recorded decision before the next ``smoke-run``)."""
    path = run_root(spec)
    chain_root = path.parent.parent
    with smoke._backends(spec, m, manifest_path, fake=fake, env_path=env_path, roles_repo=roles_repo) as (setting, _):
        items = smoke._slice("S4", BENCH, setting.pools[BENCH])
        parent = empty(step="smoke/s0", evidence=setting.evidence)
        services = replace(manifest.services_of(m, budgets.SMOKE, setting=setting),
                           registry=Registry(chain_root / smoke.DRILL_HISTORY, evidence=setting.evidence))
        mini = step.SmokeStep(items=tuple(items), candidate=replace(fixtures.fixture_package(),
                                                                    parent_sha256=parent.sha256),
                              model=smoke.solver_of(spec).model)  # registrar addendum 2026-10-23 02:3x
        st = step._Step(setting, services, budgets.SMOKE, step.SMOKE_BENCH, K, parent, chain_root, mini)
        try:
            if not (path / "unit.json").exists():
                smoke._confirm(spec, setting, STAGE, BENCH, items[0])
            step._run(st, step._slices(st))
        except Pause as pause:
            return {"stage": STAGE, "complete": False, "stopped": pause.kind, "reason": pause.reason,
                    "unit": pause.cell}
    return protocol.verified(read_json(path / "unit.json"), "unit")


# ----------------------------------------------------------------------------------------------------- the guard
class Guard:
    """S3's GLM guards over every role endpoint of one attempt (module docstring): the first reply and the cap.
    ``before``: S3's spend in earlier attempts (``METER_SCOPE`` settled + open)."""

    def __init__(self, before, *, cap, response_ids, unit):
        self.before, self.cap, self.response_ids, self.unit = before, cap, frozenset(response_ids), unit
        self.spent, self.by_role, self.sends, self.first, self.refused = 0, {}, 0, None, None

    def total(self):
        return self.before + self.spent

    def confirmed(self):
        return self.first is not None and self.first["confirmed"]

    def gate(self):
        """Nothing is sent (or waited for) after an unconfirmed first reply."""
        if self.first is not None and not self.first["confirmed"]:
            raise Pause("first_call_not_confirmed", "nothing is sent after an unconfirmed first S3 reply (%s)"
                        % self.first["label"], self.unit)

    def admit(self, size, max_tokens, label):
        """Before the endpoint reserves: ``gate``; nothing whose single-attempt bound would take S3 over its cap."""
        self.gate()
        bound = attempt_bound(size, max_tokens)
        if self.total() + bound > self.cap:
            self.refused = {"label": label, "attempt_bound": bound, "total": self.total(), "cap": self.cap}
            raise BudgetStop("budget_stop:%s:%d" % (METER_SCOPE, self.cap))

    def after(self, role, label, sends):
        """Every send's charge; the first sent request's receipt decides the confirmation."""
        for entry in sends:
            if type(entry.get("charged")) is int:
                self.spent += entry["charged"]
                self.by_role[role] = self.by_role.get(role, 0) + entry["charged"]
            if "receipt" not in entry:
                continue  # refused, halted or failed before anything was sent
            self.sends += 1
            if self.first is None:
                receipt = entry["receipt"] if isinstance(entry["receipt"], dict) else {}
                model, error = receipt.get("returned_model"), receipt.get("error_type")
                model = model if isinstance(model, str) and model in self.response_ids else None
                confirmed = receipt.get("ok") is True and model is not None
                self.first = {"label": label, "confirmed": confirmed,
                              "returned_model": model or "other",
                              "error_type": error if isinstance(error, str) and CATEGORY.fullmatch(error) else None}

    def state(self):
        return {"cap": self.cap, "scope": METER_SCOPE, "before": self.before, "spent": self.spent,
                "total": self.total(), "within_cap": self.total() <= self.cap,
                "by_role": dict(sorted(self.by_role.items())), "sends": self.sends, "first": self.first,
                "refused": self.refused}


class Metered:
    """One role's frozen ``calls.Endpoint`` behind the guard: ``send`` asks the guard BEFORE the endpoint reserves
    anything and reports every send's charge afterwards; ``recorder`` is the frozen ``Recorder`` over this object, so
    a resend passes the guard too -- and its cooldown is not waited for when the guard refuses everything after an
    unconfirmed first reply."""

    def __init__(self, endpoint, guard, role):
        self.endpoint, self.guard, self.role = endpoint, guard, role
        self.model, self.max_tokens, self.cooldown = endpoint.model, endpoint.max_tokens, endpoint.cooldown

    def recorder(self, *, label, on_reply=None):
        return Recorder(self, label, on_reply)

    def sleep(self, seconds):
        self.guard.gate()
        self.endpoint.sleep(seconds)

    def send(self, system, user, recorder):
        self.guard.admit(request_bytes(system, user), self.max_tokens, recorder.label)
        before = len(recorder.sends)
        try:
            return self.endpoint.send(system, user, recorder)
        finally:
            self.guard.after(self.role, recorder.label, recorder.sends[before:])


def role_set(setting, guard):
    """{role: frozen ``Roles``} of one attempt: GLM-5.3 on ``smoke:glm`` + ``METER_SCOPE`` with B =
    ``ROLE_MAX_TOKENS`` (``step._Step.roles`` in smoke mode), each endpoint behind ``guard``."""
    client = setting.clients(protocol.ROLE_MODEL, None)
    require(client.model == protocol.ROLE_MODEL, "Every method role is GLM-5.3")
    out = {}
    for role in ROLES_USED:
        scopes = budgets.glm_scopes(budgets.SMOKE, role, None, None) + (METER_SCOPE,)
        endpoint = budgets.endpoint(setting, scopes, client=client, max_tokens_bound=protocol.ROLE_MAX_TOKENS)
        out[role] = units.roles(Metered(endpoint, guard, role), configuration=protocol.configuration_of(setting))
    return out


# ----------------------------------------------------------------------------------------------------- the pieces
def rule_text():
    """The adjudicated rule: the description of the engineering fixture ``RULE_PROCEDURE`` (registrar text)."""
    return next(p.description for p in fixtures.fixture_package().procedures if p.id == RULE_PROCEDURE)


def _leakage(roles, unit, guard):
    text = rule_text()
    label = "leak/%s/%s" % (unit, RULE_PROCEDURE)
    keep = leakage.adjudicate(roles, text, label=label)
    if not guard.confirmed():
        raise Pause("first_call_not_confirmed", "the single first S3 reply is not a confirmed %s reply"
                    % protocol.ROLE_MODEL, unit)
    call = roles.calls[-1]
    return {"label": label, "rule_sha256": digest(text), "valid": call["valid"], "keep": keep,
            "reason": call["reason"]}


def _engineer(roles, setting, workers, unit, run, evidence):
    parents = [t for t in run if t["arm_kind"] == "parent"]
    by_key = {rounds.key(BENCH, item["task_id"]): item for item in setting.pools[BENCH]}
    keys = sorted({t["task_id"] for t in run})
    require(all(key in by_key for key in keys), "S3's run unit's items are smoke SearchQA items")
    failed = {t["task_id"] for t in parents if t["token"] == "fail"}
    references = {}
    for key in sorted(failed):
        private = by_key[key]["private"]
        reference = private.get("answer", private.get("answers"))
        if isinstance(reference, (str, list)) and reference:
            references[key] = reference
    routing = {}
    if protocol.CHECK_NON_FIRING[protocol.configuration_of(setting)]:
        routing = {"routing_items": [(key, solver.routing_view(BENCH, by_key[key]["public"])) for key in keys],
                   "routing_workers": lambda package, key: workers(package, kind="cell", inputs_dir=None),
                   "routing_shared_worker": True}
    ctx = engineer.Context(bench=BENCH, k=K, step=unit, evidence=evidence, parent=empty(step="smoke/s0",
                                                                                        evidence=evidence),
                           trajectories=run, corpora={BENCH: leakage.Corpus(BENCH, [by_key[k] for k in keys])},
                           workers=workers, roles=roles, label=unit, card=setting.cards.get(BENCH, ""),
                           references=references, inputs_dirs=None, configuration=protocol.configuration_of(setting),
                           detectors=detectors.counts(detectors.diagnosis(parents, bench=BENCH)), previous=None,
                           **routing)
    candidate, sealed = engineer.run(ctx)
    checked = [c for c in sealed["changes"] if c["attempts"] and c["attempts"][-1]["checks"]]
    ran = (any(p["parsed"] for p in sealed["proposals"]) and bool(sealed["changes"])
           and len(checked) == len(sealed["changes"]))
    return {"record": sealed, "candidate_sha256": candidate.sha256 if candidate is not None else None,
            "changes": len(sealed["changes"]), "survived": sum(1 for c in sealed["changes"] if c["survived"]),
            "ran": ran}, candidate


def _detector(roles, workers, unit, card, attempt, evidence):
    halves = detectors.split(card, bench=BENCH, unit=unit)
    payload = examiner.detector_payload(halves, bench=BENCH, library=(), workers=workers)
    candidates, written = examiner.detector_write(roles, payload, k=K, label=unit, evidence=evidence)
    out = {"split": {key: value for key, value in halves.items() if key not in ("write", "hold")},
           "written": written, "validation": None, "detectors": [], "ran": False}
    if candidates:
        source = unit + "/write-half"
        sealed = detectors.seal_candidates(attempt / "detectors", candidates, unit=unit, written_from=source,
                                           evidence=evidence)
        validation = detectors.validate(sealed, candidates, halves, bench=BENCH, library=[], workers=workers,
                                        evidence=evidence)
        out.update(validation=validation, ran=validation["status"] == "ok",
                   detectors=detectors.detector_records(validation, candidates, written_from=source,
                                                        evidence=evidence))
    return out


def provenance(found, researcher, roles, store):
    """§21 owner rule (b) in the S3 path: the material the generation consumes is the finding of THIS attempt's one
    dispatched research request -- its calls went through ``roles``, its page is archived write-once in ``store``
    under its own digest, the quote is verbatim on it. Anything else raises ``ConfigurationError``."""
    label = "%s/family_material-1/" % researcher.label
    if not (isinstance(found, dict) and found.get("status") == "found" and found.get("purpose") == "definition"
            and researcher.log and researcher.log[-1] is found and researcher.dispatched() == 1
            and type(found.get("calls")) is int and 1 <= found["calls"] <= protocol.RESEARCH_MAX_CALLS
            and roles.count(label) == found["calls"] and type(found.get("archive")) is str):
        raise ConfigurationError("generation_without_research: no dispatched research request of this attempt "
                                 "found the material (registration §21 (b))")
    path = safe_path(store) / "sources" / (found["archive"] + ".json")
    page = read_json(path) if path.exists() else None
    if not isinstance(page, dict) or digest(page) != found["archive"] or page.get("kind") != "page" \
            or page.get("source") != "wikipedia" or type(page.get("html")) is not str:
        raise ConfigurationError("generation_without_research: the finding's page is not archived in this attempt")
    if not research.verbatim(found["quote"], research.page_text(page["html"])[0]):
        raise ConfigurationError("generation_without_research: the quote is not verbatim on the archived page")
    return {"label": label.rstrip("/"), "calls": found["calls"], "archive": found["archive"], "archived": True,
            "verbatim": True, "title": page["title"], "revid": page["revid"]}


def _generate(roles, setting, m, workers, unit, attempt, evidence, wikipedia_transport):
    """(research, generator) of piece 4 (module docstring)."""
    entry = m["data"].get("research")
    require(isinstance(entry, dict) and set(entry) == manifest.RESEARCH_FIELDS, "The data pins bind the archive")
    archive = research.Archive(entry["archive"])
    require(archive.index_sha256 == entry["index_sha256"], "The research archive differs from the manifest")
    wikipedia = research.Wikipedia(proxy=protocol.GATEWAY, transport=wikipedia_transport)
    try:
        store = attempt / "research"
        sources = research.Sources(wikipedia, archive, store)
        researcher = research.Researcher(roles["examiner_research"], sources,
                                         leakage.Corpus(LIVEMATH, list(setting.pools[LIVEMATH])), bench=LIVEMATH,
                                         label=unit + "/research")
        found = researcher.family_material(concept=CONCEPT)
        searched = {"request": found, "summary": researcher.summary(), "gateway": protocol.GATEWAY,
                    "trust_env": False, "archive_index_sha256": archive.index_sha256, "provenance": None}
        generated = {"ran": False, "reason": None, "specs_record": None, "items": 0, "kept": [], "dropped": {},
                     "checker": [], "solved": 0}
        if found["status"] != "found":
            generated["reason"] = "no_research_finding"  # no fallback: generation consumes research only
            return searched, generated
        searched["provenance"] = provenance(found, researcher, roles["examiner_research"], store)
        halves = research.split([found], unit, evidence=evidence)
        write_json(attempt / "research-split.json", halves)
        payload = examiner.generator_payload(LIVEMATH, halves["g_self"])
        specs, written = examiner.generator_write(roles["examiner"], payload, label=unit, evidence=evidence)
        checker = livemath.WorkerChecker(workers)
        with checker.session():
            built = examiner.build(specs, halves["g_self"], bench=LIVEMATH, generator=GENERATOR, set_name=SET_NAME,
                                   seed=protocol.generator_seed(GENERATOR, unit), evidence=evidence, start=0,
                                   checker=checker)
        items = built.items
        write_json(attempt / ("generated-%s.json" % SET_NAME), items)
        dropped = {}
        for result in built.results:
            for reason, n in result["dropped"].items():
                dropped[reason] = dropped.get(reason, 0) + n
        checked = [i for i in items if i["private"]["truth"].get("checked_by") == livemath.CHECKED_BY]
        solved = sum(1 for entry in checker.solved if entry["ok"] and entry["exact"] is not None)
        generated.update(ran=True, specs_record=written, items=len(items), kept=[i["id"] for i in checked],
                         dropped=dict(sorted(dropped.items())), checker=checker.solved, solved=solved)
        return searched, generated
    finally:
        wikipedia.close()


def _note_procedure(candidate):
    """(procedure, origin): the engineer's first surviving procedure with a note hook, else the fixture fx-note."""
    for procedure in candidate.procedures if candidate is not None else ():
        if procedure.max_note_chars:
            return procedure, "engineer"
    return next(p for p in fixtures.fixture_package().procedures if p.id == RULE_PROCEDURE), "fixture"


def _describe(roles, workers, unit, candidate, run, evidence):
    procedure, origin = _note_procedure(candidate)
    entries = [e for e in (replay.inputs_of(t) for t in run if t["arm_kind"] == "parent") if e is not None]
    outcomes = replay.replay_many(procedure, entries, workers)
    lengths = [len(note["text"]) for outcome in outcomes.values() for note in outcome.notes if note["text"]]
    value = describer.describe(roles, procedure, lengths=lengths, label="%s/describe/%s" % (unit, procedure.id),
                               evidence=evidence)
    return {"procedure": procedure.id, "origin": origin, "lengths": len(lengths), "record": value,
            "ran": value["request_sha256"] is not None and value["reason"] is None}


def ran_rows(pieces, glm):
    """{row: bool} of ``smoke.S3_ROWS`` from the pieces of one complete attempt."""
    generated = pieces["generator"]
    return {"engineer": pieces["engineer"]["ran"], "detector": pieces["detector"]["ran"],
            "generator_research": (pieces["research"]["provenance"] is not None and generated["ran"]
                                   and len(generated["kept"]) >= MIN_CHECKED and generated["solved"] >= MIN_CHECKED),
            "leakage": pieces["leakage"]["valid"], "describer": pieces["describer"]["ran"],
            "glm_cap": glm["within_cap"]}


def _calls(role_sets):
    """Every role call of the attempt, compact (role, label, request hash, sends, charge, the largest request bytes
    of its sends -- S-E6's next reservation, registrar addendum 14:3x -- valid, reason)."""
    out = []
    for name, roles in role_sets.items():
        for call in roles.calls:
            sends = call["sends"] or []
            out.append({"role": name, "call": call["role"], "label": call["label"],
                        "request_sha256": call["request_sha256"], "sends": len(sends),
                        "charged": sum(s.get("charged") or 0 for s in sends),
                        "request_bytes": max([s["request_bytes"] for s in sends
                                              if type(s.get("request_bytes")) is int], default=None),
                        "valid": call["valid"], "reason": call["reason"]})
    return out


# -------------------------------------------------------------------------------------------------- the unit
@contextlib.contextmanager
def backends(spec, m, manifest_path, *, fake, env_path, roles_repo, rehearsal=None):
    """(Setting, Wikipedia transport) of S3: real -- ``smoke._backends`` (the named credentials must be the manifest's
    paths of the smoke solver and the roles, the code map and image verified), Wikipedia through the gateway; fake --
    the ``S3Rehearsal`` (or the given one) on the manifest's Setting, no credential named."""
    if not fake:
        require(rehearsal is None, "A real S3 runs on no fake")
        with smoke._backends(spec, m, manifest_path, fake=False, env_path=env_path,
                             roles_repo=roles_repo) as (setting, _):
            yield setting, None
        return
    require(env_path is None and roles_repo is None, "A rehearsal names no credential")
    if rehearsal is None:
        from tests import execskill_fakes_s3 as fakes  # the S3 rehearsal's fakes (plan §7) live with the tests
        rehearsal = fakes.S3Rehearsal(safe_path(spec["root"]) / "rehearsal-s3")
    try:
        yield (manifest.setting_of(m, budgets.SMOKE, path=manifest_path, docker=rehearsal.docker,
                                   transport=rehearsal.transport), rehearsal.wikipedia.transport)
    finally:
        rehearsal.docker.close()


def unit(spec, m, manifest_path, *, fake=False, env_path=None, roles_repo=None, rehearsal=None, name=UNIT_NAME,
         cap=S3_GLM_CAP):
    """Run (or read back) the S3 roles unit ``<root>/units/S3/<name>``: its unit record, or the stopped report
    {"stage", "complete": False, "stopped", "reason", "unit"} of a unit that paused (its attempt kept). S3's own run
    unit (``own_run``) must be complete (refused before anything is sent)."""
    path = run_root(spec)
    require((path / "unit.json").exists(), "S3's roles read its own completed run unit: run it first (own_run)")
    run = trajectories.load_run(path)
    card = [t for t in run if t["arm_kind"] == "parent"]  # the diagnose unit's input (step._diagnose)
    require(card, "S3's run unit holds parent-arm trajectories")
    label = _unit_label(name)
    with backends(spec, m, manifest_path, fake=fake, env_path=env_path, roles_repo=roles_repo,
                  rehearsal=rehearsal) as (setting, wikipedia_transport):
        local = units.for_unit(setting, budgets.SMOKE, BENCH, label)
        workers = functools.partial(sandbox.with_worker, **local.sandbox, live=local.slots[slots.LIVE],
                                    per_call=local.slots[slots.CALL])
        evidence = setting.evidence

        def work(attempt):
            setting.budget.declare({METER_SCOPE: protocol.SMOKE_CAPS["glm"]})
            spent = setting.budget.snapshot()[METER_SCOPE]
            client = setting.clients(protocol.ROLE_MODEL, None)
            guard = Guard(spent["settled"] + spent["open"], cap=cap, response_ids=client.response_model_ids,
                          unit=label)
            roles = role_set(setting, guard)
            pieces = {}
            try:
                pieces["leakage"] = _leakage(roles["leakage"], label, guard)
                pieces["engineer"], candidate = _engineer(roles["engineer"], setting, workers, label, run, evidence)
                pieces["detector"] = _detector(roles["examiner"], workers, label, card, attempt, evidence)
                pieces["research"], pieces["generator"] = _generate(roles, setting, m, workers, label, attempt,
                                                                    evidence, wikipedia_transport)
                pieces["describer"] = _describe(roles["describer"], workers, label, candidate, run, evidence)
            finally:
                write_json(attempt / "glm.json", guard.state())
                write_json(attempt / "role-calls.json", {role: r.calls for role, r in roles.items()})
            glm = guard.state()
            return {"unit": label, "pieces": pieces, "glm": glm, "calls": _calls(roles),
                    "ran": ran_rows(pieces, glm)}

        identity = {"unit": label, "stage": STAGE, "spec": spec[protocol.RECORD_HASH]}
        try:
            return units.run_unit(unit_root(spec, name), run=setting.run, identity=identity, work=work,
                                  evidence=evidence, drain=units.drainer(setting, budgets.SMOKE, label))
        except Pause as pause:
            return {"stage": STAGE, "complete": False, "stopped": pause.kind, "reason": pause.reason,
                    "unit": pause.cell}


def judged(value):
    """The S3 stage result from the unit record: ``smoke.s3_roles`` of its rows, the unit, its record hash and the
    GLM spend."""
    result = value["result"]
    return {**smoke.s3_roles(result["ran"]), "unit": result["unit"], "unit_sha256": value[protocol.RECORD_HASH],
            "glm": result["glm"]}


def run(spec, m, manifest_path, *, fake=False, env_path=None, roles_repo=None, rehearsal=None):
    """``smoke.run_stage(..., "S3")``: S3's own run unit (``own_run``), then the roles unit, then its judged stage
    record written once (``smoke.record``) -- or the stopped report of a unit that paused (nothing recorded)."""
    first = own_run(spec, m, manifest_path, fake=fake, env_path=env_path, roles_repo=roles_repo)
    if first.get("complete") is False:
        return first
    value = unit(spec, m, manifest_path, fake=fake, env_path=env_path, roles_repo=roles_repo, rehearsal=rehearsal)
    if value.get("complete") is False:
        return value
    return smoke.record(spec, STAGE, judged(value),  # a rehearsal's record is a fixture's (registrar addendum 15:0x)
                        evidence=smoke.REHEARSAL_EVIDENCE if fake else manifest.SMOKE_EVIDENCE)


def zebra_training(setting, services, chain, items):
    """One real engineer/train round on synthetic grids; no family or research role."""
    from dataclasses import replace
    from . import step
    from .registry import Registry
    from .package import empty
    root = safe_path(setting.root) / chain / "role-smoke"
    services = replace(services, registry=Registry(root / "fixture-history", evidence=setting.evidence))
    setting = replace(setting, pools={"zebralogic": list(items)})
    parent = empty(step="%s/s0" % chain, evidence=setting.evidence)
    st = step._Step(setting, services, chain, "zebralogic", 1, parent, root, None)
    cut = {"run": list(items), "accept": []}
    step._run(st, cut)
    step._diagnose(st, cut)
    generated = step._generate(st, cut)
    engineered = step._engineer_train(st, cut, 1, parent, done=[], fed=None, history=[], training=None,
                                      lint=[], reserved=frozenset(), analysed=frozenset(), disclosed=frozenset(),
                                      generated=generated)
    candidate = step._package(st, engineered["candidate_sha256"]) if engineered["candidate_sha256"] else None
    evaluated = step._train_eval(st, cut, 1, parent, candidate, generated) if candidate is not None else None
    return {"passed": candidate is not None and evaluated is not None and evaluated["cells"] > 0, "rounds": 1,
            "engineer": engineered, "training": evaluated, "fixtures": len(items),
            "generator": "selection", "research": "not_applicable"}
