"""Integration of batch B2, sandbox and shell (protocol ``fivebench-execskill-v1``): A5's sandbox worker and client,
A6's shell and router, A7's outcome rows and judge, wired with B1's package, pools and records (implementation plan §3,
§4, §5, §8.1 and §9 gate (i); registration §2.3-§2.6, §4.4).

Each row tested against its own fakes; these tests put the rows together:
- gate (i) with the REAL sandbox worker in the loop: the empty package still reproduces the frozen ``backends.solve``
  on both registered projections on all five benches (ALFWorld on ``tag_exact`` episodes); QA and SpreadsheetBench
  cells start no container, an ALFWorld episode starts exactly one (the card arm's ping, registration §6.2);
- what ``outcomes_ext`` and ``judge`` read is what the real shell records (deciding receipt, call reasons, fallback,
  the ALFWorld step log), on receipts of the real client;
- procedures run in the real worker behind the shell: the SpreadsheetBench input mount, ALFWorld state kept by the
  host, predicate and hook faults;
- the pools of A1, the worker's live and per-call slots, the shell's native slot and a model pool keep the lock order;
- ``router.plan`` with real workers; the B2 records carry the protocol stamp (T-ID-2) and the B2 stops their kind
  (T-ID-1).

Offline and deterministic: FakeDocker runs the real worker.py in local subprocesses, FakeSolver answers through the real
ElucidClient, FakeAlfEnv and FakeNative stand for ALFWorld and the native containers.
"""
from __future__ import annotations

import json
import threading

import pytest

from skillopt.coevo5.calls import _request_hash
from skillopt.coevo5.outcomes import BudgetStop, finalize
from skillopt.continual_eval import backends
from skillopt.continual_eval.code_delivery import extract_python
from skillopt.execskill import judge, outcomes_ext, router, slots, solver
from skillopt.execskill.errors import STOP_KINDS, CleanupUnconfirmed, ConfigurationError, SandboxUnavailable, stop_kind
from skillopt.execskill.package import Package, empty
from skillopt.execskill.protocol import NOT_RECOMMENDED_PREFIX, NOTE_HEADERS, NOTES_KEY, kind, verified
from skillopt.execskill.sandbox import client
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import QA_MAX_TOKENS, FakeSolver, calc, over_nominal, tagged, truncated
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeAlfEnv, FakeNative, Script, alf_sessions, procedure
from tests.fixtures.execskill.items import (alfworld_games, alfworld_items, livemath_items, officeqa_items,
                                            searchqa_items, spreadsheetbench_items)

EVIDENCE = "engineering_fixture"
EMPTY = empty(step="s0", evidence=EVIDENCE)
CARD = "Read the table rows before computing."
LIMITS = {name: client.Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
          for name in client.KINDS}
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": client.IMAGE, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
ALF_RUNTIMES = ({}, {"alfworld_trace_version": backends.ALFWORLD_TRACE_VERSION, "max_steps": 50})
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
REPAIRED = PROGRAM.replace("A1:A5", "A1:A6")
ERROR_REPORT = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Sheet2'"}

BIND_SOURCE = '''"""Quotes the customs receipts of both years."""


def applies(view):
    return "Customs" in view["context"]


def bindings(view):
    return {"bindings": [{"name": "customs_2019", "quote": "2019 | 1000", "value": "1000"},
                         {"name": "customs_2020", "quote": "2020 | 1200", "value": "1200"}]}
'''
SHEET_SOURCE = '''"""Counts the filled cells of column A in the public workbook."""


def applies(view):
    return view["required_answer_position"] == "B1"


def sheet_feedback(view, run_report, state):
    cells = public_workbook()["sheets"][0]["cells"]
    filled = len([name for name in cells if name.startswith("A")])
    return {"fields": {"warnings": ["column A of the input has %d filled cells" % filled]},
            "request_repair": run_report["status"] == "exception"}
'''
ALF_SOURCE = '''"""Counts the steps taken and discourages two idle commands."""


def applies(view):
    return "fridge" in view["task_text"]


def alf_before_step(view, state):
    taken = 0 if state is None else state["taken"]
    return {"fields": {"facts": ["steps taken so far: %d" % taken]}, "discourage": ["look", "inventory"]}


def alf_after_step(event, state):
    taken = 0 if state is None else state["taken"]
    return {"taken": taken + 1}
'''
CRASH_SOURCE = '''"""Fails on every item."""


def applies(view):
    return True


def before_call(view, state):
    return {"facts": [str(1 / 0)]}
'''
NOT_BOOL_SOURCE = '''"""Its predicate gives text, not a bool."""


def applies(view):
    return "yes"


def before_call(view, state):
    return {"facts": ["never shown"]}
'''
BIND = procedure("fx-bind", ("applies", "bindings"), requests_second_call=True, source=BIND_SOURCE)
SHEET = procedure("fx-sheet", ("applies", "sheet_feedback"), origin="spreadsheetbench", requests_second_call=True,
                  source=SHEET_SOURCE)
ALF = procedure("fx-alf", ("applies", "alf_before_step", "alf_after_step"), origin="alfworld", source=ALF_SOURCE)
CRASH = procedure("fx-crash", ("applies", "before_call"), source=CRASH_SOURCE)
NOT_BOOL = procedure("fx-notbool", ("applies", "before_call"), source=NOT_BOOL_SOURCE)


def package(*procedures):
    return Package(tuple(procedures), "fixture", EVIDENCE)


@pytest.fixture
def docker(tmp_path):
    fake = FakeDocker(tmp_path / "containers")
    yield fake
    fake.close()


def worker_for(docker, tmp_path, **options):
    """An unstarted real sandbox worker (the shell starts and closes it)."""
    return client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path, **options)


def project(prediction):
    """The second registered projection (registration §2.3): the prediction without ``shell``."""
    return {key: value for key, value in prediction.items() if key != "shell"}


def sent(call, k=-1):
    return json.loads(call.requests[k][1])


def alf_public(root, number=0):
    """An ALFWorld fixture item with its registered pre-reset routing view (``supply.prereset``'s shape)."""
    item, game = alfworld_items(root)[number], alfworld_games()[number]
    observations, _, infos = FakeAlfEnv(game).reset()
    view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
    return {**item["public"], "routing_view": view, "routing_view_sha256": digest(view)}, item, game


def plan_replies(game):
    return ["<action>%s</action>" % step for step in game["plan"]]


class Logged:
    """A call function over a FakeSolver keeping one receipt per logical call that returned, as the frozen Recorder's
    ``receipts`` (coevo5/calls.py ``Recorder.__call__``); ``fail_at`` {call number: exception} raises instead."""

    def __init__(self, fake, fail_at=None):
        self.fake, self.fail_at, self.receipts, self.count = fake, dict(fail_at or {}), [], 0

    def __call__(self, system, user):
        self.count += 1
        if self.count in self.fail_at:
            raise self.fail_at[self.count]
        self.receipts.append(self.fake.call(system, user))
        return self.receipts[-1]


# ------------------------------------------------------------------- gate (i): T-SOLVER-1 with the real worker
def test_gate_i_empty_package_equals_the_frozen_solver_with_the_real_worker_on_five_benches(tmp_path, monkeypatch,
                                                                                             docker):
    native = FakeNative().install(monkeypatch)
    alf_sessions(monkeypatch)

    def check(bench, public, replies, runtime):
        frozen_call, shell_call = Script(replies), Script(replies)
        frozen = backends.solve(bench, public, CARD, frozen_call, runtime=runtime)
        worker = worker_for(docker, tmp_path)
        routed = solver.solve(bench, public, CARD, EMPTY, shell_call, runtime=runtime, worker=worker)
        assert shell_call.requests == frozen_call.requests  # system and user, byte for byte
        assert project(routed) == frozen
        shell = verified(routed["shell"], "shell")  # T-ID-2
        assert [c["request_sha256"] for c in shell["calls"]] == [_request_hash(s, u) for s, u in frozen_call.requests]
        assert outcomes_ext.deciding_receipt(routed, shell_call.receipts) == len(shell_call.receipts) - 1
        return routed, worker

    for bench, items in (("searchqa", searchqa_items(2)), ("officeqa", officeqa_items(2)),
                         ("livemath", livemath_items(2))):
        for item in items:
            for runtime in ({}, {"prompt_layout": "contract-first-v2"}):
                _, worker = check(bench, item["public"], [tagged("Fixtown 1")], runtime)
                assert worker.names == []  # an empty package starts no container on a QA cell
    for item in spreadsheetbench_items(tmp_path / "sheets", 2):
        _, worker = check("spreadsheetbench", item["public"], [PROGRAM], SHEET_RUNTIME)
        assert worker.names == []
    # two items, the frozen and the shell's run each; the shell pre-checks every extracted program once, also with an
    # empty package (registration §2.5; ticket A9-1, integration B3), and the frozen solver never does
    assert len(native.prechecks) == 2 and len(native.cases) == 4
    for number in range(3):
        public, _, game = alf_public(tmp_path / ("alf-%d" % number), number)
        for runtime in ALF_RUNTIMES:
            routed, worker = check("alfworld", public, plan_replies(game), runtime)
            assert [s["how"] for s in routed["shell"]["alfworld_steps"]] == ["tag_exact"] * len(game["plan"])
            assert len(worker.names) == 1 and worker.info["worker"] == "execskill-worker-v1"  # the card arm's ping
            assert worker.names[0] not in docker.containers  # removed when the episode ended
    assert len(docker.argvs) == 6 and docker.containers == {}
    client.drain_check(docker=docker)


# ---------------------------------------------------------- the shell's records are what outcomes and judge read
def test_outcomes_and_judge_read_the_records_of_the_real_shell(tmp_path, docker):
    item = officeqa_items(1)[0]
    public, private = item["public"], item["private"]
    first = calc("customs_2020 - customs_2019") + "\n" + tagged("200")
    # P5: a valid first reply and a truncated second one -- the first reply decides and is scored
    call = Logged(FakeSolver(tmp_path / "p5", [(None, [first, truncated(tagged("2"))])]))
    prediction = solver.solve("officeqa", public, CARD, package(BIND), call, worker=worker_for(docker, tmp_path))
    shell = prediction["shell"]
    assert len(call.receipts) == 2 and shell["deciding_receipt"] == 0 and shell["fallback"] == "second_call_fallback"
    assert [c["reason"] for c in shell["calls"]] == ["model_response_available", "model_response_truncated"]
    assert shell["worst_delivery"] == outcomes_ext.worst_delivery(call.receipts) == "truncated"
    deciding = outcomes_ext.deciding_receipt(prediction, call.receipts)
    assert outcomes_ext.preflight("officeqa", prediction, call.receipts, deciding=deciding) is None
    score = backends.score("officeqa", public, private, prediction)
    verdict = finalize(outcomes_ext.classify("officeqa", prediction, score, call.receipts, deciding=deciding))
    assert (verdict.outcome, verdict.row) == ("pass", "10")
    judged = judge.judge("officeqa", public, private, prediction, call.receipts, runtime={}, score=score,
                         verdict=verdict, deciding=deciding)
    assert judged["version"] == kind("judge") and judged["v2"] == {"token": "pass"}
    assert judged["flags"] == ["second_call_fallback"]
    # a stop inside the second call: recorded as the call's reason by the shell, raised by outcomes_ext (A7-1 item 2)
    for stop in (ConfigurationError("slot_lock_order: glm-5.3 requested while holding spreadsheet-native"),
                 BudgetStop("cap")):
        call = Logged(FakeSolver(tmp_path / type(stop).__name__, [(None, [first])]), fail_at={2: stop})
        prediction = solver.solve("officeqa", public, CARD, package(BIND), call, worker=worker_for(docker, tmp_path))
        assert prediction["status"] == "available" and prediction["reason"] == "model_response_available"
        assert prediction["shell"]["calls"][1]["reason"] == "model_call_exception:" + type(stop).__name__
        with pytest.raises(type(stop)) as caught:
            outcomes_ext.preflight("officeqa", prediction, call.receipts,
                                   deciding=outcomes_ext.deciding_receipt(prediction, call.receipts))
        assert stop_kind(caught.value) == STOP_KINDS[type(stop)]
    # chain D's margin rule (registration §4.1, A7-1 item 5): visible completion >= M - 16 with an unclosed tag
    call = Logged(FakeSolver(tmp_path / "margin", [(None, [over_nominal("<answer>20", QA_MAX_TOKENS - 10)])]))
    prediction = solver.solve("officeqa", public, CARD, EMPTY, call, nominal_tokens=QA_MAX_TOKENS)
    assert (prediction["status"], prediction["reason"]) == ("unknown", "model_response_truncated")
    judged = judge.judge("officeqa", public, private, prediction, call.receipts, runtime={})
    assert (judged["final"]["outcome"], judged["final"]["kind"], judged["final"]["row"]) == ("fail", "noncompletion",
                                                                                           "5")
    assert judged["v2"] == {"token": "fail"} and judged["flags"] == ["truncated"]


def test_every_alfworld_prediction_carries_the_step_log_the_judge_reads(tmp_path, monkeypatch, docker):
    alf_sessions(monkeypatch)
    public, item, game = alf_public(tmp_path)
    # an episode that ends before its first step (frozen row 11, not a stop): judged, with an empty step log
    prediction = solver.solve("alfworld", public, CARD, EMPTY, Script(plan_replies(game)),
                              runtime={"prompt_layout": "contract-first-v2"}, worker=worker_for(docker, tmp_path))
    assert prediction["reason"] == "invalid_prompt_layout" and prediction["shell"]["alfworld_steps"] == []
    judged = judge.judge("alfworld", public, item["private"], prediction, [], runtime={})
    assert judged["final"]["row"] == "11" and judged["format"] == {"steps": 0, "admissible_steps": 0,
                                                                   "violation": None}
    # one level-1 step and one inadmissible step: J4's admissible share counts the shell's ``how`` per step
    replies = ["Action: Go to countertop 1.", "<action>dance</action>"] + plan_replies(game)[1:]
    call = Script(replies)
    prediction = solver.solve("alfworld", public, CARD, EMPTY, call, worker=worker_for(docker, tmp_path))
    assert [s["how"] for s in prediction["shell"]["alfworld_steps"]] == (
        ["whole_level1", "unchanged"] + ["tag_exact"] * (len(game["plan"]) - 1))
    judged = judge.judge("alfworld", public, item["private"], prediction, call.receipts, runtime={})
    assert judged["v2"] == {"token": "pass"}
    assert judged["format"] == {"steps": len(replies), "admissible_steps": len(replies) - 1, "violation": True}


# ---------------------------------------------------------------- procedures in the real worker behind the shell
def test_procedures_run_in_the_real_worker_behind_the_shell(tmp_path, monkeypatch, docker):
    # SpreadsheetBench: the hook reads the public workbook through the read-only /input mount and asks for the repair
    native = FakeNative(report=ERROR_REPORT).install(monkeypatch)
    item = spreadsheetbench_items(tmp_path / "sheets", 1)[0]
    worker = worker_for(docker, tmp_path)
    call = Script([PROGRAM, REPAIRED])
    prediction = solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), call, runtime=SHEET_RUNTIME,
                              worker=worker)
    repair = sent(call, 1)
    assert repair["repair_notes"] == NOTE_HEADERS["warnings"] + "\n- column A of the input has 5 filled cells"
    assert repair["run_report"] == ERROR_REPORT and len(native.prechecks) == 1
    assert prediction["output"]["code"] == extract_python(REPAIRED)["code"]
    assert "type=bind,source=" in " ".join(docker.argvs[-1]) and any(
        a.endswith(",target=/input,readonly") for a in docker.argvs[-1])
    shell = prediction["shell"]
    assert shell["faults"] == [] and shell["deciding_receipt"] == 1
    assert shell["precheck"]["version"] == kind("precheck") and shell["precheck"]["evidence"] == EVIDENCE  # T-ID-2
    assert len(worker.names) == 1 and docker.containers == {}
    # ALFWorld: notes and discouraged commands per step, the state kept by the host between the step hooks
    alf_sessions(monkeypatch)
    public, _, game = alf_public(tmp_path / "alf")
    worker = worker_for(docker, tmp_path)
    call = Script(plan_replies(game))
    prediction = solver.solve("alfworld", public, CARD, package(ALF), call, worker=worker)
    assert prediction["output"] == {"won": True, "steps": len(game["plan"])}
    for k, (_, user) in enumerate(call.requests):
        request = json.loads(user)
        assert list(request)[-1] == NOTES_KEY and {"look", "inventory"} <= set(request["admissible_commands"])
        assert request[NOTES_KEY] == (NOTE_HEADERS["facts"] + "\n- steps taken so far: %d\n" % k
                                      + NOT_RECOMMENDED_PREFIX + "look, inventory")
    steps = prediction["shell"]["alfworld_steps"]
    assert [s["state_sha256"] for s in steps] == [{"fx-alf": digest({"taken": k + 1})} for k in range(len(steps))]
    assert len(worker.names) == 1 and docker.containers == {}
    # a predicate that is no bool (P2) and a crashing hook (P1): logged, nothing shown, the frozen request
    public = officeqa_items(1)[0]["public"]
    frozen_call, call = Script([tagged("200")]), Script([tagged("200")])
    backends.solve("officeqa", public, CARD, frozen_call)
    prediction = solver.solve("officeqa", public, CARD, package(NOT_BOOL, CRASH), call,
                              worker=worker_for(docker, tmp_path))
    assert call.requests == frozen_call.requests and prediction["status"] == "available"
    assert [(f["procedure"], f["hook"], f["kind"], f["exc_type"]) for f in prediction["shell"]["faults"]] == [
        ("fx-notbool", "applies", "not_bool", None), ("fx-crash", "before_call", "exception", "ZeroDivisionError")]
    route = verified(prediction["shell"]["route"], "route")  # T-ID-2
    assert route["enabled"] == ["fx-crash"] and route["per_procedure"]["fx-notbool"]["fault"] == "not_bool"


# ------------------------------------------------------------------------------------------ lock order (plan §4)
def test_the_worker_shell_and_model_slots_keep_the_registered_lock_order(tmp_path, monkeypatch):
    pools = slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None)
    holdings = pools[slots.NATIVE].holdings
    model = pools["deepseek-v4.1-flash-1017"]
    native = FakeNative(report=ERROR_REPORT, holdings=holdings).install(monkeypatch)
    seen, errors, lock = [], [], threading.Lock()

    def during(system, user):
        with lock:
            seen.append(holdings.held())
        with model.hold():  # refused (slot_lock_order) while a later pool is held
            pass

    # SpreadsheetBench: three cells of one unit, at most two live sandboxes (registration §2.6)
    items = spreadsheetbench_items(tmp_path / "sheets", 3)
    live = pools[slots.LIVE].limited(2)
    dockers = [FakeDocker(tmp_path / ("containers-%d" % k)) for k in range(3)]
    results = [None] * 3

    def run(k):
        worker = client.Worker(docker=dockers[k], limits=LIMITS, scratch=tmp_path, live=live,
                               per_call=pools[slots.CALL])
        try:
            results[k] = solver.solve("spreadsheetbench", items[k]["public"], CARD, package(SHEET),
                                      Script([PROGRAM, REPAIRED], during=during), runtime=SHEET_RUNTIME,
                                      worker=worker, native=pools[slots.NATIVE])
        except BaseException as error:  # reported by the assertion below
            errors.append(error)

    threads = [threading.Thread(target=run, args=(k,)) for k in range(3)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        assert not errors and not any(thread.is_alive() for thread in threads)
        assert all(r["status"] == "available" and r["shell"]["deciding_receipt"] == 1 for r in results)
        # the cell's container lives across its model calls; no per-call or native slot is held during one
        assert seen == [(slots.LIVE,)] * 6
        assert sorted(what for what, _ in native.held) == ["case"] * 3 + ["precheck"] * 3
        assert {held for _, held in native.held} == {(slots.LIVE, slots.NATIVE)}
        assert all(d.containers == {} for d in dockers)
    finally:
        for fake in dockers:
            fake.close()
    # ALFWorld: the unit holds the episode slot; the worker adds the live slot and, per hook call, the per-call slot
    alf_sessions(monkeypatch)
    public, _, game = alf_public(tmp_path / "alf")
    seen.clear()
    docker = FakeDocker(tmp_path / "alf-containers")
    try:
        with pools[slots.EPISODE].hold():
            worker = client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path, live=pools[slots.LIVE],
                                   per_call=pools[slots.CALL])
            prediction = solver.solve("alfworld", public, CARD, package(ALF), Script(plan_replies(game), during=during),
                                      worker=worker)
            assert holdings.held() == (slots.EPISODE,)  # the live slot went with the container
        assert prediction["output"]["won"] is True and seen == [(slots.EPISODE, slots.LIVE)] * len(game["plan"])
        assert holdings.held() == () and docker.containers == {}
    finally:
        docker.close()


# ---------------------------------------------------------------------------- router.plan with real workers
def test_router_plan_routes_the_candidate_and_its_parent_in_real_workers(tmp_path, docker):
    candidate = Package((BIND,), "s1", EVIDENCE, parent_sha256=EMPTY.sha256)
    views = {item["task_id"]: solver.routing_view("officeqa", item["public"]) for item in officeqa_items(4)}

    def workers(package_, item):
        return client.with_worker(package_, kind="cell", docker=docker, limits=LIMITS, scratch=tmp_path)

    plan = verified(router.plan(candidate, EMPTY, "officeqa", views, workers, unit="u-b2"), "firing-plan")  # T-ID-2
    assert plan["astar"] == list(views) and plan["decision"] == "not_run_small_astar"  # 4 < MIN_ASTAR
    assert all(plan["routes"][i]["candidate"]["enabled"] == ["fx-bind"] and plan["routes"][i]["parent"]["enabled"] == []
               for i in views)
    assert len(docker.argvs) == 4 and docker.containers == {}  # the candidate's workers; the empty parent starts none
    assert router.plan(candidate, EMPTY, "officeqa", views, workers, unit="u-b2") == plan
    client.drain_check(docker=docker)


# ------------------------------------------------------------------------------- T-ID-1: B2 stops and their kind
def test_t_id_1_b2_stops_reach_the_caller_with_their_kind(tmp_path, docker):
    public = officeqa_items(1)[0]["public"]
    docker.image_missing = True
    with pytest.raises(SandboxUnavailable, match="sandbox_image_missing") as caught:
        solver.solve("officeqa", public, CARD, package(BIND), Script([tagged("1")]),
                     worker=worker_for(docker, tmp_path))
    assert STOP_KINDS[type(caught.value)] == stop_kind(caught.value) == "sandbox"
    docker.image_missing = False
    worker = worker_for(docker, tmp_path).start(package(BIND), kind="cell")
    worker.ping()
    docker.sticky.add(worker.names[0])
    with pytest.raises(CleanupUnconfirmed) as caught:
        worker.close()
    assert STOP_KINDS[type(caught.value)] == stop_kind(caught.value) == STOP_KINDS[CleanupUnconfirmed]
    with pytest.raises(CleanupUnconfirmed):
        client.drain_check(docker=docker)
    docker.sticky.clear()
    client.cleanup(worker.names[0], docker=docker)
    client.drain_check(docker=docker)
