import json
from collections import Counter, defaultdict

import pytest

from skillopt.coevolution_v3 import tasks
from skillopt.coevolution_v3 import tasks_development as development
from skillopt.coevolution_v3.executor import RepoTask, evaluate, execute_inputs

TASKS = tasks.build_tasks()


def test_fixed_project_cluster_splits_and_json_manifest():
    assert len(TASKS) == 24
    assert Counter(bundle["phase"] for bundle in TASKS) == {
        "learn0": 4,
        "gate0": 2,
        "learn1": 4,
        "gate1": 2,
        "holdout": 12,
    }
    clusters = defaultdict(list)
    for bundle in TASKS:
        task = bundle["task"]
        clusters[task.cluster_id].append(bundle)
        assert RepoTask.from_dict(json.loads(json.dumps(task.to_dict()))) == task
        assert 3 <= len(task.files) <= 5
        assert task.metadata["domain"] == "coding"
    assert len(clusters) == 12
    for bundles in clusters.values():
        assert len(bundles) == 2
        assert len({bundle["phase"] for bundle in bundles}) == 1
        assert {bundle["mode"] for bundle in bundles} == set(tasks.MODES)


@pytest.mark.parametrize("bundle", TASKS, ids=lambda bundle: bundle["task"].id)
def test_every_frozen_case_is_in_public_domain_and_has_independent_expectation(bundle):
    task = bundle["task"]
    cases = task.public_cases + task.private_cases
    assert len(cases) >= 8 and len(task.private_cases) >= 5
    assert len({case["label"] for case in cases}) == len(cases)
    assert all(tasks.input_valid(task.id, case["input"]) for case in cases)
    assert {case["dimension"] for case in cases} == {"requested_behavior", "preserved_behavior"}
    assert all(set(case) == {"label", "input", "expected", "exception", "dimension", "public"} for case in cases)


@pytest.mark.parametrize("bundle", TASKS, ids=lambda bundle: bundle["task"].id)
@pytest.mark.parametrize("kind", ["reference", "alternative", "starter", "semantic_mutant", "preservation_mutant"])
def test_all_controls_with_real_isolated_modules(bundle, kind):
    task = bundle["task"]
    fixture = next(control for control in tasks.controlled_fixtures(task) if control["kind"] == kind)
    result = evaluate(task, {"files": fixture["files"]})
    assert result["execution_ok"] is True, result
    assert result["hard"] is (kind in {"reference", "alternative"}), result
    assert len(result["case_results"]) == 2 * (len(task.public_cases) + len(task.private_cases))
    assert len({row["id"] for row in result["case_results"]}) == len(result["case_results"])
    if kind == "preservation_mutant":
        requested = result["dimensions"]["requested_behavior"]
        assert requested["passed"] == requested["total"], result
        assert (
            result["dimensions"]["preserved_behavior"]["passed"] < result["dimensions"]["preserved_behavior"]["total"]
        )


def test_public_export_cannot_leak_controls_reference_or_private_cases():
    for bundle in TASKS:
        task = bundle["task"]
        visible = tasks.public_task(task)
        assert visible == task.public_task()
        assert set(visible) == {
            "id",
            "prompt",
            "files",
            "editable_paths",
            "input_domain",
            "public_cases",
            "entry_module",
            "entry_function",
        }
        assert all(case["public"] is True for case in visible["public_cases"])
        assert not {case["label"] for case in task.private_cases} & {case["label"] for case in visible["public_cases"]}
        visible["files"]["api.py"] = "changed outside"
        assert task.files["api.py"] != "changed outside"


def test_build_and_public_structures_are_defensive_copies():
    first = tasks.build_tasks()
    first[0]["task"].files["api.py"] = "not persisted"
    assert tasks.build_tasks()[0]["task"].files["api.py"] != "not persisted"


def test_new_schema_legal_input_is_not_limited_to_private_fixture_library():
    task = TASKS[0]["task"]
    value = {"action": "apply", "balances": {"a": 17, "b": 11}, "entries": [{"from": "b", "to": "a", "amount": 7}]}
    assert value not in [case["input"] for case in task.public_cases + task.private_cases]
    assert tasks.input_valid(task.id, value)
    row = execute_inputs(task, task.reference_files, [value])[0]
    assert row["value"] == {"result": {"balances": {"a": 24, "b": 4}, "statuses": ["posted"]}, "api_version": 1}


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "apply", "balances": {"a": True, "b": 1}, "entries": []},
        {
            "action": "apply",
            "balances": {"a": 1, "b": 1},
            "entries": (),
        },
        {"action": "apply", "balances": {"a": 1, "b": 1}, "entries": [], "extra": 1},
        {"action": "apply", "balances": {"a": 21, "b": 1}, "entries": []},
    ],
)
def test_domain_rejects_non_json_boolean_integer_aliases_and_outside_contract(bad):
    assert tasks.input_valid(TASKS[0]["task"].id, bad) is False


def test_duplicate_input_keys_and_unknown_task_rejected():
    assert not tasks.input_valid(TASKS[0]["task"].id, '{"action":"apply","action":"legacy"}')
    assert not tasks.input_valid("unknown", {})


def test_independent_oracle_contract_anchors():
    ledger = {
        "balances": {"a": 0, "b": 0},
        "entries": [{"from": "a", "to": "b", "amount": 2}, {"from": "b", "to": "a", "amount": 2}],
    }
    assert development._ledger_oracle(ledger, "local-update")["statuses"] == ["rolled_back", "rolled_back"]
    assert development._ledger_oracle(ledger, "full-policy-replacement")["statuses"] == ["posted", "posted"]
    cfg = {"layers": [{"labels": {"x": 1}, "enabled": True}, {"labels": {"x": None, "y": 0}, "enabled": False}]}
    assert development._config_oracle(cfg, "local-update") == {"labels": {"y": 0}, "enabled": False}
    assert development._config_oracle(cfg, "full-policy-replacement") == cfg["layers"][-1]
    graph = {"graph": {"a": ["b"], "b": ["a"]}, "targets": ["a"], "changed": []}
    assert development._build_oracle(graph, "old") == {"__expected_exception__": "ValueError"}
    assert development._build_oracle(graph, "full-policy-replacement") == ["a"]


def test_development_references_need_real_changes_in_multiple_modules():
    for bundle in TASKS[:12]:
        task = bundle["task"]
        assert sum(task.files[path] != task.reference_files[path] for path in task.files) >= 2
        assert "new_policy" not in task.files["policy.py"]
        assert "new_policy" in task.reference_files["policy.py"]
