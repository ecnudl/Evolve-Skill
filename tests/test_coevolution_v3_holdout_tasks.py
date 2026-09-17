"""Authored fixtures only: immutable expectations and actual isolated execution."""

import ast
import copy
import json
import sys

import pytest

from skillopt.coevolution_v3.executor import RepoTask, evaluate, execute_inputs, validate_files
from skillopt.coevolution_v3.tasks import _schema_valid
from skillopt.coevolution_v3.tasks_holdout import MODES, _extra_valid, build_projects

PROJECTS = build_projects()
SLUGS = [project["slug"] for project in PROJECTS]


def task_for(project, mode):
    specification = project["modes"][mode]
    cases = [{"label": str(index), "input": value, "expected": expected,
              "exception": None, "public": index in project["public_indices"],
              "dimension": "preserved_behavior" if index in project["preserved_indices"] else "requested_behavior"}
             for index, (value, expected) in enumerate(zip(project["inputs"], specification["expected"]))]
    return RepoTask(id=project["slug"] + mode, split="holdout", family=project["slug"],
                    cluster_id=project["slug"], prompt=specification["contract"], files=project["files"],
                    reference_files=specification["reference_files"], editable_paths=project["editable_paths"],
                    input_domain=project["input_domain"], public_cases=[c for c in cases if c["public"]],
                    private_cases=[c for c in cases if not c["public"]], metadata={})


def test_six_original_four_module_projects_and_two_modes():
    assert len(PROJECTS) == len(set(SLUGS)) == 6
    assert len({project["context"] for project in PROJECTS}) == 6
    for project in PROJECTS:
        assert set(project["modes"]) == set(MODES)
        assert len(project["files"]) == 4
        assert 70 <= sum(len(source.splitlines()) for source in project["files"].values()) <= 120
        assert set(project["editable_paths"]) == set(project["files"])
        assert len(project["inputs"]) >= 8
        assert len(project["public_indices"]) == 2
        assert len(project["preserved_indices"]) >= 2
        assert project["modes"][MODES[0]]["expected"] != project["modes"][MODES[1]]["expected"]
        assert "full-policy-replacement" not in "\n".join(project["files"].values())
        for mode in MODES:
            spec = project["modes"][mode]
            assert len(spec["expected"]) == len(project["inputs"])
            changed = {path for path, source in spec["reference_files"].items() if source != project["files"][path]}
            assert {"engine.py", "policy.py"} <= changed
            assert spec["reference_files"] != spec["alternative_files"]
            for key in ["reference_files", "alternative_files", "semantic_mutant_files", "preservation_mutant_files"]:
                files = spec[key]
                assert set(files) == set(project["files"])
                validate_files(task_for(project, mode), files)
                for source in files.values():
                    ast.parse(source)


def test_all_fixed_inputs_obey_public_schema_and_extra_relations():
    for project in PROJECTS:
        for value in project["inputs"]:
            assert _schema_valid(value, project["input_domain"]), (project["slug"], value)
            assert project["input_validator"](value), (project["slug"], value)
        assert project["input_domain"]["additionalProperties"] is False
        invalid = {**project["inputs"][0], "unexpected": True}
        assert not _schema_valid(invalid, project["input_domain"])


def test_extra_domain_relations_are_checked_not_only_fixture_membership():
    slots = copy.deepcopy(PROJECTS[0]["inputs"][0])
    slots["requests"][0]["start"] = slots["requests"][0]["end"]
    assert not _extra_valid(SLUGS[0], slots)
    slots = copy.deepcopy(PROJECTS[0]["inputs"][0])
    slots["requests"][1]["id"] = slots["requests"][0]["id"]
    assert not _extra_valid(SLUGS[0], slots)
    localization = copy.deepcopy(PROJECTS[2]["inputs"][0])
    localization["locale"] = "a-b-c"
    assert not _extra_valid(SLUGS[2], localization)
    indexing = copy.deepcopy(PROJECTS[3]["inputs"][0])
    indexing["index"]["UPPER"] = ["A"]
    assert not _extra_valid(SLUGS[3], indexing)
    packaging = copy.deepcopy(PROJECTS[4]["inputs"][0])
    packaging["paths"].append("a/../private")
    assert not _extra_valid(SLUGS[4], packaging)
    cors = copy.deepcopy(PROJECTS[5]["inputs"][0])
    cors["headers"].append(["X-\N{KELVIN SIGN}", "bad"])
    assert not _extra_valid(SLUGS[5], cors)


@pytest.mark.skipif(sys.platform != "darwin", reason="closed-module executor requires macOS OS sandbox")
@pytest.mark.parametrize("project", PROJECTS, ids=SLUGS)
@pytest.mark.parametrize("mode", MODES)
def test_references_alternatives_and_both_defect_controls(project, mode):
    task = task_for(project, mode)
    specification = project["modes"][mode]
    for kind in ["reference_files", "alternative_files", "semantic_mutant_files", "preservation_mutant_files"]:
        result = evaluate(task, {"files": specification[kind]})
        assert result["execution_ok"] is True, (project["slug"], mode, kind, result)
        assert result["artifact_execution_ok"] is True, (project["slug"], mode, kind, result)
        assert all(row["passed"] for row in result["case_results"] if row["id"].endswith(":input_unchanged"))
        if kind in ("reference_files", "alternative_files"):
            assert result["hard"] is True, (project["slug"], mode, kind, result["private_diagnostics"], result["public_observations"])
        else:
            assert result["hard"] is False, (project["slug"], mode, kind)
        if kind == "preservation_mutant_files":
            dimension = result["dimensions"]["preserved_behavior"]
            assert dimension["passed"] < dimension["total"]
            assert all(row["passed"] for row in result["case_results"] if row["dimension"] == "requested_behavior")
    starter = evaluate(task, {"files": project["files"]})
    assert starter["execution_ok"] is True and starter["artifact_execution_ok"] is True
    assert starter["hard"] is False
    assert starter["dimensions"]["preserved_behavior"]["passed"] == starter["dimensions"]["preserved_behavior"]["total"]
    for path in ("engine.py", "policy.py"):
        partial = {**project["files"], path: specification["reference_files"][path]}
        partial_result = evaluate(task, {"files": partial})
        assert partial_result["execution_ok"] is True
        assert partial_result["hard"] is False, "Shipped repair genuinely spans engine and policy; no hidden MODE-only answer"


@pytest.mark.skipif(sys.platform != "darwin", reason="closed-module executor requires macOS OS sandbox")
@pytest.mark.parametrize("project", PROJECTS, ids=SLUGS)
def test_novel_valid_counterexample_inputs_and_missing_action(project):
    value = copy.deepcopy(project["inputs"][0])
    value.pop("action")
    assert value not in project["inputs"]
    assert _schema_valid(value, project["input_domain"]) and project["input_validator"](value)
    for mode in MODES:
        task = task_for(project, mode)
        observations = execute_inputs(task, task.reference_files, [value])
        assert observations[0]["ok"] is True
        assert observations[0]["exception"] is None
        assert observations[0]["input_unchanged"] is True
        assert observations[0]["value"] == project["modes"][mode]["expected"][0]


def test_projects_are_fresh_values_and_expected_cases_not_reference_execution(monkeypatch):
    def no_execution(*args, **kwargs):
        raise AssertionError("Builder must not execute sources to synthesize expectations")

    monkeypatch.setattr("skillopt.coevolution_v3.executor.execute_inputs", no_execution)
    first = build_projects()
    original = json.dumps(first[0]["modes"][MODES[0]]["expected"], sort_keys=True)
    first[0]["modes"][MODES[0]]["expected"][0]["accepted"].append("changed")
    second = build_projects()
    assert json.dumps(second[0]["modes"][MODES[0]]["expected"], sort_keys=True) == original
