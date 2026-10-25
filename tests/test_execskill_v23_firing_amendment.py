"""Amendment 2: C6b repair and train dispatch with authored replies/hooks, no model, network or subprocess."""
from __future__ import annotations

import json
import socket
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, protocol, smoke_roles, solver, step, supply
from skillopt.execskill.package import FIXTURE, Package, empty
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import engineer_reply
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.test_execskill_replay import test_case, trajectory
from tests.test_execskill_v23_training_amendment import cell

V23 = protocol.MAIN_V2_3
BENCHES = ("officeqa", "alfworld")
TEXT = "SYNTHETIC-PUBLIC-CONTENT-NEVER-IN-CHECK-FEEDBACK"
PRIVATE = "SYNTHETIC-PRIVATE-ANSWER-NEVER-IN-CHECK-FEEDBACK"
OLD_CHECKS = ["C1", "C2", "C4", "C3", "C5", "C6", "C4", "C7", "C8", "C9"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("These fixtures must never open a network connection or listener")

    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, forbidden)


@contextmanager
def workers(package, *, kind="cell", hashseed=0, inputs_dir=None):
    """Only authored fixture source, in process, through the shell's existing FakeSandbox interface."""
    hooks = {}
    for entry in package.procedures:
        namespace = {}
        exec(compile(entry.source, "<authored-firing-fixture>", "exec"), namespace)
        hooks[entry.id] = {hook: namespace[hook] for hook in entry.hooks}
    worker = FakeSandbox(hooks).start(package, kind=kind, inputs_dir=inputs_dir)
    worker.rejected = {}
    try:
        yield worker
    finally:
        worker.close()


@contextmanager
def routing_workers(package, item):
    with workers(package) as worker:
        yield worker


class Roles:
    def __init__(self, entry, proposed, fixed=None):
        self.entry, self.proposed, self.fixed = entry, proposed, fixed or proposed
        self.calls, self.seen = [], []

    def count(self, prefix):
        return sum(c["label"].startswith(prefix) for c in self.calls)

    def plain(self, role, system, user, *, label, **options):
        payload = json.loads(user)
        self.seen.append(payload)
        self.calls.append({"label": label, "request_sha256": digest([system, user])})
        assert role == "engineer", "These passing trajectories need no analyst or adjudicator"
        source = self.fixed if payload["request"] == "fix" else self.proposed
        return engineer_reply({"changes": [self.entry]}, [source])


def public(bench, marker=TEXT):
    if bench != "alfworld":
        return {"question": marker, "context": "Public context " + marker}
    view = supply.routing_view("Initial room " + marker + ". Your task is to: inspect.", ["look"])
    return {"game_file": "never-opened-authored-game", "routing_view": view,
            "routing_view_sha256": digest(view)}


def item(bench, task_id="one", marker=TEXT):
    return {"task_id": task_id, "public": public(bench, marker), "private": {"answer": PRIVATE}}


def stored(bench, one):
    view = solver.routing_view(bench, one["public"])
    if bench != "alfworld":
        return trajectory("c-" + one["task_id"], bench, one["task_id"], "pass", [view])
    step_view = {"initial_observation": view["initial_observation"], "observation": TEXT,
                 "admissible_commands": ["look"], "recent_history": []}
    steps = [{"i": 0, "view_sha256": digest(step_view), "observation": TEXT, "notes": "",
              "discouraged": [], "reply": "look", "action": "look", "how": "exact",
              "post_observation": TEXT, "state_sha256": {}}]
    return trajectory("c-" + one["task_id"], bench, one["task_id"], "pass", [step_view], steps=steps)


def source(bench, *, fires):
    key = ("initial_observation" if fires else "recent_history") if bench == "alfworld" else (
        "question" if fires else "computed")
    hook = ("def alf_before_step(view, state):\n"
            "    return {'fields': {'facts': ['The public view is available.']}, 'discourage': []}\n"
            if bench == "alfworld" else
            "def before_call(view, state):\n    return {'facts': ['The public view is available.']}\n")
    return "def applies(view):\n    return %r in view\n" % key + hook


def context(bench, *, fires=False, fix=False, kind="new", configuration=V23, examples=None):
    examples = examples if examples is not None else [item(bench)]
    hooks = ("applies", "alf_before_step" if bench == "alfworld" else "before_call")
    parent = empty(step="s0", evidence=FIXTURE)
    entry = {"kind": kind, "description": "Records facts about the public view.",
             "hooks": list(hooks), "max_note_chars": 500}
    if kind == "revision":
        old = procedure("fx-existing", hooks, origin=bench, source=source(bench, fires=False))
        parent = Package((old,), "s0", FIXTURE)
        entry["revises"] = old.id
    roles = Roles(entry, source(bench, fires=fires), source(bench, fires=fix or fires))
    trajectories = [stored(bench, one) for one in examples]
    ctx = engineer.Context(bench=bench, k=1, step="s1", evidence=FIXTURE, parent=parent, base=parent,
                           trajectories=trajectories, current=[], corpora={}, workers=workers, roles=roles,
                           label="D/s1-%s/engineer-r1" % bench, mode="train", round=1,
                           configuration=configuration, echo=protocol.FIX_ECHO[configuration],
                           counterfactual=protocol.META_COUNTERFACTUAL[configuration],
                           routing_items=[("%s/%s" % (bench, one["task_id"]),
                                           solver.routing_view(bench, one["public"])) for one in examples],
                           routing_workers=routing_workers)
    return ctx, {"run": examples}


def train(tmp_path, monkeypatch, ctx, cut, candidate, generated=None):
    setting = SimpleNamespace(extra={"configuration": ctx.configuration}, evidence=FIXTURE,
                              cards={}, runtime={ctx.bench: {}})
    st = step._Step(setting, SimpleNamespace(item_workers=routing_workers, workers=workers),
                    "D", ctx.bench, 1, ctx.parent, tmp_path)
    seen = []

    def unit(name, work, **kwargs):
        attempt = tmp_path / name / "attempt-1"
        attempt.mkdir(parents=True)
        return work(attempt)

    def cells(st, attempt, endpoint, name, jobs, **kwargs):
        seen.extend(jobs)
        return [cell(arm, key, "pass" if arm == "S'" else "fail", run)
                for arm, package, key, run, task in jobs]

    monkeypatch.setattr(st, "unit", unit)
    monkeypatch.setattr(st, "solver", lambda *args, **kwargs: object())
    monkeypatch.setattr(step, "_cells", cells)
    result = step._train_eval(st, cut, 1, ctx.parent, candidate, generated or {})
    return result, seen


def firing_report(attempt):
    return next(c for c in attempt["checks"] if c["check"] == "C6b")


@pytest.mark.parametrize("bench", BENCHES)
@pytest.mark.parametrize("kind", ("new", "revision"))
def test_idle_predicate_receives_only_keys_and_counts_then_fix_reaches_training(tmp_path, monkeypatch, bench, kind):
    ctx, cut = context(bench, fix=True, kind=kind)
    candidate, sealed = engineer.run_train(ctx)
    assert protocol.verified(sealed, "engineer") == sealed
    change = sealed["changes"][0]
    assert [a["failed"] for a in change["attempts"]] == ["C6b", None]
    assert change["survived"] and change["fix_calls"] == 1 and sealed["calls"] == 2
    failed = firing_report(change["attempts"][0])
    feedback = next(p for p in ctx.roles.seen if p["request"] == "fix")
    assert feedback["failed"] == failed and feedback["attempts"] == protocol.TRAIN_FIXES
    detail = failed["detail"]
    assert detail["fires_on"] == 0 and detail["items"] == 1 and detail["predicate_faults"] == 0
    assert detail["routing_view_keys"] == sorted(ctx.routing_items[0][1])
    fields = {"fires_on", "items", "predicate_faults", "routing_view_keys"}
    if bench == "alfworld":
        fields |= {"step_view_keys", "note"}
        assert "recent_history" in detail["step_view_keys"] and "recent_history" not in detail["routing_view_keys"]
        assert detail["note"] == "applies() receives the routing view; hooks receive the step view"
    assert set(detail) == fields
    rendered = json.dumps(feedback, sort_keys=True)
    assert TEXT not in rendered and PRIVATE not in rendered and "c-one" not in rendered
    assert firing_report(change["attempts"][1])["detail"]["fires_on"] == 1
    trained, dispatched = train(tmp_path, monkeypatch, ctx, cut, candidate)
    assert trained["differs"] == 1 and trained["pruned"] == [] and trained["cells"] == len(dispatched) > 0
    assert trained["verdict"]["fixed"] == [bench + "/one"]


@pytest.mark.parametrize("bench", BENCHES)
def test_unchanged_idle_change_dies_after_registered_repairs_and_creates_no_train_cells(monkeypatch, bench):
    ctx, cut = context(bench)
    candidate, sealed = engineer.run_train(ctx)
    change = sealed["changes"][0]
    assert candidate is None and not change["survived"]
    assert change["fix_calls"] == protocol.TRAIN_FIXES
    assert sealed["calls"] == 1 + protocol.TRAIN_FIXES <= protocol.TRAIN_ENGINEER_CALLS
    assert [a["failed"] for a in change["attempts"]] == ["C6b"] * (1 + protocol.TRAIN_FIXES)
    engineered = {"engineer": sealed, "candidate_sha256": None}
    monkeypatch.setattr(step, "_engineer_train", lambda *args, **kwargs: engineered)
    monkeypatch.setattr(step, "_train_eval", lambda *args, **kwargs: pytest.fail("Dead changes get no train unit"))
    monkeypatch.setattr(step, "_cells", lambda *args, **kwargs: pytest.fail("Dead changes get no train cells"))
    st = SimpleNamespace(parent=ctx.parent, setting=SimpleNamespace(extra={"configuration": V23}))
    final, rounds, last = step._train(st, cut, {})
    assert final is ctx.parent and last is None and len(rounds) == protocol.TRAIN_PATIENCE
    assert all(r["proposals"][0]["fate"] == "check_failed:C6b" for r in rounds)
    assert all(r["proposals"][0]["description"] == "" for r in rounds)


@pytest.mark.parametrize("bench", BENCHES)
def test_firing_change_preserves_existing_checks_and_uses_no_repairs(bench):
    ctx, _ = context(bench, fires=True)
    candidate, sealed = engineer.run_train(ctx)
    change = sealed["changes"][0]
    assert candidate is not None and change["fix_calls"] == 0 and sealed["calls"] == 1
    report = change["attempts"][0]
    assert report["passed"] and [c["check"] for c in report["checks"] if c["check"] != "C6b"] == OLD_CHECKS
    assert firing_report(report)["detail"]["fires_on"] == 1


@pytest.mark.parametrize("configuration", [c for c in protocol.CONFIGURATIONS if c != V23])
def test_legacy_configurations_keep_idle_proposals_and_original_check_sequence(configuration):
    ctx, _ = context("officeqa", configuration=configuration)
    candidate, sealed = engineer.run_train(ctx)
    change = sealed["changes"][0]
    assert candidate is not None and change["survived"] and change["fix_calls"] == 0 and sealed["calls"] == 1
    assert [c["check"] for c in change["attempts"][0]["checks"]] == OLD_CHECKS
    assert sealed["version"] == protocol.kind("engineer")


def test_single_smoke_without_training_items_records_skip_and_keeps_replay_tests():
    ctx, _ = context("officeqa", fires=True)
    ctx.roles.entry["replay_tests"] = [test_case("c-one", "before_call",
                                                  {"kind": "note_contains", "value": "available"})]
    failed = dict(ctx.trajectories[0])
    failed.pop("record_sha256")
    failed["token"] = "fail"
    failed["judge"] = {"v2": {"token": "fail"}}
    fields = {k: v for k, v in failed.items() if k not in ("version", "evidence")}
    ctx = replace(ctx, mode="single", round=0, base=None, routing_items=[], echo=True, counterfactual=False,
                  label="D/s1-officeqa/engineer", trajectories=[protocol.record("trajectory", FIXTURE, fields)])
    candidate, sealed = engineer.run(ctx)
    report = sealed["changes"][0]["attempts"][0]
    assert candidate is not None and report["passed"] and sealed["calls"] == 1
    skipped = firing_report(report)
    assert skipped["passed"] and skipped["detail"]["skipped"] is True
    assert skipped["detail"]["reason"] == "no_training_items" and skipped["detail"]["items"] == 0
    assert next(c for c in report["checks"] if c["check"] == "C7")["detail"]["tests"][0]["holds"]


@pytest.mark.parametrize("bench", BENCHES)
def test_firing_on_one_generated_item_is_enough_and_training_routes_that_item(tmp_path, monkeypatch, bench):
    ctx, cut = context(bench, fires=True)
    marker = "generated-only-public-key"
    # C6 still executes the source on stored trajectories; C6b must use the separate training population.
    predicate = "def applies(view):\n    return %r in str(view)\n" % marker
    ctx.roles.proposed = ctx.roles.fixed = predicate + source(bench, fires=True).split("\n", 2)[2]
    generated = protocol.record("generated-item", FIXTURE, {"id": "g-one", "benchmark": bench,
                                                           "public": public(bench, marker), "private": {}})
    ctx.routing_items.append(("g-one", solver.routing_view(bench, generated["public"])))
    candidate, sealed = engineer.run_train(ctx)
    report = firing_report(sealed["changes"][0]["attempts"][0])
    assert candidate is not None and report["detail"]["fires_on"] == 1 and report["detail"]["items"] == 2
    assert sealed["changes"][0]["fix_calls"] == 0
    trained, dispatched = train(tmp_path, monkeypatch, ctx, cut, candidate,
                                 {"generator": {"status": "admitted"}, "g_self": [generated]})
    assert trained["differs"] == 1 and trained["verdict"]["items"] == 0 and trained["verdict"]["generated"] == 1
    assert {(arm, key, run) for arm, package, key, run, task in dispatched} == {
        ("S", "g-one", 0), ("S'", "g-one", 0)}


@pytest.mark.parametrize("bench", BENCHES)
@pytest.mark.parametrize("status", ("admitted", "rejected", None))
def test_engineer_and_train_receive_the_same_run_and_capped_admitted_generated_views(tmp_path, monkeypatch,
                                                                                  bench, status):
    ctx, cut = context(bench, fires=True, examples=[item(bench, "one"), item(bench, "two")])
    setting = SimpleNamespace(extra={"configuration": V23}, evidence=FIXTURE, cards={}, runtime={bench: {}})
    st = step._Step(setting, SimpleNamespace(item_workers=routing_workers, workers=workers),
                    "D", bench, 1, ctx.parent, tmp_path)
    captured, routed = [], []

    def unit(name, work, **kwargs):
        attempt = tmp_path / name / "attempt-1"
        attempt.mkdir(parents=True)
        return work(attempt)

    def capture(found):
        captured.append(found)
        return None, {"captured": True}

    actual_routes = step._routes

    def routes(st, package, views, publics):
        routed.append(views)
        return actual_routes(st, package, views, publics)

    monkeypatch.setattr(st, "unit", unit)
    monkeypatch.setattr(st, "roles", lambda *args: ctx.roles)
    monkeypatch.setattr(st, "solver", lambda *args: pytest.fail("Equal empty packages dispatch no cells"))
    monkeypatch.setattr(step, "_earlier", lambda *args: [])
    monkeypatch.setattr(step, "_run_trajectories", lambda *args: ctx.trajectories)
    monkeypatch.setattr(step, "_current", lambda *args: [])
    monkeypatch.setattr(step, "_evaluated", lambda *args: [])
    monkeypatch.setattr(step, "_corpora", lambda *args: {})
    monkeypatch.setattr(step, "_routes", routes)
    monkeypatch.setattr(engineer, "run_train", capture)
    made = [protocol.record("generated-item", FIXTURE, {"id": "g-%d" % n, "benchmark": bench,
                "public": public(bench, "generated-%d" % n), "private": {"answer": PRIVATE}})
            for n in range(protocol.G_SELF_MAX + 2)]
    generated = {"generator": {"status": status}, "g_self": made} if status else {"g_self": made}
    step._engineer_train(st, cut, 1, ctx.parent, done=[], fed=None, history=[], training=None, lint=[],
                         reserved=[], analysed=[], disclosed=[], generated=generated)
    step._train_eval(st, cut, 1, ctx.parent, ctx.parent, generated)
    expected = [(bench + "/" + one["task_id"], solver.routing_view(bench, one["public"])) for one in cut["run"]]
    if status == "admitted":
        expected += [(one["id"], solver.routing_view(bench, one["public"])) for one in made[:protocol.G_SELF_MAX]]
    assert captured[0].routing_items == expected
    assert routed == [expected, expected]
    assert PRIVATE not in json.dumps(expected)
    with captured[0].routing_workers(ctx.parent, expected[0][0]) as worker:
        assert worker.package is ctx.parent


def test_nonempty_single_smoke_routes_its_actual_items_with_a_working_factory(monkeypatch):
    one = item("searchqa")
    one["benchmark"] = "searchqa"
    one["private"] = {"answers": [PRIVATE]}
    shown = stored("searchqa", {**one, "task_id": "searchqa/one"})
    setting = SimpleNamespace(extra={"configuration": V23}, pools={"searchqa": [one]}, cards={})
    captured = []
    probe = procedure("fx-smoke-check", ("applies", "before_call"), origin="searchqa",
                      source=source("officeqa", fires=True))

    def run(ctx):
        captured.append(ctx)
        passed, detail = engineer._firing(probe, ctx)
        assert passed and detail["fires_on"] == detail["items"] == 1 and "skipped" not in detail
        return None, {"changes": [], "proposals": []}

    monkeypatch.setattr(engineer, "run", run)
    smoke_roles._engineer(object(), setting, workers, "D/s1-searchqa/engineer", [shown], FIXTURE)
    assert captured[0].mode == "single"
    assert captured[0].routing_items == [("searchqa/one", solver.routing_view("searchqa", one["public"]))]
