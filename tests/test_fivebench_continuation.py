"""Offline contract tests: no solver, external network or generated execution."""
from copy import deepcopy

import pytest

from scripts.continue_fivebench_baselines import policy_key, require_safe_handoff, split_panel, transition
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import write_json


def panel():
    return {"version": "continual-panel-v1", "benchmark": "searchqa", "dataset_revision": "authored",
            "provenance": "fixture", "tasks": [
                {"task_id": f"t{i}", "family_id": f"f{i // 2}", "project_id": "", "partition": "development",
                 "public": {"question": f"Question {i}?", "context": "Authored fixture"},
                 "private": {"answers": [str(i)]}} for i in range(20)]}


def test_outcome_blind_split_keeps_whole_families():
    original = panel()
    selected, train, selection = split_panel(original, 3, 3, 42)
    assert len(selected["tasks"]) == 12
    assert not set(train) & set(selection)
    assert selected == split_panel(original, 3, 3, 42)[0]
    changed = deepcopy(original)
    for task in changed["tasks"]:
        task["private"]["answers"] = ["different label"]
    assert split_panel(changed, 3, 3, 42)[1:] == (train, selection)
    assert len(original["tasks"]) == 20


def test_split_rejects_final_and_project_overlap():
    value = panel()
    value["tasks"][0]["partition"] = "final"
    value["tasks"][1]["partition"] = "final"
    with pytest.raises(ValueError, match="Development"):
        split_panel(value, 3, 3, 42)
    value = panel()
    for task in value["tasks"]:
        task["project_id"] = "common-project"
    with pytest.raises(ValueError, match="Project crosses"):
        split_panel(value, 3, 3, 42)


@pytest.mark.parametrize("counts", [(0, 1), (10, 1), (True, 2)])
def test_bad_family_budget(counts):
    with pytest.raises(ValueError):
        split_panel(panel(), *counts, 42)


def test_completed_empty_parent_is_valid_no_update():
    assert transition("", {"status": "completed", "candidate_skill": ""}) == {
        "skill": "", "action": "completed_no_update", "learning_completed": True}


def test_pending_carries_parent_but_not_completion():
    state = transition("parent", {"status": "pending", "candidate_skill": "parent"})
    assert state == {"skill": "parent", "action": "pending_carry_parent", "learning_completed": False}
    with pytest.raises(ValueError, match="Pending learner"):
        transition("parent", {"status": "pending", "candidate_skill": "unconfirmed"})


def test_update_and_reuse_bind_both_policy_and_eval_identity():
    assert transition("", {"status": "completed", "candidate_skill": "learned"})["action"] == "selected_update"
    assert policy_key({"plan_hash": "old"}, "") != policy_key({"plan_hash": "new"}, "")
    assert policy_key({"plan_hash": "old"}, "") != policy_key({"plan_hash": "old"}, " ")


def test_unknown_terminal_status_not_completion():
    with pytest.raises(ValueError):
        transition("", {"status": "success", "candidate_skill": ""})


def test_native_unknown_not_automatically_safe_to_continue(tmp_path):
    result = {"costs": {"unclosed_calls": 0}}
    write_json(tmp_path / "evaluation_intents/a.json", seal({"id": "a"}))
    with pytest.raises(ValueError, match="Open evaluation"):
        require_safe_handoff(tmp_path, result)
    write_json(tmp_path / "evaluations/a.json", seal({"score": {"reason": "container_cleanup_unconfirmed"}}))
    with pytest.raises(ValueError, match="cleanup unconfirmed"):
        require_safe_handoff(tmp_path, result)


def test_open_model_call_blocks_queue(tmp_path):
    with pytest.raises(ValueError, match="Open model"):
        require_safe_handoff(tmp_path, {"costs": {"unclosed_calls": 1}})
