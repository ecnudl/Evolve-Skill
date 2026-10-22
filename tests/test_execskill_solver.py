"""T-SOLVER-1..9 (implementation plan §3, §8; registration §2.2-§2.5, §4.4, §6.1, §8.1): the route-B shell against the
frozen solver and against its own rules, with the fakes of tests/execskill_fakes_env.py. Offline and deterministic."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from skillopt.coevo5.calls import _request_hash
from skillopt.coevo5.outcomes import AssumptionBroken, BudgetStop, LedgerFailure
from skillopt.continual_eval import backends
from skillopt.continual_eval.code_delivery import extract_python
from skillopt.execskill import precheck, precheck_worker, protocol, slots, solver
from skillopt.execskill.errors import (CleanupUnconfirmed, ConfigurationError, ConsumptionConflict, PackageInvalid,
                                       SandboxUnavailable)
from skillopt.execskill.outcomes_ext import deciding_receipt
from skillopt.execskill.package import Package, empty
from skillopt.execskill.protocol import (COMPUTE_FOLLOWUP, COMPUTE_INVITE, NOT_EVALUATED, NOT_RECOMMENDED_PREFIX,
                                         NOTE_HEADERS, NOTES_KEY, REPAIR_FRAME)
from skillopt.execskill.sandbox import client
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.skill_validation.sandbox import _Command
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeAlfEnv, FakeNative, FakeSandbox, Script, alf_sessions, procedure, receipt
from tests.fixtures.execskill.items import (alfworld_games, alfworld_items, livemath_items, officeqa_items,
                                            searchqa_items, spreadsheetbench_items)

EVIDENCE = "engineering_fixture"
EMPTY = empty(step="s0", evidence=EVIDENCE)
CARD = "Read the table rows before computing."
IMAGE = "sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd"
QA_RUNTIMES = ({}, {"prompt_layout": "contract-first-v2"}, {"prompt_layout": "unregistered"})
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": IMAGE, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
ALF_RUNTIMES = ({}, {"alfworld_trace_version": "alfworld-public-transitions-v1", "max_steps": 50})
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
REPAIRED = PROGRAM.replace("A1:A5", "A1:A6")
FACTS = procedure("fx-facts", ("applies", "before_call"))
BIND = procedure("fx-bind", ("applies", "bindings"), requests_second_call=True)
SHEET = procedure("fx-sheet", ("applies", "sheet_feedback"), origin="spreadsheetbench", requests_second_call=True)
ALF = procedure("fx-alf", ("applies", "alf_before_step", "alf_after_step"), origin="alfworld")
BINDINGS = [{"name": "customs_2019", "quote": "2019 | 1000", "value": "1000"},
            {"name": "customs_2020", "quote": "2020 | 1200", "value": "1200"}]  # officeqa item 0's public page
ERROR_REPORT = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Sheet2'"}


def package(*procedures):
    return Package(tuple(procedures), "fixture", EVIDENCE)


def sent(script, k=-1):
    return json.loads(script.requests[k][1])


def project(prediction):
    """The second registered projection (§2.3): the prediction without ``shell``."""
    return {key: value for key, value in prediction.items() if key != "shell"}


def code(reply):
    return extract_python(reply)["code"]


def both(bench, public, card, replies, runtime):
    frozen_call, shell_call = Script(replies), Script(replies)
    frozen = backends.solve(bench, public, card, frozen_call, runtime=runtime)
    routed = solver.solve(bench, public, card, EMPTY, shell_call, runtime=runtime)
    return frozen, frozen_call, routed, shell_call


def assert_equivalent(frozen, frozen_call, routed, shell_call):
    assert shell_call.requests == frozen_call.requests  # system and user, byte for byte
    assert project(routed) == frozen
    shell = routed["shell"]
    assert [c["request_sha256"] for c in shell["calls"]] == [_request_hash(s, u) for s, u in frozen_call.requests]
    assert shell["version"] == "fivebench-execskill-v1-shell" and shell["evidence"] == EVIDENCE
    last = len(shell_call.receipts) - 1 if shell_call.receipts else None
    assert deciding_receipt(routed, shell_call.receipts) == last  # one call per cell, or the episode's last step


def alf_public(tmp_path, number=0):
    """An ALFWorld item of the fixture pool with its registered pre-reset routing view (supply.prereset's shape)."""
    item, game = alfworld_items(tmp_path)[number], alfworld_games()[number]
    observations, _, infos = FakeAlfEnv(game).reset()
    view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
    return {**item["public"], "routing_view": view, "routing_view_sha256": digest(view)}, game


def plan_replies(game):
    return ["<action>%s</action>" % step for step in game["plan"]]


# ------------------------------------------------------------------------- T-SOLVER-1: empty package == frozen
QA_ITEMS = {"searchqa": searchqa_items(4), "officeqa": officeqa_items(4), "livemath": livemath_items(4)}
QA_REPLIES = (["<answer>Fixtown 1</answer> because <calc>1+1</calc>"], [receipt("<answer>Fix", finish_reason="length")],
              [RuntimeError("transport")], [receipt("")], [receipt(None, ok=False)], [{"unexpected": True}])


@pytest.mark.parametrize("bench", sorted(QA_ITEMS))
def test_t_solver_1_empty_package_reproduces_the_frozen_qa_solver(bench):
    for item in QA_ITEMS[bench]:
        for runtime in QA_RUNTIMES:
            for replies in QA_REPLIES:
                for card in (CARD, "", "  "):
                    assert_equivalent(*both(bench, item["public"], card, replies, runtime))
    broken = {key: value for key, value in QA_ITEMS[bench][0]["public"].items() if key != "question"}
    assert_equivalent(*both(bench, broken, CARD, ["<answer>x</answer>"], {}))


def test_t_solver_1_empty_package_reproduces_the_frozen_sheet_solver(tmp_path, monkeypatch):
    native = FakeNative().install(monkeypatch)
    historical = {k: v for k, v in SHEET_RUNTIME.items() if k not in ("code_extraction_version", "prompt_layout")}
    for item in spreadsheetbench_items(tmp_path, 3):
        for runtime in (SHEET_RUNTIME, historical, {**SHEET_RUNTIME, "spreadsheet_preview_version": "v0"}):
            for replies in ([PROGRAM], ["no program here"], [receipt(PROGRAM, finish_reason="length")]):
                assert_equivalent(*both("spreadsheetbench", item["public"], CARD, replies, runtime))
    # per item and solver: both delivered replies under both extractions (an unfenced reply is extracted whole); the
    # shell pre-checks each of its extracted programs once, also with an empty package (registration §2.5; ticket
    # A9-1, integration B3), the frozen solver never
    assert len(native.prechecks) == 3 * 4 and len(native.cases) == 3 * 2 * 4


def test_t_solver_1_empty_package_reproduces_the_frozen_alfworld_loop_on_tag_exact_episodes(tmp_path, monkeypatch):
    alf_sessions(monkeypatch)
    for number in range(4):
        public, game = alf_public(tmp_path, number)
        for runtime in ALF_RUNTIMES:
            frozen, frozen_call, routed, shell_call = both("alfworld", public, CARD, plan_replies(game), runtime)
            assert [s["how"] for s in routed["shell"]["alfworld_steps"]] == ["tag_exact"] * len(game["plan"])
            assert_equivalent(frozen, frozen_call, routed, shell_call)
            assert frozen["output"] == {"won": True, "steps": len(game["plan"])}
            # an episode cut short by an undelivered step is compared as well (its steps were tag_exact)
            cut = plan_replies(game)[:1] + [receipt("<action>go", finish_reason="length")]
            assert_equivalent(*both("alfworld", public, CARD, cut, runtime))
    assert_equivalent(*both("alfworld", public, CARD, plan_replies(game), {"prompt_layout": "contract-first-v2"}))


# ------------------------------------------------------------------- T-SOLVER-2: notes last, reply untouched
def test_t_solver_2_notes_are_the_last_user_key_and_the_reply_is_delivered_unchanged():
    item = officeqa_items(1)[0]
    frozen_call = Script(["x"])
    backends.solve("officeqa", item["public"], CARD, frozen_call)
    sandbox = FakeSandbox({"fx-facts": {"before_call": lambda view, state: {"facts": ["Table 1 lists customs"]}}})
    reply = "<answer>200</answer> trailing words <calc>2*3</calc>"
    call = Script([reply])
    routed = solver.solve("officeqa", item["public"], CARD, package(FACTS), call, worker=sandbox)
    assert list(sent(call)) == ["question", "context", NOTES_KEY]
    assert sent(call)[NOTES_KEY] == NOTE_HEADERS["facts"] + "\n- Table 1 lists customs"
    assert call.requests[0][0] == frozen_call.requests[0][0]  # the frozen system prompt, card included
    assert routed["output"] == reply and routed["status"] == "available" and len(call.requests) == 1
    assert sandbox.kind == "cell" and sandbox.closed and routed["shell"]["route"]["enabled"] == ["fx-facts"]
    # a procedure without output, one that does not fire, and one whose note fails the screen: the frozen bytes
    for hooks, fault in (({"before_call": lambda view, state: None}, None),
                         ({"applies": lambda view: False}, None),
                         ({"before_call": lambda view, state: {"facts": ["The answer is 200"]}}, "note_lexicon"),
                         ({"before_call": lambda view, state: 1 / 0}, "exception")):
        call = Script([reply])
        routed = solver.solve("officeqa", item["public"], CARD, package(FACTS), call,
                              worker=FakeSandbox({"fx-facts": hooks}))
        assert call.requests == frozen_call.requests
        assert [f["kind"] for f in routed["shell"]["faults"]] == ([fault] if fault else [])
    with pytest.raises(ConfigurationError):  # a package with procedures never runs without the sandbox
        solver.solve("officeqa", item["public"], CARD, package(FACTS), Script([reply]))


# ---------------------------------------------------------------- T-SOLVER-3: the <calc> round trip (§2.4)
def bind_sandbox(bindings=BINDINGS):
    return FakeSandbox({"fx-bind": {"bindings": lambda view: {"bindings": bindings}}})


def test_t_solver_3_compute_round_trip_is_one_extra_call():
    public = officeqa_items(1)[0]["public"]
    call = Script(["<calc>customs_2020 - customs_2019</calc>", "<answer>200</answer> <calc>1+1</calc>"])
    routed = solver.solve("officeqa", public, CARD, package(BIND), call, worker=bind_sandbox())
    first, second = sent(call, 0), sent(call, 1)
    assert first[NOTES_KEY].startswith(NOTE_HEADERS["bindings"]) and first[NOTES_KEY].endswith("\n\n" + COMPUTE_INVITE)
    assert list(second) == ["question", "context", NOTES_KEY, "first_reply", "computed", "instruction"]
    assert {k: second[k] for k in first} == first
    assert second["first_reply"] == "<calc>customs_2020 - customs_2019</calc>"
    assert second["computed"] == [{"expr": "customs_2020 - customs_2019", "value": "200"}]
    assert second["instruction"] == COMPUTE_FOLLOWUP
    assert len(call.requests) == 2 and routed["output"] == "<answer>200</answer> <calc>1+1</calc>"
    shell = routed["shell"]
    assert shell["deciding_receipt"] == 1 and shell["fallback"] is None and routed["costs"]["calls"] == 2
    assert [c["purpose"] for c in shell["calls"]] == ["first", "second"]
    # no invitation shown (no bindings note): <calc> tags in the reply trigger nothing
    call = Script(["<calc>1+1</calc> <answer>2</answer>"])
    solver.solve("officeqa", public, CARD, EMPTY, call)
    assert len(call.requests) == 1


def test_t_solver_3_truncated_first_reply_and_second_call_fallback():
    public = officeqa_items(1)[0]["public"]
    call = Script([receipt("<calc>customs_2020 - customs_2019</calc>", finish_reason="length")])
    routed = solver.solve("officeqa", public, CARD, package(BIND), call, worker=bind_sandbox())
    assert (routed["status"], routed["reason"], len(call.requests)) == ("unknown", "model_response_truncated", 1)
    first = "<calc>customs_2020 - customs_2019</calc> <answer>190</answer>"
    for second in (receipt("<answer>2", finish_reason="length"), BudgetStop("cap")):
        call = Script([first, second])
        routed = solver.solve("officeqa", public, CARD, package(BIND), call, worker=bind_sandbox())
        shell = routed["shell"]
        assert routed["output"] == first and routed["status"] == "available"
        assert shell["fallback"] == "second_call_fallback" and shell["deciding_receipt"] == 0
        assert routed["costs"]["calls"] == 2 and len(call.requests) == 2
    assert shell["calls"][1]["reason"] == "model_call_exception:BudgetStop"  # where outcomes_ext finds the stop
    # chain D's margin rule (§4.1): visible completion >= M - 16 with an unclosed tag is a truncation
    for reply, visible, status in (("<calc>customs_2020 - customs_2019", 90, "unknown"),
                                   ("<answer>200</answer>", 95, "available"), ("<answer>200", 50, "available")):
        call = Script([receipt(reply, visible=visible)])
        routed = solver.solve("officeqa", public, CARD, package(BIND), call, worker=bind_sandbox(),
                              nominal_tokens=100)
        assert routed["status"] == status and len(call.requests) == 1
    # a repeated binding name: the later procedure is a fault and its note is not shown
    other = procedure("fx-bind2", ("applies", "bindings"), requests_second_call=True)
    sandbox = FakeSandbox({"fx-bind": {"bindings": lambda view: {"bindings": BINDINGS[:1]}},
                           "fx-bind2": {"bindings": lambda view: {"bindings": BINDINGS}}})
    call = Script(["<answer>1</answer>"])
    routed = solver.solve("officeqa", public, CARD, package(BIND, other), call, worker=sandbox)
    assert [(f["procedure"], f["kind"]) for f in routed["shell"]["faults"]] == [("fx-bind2", "note_duplicate_name")]
    assert sent(call)[NOTES_KEY].count("customs_2019") == 1 and "customs_2020" not in sent(call)[NOTES_KEY]


# ------------------------------------------------------------ T-SOLVER-4: pre-check, feedback, one repair call
def sheet_sandbox(seen=None, repair=True):
    def feedback(view, report, state):
        if seen is not None:
            seen.append(report)
        return {"fields": {"warnings": ["the sheet named in the program is missing"]},
                "request_repair": repair and report["status"] == "exception"}
    return FakeSandbox({"fx-sheet": {"sheet_feedback": feedback}})


def test_t_solver_4_sheet_precheck_feedback_and_one_repair_call(tmp_path, monkeypatch):
    native = FakeNative(report=ERROR_REPORT).install(monkeypatch)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    frozen_call = Script([PROGRAM])
    backends.solve("spreadsheetbench", item["public"], CARD, frozen_call, runtime=SHEET_RUNTIME)
    seen, call = [], Script([PROGRAM, REPAIRED])
    sandbox = sheet_sandbox(seen)
    routed = solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), call, runtime=SHEET_RUNTIME,
                          worker=sandbox)
    assert call.requests[0] == frozen_call.requests[0]  # no first-call note: the frozen first request
    repair = sent(call, 1)
    assert list(repair) == list(sent(call, 0)) + ["previous_program", "repair_instruction", "run_report",
                                                  "repair_notes"]
    assert {key: repair[key] for key in sent(call, 0)} == sent(call, 0)  # the task's instruction is kept
    assert repair["previous_program"] == code(PROGRAM) and repair["repair_instruction"] == REPAIR_FRAME
    assert repair["run_report"] == ERROR_REPORT
    assert repair["repair_notes"] == NOTE_HEADERS["warnings"] + "\n- the sheet named in the program is missing"
    assert seen == [{**ERROR_REPORT, "answer_cells": None}] and len(native.prechecks) == 1
    assert native.prechecks[0]["program"] == code(PROGRAM) and native.prechecks[0]["answer_position"] == "B1"
    # the frozen run above executed its program once; the shell executes the repaired one
    assert routed["output"]["code"] == code(REPAIRED)
    assert [c["code"] for c in native.cases] == [code(PROGRAM), code(REPAIRED)]
    assert sandbox.inputs == ["input.xlsx"] and sandbox.kind == "cell" and sandbox.closed
    shell = routed["shell"]
    assert shell["precheck"]["status"] == "exception" and shell["precheck"]["version"].endswith("-precheck")
    assert shell["deciding_receipt"] == 1 and routed["costs"]["calls"] == 2
    # replay reads the stored report back: nothing runs again, the same requests and prediction
    again = Script([PROGRAM, REPAIRED])
    replayed = solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), again, runtime=SHEET_RUNTIME,
                            worker=sheet_sandbox(), precheck_report=shell["precheck"])
    assert len(native.prechecks) == 1 and again.requests == call.requests
    assert project(replayed) == project(routed)
    # an undeliverable repair keeps the first program; a successful pre-check asks for nothing
    call = Script([PROGRAM, receipt(REPAIRED, finish_reason="length")])  # (the frozen extraction takes any text)
    routed = solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), call, runtime=SHEET_RUNTIME,
                          worker=sheet_sandbox())
    assert routed["output"]["code"] == code(PROGRAM) and routed["shell"]["fallback"] == "second_call_fallback"
    native.report = {"status": "ok", "answer_cells": {"Sheet!B1": "=SUM(A1:A5)"}}
    call = Script([PROGRAM])
    routed = solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), call, runtime=SHEET_RUNTIME,
                          worker=sheet_sandbox())
    assert len(call.requests) == 1 and routed["shell"]["deciding_receipt"] == 0
    # a repair request from a procedure that did not declare a second call is a fault, not a call
    undeclared = procedure("fx-sheet", ("applies", "sheet_feedback"), origin="spreadsheetbench")
    native.report = ERROR_REPORT
    call = Script([PROGRAM])
    routed = solver.solve("spreadsheetbench", item["public"], CARD, package(undeclared), call,
                          runtime=SHEET_RUNTIME, worker=sheet_sandbox())
    assert len(call.requests) == 1 and routed["shell"]["faults"][0]["kind"] == "undeclared_second_call"


# --------------------------------------------------------- T-SOLVER-5: the pre-check's frozen container argv
def fake_docker(monkeypatch, *, cleanup_code=0):
    runs = []

    def bounded(argv, timeout, limit=None):
        if argv[1:3] == ["image", "inspect"]:
            return _Command(0, json.dumps([{"Os": "linux", "Config": {}, "Id": IMAGE}]).encode())
        if argv[1] == "run":
            mount = argv[argv.index("--mount") + 1]
            root = Path(mount.split(",")[1].split("=", 1)[1])
            request = json.loads((root / "request.json").read_text())
            runs.append({"argv": list(argv), "files": sorted(p.name for p in root.iterdir()), "request": request,
                         "worker": (root / "worker.py").read_bytes()})
            result = ({"status": "exception", "exc_type": "ZeroDivisionError",
                       "message": "ZeroDivisionError: division by zero", "answer_cells": None}
                      if request["operation"] == "spreadsheet_precheck" else {"status": "available"})
            return _Command(0, json.dumps({"protocol": backends.PROTOCOL, "result": result}).encode())
        return _Command(cleanup_code, b"", b"daemon unreachable" if cleanup_code else b"")

    monkeypatch.setattr(backends, "_bounded_command", bounded)
    monkeypatch.setattr(shutil, "which", lambda name, *args, **kwargs: "/usr/bin/docker")
    return runs


def normal(argv):
    """The argv without the per-run container name and temporary mount."""
    name, mount = argv[argv.index("--name") + 1], argv[argv.index("--mount") + 1]
    return [a.replace(name, "<name>").replace(mount, "<mount>") for a in argv]


class _Listed:
    """A pre-check container as FakeDocker lists it: there from its ``docker run`` until ``rm --force`` removes it."""

    def stop(self):
        pass


def precheck_docker(tmp_path, monkeypatch, *, transient=0, sticky=False):
    """FakeDocker for the pre-check's removal (``sandbox.cleanup``): every pre-check ``docker run`` of ``fake_docker``
    leaves its container listed until removed; ``transient``: its first n removals fail; ``sticky``: it stays."""
    docker, bounded = FakeDocker(tmp_path / "docker"), backends._bounded_command

    def run(argv, timeout, limit=None):
        name = argv[argv.index("--name") + 1] if argv[1] == "run" else ""
        if name.startswith(client.PREFIX):
            docker.containers[name] = _Listed()
            docker.transient[name] = transient
            if sticky:
                docker.sticky.add(name)
        return bounded(argv, timeout, limit=limit)

    monkeypatch.setattr(backends, "_bounded_command", run)
    monkeypatch.setattr(client, "CLEANUP_PAUSE_SECONDS", 0)
    return docker


def test_t_solver_5_precheck_uses_the_frozen_container_argv_and_env(tmp_path, monkeypatch):
    runs = fake_docker(monkeypatch)
    docker = precheck_docker(tmp_path, monkeypatch)
    workbook = spreadsheetbench_items(tmp_path, 1)[0]["public"]["input_files"][0]
    frozen = backends._native({"operation": "spreadsheet_generate", "code": "x = 1",
                               "input_base64": base64.b64encode(Path(workbook).read_bytes()).decode()}, SHEET_RUNTIME)
    report = precheck.precheck("1 / 0", workbook, "B1", SHEET_RUNTIME, evidence=EVIDENCE, docker=docker)
    assert frozen["status"] == "available" and frozen["cleanup_confirmed"] is True
    assert normal(runs[0]["argv"]) == normal(runs[1]["argv"])  # byte for byte but the name and the mount
    name = runs[1]["argv"][runs[1]["argv"].index("--name") + 1]
    assert client.NAME.fullmatch(name) and not name.startswith("continual-eval-")  # C5-2: not the frozen prefix
    assert runs[0]["files"] == runs[1]["files"] == ["request.json", "worker.py"]
    assert runs[1]["worker"] == precheck.WORKER.read_bytes() and runs[1]["request"]["answer_position"] == "B1"
    assert report == {"version": "fivebench-execskill-v1-precheck", "evidence": EVIDENCE, "status": "exception",
                      "exc_type": "ZeroDivisionError", "message": "ZeroDivisionError: division by zero",
                      "answer_cells": None, "reason": "exception", "runtime_image_id": IMAGE,
                      "cleanup_confirmed": True, "execution_costs": report["execution_costs"]}
    assert report["execution_costs"]["cleanup_seconds"] >= 0 and docker.containers == {}
    assert [c for c in docker.commands if c[0] == "rm"] == [["rm", "--force", name]]
    # an unconfirmed removal is a stop of the pre-check (the frozen case run reports it unknown)
    docker = precheck_docker(tmp_path / "sticky", monkeypatch, sticky=True)
    with pytest.raises(CleanupUnconfirmed):
        precheck.precheck("1 / 0", workbook, "B1", SHEET_RUNTIME, evidence=EVIDENCE, docker=docker)


def test_c5_2_precheck_containers_carry_the_unit_tag_and_their_removal_is_retried(tmp_path, monkeypatch):
    fake_docker(monkeypatch)
    workbook = spreadsheetbench_items(tmp_path, 1)[0]["public"]["input_files"][0]
    unit, tag = "G/s1-spreadsheetbench/run", client.unit_tag("G", "G/s1-spreadsheetbench/run")
    # a slow removal: two failed tries, confirmed at the third (3 tries of 10 s each, registrar decision 2026-10-22)
    docker = precheck_docker(tmp_path / "slow", monkeypatch, transient=2)
    report = precheck.precheck("1 / 0", workbook, "B1", SHEET_RUNTIME, evidence=EVIDENCE, tag=tag, docker=docker)
    removed = [c[2] for c in docker.commands if c[0] == "rm"]
    assert report["status"] == "exception" and len(removed) == client.CLEANUP_TRIES == 3 and len(set(removed)) == 1
    assert removed[0].startswith(client.PREFIX + tag + "-") and client.NAME.fullmatch(removed[0])
    assert docker.containers == {}
    # a removal never confirmed: CleanupUnconfirmed after the third try; the leftover is the unit's (its drain and
    # the S2 leftovers row's prefix list it), not the other chain's
    docker = precheck_docker(tmp_path / "stuck", monkeypatch, sticky=True)
    with pytest.raises(CleanupUnconfirmed):
        precheck.precheck("1 / 0", workbook, "B1", SHEET_RUNTIME, evidence=EVIDENCE, tag=tag, docker=docker)
    assert len([c for c in docker.commands if c[0] == "rm"]) == 3
    with pytest.raises(CleanupUnconfirmed):
        client.drain_unit("G", unit, docker=docker)
    with pytest.raises(CleanupUnconfirmed):
        client.drain_check(docker=docker)
    client.drain_unit("D", "D/s1-spreadsheetbench/run", docker=docker)
    assert client.NAME.fullmatch(precheck.container_name()) and precheck.container_name(tag).count("-") == 4
    with pytest.raises(ValueError):
        precheck.container_name("G-not-a-tag")


class ClosingSandbox(FakeSandbox):
    """A tagged worker with one restart, whose close confirms one removal (as ``client.Worker._discard`` records it)."""
    tag = client.unit_tag("G", "G/s1-officeqa/run")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.restarts = [{"cause": "oom", "container": client.PREFIX + self.tag + "-" + "0" * 32,
                          "procedure": "fx-facts"}]
        self.cleanups = []

    def close(self):
        super().close()
        self.cleanups.append({"container": client.PREFIX + self.tag + "-" + "1" * 32, "seconds": 0.25})


def test_c5_4_the_shell_record_carries_restarts_and_cleanups_after_the_worker_closed(tmp_path):
    item = officeqa_items(1)[0]
    worker = ClosingSandbox({"fx-facts": {"before_call": lambda view, state: {"facts": ["one fact"]}}})
    routed = solver.solve("officeqa", item["public"], CARD, package(FACTS), Script(["<answer>1</answer>"]),
                          worker=worker)
    shell = protocol.verified(routed["shell"], "shell")
    assert worker.closed and shell["sandbox"] == {"restarts": worker.restarts, "cleanups": worker.cleanups}
    assert len(shell["sandbox"]["cleanups"]) == 1  # the closing removal is in the record
    assert solver.solve("officeqa", item["public"], CARD, EMPTY, Script(["<answer>1</answer>"]))["shell"][
        "sandbox"] is None


def test_c5_2_the_shell_names_its_precheck_container_with_the_workers_unit_tag(tmp_path, monkeypatch):
    FakeNative(report=ERROR_REPORT).install(monkeypatch)
    tags = []

    def tagged(program, workbook, answer_position, runtime, *, evidence, tag=None):
        tags.append(tag)
        return precheck.report("ok", evidence=evidence, answer_cells={"Sheet!B1": "15"})

    monkeypatch.setattr(precheck, "precheck", tagged)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    worker = ClosingSandbox({"fx-sheet": {"sheet_feedback": lambda view, report, state: None}})
    solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), Script([PROGRAM]), runtime=SHEET_RUNTIME,
                 worker=worker)
    solver.solve("spreadsheetbench", item["public"], CARD, EMPTY, Script([PROGRAM]), runtime=SHEET_RUNTIME)
    assert tags == [ClosingSandbox.tag, None]


def test_t_solver_5_precheck_worker_report_helpers(tmp_path):
    try:
        {}["Sheet2"]
    except KeyError as error:
        assert precheck_worker.last_line(error) == "KeyError: 'Sheet2'"
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Data"
    book.active["B1"], book.active["B2"] = "=SUM(A1:A5)", 7
    book.save(tmp_path / "output.xlsx")
    assert precheck_worker.answer_cells(tmp_path / "output.xlsx", "B1:B3") == {
        "Data!B1": "=SUM(A1:A5)", "Data!B2": "7", "Data!B3": None}
    assert precheck_worker.answer_cells(tmp_path / "output.xlsx", "not a range") is None
    done = subprocess.run([sys.executable, "-I", "-B", str(Path(precheck_worker.__file__))], capture_output=True,
                          text=True, timeout=60, env={"PATH": "/usr/bin:/bin"})
    assert done.returncode != 0 and "Container-only worker" in done.stderr  # never on the host


# ---------------------------------------------------- T-SOLVER-6: native slot only around container runs
def test_t_solver_6_native_slot_never_held_during_a_model_call(tmp_path, monkeypatch):
    pools = slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None)
    native = FakeNative(report=ERROR_REPORT, holdings=pools[slots.NATIVE].holdings).install(monkeypatch)
    items = spreadsheetbench_items(tmp_path / "items", 12)
    model = pools["glm-5.3"]

    def during(system, user):
        with model.hold():  # refused (slot_lock_order) if this thread still held a native slot
            pass

    results, errors = [None] * 12, []

    def run(k):
        try:
            results[k] = solver.solve("spreadsheetbench", items[k]["public"], CARD, package(SHEET),
                                      Script([PROGRAM, REPAIRED], during=during), runtime=SHEET_RUNTIME,
                                      worker=sheet_sandbox(), native=pools[slots.NATIVE])
        except BaseException as error:  # reported by the assertion below
            errors.append(error)

    threads = [threading.Thread(target=run, args=(k,)) for k in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not errors and not any(thread.is_alive() for thread in threads)
    assert all(r["status"] == "available" and [c["reason"] for c in r["shell"]["calls"]]
               == ["model_response_available"] * 2 for r in results)
    assert len(native.prechecks) == 12 and len(native.cases) == 12
    assert {held for _, held in native.held} == {(slots.NATIVE,)}


# ------------------------------------------------------- T-SOLVER-7: the ALFWorld catch-all re-raises stops
STOPS = (SandboxUnavailable("lost"), CleanupUnconfirmed("rm"), BudgetStop("cap"), AssumptionBroken("drift"),
         LedgerFailure("ledger"), ConfigurationError("config"), ConsumptionConflict("held"), PackageInvalid("bad"))


@pytest.mark.parametrize("stop", STOPS, ids=[type(s).__name__ for s in STOPS])
def test_t_solver_7_alfworld_reraises_every_stop_before_the_catch_all(tmp_path, monkeypatch, stop):
    sessions = alf_sessions(monkeypatch)
    public, game = alf_public(tmp_path)
    sandbox = FakeSandbox(raises={("fx-alf", "alf_after_step"): stop})
    with pytest.raises(type(stop)):
        solver.solve("alfworld", public, CARD, package(ALF), Script(plan_replies(game)), worker=sandbox)
    assert sessions[0].closed and sandbox.closed


def test_t_solver_7_unconfirmed_close_under_a_stop_and_the_frozen_catch_all(tmp_path, monkeypatch):
    sessions = alf_sessions(monkeypatch, close_error=RuntimeError("stuck"))
    public, game = alf_public(tmp_path)
    sandbox = FakeSandbox(raises={("fx-alf", "alf_before_step"): SandboxUnavailable("lost")})
    with pytest.raises(CleanupUnconfirmed) as caught:
        solver.solve("alfworld", public, CARD, package(ALF), Script(plan_replies(game)), worker=sandbox)
    assert isinstance(caught.value.__cause__, SandboxUnavailable) and sessions[0].closed
    # a failed close after a completed episode stays the frozen unknown
    routed = solver.solve("alfworld", public, CARD, package(ALF), Script(plan_replies(game)), worker=FakeSandbox())
    assert routed["reason"] == "alfworld_cleanup_unconfirmed"

    def broken(public_view, runtime):
        raise RuntimeError("no environment")

    monkeypatch.setattr(backends, "_new_alfworld", broken)
    frozen = backends.solve("alfworld", public, CARD, Script([]))
    routed = solver.solve("alfworld", public, CARD, package(ALF), Script([]), worker=FakeSandbox())
    assert project(routed) == frozen and frozen["reason"] == "alfworld_environment_error:RuntimeError"


# ------------------------------- T-SOLVER-8: ALFWorld notes, discouraged list, canonical action, state, privacy
def test_t_solver_8_alfworld_hooks_keep_the_shown_list_and_no_private_metadata(tmp_path, monkeypatch):
    sessions = alf_sessions(monkeypatch)
    public, game = alf_public(tmp_path)

    def before(view, state):
        return {"fields": {"facts": ["visit %d" % (state or {}).get("n", 0)]},
                "discourage": ["look", "inventory", "fly away"]}

    def after(event, state):
        return {"n": (state or {}).get("n", 0) + 1}

    sandbox = FakeSandbox({"fx-alf": {"alf_before_step": before, "alf_after_step": after}})
    replies = ["<action>%s</action>" % game["plan"][0].upper()] + plan_replies(game)[1:]
    call = Script(replies)
    routed = solver.solve("alfworld", public, CARD, package(ALF), call, runtime=ALF_RUNTIMES[1], worker=sandbox)
    assert routed["output"] == {"won": True, "steps": len(game["plan"])}
    steps = routed["shell"]["alfworld_steps"]
    assert steps[0]["how"] == "tag_level1" and sessions[0].actions[0] == game["plan"][0]
    assert routed["trace"][0]["action"] == game["plan"][0]
    for k, (_, text) in enumerate(call.requests):
        request = json.loads(text)
        assert list(request)[-1] == NOTES_KEY
        shown = game["admissible_commands"] + [c for c in game["plan"][k:k + 1] if c not in game["admissible_commands"]]
        assert request["admissible_commands"] == shown  # the environment's list, unchanged
        assert request[NOTES_KEY] == (NOTE_HEADERS["facts"] + "\n- visit %d\n" % k
                                      + NOT_RECOMMENDED_PREFIX + "look, inventory")
        assert steps[k]["discouraged"] == ["look", "inventory"]
    events = [args[0] for _, args in sandbox.called("alf_after_step")]
    assert all(set(event) == {"step", "action", "observation", "admissible_commands"} for event in events)
    blob = json.dumps([call.requests, sandbox.calls, routed])
    assert game["gamefile"] not in blob and "expert_plan" not in blob and "trial_T2019" not in blob
    assert sandbox.kind == "episode" and sandbox.pings == 1
    # a state over the declared bytes is a fault; the procedure is dropped for the rest of the episode
    big = {"pad": "x" * 400}
    sandbox = FakeSandbox({"fx-alf": {"alf_after_step": lambda event, state: big}})
    routed = solver.solve("alfworld", public, CARD, package(ALF), Script(plan_replies(game)), worker=sandbox)
    size = str(len(json.dumps(big, separators=(",", ":"))))
    assert routed["shell"]["faults"] == [{"procedure": "fx-alf", "hook": "alf_after_step",
                                          "kind": "state_over_declared_bytes", "exc_type": None, "message": size}]
    assert len(sandbox.called("alf_before_step")) == 1


def test_t_route_4_alfworld_routing_view_hash_is_asserted(tmp_path, monkeypatch):
    alf_sessions(monkeypatch)
    public, game = alf_public(tmp_path)
    with pytest.raises(ConfigurationError, match="items file"):
        solver.solve("alfworld", {**public, "routing_view_sha256": "0" * 64}, CARD, package(ALF),
                     Script(plan_replies(game)), worker=FakeSandbox())
    other, _ = alf_public(tmp_path, 1)  # a registered view of another game: consistent, but not this reset
    with pytest.raises(ConfigurationError, match="live reset"):
        solver.solve("alfworld", {**public, "routing_view": other["routing_view"],
                                  "routing_view_sha256": other["routing_view_sha256"]},
                     CARD, package(ALF), Script(plan_replies(game)), worker=FakeSandbox())
    with pytest.raises(ConfigurationError, match="missing"):
        solver.solve("alfworld", {"game_file": public["game_file"]}, CARD, package(ALF), Script(plan_replies(game)),
                     worker=FakeSandbox())
    assert solver.routing_view("alfworld", public) == public["routing_view"]


# ------------------------------------------------------------------------------------ arms: placebo, twins
def test_placebo_arm_shows_sham_content_with_the_same_predicates_and_trigger_rules(tmp_path, monkeypatch):
    public = officeqa_items(1)[0]["public"]
    sham = {"bindings": {"bindings": [{"name": "amount_a", "quote": "a 7", "value": "7"}]}}
    placebo = {"procedures": {"fx-bind": sham}, "seed": "fixture-seed"}
    sandbox = bind_sandbox()
    call = Script(["<calc>amount_a * 2</calc>", "<answer>14</answer>"])
    routed = solver.solve("officeqa", public, CARD, package(BIND), call, worker=sandbox, placebo=placebo)
    assert '- amount_a = 7 (quoted: "a 7")' in sent(call, 0)[NOTES_KEY]
    assert sent(call, 1)["computed"] == [{"expr": "amount_a * 2", "value": NOT_EVALUATED}]
    assert sandbox.called("bindings") == [] and len(sandbox.called("applies")) == 1
    assert routed["shell"]["arm"]["placebo"] == ["fx-bind"]
    # SpreadsheetBench: the shadow of the real hook decides the repair; the donor's advice is shown
    FakeNative(report=ERROR_REPORT).install(monkeypatch)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    placebo = {"procedures": {"fx-sheet": {"sheet_feedback": {"facts": ["donor advice"]}}}, "seed": "fixture-seed"}
    call = Script([PROGRAM, REPAIRED])
    solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), call, runtime=SHEET_RUNTIME,
                 worker=sheet_sandbox(), placebo=placebo)
    assert sent(call, 1)["repair_notes"] == NOTE_HEADERS["facts"] + "\n- donor advice"
    assert sent(call, 1)["run_report"] == ERROR_REPORT  # the shell's own error message is kept (FA-F11)
    # ALFWorld: the discouragement drawn at dispatch from the admissible commands with the seed
    alf_sessions(monkeypatch)
    alf, game = alf_public(tmp_path)
    placebo = {"procedures": {"fx-alf": {"alf_before_step": [{"fields": {"facts": ["donor"]}, "discourage": 2}]}},
               "seed": "fixture-seed"}
    sandbox, call = FakeSandbox(), Script(plan_replies(game))
    solver.solve("alfworld", alf, CARD, package(ALF), call, worker=sandbox, placebo=placebo)
    first = json.loads(call.requests[0][1])
    drawn = solver.sham_discouraged(first["admissible_commands"], 2, "fixture-seed", 0)
    assert len(drawn) == 2 and first[NOTES_KEY].endswith(NOT_RECOMMENDED_PREFIX + ", ".join(drawn))
    assert sandbox.called("alf_before_step") == [] and sandbox.called("alf_after_step") == []


def test_r3_bindings_is_qa_only_no_note_and_no_invitation_on_spreadsheetbench(tmp_path, monkeypatch):
    """Registration §2.4, §3 (registrar addendum 2026-10-22 15:5x R3): SpreadsheetBench never runs the <calc> round
    trip, so the shell runs no bindings hook there -- the first request is the frozen one, without a bindings note or
    the compute invitation; a before_call note of the same package is still shown."""
    FakeNative().install(monkeypatch)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    frozen_call = Script([PROGRAM])
    backends.solve("spreadsheetbench", item["public"], CARD, frozen_call, runtime=SHEET_RUNTIME)
    sandbox, call = bind_sandbox(), Script([PROGRAM])
    routed = solver.solve("spreadsheetbench", item["public"], CARD, package(BIND), call, runtime=SHEET_RUNTIME,
                          worker=sandbox)
    assert call.requests == frozen_call.requests and sandbox.called("bindings") == []
    assert routed["shell"]["route"]["enabled"] == ["fx-bind"] and routed["shell"]["faults"] == []
    sandbox = FakeSandbox({"fx-facts": {"before_call": lambda view, state: {"facts": ["row 2019"]}},
                           "fx-bind": {"bindings": lambda view: {"bindings": BINDINGS}}})
    call = Script([PROGRAM])
    solver.solve("spreadsheetbench", item["public"], CARD, package(FACTS, BIND), call, runtime=SHEET_RUNTIME,
                 worker=sandbox)
    shown = sent(call, 0)[NOTES_KEY]
    assert "row 2019" in shown and NOTE_HEADERS["bindings"] not in shown and COMPUTE_INVITE not in shown
    assert sandbox.called("bindings") == [] and len(call.requests) == 1


def test_withholding_twin_runs_the_predicate_and_shows_nothing():
    public = officeqa_items(1)[0]["public"]
    frozen_call = Script(["<answer>1</answer>"])
    backends.solve("officeqa", public, CARD, frozen_call)
    sandbox, call = bind_sandbox(), Script(["<answer>1</answer>"])
    routed = solver.solve("officeqa", public, CARD, package(BIND), call, worker=sandbox, withhold={"fx-bind"})
    entry = routed["shell"]["route"]["per_procedure"]["fx-bind"]
    assert entry["shadow_fired"] is True and entry["enabled"] is False and entry["withheld"] is True
    assert call.requests == frozen_call.requests and sandbox.called("bindings") == []
    routed = solver.solve("officeqa", public, CARD, package(BIND), Script(["<answer>1</answer>"]),
                          worker=bind_sandbox(), restore={"fx-bind"})
    assert routed["shell"]["route"]["per_procedure"]["fx-bind"]["restored"] is True


# ----------------------------------------------------------------------------- T-SOLVER-9: the text arm T_F
def test_t_solver_9_text_arm_per_hook(tmp_path, monkeypatch):
    public = officeqa_items(1)[0]["public"]
    texts = {"fx-facts": "Lists the table rows named in the question.", "fx-bind": "Names the quoted table values."}
    sandbox = FakeSandbox({"fx-facts": {"before_call": lambda view, state: {"facts": ["row 2019"]}},
                           "fx-bind": {"bindings": lambda view: {"bindings": BINDINGS}}})
    call = Script(["<calc>2 + 3</calc> <calc>customs_2020</calc>", "<answer>5</answer>"])
    routed = solver.solve("officeqa", public, CARD, package(FACTS, BIND), call, worker=sandbox, text=texts)
    assert sent(call, 0)[NOTES_KEY] == "\n\n".join([texts["fx-facts"], texts["fx-bind"], COMPUTE_INVITE])
    assert sent(call, 1)["computed"] == [{"expr": "2 + 3", "value": "5"},
                                         {"expr": "customs_2020", "value": NOT_EVALUATED}]  # no names, no values
    assert routed["shell"]["arm"]["text"] == ["fx-bind", "fx-facts"]
    # no output on the item: nothing shown, the frozen request
    frozen_call = Script(["<answer>1</answer>"])
    backends.solve("officeqa", public, CARD, frozen_call)
    call = Script(["<answer>1</answer>"])
    solver.solve("officeqa", public, CARD, package(FACTS), call, worker=FakeSandbox(),
                 text={"fx-facts": texts["fx-facts"]})
    assert call.requests == frozen_call.requests
    # sheet_feedback: the description and the shell's error message; no procedure code runs
    FakeNative(report=ERROR_REPORT).install(monkeypatch)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    sandbox, call = sheet_sandbox(), Script([PROGRAM, REPAIRED])
    solver.solve("spreadsheetbench", item["public"], CARD, package(SHEET), call, runtime=SHEET_RUNTIME,
                 worker=sandbox, text={"fx-sheet": "Checks the sheet names used by the program."})
    assert sent(call, 1)["repair_notes"] == "Checks the sheet names used by the program."
    assert sent(call, 1)["run_report"] == ERROR_REPORT and sandbox.called("sheet_feedback") == []
    # ALFWorld: the description every step, no discouraged list, no state
    alf_sessions(monkeypatch)
    alf, game = alf_public(tmp_path)
    sandbox, call = FakeSandbox(), Script(plan_replies(game))
    routed = solver.solve("alfworld", alf, CARD, package(ALF), call, worker=sandbox,
                          text={"fx-alf": "Suggests where objects are kept."})
    assert all(json.loads(u)[NOTES_KEY] == "Suggests where objects are kept." for _, u in call.requests)
    assert sandbox.called("alf_before_step") == [] and sandbox.called("alf_after_step") == []
    assert all(s["discouraged"] == [] for s in routed["shell"]["alfworld_steps"])


# ------------------------------------------------------------- the real sandbox worker behind the shell
def test_the_shell_drives_the_real_worker_through_fake_docker(tmp_path):
    from skillopt.execskill.sandbox import client
    from tests.execskill_fakes_docker import FakeDocker

    hooks = ('"""Quotes the 2019 customs value."""\n\n\ndef applies(view):\n    return "Customs" in view["context"]\n'
             '\n\ndef bindings(view):\n    return {"bindings": [{"name": "customs_2019", "quote": "2019 | 1000", '
             '"value": "1000"}]}\n')
    real = procedure("fx-real", ("applies", "bindings"), requests_second_call=True, source=hooks)
    docker = FakeDocker(tmp_path / "containers")
    limits = {kind: client.Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
              for kind in client.KINDS}
    worker = client.Worker(docker=docker, limits=limits, scratch=tmp_path)
    try:
        call = Script(["<calc>customs_2019 * 2</calc>", "<answer>2000</answer>"])
        routed = solver.solve("officeqa", officeqa_items(1)[0]["public"], CARD, package(real), call, worker=worker)
    finally:
        worker.close()
        docker.close()
    assert sent(call, 1)["computed"] == [{"expr": "customs_2019 * 2", "value": "2000"}]
    assert routed["output"] == "<answer>2000</answer>" and routed["shell"]["faults"] == []
