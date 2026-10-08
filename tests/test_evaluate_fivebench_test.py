"""Canonical-test evaluation of a study's policies; no model calls.

Controller tests use a fake study and a fake worker. The worker tests run the real
worker in-process: real plans, checkpoints, identities, reports and the real SearchQA
scorer, with authored fixture inference instead of a model.
"""
import contextlib
import fcntl
import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts import continue_fivebench_baselines as sequence
from scripts import evaluate_fivebench_test as tool
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import core, datasets, runner
from skillopt.continual_eval.core import BENCHMARKS, LONG_RESPONSE_VERSION, checkpoint_path, read_json, write_json
from skillopt.continual_eval.fixtures import fixture_panel, fixture_score, fixture_solve

SERVICE = {"name": "fixture-service"}
IDENTITY = {"source_identity": {"a.py": "1"}, "host_runtime": {"python": "3"}}
# Per method: (action, skill) for S1..S5, mirroring study F's shapes.
STAGES = {"skillopt": [("selected_update", "A"), ("pending_carry_parent", "A"), ("selected_update", "B"),
                       ("selected_update", "C"), ("completed_no_update", "C")],
          "gepa": [("completed_no_update", ""), ("completed_no_update", ""), ("selected_update", "G"),
                   ("selected_update", "H"), ("completed_no_update", "H")]}
TRAIN = {b: [f"{b}-d{i}" for i in range(2)] for b in BENCHMARKS}
TEST = {b: [f"{b}-t{i}" for i in range(3)] for b in BENCHMARKS}
TEST["spreadsheetbench"].append("42930")  # released but unscorable; excluded from evaluation
PASSING = {"no_skill": 1, "skillopt-s1": 2, "skillopt-s3": 2, "skillopt-s4": 3, "gepa-s3": 0, "gepa-s4": 2}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_study(root, *, learning=None, usage=None):
    references, roles = {}, {}
    for benchmark in BENCHMARKS:
        ref_root = root.parent / f"ref-{benchmark}"
        plan = seal({"config": {"panels": {b: f"/dev/{b}.json" for b in BENCHMARKS}, "partition": "development",
                                "repeats": 2, "methods": ["no_skill"], "model": {"name": "m"},
                                "runtime": {benchmark: {"recalculation": {"engine": "x", "qualification_path": "old"}}}},
                     "tasks": [{"benchmark": benchmark, "task_id": t} for t in TRAIN[benchmark]]})
        write_json(ref_root / "plan.json", plan)
        write_json(root.parent / f"learning-{benchmark}.json",
                   {"tasks": [{"task_id": t} for t in (learning or {}).get(benchmark, TRAIN[benchmark][:1])]})
        references[benchmark] = {"root": str(ref_root), "plan_hash": plan["record_hash"], "source": "/frozen/src",
                                 "evaluation_source": f"/frozen/derived-{benchmark}", "python": "/frozen/python",
                                 "model_service": SERVICE}
        roles[benchmark] = {"path": str(root.parent / f"learning-{benchmark}.json"), "runtime": {}}
    protocol = seal({"version": sequence.BUDGET_SEQUENCE, "root": str(root), "order": list(BENCHMARKS),
                     "methods": ["skillopt", "gepa"], "references": references, "model": {"provider": "fixture"},
                     "roles": roles, "source_files": {str(Path(sequence.__file__).absolute()): "o" * 64},
                     "config": {"workers": 10, "native_lock": str(root.parent / "native.lock"),
                                "learning_recovery_policy": {"skill_budget_bytes": 32000}},
                     "evaluation_runtime_overrides": {"spreadsheetbench": {"recalculation": {
                         "qualification_path": "new", "qualification_sha256": "s", "qualification_hash": "h"}}}})
    write_json(root / "protocol.json", protocol)
    for method, stages in STAGES.items():
        previous, parent = "", None
        for number, (action, skill) in enumerate(stages, 1):
            cells = {}
            for benchmark in BENCHMARKS:
                if action == "selected_update":  # the study evaluated this new policy itself
                    run = root / f"{method}/s{number}-{BENCHMARKS[number - 1]}/evaluations/{benchmark}"
                    plan = seal({**IDENTITY, "cell": f"{method}-s{number}-{benchmark}"})
                    write_json(run / "plan.json", plan)
                    cells[benchmark] = {"kind": "new_frozen_policy_evaluation", "reused": False,
                                        "result": {"root": str(run), "plan_hash": plan["record_hash"]}}
                else:
                    cells[benchmark] = {"kind": "new_frozen_policy_evaluation", "reused": True, "result": {}}
            record = seal({"protocol_hash": protocol["record_hash"], "method": method, "stage": number,
                           "benchmark": BENCHMARKS[number - 1], "parent_skill": previous, "parent_stage_hash": parent,
                           "action": action, "skill": skill, "cells": cells})
            write_json(root / f"{method}/s{number}-{BENCHMARKS[number - 1]}/stage.json", record)
            previous, parent = skill, record["record_hash"]

    def entries(tasks):
        return [{"task_id": t, "family_id": "family-" + t} for t in tasks]
    split = seal({"version": tool.SPLIT_VERSION, "sources": {},
                  "f_study_usage": {b: {"protocol_hash": protocol["record_hash"],
                                        "reference_plan_hash": references[b]["plan_hash"],
                                        "learning_panel_sha256": sha(roles[b]["path"]), **(usage or {})}
                                    for b in BENCHMARKS},
                  "splits": {b: {"train": entries(TRAIN[b]), "val": entries([f"{b}-v0"]), "test": entries(TEST[b]),
                                 "reserve": []} for b in BENCHMARKS}})
    write_json(root.parent / "split.json", split)
    return root


def fake_panels(split, **_):
    return {b: {"tasks": [{"task_id": t, "family_id": f} for t, f in sorted(tool._test_families(split, b).items())]}
            for b in BENCHMARKS}


class Process:
    """A fake worker process: after ``polls`` polls it runs its work and exits (an exception is exit 1)."""

    pid = 0

    def __init__(self, work, polls=0):
        self.work, self.polls, self.code, self.signals = work, polls, None, []

    def poll(self):
        if self.code is None:
            if self.polls > 0:
                self.polls -= 1
                return None
            try:
                self.work()
                self.code = 0
            except Exception:  # noqa: BLE001 - the controller only sees the exit code
                self.code = 1
        return self.code

    def wait(self):
        while self.poll() is None:
            pass
        return self.code

    def kill(self):
        self.signals.append("kill")
        if self.code is None:
            self.code = -9


class Calls(list):
    """The launched worker operations, with the fake workers' shared state."""


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls, state = Calls(), {"generating": 0, "scoring": 0, "peak": 0, "overlap": [], "processes": []}
    calls.state = state

    def launch(request, operation, request_path, output, handle, admit=lambda: True):
        if not admit():
            return None
        key = (operation, request["benchmark"], request["policy"])
        calls.append(key)
        run = tool.safe_path(request["run"])
        kind = {"generate": "generating", "score": "scoring"}.get(operation)
        if kind:
            state[kind] += 1
        if operation == "generate":
            state["peak"] = max(state["peak"], state["generating"])
            if request["benchmark"] in tool.NATIVE_GENERATION and state["scoring"]:
                state["overlap"].append(key)  # a native generation beside native scoring

        def work():
            if operation == "generate":
                assert not run.exists()
                write_json(checkpoint_path(run, request["method"], "h0", request["stage"]),
                           seal({"skill_text": request["chain"][-1] if request["chain"] else ""}))
                result = seal({"benchmark": request["benchmark"], "policy": request["policy"]})
            elif operation == "score":
                assert run.exists()
                tasks = sorted(tool._test_families(read_json(tmp_path / "split.json"), request["benchmark"]))
                rows = [{"task_id": t, "family_id": t, "repeat": 0, "record_hash": "0" * 64,
                         "status": "pass" if i < PASSING[request["policy"]] else "fail"} for i, t in enumerate(tasks)]
                result = seal({"benchmark": request["benchmark"], "policy": request["policy"],
                               "positions": len(rows), "rows": rows, "counts": {},
                               "costs": {"logical_calls": len(rows)}})
            else:
                result = read_json(Path(output).parent.parent.parent / "results" / request["benchmark"]
                                   / f"{request['policy']}.json", sealed=True)
            write_json(output, result)
            if kind:
                state[kind] -= 1
        process = Process(work, polls=2 if operation == "score" else 0)  # scoring outlasts the next start
        state["processes"].append((key, process))
        return process
    monkeypatch.setattr(sequence, "check_frozen_files", lambda protocol: None)
    monkeypatch.setattr(sequence, "_check_budget_source", lambda source, derived, budget: {})
    monkeypatch.setattr(sequence, "verify_service", lambda root, expected=None: SERVICE)
    monkeypatch.setattr(tool, "build_test_panels", fake_panels)
    monkeypatch.setattr(tool, "_launch", launch)
    monkeypatch.setattr(tool, "POLL_SECONDS", 0)
    monkeypatch.setattr("skillopt.continual_learning.launch.learning_environment",
                        lambda manifest: contextlib.nullcontext())
    return tmp_path, write_study(tmp_path / "study"), calls


def prepare(tmp_path, study, out="out"):
    return tool.prepare(study, tmp_path / "split.json", tmp_path / out, tmp_path / "repo")


def paid(calls):
    return [c for c in calls if c[0] != "lock"]


def wrap_work(monkeypatch, after):
    """Run ``after(request, operation)`` when a fake worker's work has completed."""
    fake = tool._launch

    def launch(request, operation, *args):
        process = fake(request, operation, *args)
        if process is None:
            return None
        work = process.work

        def then():
            work()
            after(request, operation)
        process.work = then
        return process
    monkeypatch.setattr(tool, "_launch", launch)


# ------------------------------------------------------------------ controller
def test_policies_are_no_skill_plus_each_accepted_update_and_rows_point_at_them(env):
    tmp_path, study, _ = env
    protocol = read_json(study / "protocol.json", sealed=True)
    found, rows = tool.policies(tool._stages(study, protocol))
    assert sorted(found) == ["gepa-s3", "gepa-s4", "no_skill", "skillopt-s1", "skillopt-s3", "skillopt-s4"]
    assert found["skillopt-s4"]["chain"] == ["A", "A", "B", "C"] and found["gepa-s3"]["chain"] == ["", "", "G"]
    assert rows == {"skillopt-s1": "skillopt-s1", "skillopt-s2": "skillopt-s1", "skillopt-s3": "skillopt-s3",
                    "skillopt-s4": "skillopt-s4", "skillopt-s5": "skillopt-s4", "gepa-s1": "no_skill",
                    "gepa-s2": "no_skill", "gepa-s3": "gepa-s3", "gepa-s4": "gepa-s4", "gepa-s5": "gepa-s4"}
    assert found["skillopt-s3"]["skill_sha256"] == hashlib.sha256(b"B").hexdigest()
    assert found["no_skill"]["skill_sha256"] == hashlib.sha256(b"").hexdigest()
    # No-Skill, then each method's final policy (the headline comparison), then the earlier stages.
    assert tool.policy_order(found, rows, protocol) == ["no_skill", "skillopt-s4", "gepa-s4", "skillopt-s1",
                                                        "skillopt-s3", "gepa-s3"]


def test_each_cell_changes_only_panel_partition_repeats_and_methods_and_binds_identities(env):
    tmp_path, study, calls = env
    plan = prepare(tmp_path, study)
    assert len(plan["cells"]) == 30 and calls == [] and plan["tool_sha256"] == sha(tool.__file__)
    request = read_json(tmp_path / "out/requests/spreadsheetbench/gepa-s4.json", sealed=True)
    config = request["config"]
    assert config["partition"] == "final" and config["repeats"] == 1 and config["methods"] == ["no_skill", "gepa"]
    assert config["panels"]["spreadsheetbench"] == str(tmp_path / "out/panels/spreadsheetbench.json")
    assert all(v is None for b, v in config["panels"].items() if b != "spreadsheetbench")
    assert config["runtime"]["spreadsheetbench"]["recalculation"] == {
        "engine": "x", "qualification_path": "new", "qualification_sha256": "s", "qualification_hash": "h"}
    assert request["evaluation_source"] == "/frozen/derived-spreadsheetbench" and request["chain"] == ["", "", "G", "H"]
    assert request["expected_source_identity"] == IDENTITY["source_identity"]
    assert request["expected_host_runtime"] == IDENTITY["host_runtime"]
    assert request["panel_sha256"] == sha(tmp_path / "out/panels/spreadsheetbench.json")
    assert request["tool_sha256"] == sha(tool.__file__) and request["orchestrator_sha256"] == "o" * 64
    no_skill = read_json(tmp_path / "out/requests/korbench/no_skill.json", sealed=True)
    assert no_skill["config"]["methods"] == ["no_skill"] and no_skill["chain"] == [] and no_skill["stage"] == 0
    panel = read_json(tmp_path / "out/panels/spreadsheetbench.json")
    assert "42930" not in {t["task_id"] for t in panel["tasks"]} and plan["excluded"] == tool.EXCLUDED


def test_outputs_inside_the_study_or_a_reference_are_refused(env):
    tmp_path, study, _ = env
    for out in (study / "test", tmp_path / "ref-korbench" / "test"):
        with pytest.raises(ValueError, match="new directory outside"):
            tool.prepare(study, tmp_path / "split.json", out, tmp_path / "repo")


def test_a_split_verified_against_another_study_or_learning_outside_train_is_refused(tmp_path, monkeypatch, env):
    _, study, _ = env
    write_study(tmp_path / "other/study", usage={"protocol_hash": "another-study"})
    with pytest.raises(ValueError, match="not verified against this study"):
        tool.prepare(tmp_path / "other/study", tmp_path / "other/split.json", tmp_path / "o1", tmp_path / "repo")
    write_study(tmp_path / "leak/study", learning={"korbench": ["korbench-d0", "korbench-t0"]})
    with pytest.raises(ValueError, match="outside train"):
        tool.prepare(tmp_path / "leak/study", tmp_path / "leak/split.json", tmp_path / "o2", tmp_path / "repo")


def test_run_waits_for_the_lock_generates_one_cell_at_a_time_and_replays_without_calls(env, monkeypatch):
    tmp_path, study, calls = env
    plan = prepare(tmp_path, study)
    real = fcntl.flock
    monkeypatch.setattr(tool.fcntl, "flock", lambda fd, op: calls.append(("lock", op)) or real(fd, op))
    summary = tool.run(tmp_path / "out")
    work, state = paid(calls), calls.state
    assert ("lock", fcntl.LOCK_EX) in calls[:calls.index(work[0])]
    assert [(b, n) for op, b, n in work if op == "generate"] == [tuple(c) for c in plan["cells"]]
    assert plan["cells"][:5] == [[b, "no_skill"] for b in tool.GENERATION_ORDER]  # No-Skill rows first
    assert [name for _, name in plan["cells"][::5]] == ["no_skill", "skillopt-s4", "gepa-s4", "skillopt-s1",
                                                        "skillopt-s3", "gepa-s3"]  # then the final policies
    assert len([c for c in work if c[0] == "score"]) == 30 and state["peak"] == 1  # one generation at a time
    assert state["overlap"] == []  # Sheet/ALFWorld generation never started beside native scoring
    cell = summary["cells"]["korbench"]
    assert cell["skillopt-s4"]["counts"] == {"pass": 3, "fail": 0, "unknown": 0}
    assert cell["skillopt-s4"]["vs_no_skill"] == {"tie": 1, "win": 2}
    assert cell["gepa-s3"]["vs_no_skill"] == {"loss": 1, "tie": 2}
    assert summary["cells"]["spreadsheetbench"]["no_skill"]["positions"] == 3  # 42930 excluded
    assert "not_an_exposure_filtered" in summary["data_scope"]
    calls.clear()
    assert tool.run(tmp_path / "out") == summary
    assert {c[0] for c in paid(calls)} == {"verify"}  # replay: no generation or scoring


def test_scoring_overlaps_the_next_api_only_generation(env):
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    tool.run(tmp_path / "out")
    order = [c for c in calls if c[0] in {"generate", "score"}]
    # Sheet is scored while BigCodeBench (API-only) generates: its generation starts before that scoring ends,
    # which the fake makes visible as the launch order score(sheet) -> generate(bcb) with scoring still active.
    sheet, bcb = order.index(("score", "spreadsheetbench", "no_skill")), order.index(("generate", "bigcodebench", "no_skill"))
    assert bcb == sheet + 1


def test_an_interrupted_cell_is_never_resumed(env):
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    (tmp_path / "out/runs/bigcodebench/no_skill").mkdir(parents=True)
    with pytest.raises(ValueError, match="never resumed"):
        tool.run(tmp_path / "out")
    assert paid(calls) == []


def test_after_a_failed_cell_nothing_starts_and_a_running_worker_finishes(env, monkeypatch):
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    fake = tool._launch

    def failing(request, operation, *args):
        process = fake(request, operation, *args)
        if process is None:
            return None
        if operation == "score" and request["benchmark"] == "korbench":
            process.work = lambda: 1 / 0  # this scoring worker crashes
        return process
    monkeypatch.setattr(tool, "_launch", failing)
    with pytest.raises(ValueError, match="worker failed"):
        tool.run(tmp_path / "out")
    generated = [c for c in calls if c[0] == "generate"]
    # The next (API-only) generation was already running beside the failing scoring: it finishes, nothing follows.
    assert generated[-1] == ("generate", "searchqa", "skillopt-s4") and len(generated) == 6
    assert (tmp_path / "out/generated/searchqa/skillopt-s4.json").is_file()
    assert all(process.signals == [] for _, process in calls.state["processes"])  # nobody was killed
    with pytest.raises(ValueError, match="never resumed"):  # generated-but-unscored cells need review
        tool.run(tmp_path / "out")


def test_a_request_changed_during_the_wait_or_a_swapped_policy_is_refused(env, monkeypatch):
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    path = tmp_path / "out/requests/searchqa/skillopt-s3.json"
    original = path.read_text()
    real = fcntl.flock

    def flock(fd, op):
        real(fd, op)
        if op == fcntl.LOCK_EX:
            value = json.loads(original)
            value["chain"] = ["A", "A", "Z"]
            path.write_text(json.dumps(seal({k: v for k, v in value.items() if k != "record_hash"})))
    monkeypatch.setattr(tool.fcntl, "flock", flock)
    with pytest.raises(ValueError, match="request changed"):
        tool.run(tmp_path / "out")
    assert paid(calls) == []
    monkeypatch.setattr(tool.fcntl, "flock", real)
    path.write_text(original)

    def swap(request, operation):
        if operation == "generate":
            target = checkpoint_path(tool.safe_path(request["run"]), request["method"], "h0", request["stage"])
            target.unlink()
            write_json(target, seal({"skill_text": "not the study Skill"}))
    wrap_work(monkeypatch, swap)
    with pytest.raises(ValueError, match="differs from the study policy"):
        tool.run(tmp_path / "out")


def test_everything_is_revalidated_before_every_worker(env, monkeypatch):
    tmp_path, study, calls = env
    prepare(tmp_path, study)

    def tamper(request, operation):
        if operation == "generate":  # the panel changes while the first cell runs
            (tmp_path / "out/panels/korbench.json").write_text(json.dumps({"tasks": [
                {"task_id": "korbench-t0", "family_id": "family-korbench-t0"}]}))
    wrap_work(monkeypatch, tamper)
    with pytest.raises(ValueError, match="test panel changed"):
        tool.run(tmp_path / "out")
    assert len([c for c in calls if c[0] == "generate"]) == 1 and not [c for c in calls if c[0] == "score"]


@pytest.mark.parametrize("tamper,message", [
    ("tool", "changed tool"), ("study_plan", "evaluation plan changed"), ("split", "split changed"),
    ("derived", "Derived evaluation source differs"),
])
def test_a_changed_tool_study_identity_split_or_derived_source_is_refused(env, monkeypatch, tamper, message):
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    if tamper == "tool":
        real = tool._sha
        monkeypatch.setattr(tool, "_sha", lambda path: "changed" if Path(path).name == Path(tool.__file__).name
                            else real(path))
    elif tamper == "study_plan":
        plan = study / "skillopt/s1-bigcodebench/evaluations/korbench/plan.json"
        plan.write_text(json.dumps(seal({"source_identity": {"a.py": "2"}, "host_runtime": {"python": "3"}})))
    elif tamper == "split":
        split = read_json(tmp_path / "split.json", sealed=True)
        (tmp_path / "split.json").write_text(json.dumps(seal({**{k: v for k, v in split.items() if k != "record_hash"},
                                                                "note": "edited"})))
    else:
        def differs(source, derived, budget):
            raise ValueError("Derived evaluation source differs outside the Skill budget")
        monkeypatch.setattr(sequence, "_check_budget_source", differs)
    with pytest.raises(ValueError, match=message):
        tool.run(tmp_path / "out")
    assert paid(calls) == []


# ------------------------------------------------------------------ failures between polls, and stopping
def test_a_worker_that_fails_during_the_next_revalidation_is_collected_before_anything_starts(env, monkeypatch):
    """Workers exit on their own, not when polled: a scoring crash during the next cell's validation."""
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    fake, load, running = tool._launch, tool._load, {}

    def launch(request, operation, *args):
        process = fake(request, operation, *args)
        if process is None:
            return None
        if (operation, request["benchmark"], request["policy"]) == ("score", "spreadsheetbench", "no_skill"):
            process.polls, process.work = 10 ** 6, None  # keeps running until it crashes below
            running["scoring"] = process
        return process

    def slow_load(output):
        value = load(output)
        if "scoring" in running and running["scoring"].code is None:
            running["scoring"].code = 1  # the scoring worker crashes while the next generation is validated
        return value
    monkeypatch.setattr(tool, "_launch", launch)
    monkeypatch.setattr(tool, "_load", slow_load)
    with pytest.raises(ValueError, match="worker failed"):
        tool.run(tmp_path / "out")
    generated = [c for c in calls if c[0] == "generate"]
    assert generated[-1] == ("generate", "spreadsheetbench", "no_skill")  # BigCodeBench was never launched
    assert not (tmp_path / "out/runs/bigcodebench").exists()


def test_a_worker_that_fails_during_launch_preparation_stops_that_launch(env, monkeypatch):
    """The admission point comes after all preparation, immediately before the process is created."""
    tmp_path, study, calls = env
    prepare(tmp_path, study)
    fake, load, read, state = tool._launch, tool._load, tool.read_json, {"validated": False}

    def launch(request, operation, *args):
        process = fake(request, operation, *args)
        if process is not None and (operation, request["benchmark"], request["policy"]) == (
                "score", "spreadsheetbench", "no_skill"):
            process.polls, process.work = 10 ** 9, None  # keeps running until it crashes below
            state["scoring"] = process
        return process

    def validated_load(output):
        value = load(output)
        state["validated"] = "scoring" in state  # the next start's re-verification has just finished
        return value

    def preparing_read(path, **kwargs):
        if state["validated"] and "requests/bigcodebench" in str(path) and state["scoring"].code is None:
            state["scoring"].code = 1  # ... and the scoring worker crashes while that launch is prepared
        return read(path, **kwargs)
    monkeypatch.setattr(tool, "_launch", launch)
    monkeypatch.setattr(tool, "_load", validated_load)
    monkeypatch.setattr(tool, "read_json", preparing_read)
    with pytest.raises(ValueError, match="worker failed"):
        tool.run(tmp_path / "out")
    assert not [c for c in calls if c[:2] == ("generate", "bigcodebench")]  # refused at the admission point
    assert not (tmp_path / "out/runs/bigcodebench").exists()


def test_the_admission_point_is_the_last_step_before_the_process_is_created(tmp_path, monkeypatch):
    import subprocess

    order = []
    monkeypatch.setattr(subprocess, "Popen", lambda command, **kwargs: order.append("spawn") or "process")
    request = {"evaluation_source": str(tmp_path), "python": "/frozen/python"}

    def admit(answer):
        return lambda: order.append("admit") or answer
    assert tool._launch(request, "generate", tmp_path / "r", tmp_path / "o", None, admit(True)) == "process"
    assert tool._launch(request, "generate", tmp_path / "r", tmp_path / "o", None, admit(False)) is None
    assert order == ["admit", "spawn", "admit"]  # refused: nothing was spawned


@pytest.mark.parametrize("error", [KeyboardInterrupt, RuntimeError])
def test_when_the_controller_is_interrupted_or_fails_its_running_workers_are_killed(env, monkeypatch, error):
    from skillopt.continual_eval import core as eval_core

    tmp_path, study, calls = env
    prepare(tmp_path, study)
    events, fake, lock = [], tool._launch, eval_core.output_lock

    def launch(request, operation, *args):
        process = fake(request, operation, *args)
        if process is None:
            return None
        key = (operation, request["benchmark"])
        if key in {("generate", "bigcodebench"), ("score", "spreadsheetbench")}:
            process.polls, process.work = 10 ** 9, None  # both are still running when the controller stops
            kill = process.kill
            process.kill = lambda: (kill(), events.append(("killed", key)))
        return process

    def sleep(seconds):  # an interrupt (or a controller bug) while it waits beside two running workers
        if any(c[:2] == ("generate", "bigcodebench") for c in calls):
            raise error("the controller stops")

    @contextlib.contextmanager
    def recorded_lock(root):
        try:
            with lock(root):
                yield
        finally:
            events.append("locks released")
    monkeypatch.setattr(tool, "_launch", launch)
    monkeypatch.setattr(tool.time, "sleep", sleep)
    monkeypatch.setattr(eval_core, "output_lock", recorded_lock)
    with pytest.raises(error, match="the controller stops"):
        tool.run(tmp_path / "out")
    assert set(events[:-1]) == {("killed", ("generate", "bigcodebench")), ("killed", ("score", "spreadsheetbench"))}
    assert events[-1] == "locks released" and len(events) == 3  # only after both workers were killed and reaped
    assert [c for c in calls if c[0] == "generate"][-1] == ("generate", "bigcodebench", "no_skill")
    assert all(process.code is not None for _, process in calls.state["processes"])  # nothing left running


def test_workers_are_plain_children_started_in_the_evaluation_source(tmp_path, monkeypatch):
    import subprocess

    seen = {}

    def popen(command, **kwargs):
        seen.update(kwargs, command=command)
        return "process"
    monkeypatch.setattr(subprocess, "Popen", popen)
    request = {"evaluation_source": str(tmp_path), "python": "/frozen/python"}
    assert tool._launch(request, "score", tmp_path / "r.json", tmp_path / "o.json", None) == "process"
    assert seen["cwd"] == tmp_path and seen["env"]["PYTHONPATH"] == str(tmp_path)
    assert seen["command"] == ["/frozen/python", str(Path(tool.__file__).resolve()), "worker", "--operation",
                               "score", "--request", str(tmp_path / "r.json"), "--output", str(tmp_path / "o.json")]
    assert "start_new_session" not in seen  # same process group as the controller, like the study's orchestrator


# ------------------------------------------------------------------ test panels
def panel_sources(tmp_path, *, alf_split="valid_unseen"):
    """Small real source files plus the split built from them."""
    sources, panels = {}, {}
    for benchmark, name in (("bigcodebench", "bcb_final"), ("spreadsheetbench", "sheet_final"), ("korbench", "kor_final")):
        panel = fixture_panel(benchmark)
        if benchmark == "spreadsheetbench":
            panel["tasks"].append({**panel["tasks"][0], "task_id": "42930", "family_id": "misnamed-gold"})
        sources[name] = tmp_path / f"{benchmark}-final.json"
        write_json(sources[name], panel)
        panels[benchmark] = panel
    rows = [{"id": f"q{i}", "question": f"What is {i}?", "context": "c", "answers": ["a"]} for i in range(3)]
    sources["searchqa_test"] = tmp_path / "searchqa-test.json"
    write_json(sources["searchqa_test"], rows)
    sources["alfworld_test"] = tmp_path / "alfworld-test.json"
    write_json(sources["alfworld_test"], [{"id": "test:0", "gamefile": "g", "task_type": "t"}])
    alf = {**fixture_panel("alfworld"), "tasks": [{**fixture_panel("alfworld")["tasks"][0], "task_id": "test:0",
           "private": {"game_metadata": {"source_split": alf_split}}}]}
    test = {b: [{"task_id": t["task_id"], "family_id": t["family_id"]} for t in p["tasks"]] for b, p in panels.items()}
    test["searchqa"] = [{"task_id": r["id"], "family_id": datasets._family(r["id"], {"question": r["question"]}, None)}
                        for r in rows[:2]]  # the split samples two of the three native test questions
    test["alfworld"] = [{"task_id": "test:0", "family_id": alf["tasks"][0]["family_id"]}]
    split = seal({"version": tool.SPLIT_VERSION, "splits": {b: {"test": test[b]} for b in BENCHMARKS},
                  "sources": {str(p): sha(p) for p in sources.values()}})
    return split, {**sources, "alfworld_root": tmp_path}, alf


def test_test_panels_come_only_from_the_split_sources_with_its_ids_and_families(tmp_path, monkeypatch):
    split, sources, alf = panel_sources(tmp_path)
    monkeypatch.setattr(datasets, "import_alfworld", lambda *a, **k: alf)
    monkeypatch.setattr(datasets, "readiness", lambda panel: {"status": "ready"})
    panels = tool.build_test_panels(split, **sources)
    assert [t["task_id"] for t in panels["searchqa"]["tasks"]] == ["q0", "q1"]  # only the split's sample
    assert all(t["partition"] == "final" for t in panels["searchqa"]["tasks"])
    assert "42930" not in {t["task_id"] for t in panels["spreadsheetbench"]["tasks"]}
    moved = seal({**{k: v for k, v in split.items() if k != "record_hash"},
                  "splits": {**split["splits"], "korbench": {"test": [
                      {**split["splits"]["korbench"]["test"][0], "family_id": "a-train-rule"}]}}})
    with pytest.raises(ValueError, match="korbench: test panel tasks or families differ"):
        tool.build_test_panels(moved, **sources)
    write_json(tmp_path / "other.json", fixture_panel("bigcodebench"))  # same ids, another file
    with pytest.raises(ValueError, match="not the file the split was built from"):
        tool.build_test_panels(split, **{**sources, "bcb_final": tmp_path / "other.json"})


def test_alfworld_test_games_must_be_valid_unseen(tmp_path, monkeypatch):
    split, sources, alf = panel_sources(tmp_path, alf_split="train")
    monkeypatch.setattr(datasets, "import_alfworld", lambda *a, **k: alf)
    monkeypatch.setattr(datasets, "readiness", lambda panel: {"status": "ready"})
    with pytest.raises(ValueError, match="must come from valid_unseen"):
        tool.build_test_panels(split, **sources)


# ------------------------------------------------------------------ the real worker, zero model calls
@pytest.fixture
def real_worker(tmp_path, monkeypatch):
    panel = tmp_path / "panels/searchqa.json"
    write_json(panel, fixture_panel("searchqa"))
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 4096, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                           "initial_health_policy": "completed_response_v1"}}
    config = {"version": LONG_RESPONSE_VERSION, "order": list(BENCHMARKS),
              "panels": {b: (str(panel) if b == "searchqa" else None) for b in BENCHMARKS}, "partition": "final",
              "methods": ["no_skill", "skillopt"], "histories": ["h0"], "repeats": 1, "model": model,
              "runtime": {}, "project_disjoint": False, "exposure_manifest": None}

    def request(**changes):
        value = {"version": tool.VERSION, "benchmark": "searchqa", "policy": "skillopt-s2", "method": "skillopt",
                 "stage": 2, "chain": ["A", "A"], "provenance": "fivebench_test_eval:stage-hash", "config": config,
                 "run": str(tmp_path / "runs/searchqa/skillopt-s2"), "repo": str(tmp_path / "repo"), "workers": 2,
                 "service": seal(SERVICE), "panel_sha256": sha(panel),
                 "expected_source_identity": core.source_identity(),
                 "expected_host_runtime": core.runtime_identity(),
                 "evaluation_source": str(Path(core.__file__).resolve().parents[2]), "python": sys.executable,
                 "orchestrator": str(Path(sequence.__file__).absolute()), "orchestrator_sha256": sha(sequence.__file__),
                 "tool_sha256": sha(tool.__file__), **changes}
        path = tmp_path / f"request-{len(list(tmp_path.glob('request-*')))}.json"
        write_json(path, seal(value))
        return path

    class Client:
        service = SERVICE

        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass
    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", Client)
    original_generate, original_score = runner.generate, runner.score_checkpoint

    def generate(output, **kwargs):
        write_json(Path(output) / "model_service.json", seal(SERVICE))
        return original_generate(output, **kwargs, fixture_solve=fixture_solve)
    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "score_checkpoint",
                        lambda output, **kwargs: original_score(output, **kwargs, fixture_score=fixture_score))
    return tmp_path, request


def test_real_worker_smokes_generates_scores_and_replays_one_cell(real_worker):
    tmp_path, request = real_worker
    path = request()
    smoke = tool.worker("dryrun", path, tmp_path / "smoke/cell.json")
    assert smoke["positions"] == 1 and smoke["model_calls"] == 0 and not (tmp_path / "runs").exists()
    generated = tool.worker("generate", path, tmp_path / "generated/cell.json")
    assert generated["predictions"] == 1 and generated["plan_hash"] == smoke["plan_hash"]
    run = tmp_path / "runs/searchqa/skillopt-s2"
    plan = read_json(run / "plan.json", sealed=True)
    assert plan["source_identity"] == core.source_identity() and plan["host_runtime"] == core.runtime_identity()
    assert plan["config"]["partition"] == "final" and plan["repeats"] == 1
    assert read_json(checkpoint_path(run, "skillopt", "h0", 2), sealed=True)["skill_text"] == "A"
    with pytest.raises(ValueError, match="Never silently retry"):
        tool.worker("generate", path, tmp_path / "generated/again.json")
    result = tool.worker("score", path, tmp_path / "results/cell.json")
    assert result["positions"] == 1 and result["counts"] == {"pass": 1} and result["policy"] == "skillopt-s2"
    assert tool.worker("verify", path, tmp_path / "verify/cell.json") == result
    with pytest.raises(ValueError, match="generated, unscored cell"):
        tool.worker("score", path, tmp_path / "results/cell.json")


@pytest.mark.parametrize("changes,message", [
    ({"expected_source_identity": {"skillopt/continual_eval/core.py": "0" * 64}}, "differs from the study's own"),
    ({"expected_host_runtime": {"python": "0", "system": "x", "packages": {}}}, "differs from the study's own"),
    ({"panel_sha256": "0" * 64}, "test panel changed"),
    ({"tool_sha256": "0" * 64}, "evaluation tool changed"),
    ({"orchestrator_sha256": "0" * 64}, "orchestrator changed"),
    ({"evaluation_source": "/somewhere/else"}, "wrong evaluation source"),
])
def test_real_worker_refuses_any_identity_mismatch_before_creating_anything(real_worker, changes, message):
    tmp_path, request = real_worker
    for operation in ("dryrun", "generate"):
        with pytest.raises(ValueError, match=message):
            tool.worker(operation, request(**changes), tmp_path / f"out/{operation}.json")
    assert not (tmp_path / "runs").exists() and not (tmp_path / "out").exists()


def test_real_worker_refuses_a_panel_changed_after_generation(real_worker):
    tmp_path, request = real_worker
    path = request()
    tool.worker("generate", path, tmp_path / "generated/cell.json")
    panel = fixture_panel("searchqa")
    panel["tasks"][0]["private"]["answers"] = ["red"]
    (tmp_path / "panels/searchqa.json").write_text(json.dumps(panel))
    with pytest.raises(ValueError, match="test panel changed"):
        tool.worker("score", path, tmp_path / "results/cell.json")
