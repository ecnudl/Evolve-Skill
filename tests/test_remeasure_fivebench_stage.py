"""Re-measuring an unchanged stage policy: fake study and fake frozen worker, no model calls."""
import contextlib
import fcntl
import json

import pytest

from scripts import continue_fivebench_baselines as sequence
from scripts import remeasure_fivebench_stage as remeasure
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, checkpoint_path, read_json, write_json

SERVICE = {"name": "fixture-service"}
NO_SKILL = ["pass", "fail", "fail", "pass"]
FIRST = ["pass", "pass", "fail", "pass"]    # the study's (reused) observation of the Skill
AGAIN = ["pass", "pass", "pass", "fail"]    # the fake worker's new observation of the same Skill


def rows(statuses):
    return [{"task_id": f"t{i // 2}", "family_id": f"f{i // 2}", "repeat": i % 2, "status": s,
             "record_hash": f"{i:064d}"} for i, s in enumerate(statuses)]


def write_study(root, *, stages=(("selected_update", "skill A", False), ("pending_carry_parent", "skill A", True))):
    references = {}
    for benchmark in BENCHMARKS:
        references[benchmark] = {"benchmark": benchmark, "root": str(root.parent / f"ref-{benchmark}"),
                                 "source": "/frozen/source", "evaluation_source": "/frozen/derived",
                                 "python": "/frozen/python", "plan_hash": "p" * 64, "report_hash": "r" * 64,
                                 "positions": 4, "rows": rows(NO_SKILL), "model_service": SERVICE}
    protocol = seal({"version": sequence.VERSION, "root": str(root), "order": list(BENCHMARKS),
                     "methods": ["skillopt", "gepa"], "references": references, "model": {"provider": "fixture"},
                     "roles": {b: {"runtime": {}} for b in BENCHMARKS},
                     "config": {"workers": 10, "native_lock": str(root.parent / "native.lock")},
                     "evaluation_runtime_overrides": {"spreadsheetbench": {"recalculation": {"q": 1}}}})
    write_json(root / "protocol.json", protocol)
    previous, parent = "", None
    for number, (action, skill, reused) in enumerate(stages, 1):
        cells = {t: {"result": {"benchmark": t, "model_service": SERVICE, "rows": rows(FIRST)}, "reused": reused}
                 for t in BENCHMARKS}
        record = seal({"protocol_hash": protocol["record_hash"], "method": "skillopt", "stage": number,
                       "benchmark": BENCHMARKS[number - 1], "parent_skill": previous, "parent_stage_hash": parent,
                       "action": action, "skill": skill, "cells": cells})
        write_json(root / f"skillopt/s{number}-{BENCHMARKS[number - 1]}/stage.json", record)
        previous, parent = skill, record["record_hash"]
    return root


@pytest.fixture
def worker(monkeypatch):
    calls = []

    def invoke(reference, operation, request, output, *, log):
        calls.append((operation, read_json(request, sealed=True)["benchmark"]))
        req = read_json(request, sealed=True)
        if operation == "evaluate":
            run = remeasure.safe_path(req["run"])
            assert not run.exists()
            run.mkdir(parents=True)
            write_json(checkpoint_path(run, req["method"], "h0", len(req["chain"])), seal({"skill_text": req["chain"][-1]}))
            result = seal({"root": str(run), "benchmark": req["benchmark"], "positions": 4, "model_service": SERVICE,
                           "counts": {}, "costs": {"logical_calls": 4}, "rows": rows(AGAIN)})
        else:
            result = read_json(remeasure.safe_path(req["run"]).parent.parent / f"evaluation-{req['benchmark']}.json",
                               sealed=True)
        write_json(output, result)
        return result

    monkeypatch.setattr(sequence, "_invoke", invoke)
    monkeypatch.setattr(sequence, "check_frozen_files", lambda protocol: None)
    monkeypatch.setattr("skillopt.continual_learning.launch.learning_environment",
                        lambda manifest: contextlib.nullcontext())
    return calls


def test_prepare_poses_the_orchestrators_request_for_the_unchanged_policy(tmp_path, worker):
    study = write_study(tmp_path / "study")
    plan = remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    stage = read_json(study / "skillopt/s2-spreadsheetbench/stage.json", sealed=True)
    assert plan["stage_hash"] == stage["record_hash"] and plan["replaces_reused_cells"] is False
    for target in BENCHMARKS:
        request = read_json(plan["requests"][target], sealed=True)
        assert request["chain"] == ["skill A", "skill A"] and request["stage_hash"] == stage["record_hash"]
        assert request["workers"] == 10 and request["run"] == str(tmp_path / "out" / f"evaluations/{target}")
        assert request["reference"] == {k: f"/frozen/{v}" for k, v in
                                        (("source", "source"), ("evaluation_source", "derived"), ("python", "python"))
                                        } | {"root": str(tmp_path / f"ref-{target}")}
        assert ("evaluation_runtime" in request) == (target == "spreadsheetbench")
    assert worker == []  # preparing never calls the worker


EMPTY = (("completed_no_update", "", True), ("completed_no_update", "", True))


@pytest.mark.parametrize("stage,stages,message", [
    (1, None, "reused every observation"),      # S1 has its own observations
    (3, None, "No such file|stage.json"),       # stage not finished
])
def test_prepare_refuses_stages_that_are_not_unchanged_non_empty_policies(tmp_path, worker, stage, stages, message):
    study = write_study(tmp_path / "study", **({"stages": stages} if stages else {}))
    with pytest.raises((ValueError, FileNotFoundError), match=message):
        remeasure.prepare(study, "skillopt", stage, tmp_path / "out", tmp_path / "repo")


def test_prepare_refuses_an_output_inside_the_study_or_an_existing_one(tmp_path, worker):
    study = write_study(tmp_path / "study")
    with pytest.raises(ValueError, match="outside the study"):
        remeasure.prepare(study, "skillopt", 2, study / "remeasure", tmp_path / "repo")
    (tmp_path / "taken").mkdir()
    with pytest.raises(ValueError, match="outside the study"):
        remeasure.prepare(study, "skillopt", 2, tmp_path / "taken", tmp_path / "repo")


def test_run_waits_for_the_native_lock_evaluates_once_then_only_verifies(tmp_path, worker, monkeypatch):
    study = write_study(tmp_path / "study")
    remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    real = fcntl.flock
    monkeypatch.setattr(remeasure.fcntl, "flock", lambda fd, op: worker.append(("lock", op)) or real(fd, op))
    summary = remeasure.run(tmp_path / "out")
    paid = [c for c in worker if c[0] != "lock"]
    assert ("lock", fcntl.LOCK_EX) in worker[:worker.index(paid[0])]  # the blocking native lock comes first
    assert paid == [("evaluate", t) for t in BENCHMARKS]
    cell = summary["cells"]["korbench"]
    assert cell["remeasured"]["counts"] == {"pass": 3, "fail": 1, "unknown": 0}
    assert cell["vs_no_skill"]["positions"]["win"] == 2 and cell["vs_no_skill"]["positions"]["loss"] == 1
    assert cell["reused_observation"]["counts"]["pass"] == 3
    assert cell["remeasured_vs_reused"]["positions"] == {"win": 1, "loss": 1, "tie": 2, "unknown": 0, "unscored": 0}
    worker.clear()
    assert remeasure.run(tmp_path / "out") == summary
    assert [c for c in worker if c[0] != "lock"] == [("verify-evaluation", t) for t in BENCHMARKS]  # never pays again


def test_an_interrupted_evaluation_is_never_resumed(tmp_path, worker):
    study = write_study(tmp_path / "study")
    remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    (tmp_path / "out/evaluations/bigcodebench").mkdir(parents=True)  # begun, no recorded result
    with pytest.raises(ValueError, match="never resumed"):
        remeasure.run(tmp_path / "out")
    assert worker == []


def test_a_changed_request_or_stage_is_refused(tmp_path, worker):
    study = write_study(tmp_path / "study")
    plan = remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    path = remeasure.safe_path(plan["requests"]["korbench"])
    request = read_json(path, sealed=True)
    original = path.read_text()
    path.write_text(json.dumps(seal({**{k: v for k, v in request.items() if k != "record_hash"}, "workers": 99})))
    with pytest.raises(ValueError, match="request changed"):
        remeasure.run(tmp_path / "out")
    path.write_text(original)
    for stage in study.glob("skillopt/*/stage.json"):  # the study is re-sealed with another Skill
        stage.unlink()
    write_study(tmp_path / "study2", stages=(("selected_update", "skill B", False), ("pending_carry_parent", "skill B", True)))
    for stage in (tmp_path / "study2").glob("skillopt/*/stage.json"):
        target = study / stage.relative_to(tmp_path / "study2")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(stage.read_text().replace(str(tmp_path / "study2"), str(study)))
    with pytest.raises(ValueError, match="study or stage changed|binding mismatch"):
        remeasure.run(tmp_path / "out")
    assert worker == []


def test_an_output_inside_a_frozen_reference_is_refused(tmp_path, worker):
    study = write_study(tmp_path / "study")
    with pytest.raises(ValueError, match="frozen references"):
        remeasure.prepare(study, "skillopt", 2, tmp_path / "ref-korbench" / "remeasure", tmp_path / "repo")
    assert not (tmp_path / "ref-korbench").exists()


def test_a_request_changed_while_waiting_for_the_lock_is_refused(tmp_path, worker, monkeypatch):
    study = write_study(tmp_path / "study")
    plan = remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    path = remeasure.safe_path(plan["requests"]["alfworld"])
    request = read_json(path, sealed=True)
    real = fcntl.flock

    def flock(fd, op):
        real(fd, op)
        if op == fcntl.LOCK_EX:  # the study released its lock; the request was swapped meanwhile
            path.write_text(json.dumps(seal({**{k: v for k, v in request.items() if k != "record_hash"},
                                             "chain": ["skill A", "another skill"]})))
    monkeypatch.setattr(remeasure.fcntl, "flock", flock)
    with pytest.raises(ValueError, match="request changed"):
        remeasure.run(tmp_path / "out")
    assert worker == []


def test_the_evaluated_policy_must_be_the_stage_policy(tmp_path, worker, monkeypatch):
    study = write_study(tmp_path / "study")
    remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    invoke = remeasure.sequence._invoke

    def swapped(reference, operation, request, output, *, log):
        result = invoke(reference, operation, request, output, log=log)
        req = read_json(request, sealed=True)
        path = checkpoint_path(remeasure.safe_path(req["run"]), req["method"], "h0", len(req["chain"]))
        path.unlink()
        write_json(path, seal({"skill_text": "a different Skill"}))
        return result
    monkeypatch.setattr(remeasure.sequence, "_invoke", swapped)
    with pytest.raises(ValueError, match="differs from the stage policy"):
        remeasure.run(tmp_path / "out")


def test_an_empty_skill_re_measures_the_no_skill_policy_and_listing_finds_reused_stages(tmp_path, worker):
    study = write_study(tmp_path / "study", stages=EMPTY)
    assert remeasure.candidates(study) == [("skillopt", 1), ("skillopt", 2)]
    plan = remeasure.prepare(study, "skillopt", 2, tmp_path / "out", tmp_path / "repo")
    assert plan["skill_bytes"] == 0
    assert read_json(plan["requests"]["korbench"], sealed=True)["chain"] == ["", ""]
    summary = remeasure.run(tmp_path / "out")
    assert summary["cells"]["korbench"]["remeasured"]["counts"] == {"pass": 3, "fail": 1, "unknown": 0}
    other = write_study(tmp_path / "other")
    assert remeasure.candidates(other) == [("skillopt", 2)]  # S1 measured its own observations
