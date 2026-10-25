"""Synthetic in-process route-B control: actual units, checks, training, gates and freeze; no external execution."""
from __future__ import annotations

import itertools
import json
import socket
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, describer, engineer, examiner, profiles as protocol, rounds, slots,
                                solver, step, units, zebralogic)
from skillopt.execskill.package import FIXTURE, Package, Procedure, empty
from skillopt.execskill.registry import Registry
from tests.execskill_fakes import FakeGLM, FakeSolver, engineer_reply
from tests.execskill_fakes_env import FakeSandbox

BENCH = "zebralogic"
SOURCE = '''def applies(view):
    return "columns" in view and "House 1 | " in view.get("question", "")
def before_call(view, state):
    rows = [line.split(" | ") for line in view["question"].splitlines() if line.startswith("House ")]
    return {"table": [["House"] + view["columns"]] + rows}
'''


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Synthetic positive-control fixtures cannot use networking")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, forbidden)


class SourceWorker(FakeSandbox):
    """Executes only this module's authored procedures in process, never model-written source or a container."""
    def start(self, package, *, kind, inputs_dir=None):
        for p in package.procedures:
            namespace = {}
            exec(compile(p.source, "<authored-zebra-fixture>", "exec"), namespace)
            self.hooks[p.id] = {hook: namespace[hook] for hook in p.hooks}
        self.rejected = {}
        return super().start(package, kind=kind, inputs_dir=inputs_dir)


@contextmanager
def workers(package, *, kind="cell", hashseed=0, inputs_dir=None, tag=None):
    worker = SourceWorker().start(package, kind=kind, inputs_dir=inputs_dir)
    try:
        yield worker
    finally:
        worker.close()


def fixture_pool():
    """200 authored puzzles; each stratum includes its three registered probe IDs where applicable."""
    out = []
    for task in zebralogic.DOMAIN:
        houses, width = map(int, task.split("*"))
        columns = ["Attribute%d" % c for c in range(width)]
        prefix = "lgp-test-" + task.replace("*", "x") + "-"
        excluded = [i for i in zebralogic.EXCLUDED_IDS if i.startswith(prefix)]
        ids = excluded + ["synthetic-%s-%02d" % (task, n) for n in range(20 - len(excluded))]
        for n, ident in enumerate(ids):
            rows = [[str(h)] + ["v%s_%d_%d_%d" % (task.replace("*", "x"), n, h, c)
                                for c in range(width)] for h in range(1, houses + 1)]
            question = ("There are %d houses, numbered 1 to %d from left to right, as seen from across the street. "
                        "Synthetic puzzle %s: each line states the attributes of one house.\n") % (houses, houses, ident)
            question += "\n".join(" | ".join(["House " + row[0]] + row[1:]) for row in rows)
            out.append(zebralogic.normalize({"id": ident, "bench": BENCH, "task": task, "size": task,
                "puzzle": question, "solution": {"header": ["House"] + columns, "rows": rows}}))
    return out


def public_grid(view):
    rows = [line.split(" | ") for line in view["question"].splitlines() if line.startswith("House ")]
    return {row[0]: dict(zip(view["columns"], row[1:])) for row in rows}


def build(tmp_path, monkeypatch, *, effect="accept"):
    pool = fixture_pool()
    cut = zebralogic.slices(pool)
    run_questions = {i["public"]["question"] for i in cut["run"]}
    def answer(system, user):
        view = zebralogic.parse_user(user)
        grid = public_grid(view)
        notes = view.get(protocol.NOTES_KEY, "")
        own = all("| " + " | ".join([house] + list(row.values())) + " |" in notes
                  for house, row in grid.items())
        gain = own and effect != "no_gain" and (effect != "reject" or view["question"] in run_questions)
        if not gain:
            first = next(iter(grid))
            grid[first][view["columns"][0]] = "wrong-fixture-value"
        return json.dumps({"reasoning": "Synthetic scripted response.", "solution": grid})
    def role(system, payload):
        if system == examiner.DETECTOR_SYSTEM:
            return engineer_reply({"detectors": []}, [])
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({"findings": []}, [])
        if system == engineer.ENGINEER_SYSTEM_ZPC:
            if payload["request"] == "fix" or payload["round"] == 1:
                return engineer_reply({"changes": [{"kind": "new", "description": "Tabulates the public clues.",
                    "hooks": ["applies", "before_call"], "max_note_chars": 4000,
                    "excluded_benches": list(protocol.BENCHES)}]}, [SOURCE])
            return engineer_reply({"changes": []}, [])
        if system == describer.DESCRIBER_SYSTEM:
            return "Read each public clue and tabulate each house and its attributes."
        return {"verdict": "no", "reason": "Only a generic method is described."}
    fake_solver = FakeSolver(tmp_path / "solver", [(None, answer)], max_tokens=16_384, read_timeout=600)
    glm = FakeGLM(tmp_path / "glm", role)
    root = tmp_path / "root"
    ledger = Budget(budgets.ledger_root(root, "D"), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps("D", protocol.ZEBRA_PC_V1))
    setting = units.Setting(run="synthetic-zpc", root=root, shared=root / "shared", pools={BENCH: pool},
        cards={BENCH: zebralogic.CARD_TEXT}, runtime={BENCH: {}},
        clients=lambda model, bench: glm.client if bench is None else fake_solver.client,
        budget=ledger, slots=slots.pools(tmp_path / "slots", poll=0.01, log=lambda _: None), sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0, branch="E", extra={"configuration": protocol.ZEBRA_PC_V1})
    ticks = itertools.count()
    clock = lambda: float(next(ticks))
    original = units.cell_context
    def context(setting_, attempt, endpoint):
        ctx = original(setting_, attempt, endpoint)
        ctx.worker, ctx.clock = lambda bench: SourceWorker(), clock
        return ctx
    monkeypatch.setattr(units, "cell_context", context)
    monkeypatch.setattr(rounds, "cell_context", context)
    services = step.Services(registry=Registry(tmp_path / "registry", evidence=FIXTURE), sources=None,
                             workers=workers, clock=clock, sleep=lambda _: None)
    return setting, services, fake_solver, glm


def result(root, name):
    return protocol.verified(read_json(root / name / "unit.json"), "unit")["result"]


@pytest.mark.parametrize("effect", ["accept", "reject", "no_gain"])
def test_real_one_step_pipeline_acceptance_rejection_and_resume(tmp_path, monkeypatch, effect):
    setting, services, fake_solver, glm = build(tmp_path, monkeypatch, effect=effect)
    parent = empty(step="D/s0", evidence=FIXTURE)
    found = step.run_step(setting, "D", BENCH, 1, parent, services=services)
    root = setting.root / "D" / "s1-zebralogic"
    assert result(root, "run")["cells"] == 60
    assert result(root, "generate")["mode"] == "selection_only"
    assert result(root, "generate")["generator"] is None
    engineered = result(root, "engineer-r1")["engineer"]
    assert engineered["prompt_sha256"] == engineer.ENGINEER_PROMPT_ZPC_SHA256
    assert engineered["changes"][0]["survived"]
    assert next(c for c in engineered["changes"][0]["attempts"][-1]["checks"] if c["check"] == "C6b")["passed"]
    training = result(root, "train-r1")
    assert training["differs"] == 60 and training["cells"] == 120 and training["pruned"] == []
    assert training["verdict"]["sign_required"] is False
    if effect == "no_gain":
        assert not training["adopted"] and found.record["reason"] == "no_training_gain"
        assert not (root / "accept").exists() and found.package.sha256 == parent.sha256
    else:
        assert training["adopted"] and len(training["verdict"]["fixed"]) == 60
        assert result(root, "selftest")["reason"] == "no_generated_items"
        accepted = result(root, "accept")
        sealed = protocol.verified(read_json(root / "accept" / "sealed.json"), "acceptance-sealed")
        assert sealed["dup"] is False and sealed["g_acc"] is None
        assert sealed["placebo_i"] is None and sealed["placebo_y"] is not None
        assert sealed["j6_registered"] is False
        decision = protocol.verified(read_json(root / "accept" / "attempt-1" / "decision" / "decision.json"),
                                     "decision")
        assert decision["guards"]["J6_dup"] is None and decision["guards"]["J7_meta"] is None
        assert decision["guards"]["J1"]["ok"] is (effect == "accept")
        assert all(decision["guards"][name]["ok"] for name in ("J3", "J4_items", "J5"))
        assert sealed["reuse"]["card_sample"] is None
        assert found.record["decision"] == ("accept" if effect == "accept" else "reject")
        assert accepted["decision"] == found.record["decision"]
        assert bool(found.package.procedures) is (effect == "accept")
        if effect == "accept":
            assert found.package.procedures[0].source == SOURCE
            assert result(root, "freeze")["descriptions"]
    lines = services.registry.entries("D-zpc1", BENCH)
    assert len(lines) == (60 if effect == "no_gain" else 160)
    assert {entry["state"] for entry in lines.values()} == {"decided"}
    assert all(entry["open"] == 0 for entry in setting.budget.snapshot().values())
    calls = len(fake_solver.requests), len(glm.seen)
    again = step.run_step(setting, "D", BENCH, 1, parent, services=services)
    assert again.record == found.record and (len(fake_solver.requests), len(glm.seen)) == calls
