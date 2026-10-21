"""Controls for the cross-benchmark selection experiment (engineering fixtures, no method-effect claim): the frozen
SkillOpt v9 loop with training rows from one benchmark and the validation gate on another."""
import json

import pytest

from scripts import run_cross_bench_selection as cross
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from tests.test_continual_learning_domains import evaluate
from tests.test_continual_learning_generalization_v8 import API, LABEL, auth9


def _side(benchmark, selection=6):
    value, panel = auth9(benchmark=benchmark, selection=selection, iterations=3)
    train = [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in value["train_families"]]
    held = [{"role": "selection", "task": t} for t in panel["tasks"] if t["family_id"] not in value["train_families"]]
    return value, panel, train, held


def test_candidates_learned_on_one_benchmark_are_gated_on_the_other(tmp_path):
    a_value, a_panel, a_train, a_selection = _side("searchqa")
    b_value, b_panel, b_train, b_selection = _side("korbench")
    api_a, api_b = API(), API()
    result = cross.learn(tmp_path, {}, (a_value, a_panel, a_train, a_selection), (b_value, b_panel, b_train, b_selection),
                         [{"name": "other", "skill": "Unrelated guidance."}], apis=(api_a, api_b),
                         fixture_evaluate=(evaluate("searchqa"), evaluate("korbench")))
    # step 0: learned from the SearchQA training rows, accepted because it wins on the KOR validation rows
    assert result["gate_actions"][0] == "accept_confirmed" and result["accepted_steps"] == [0]
    assert "requested constant" in result["final_skill"] and len(result["gate_actions"]) == 3
    step = read_json(tmp_path / "steps/0.json", sealed=True)
    assert step["selection_tasks"] == 6 and step["train_tasks"] == 2 and step["wins"] == 6 and step["losses"] == 0
    assert result["selection_rows_parent_first_pass"]["pass"] == 0 and result["selection_rows_final_first_pass"]["pass"] == 6
    # every proposal call is on the TRAIN benchmark's ledger; the selection benchmark only solves
    assert api_a.reflection_calls > 0 and api_b.reflection_calls == 0
    assert any(LABEL in p for p in api_a.reflection_prompts)  # SkillOpt's labelled feedback of failed train rows
    rows = {name: [read_json(p, sealed=True) for p in (tmp_path / name / "evaluations").glob("*.json")]
            for name in ("train", "selection")}
    a_train_hashes = {cross.digest(i["task"]) for i in a_train}
    b_train_hashes = {cross.digest(i["task"]) for i in b_train}
    # the train benchmark's validation rows and the selection benchmark's training rows are solved ONLY as held-out
    # evaluation (rollout 900), never by learning or selection
    assert {r["request"]["rollout"] for r in rows["train"] if r["request"]["task_hash"] not in a_train_hashes} == {900}
    assert {r["request"]["rollout"] for r in rows["selection"] if r["request"]["task_hash"] in b_train_hashes} == {900}
    assert all(r["request"]["rollout"] in (0, 1, 2) for r in rows["train"] if r["request"]["task_hash"] in a_train_hashes)
    held = result["heldout"]
    assert held["empty"]["train_benchmark_validation_rows"] == {"pass": 0, "fail": 6, "unknown": 0}
    assert held["final"]["train_benchmark_validation_rows"]["pass"] == 6
    assert held["final"]["selection_benchmark_training_rows"] == {"pass": 2, "fail": 0, "unknown": 0}
    assert held["other"]["train_benchmark_validation_rows"]["pass"] == 0
    assert result["heldout_paired_vs_empty"]["final-empty"]["train_benchmark_validation_rows"]["wins"] == 6
    assert read_json(tmp_path / "candidates/0.json", sealed=True)["skill"] == result["final_skill"]


def test_a_candidate_that_does_not_help_the_other_benchmark_is_rejected_and_nothing_is_deployed(tmp_path):
    a_value, a_panel, a_train, a_selection = _side("searchqa")
    b_value, b_panel, b_train, b_selection = _side("korbench")
    never = lambda task, skill: ({"status": "available", "output": "zero", "reason": "fixture"},  # noqa: E731
                                 {"status": "fail", "score": 0.0, "reason": "fixture", "metrics": {}})
    result = cross.learn(tmp_path, {}, (a_value, a_panel, a_train, a_selection), (b_value, b_panel, b_train, b_selection), [],
                         apis=(API(), API()), fixture_evaluate=(evaluate("searchqa"), never))
    assert result["accepted_steps"] == [] and result["final_skill"] == ""
    assert set(result["gate_actions"]) == {"reject_screen"}
    assert result["heldout"]["final"] == result["heldout"]["empty"] and result["heldout_paired_vs_empty"] == {}


def test_prepare_and_run_bind_two_unbegun_stages_of_different_benchmarks(tmp_path, monkeypatch):
    sides = {"A": _side("searchqa"), "B": _side("korbench")}

    def stage(directory):
        key = str(directory)[-1]
        value, panel, train, held = sides[key]
        record = seal({"benchmark": value["benchmark"], "study": "s", "protocol_hash": "p", "split_hash": "h",
                       "recovery_policy": value["recovery_policy"], "budget": value["budget"],
                       "learning_model_service": {"fixture": True}, "native_lock": str(tmp_path / "lock"),
                       "repo": str(tmp_path), "seed": value["seed"], "client_options": {}})
        return tmp_path / ("stage" + key), record, value, panel, train, held

    monkeypatch.setattr(cross, "_stage", stage)
    monkeypatch.setattr(cross.tool, "_study", lambda study: (tmp_path, {"record_hash": "p"}))
    record = cross.prepare("stageA", "stageB", str(tmp_path / "x"))
    assert (record["train"]["benchmark"], record["selection"]["benchmark"]) == ("searchqa", "korbench")
    assert record["train"]["heldout_validation_tasks"] == 6 and record["selection"]["heldout_train_tasks"] == 2
    with pytest.raises(ValueError, match="DIFFERENT benchmarks"):
        cross.prepare("stageA", "stageA", str(tmp_path / "y"))
    with pytest.raises(ValueError, match="Invalid fixture callbacks"):
        cross.run(str(tmp_path / "x"))
    result = cross.run(str(tmp_path / "x"), fixture_apis=(API(), API()),
                       fixture_evaluate=(evaluate("searchqa"), evaluate("korbench")))
    assert result["status"] == "completed" and result["accepted_steps"] == [0] and result["cross_hash"] == record["record_hash"]
    assert cross.run(str(tmp_path / "x"), fixture_apis=(API(), API()),
                     fixture_evaluate=(evaluate("searchqa"), evaluate("korbench"))) == result
    assert result["usage_blocks_completion"] == {"train": False, "selection": False}
    # incomplete usage accounting on either ledger blocks completion, as in a stage
    cross.prepare("stageA", "stageB", str(tmp_path / "u"))
    real = cross.learn
    monkeypatch.setattr(cross, "learn", lambda *args, **kwargs: {
        **real(*args, **kwargs), "usage_blocks_completion": {"train": False, "selection": True}})
    gap = cross.run(str(tmp_path / "u"), fixture_apis=(API(), API()),
                    fixture_evaluate=(evaluate("searchqa"), evaluate("korbench")))
    monkeypatch.setattr(cross, "learn", real)
    assert gap["status"] == "pending" and gap["reason"] == "usage_or_receipt_accounting_incomplete"
    assert gap["accepted_steps"] == [0] and gap["costs"]["train"]["reflection_calls"] > 0  # the fields are kept
    # a manifest that no longer validates never starts
    value = sides["A"][0]
    sides["A"] = ({**value, "seed": value["seed"] + 1},) + sides["A"][1:]
    cross.prepare("stageA", "stageB", str(tmp_path / "v"))
    with pytest.raises(ValueError):
        cross.run(str(tmp_path / "v"), fixture_apis=(API(), API()),
                  fixture_evaluate=(evaluate("searchqa"), evaluate("korbench")))
    assert not (tmp_path / "v/started.json").exists()
    sides["A"] = (value,) + sides["A"][1:]
    # a failure is a durable pending result; a started directory is never resumed
    cross.prepare("stageA", "stageB", str(tmp_path / "z"))

    def broken(task, skill):
        raise RuntimeError("provider text")

    failed = cross.run(str(tmp_path / "z"), fixture_apis=(API(), API()), fixture_evaluate=(broken, broken))
    assert failed["status"] == "pending" and failed["reason"] == "error:RuntimeError"
    assert "provider text" not in json.dumps(failed)
    cross.prepare("stageA", "stageB", str(tmp_path / "w"))
    write_json(tmp_path / "w/started.json", seal({"cross_hash": "x"}))
    assert cross.run(str(tmp_path / "w"), fixture_apis=(API(), API()),
                     fixture_evaluate=(evaluate("searchqa"), evaluate("korbench")))["reason"] == "interrupted_run_no_automatic_resume"
