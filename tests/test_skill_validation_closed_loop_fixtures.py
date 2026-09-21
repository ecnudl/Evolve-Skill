"""Fixture wiring tests, not model experiments or measured safety evidence."""
import hashlib
import json
from collections import Counter
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.closed_loop_fixtures import (
    CANDIDATE_SKILL,
    PARENT_SKILL,
    SCENARIOS,
    audit_labels,
    fixture_solver,
    fixture_tasks,
    scripted_updater,
)
from skillopt.skill_validation.models import SourceFile
from skillopt.skill_validation.partitions import PartitionEntry, PartitionManifest
from skillopt.skill_validation.single_round_feedback import parse_update
from skillopt.skill_validation.views import verifier_view
from skillopt.validator_pilot.api import digest


class FixtureExecutor:
    """TEST-ONLY scripted receipts for exact registered fixture programs.

    No source is executed, evaluated, parsed into a runtime, or sent to another
    process. Expected returns come from the hand-authored public fixture table;
    every fixture operation is order-invariant after its explicit local sort.
    This helper accepts only permutations of the registered example input.
    It is not an oracle for model outputs, nor evidence of actual execution.
    """
    def __init__(self):
        self.identity = {"fixture_executor": "closed-loop-scripted-v1", "real_execution": False}
        self.calls = []
        self.programs = {}
        for row in fixture_tasks():
            case = row["task"].public_cases[0]
            expected = json.loads(case.expected_json)
            example = json.loads(case.arguments_json)["args"][0]
            host = row["host_fixture"]
            for code in {*host["codes"].values(), host["mutating"], host["wrong"]}:
                actual = None if code == host["wrong"] else expected
                value = (example, actual, "    values.sort()\n" in code)
                if code in self.programs:
                    assert self.programs[code] == value, "Ambiguous scripted fixture program"
                self.programs[code] = value

    def run(self, files, module, function, args, kwargs):
        if set(files) != {"solution.py"} or module != "solution" or function != "solve":
            raise ValueError("FixtureExecutor only handles registered fixture callables")
        code = files["solution.py"]
        if code not in self.programs:
            raise ValueError("Unregistered source cannot obtain a scripted pass")
        example, actual, mutating = self.programs[code]
        if kwargs or len(args) != 1 or not isinstance(args[0], list) or sorted(args[0]) != example:
            raise ValueError("FixtureExecutor only handles registered input permutations")
        call = deepcopy({"module": module, "function": function, "args": args, "kwargs": kwargs})
        invocation = {"files": deepcopy(files), **call}
        self.calls.append(invocation)
        after_args = deepcopy(args)
        if mutating:
            after_args[0] = sorted(after_args[0])
        return seal({"status": "observed", "actual": deepcopy(actual), "exception": None,
                     "before_args": deepcopy(args), "after_args": after_args,
                     "before_kwargs": deepcopy(kwargs), "after_kwargs": deepcopy(kwargs),
                     "input_hash": digest(invocation), "source_hash": digest(files), "call_hash": digest(call),
                     "executor_identity": self.identity, "duration_seconds": 0.0,
                     "cleanup_confirmed": True, "fixture_only": True})


def _artifact(row, condition, scenario="beneficial"):
    skill = {"no_skill": "", "current": PARENT_SKILL, "candidate": CANDIDATE_SKILL}[condition]
    return fixture_solver(row, condition=condition, skill_text=skill, scenario=scenario)


def test_partitions_have_disjoint_declared_operations_and_fixture_provenance():
    rows = fixture_tasks()
    assert Counter(row["task"].contract.partition for row in rows) == {
        "development": 1, "verifier_calibration": 4, "skill_confirmation": 6, "final": 3}
    manifest = PartitionManifest(project_disjoint=True)
    for row in rows:
        contract = row["task"].contract
        for condition in ("no_skill", "current", "candidate"):
            artifact = _artifact(row, condition)
            entry = PartitionEntry(
                artifact.content_hash, contract.original_task_id, contract.family_id, contract.project_id,
                contract.partition, artifact.provenance_kind, artifact.provenance_complete)
            manifest.register(entry)
            assert not entry.formal_eligible
    assert len(manifest.entries) == 42
    assert PartitionManifest.from_dict(manifest.to_dict()).to_dict() == manifest.to_dict()


def test_confirmation_and_final_each_cover_three_regions_without_hidden_metadata_in_views():
    rows = fixture_tasks()
    for partition, count in (("skill_confirmation", 2), ("final", 1)):
        selected = [row for row in rows if row["task"].contract.partition == partition]
        assert Counter(row["region"] for row in selected) == {
            "target": count, "retention": count, "nonapplicable": count}
        for row in selected:
            view = json.dumps(verifier_view(row["task"].contract, _artifact(row, "candidate"), ()))
            assert "host_fixture" not in view
            assert "labels_are_scripted" not in view
            assert "fixture-operation" not in view
            assert "candidate" not in view


def test_public_examples_are_sorted_and_legal_reversal_is_explicit():
    for row in fixture_tasks():
        task = row["task"]
        assert "Input values may be in any order." in task.contract.prompt
        assert len(task.public_cases) == 1
        values = json.loads(task.public_cases[0].arguments_json)["args"][0]
        assert values == sorted(values)
        assert values != list(reversed(values))
        assert task.public_cases[0].expected_json != "null"


def test_near_miss_permits_but_does_not_require_mutation():
    for row in fixture_tasks():
        if row["near_miss"]:
            task = row["task"]
            assert "Input mutation is permitted but is not required." in task.contract.prompt
            assert [(ob.id, ob.kind) for ob in task.contract.obligations] == [("return", "requested_behavior")]
            assert "required_in_place" not in task.contract.prompt
            assert "input" not in audit_labels(row, _artifact(row, "current"))


def test_development_fixture_contains_known_skill_regression_but_sorted_example_cannot_reveal_it():
    row = fixture_tasks()[0]
    assert audit_labels(row, _artifact(row, "no_skill")) == {"return": "pass", "input": "pass"}
    current = _artifact(row, "current")
    assert audit_labels(row, current) == {"return": "pass", "input": "fail"}
    assert "values.sort()" in current.files[0].content
    assert json.loads(row["task"].public_cases[0].arguments_json)["args"][0] == [-3, -1, 2, 4]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scripted_artifact_and_audit_labels_are_deterministic_and_bound(scenario):
    for row in fixture_tasks():
        for condition in ("no_skill", "current", "candidate"):
            artifact = _artifact(row, condition, scenario)
            assert artifact == _artifact(row, condition, scenario)
            labels = audit_labels(row, artifact)
            assert set(labels) == {ob.id for ob in row["task"].contract.obligations}
            assert artifact.provenance_kind == "fixture"
            if condition == "no_skill":
                assert artifact.skill_hash == hashlib.sha256(b"").hexdigest()
                assert artifact.skill_version == "none"
            else:
                assert artifact.skill_version == "skill-" + artifact.skill_hash[:16]


def test_beneficial_candidate_has_target_gain_retention_and_forced_use_near_miss_harm():
    for row in fixture_tasks():
        if row["task"].contract.partition != "skill_confirmation":
            continue
        base, candidate = (audit_labels(row, _artifact(row, condition)) for condition in ("no_skill", "candidate"))
        if row["region"] == "target":
            assert base["return"] == "fail" and set(candidate.values()) == {"pass"}
        elif row["region"] == "retention":
            assert base == candidate and set(candidate.values()) == {"pass"}
        else:
            assert base == {"return": "pass"} and candidate == {"return": "fail"}


def test_harmful_and_insufficient_scenarios_do_not_change_development():
    rows = fixture_tasks()
    for row in rows:
        if row["task"].contract.partition not in {"skill_confirmation", "final"}:
            assert audit_labels(row, _artifact(row, "candidate", "harmful")) == audit_labels(row, _artifact(row, "candidate"))
            assert audit_labels(row, _artifact(row, "candidate", "insufficient")) == audit_labels(row, _artifact(row, "candidate"))
            continue
        assert set(audit_labels(row, _artifact(row, "candidate", "insufficient")).values()) == {"unknown"}
        if row["region"] != "nonapplicable":
            assert "fail" in audit_labels(row, _artifact(row, "candidate", "harmful")).values()


def test_audit_rejects_nonfixture_changed_task_changed_code_and_source():
    row = fixture_tasks()[0]
    artifact = _artifact(row, "current")
    for changed in (
        replace(artifact, provenance_kind="model"),
        replace(artifact, task_hash="f" * 64),
        replace(artifact, files=(SourceFile("solution.py", "def solve(values): return 123\n"),)),
        replace(artifact, source_hash="f" * 64),
        replace(artifact, source_ref="synthetic:closed-loop:unregistered:hash"),
    ):
        with pytest.raises(ValueError):
            audit_labels(row, changed)


def _feedback():
    def role(status, after):
        return {"checks": [{"method": "input_state", "status": status, "observations": [{
            "information_origin": "recorded_public_execution", "status": "observed",
            "before_args": [[4, 2, -1, -3]], "after_args": [after],
            "before_kwargs": {}, "after_kwargs": {},
        }]}]}
    return {"feedback": {"paired_development": [{"roles": {
        "no_skill": role("pass", [4, 2, -1, -3]),
        "current": role("fail", [-3, -1, 2, 4]),
    }}]}}


def test_updater_returns_conditional_patch_only_for_paired_executed_failure():
    response = scripted_updater("fixture", json.dumps(_feedback()))
    assert response == CANDIDATE_SKILL
    assert parse_update(response, PARENT_SKILL)["status"] == "candidate"
    assert "every list-processing task" not in response
    assert "explicitly requires input preservation" in response


@pytest.mark.parametrize("change", ["no_observation", "unknown", "no_difference", "wrong_method", "wrong_origin", "no_base_pass"])
def test_updater_does_not_turn_status_claim_or_missing_evidence_into_update(change):
    payload = deepcopy(_feedback())
    roles = payload["feedback"]["paired_development"][0]["roles"]
    check = roles["current"]["checks"][0]
    if change == "no_observation":
        check["observations"] = []
    elif change == "unknown":
        check["observations"][0]["status"] = "unsupported"
    elif change == "no_difference":
        check["observations"][0]["after_args"] = check["observations"][0]["before_args"]
    elif change == "wrong_method":
        check["method"] = "public_examples"
    elif change == "wrong_origin":
        check["observations"][0]["information_origin"] = "host_audit"
    else:
        roles["no_skill"]["checks"][0]["status"] = "unknown"
    assert scripted_updater("fixture", json.dumps(payload)) == "NO_UPDATE"


def test_updater_returns_no_update_for_no_pairs():
    assert scripted_updater("fixture", "{}") == "NO_UPDATE"


def test_solver_refuses_nonempty_no_skill_and_unknown_scenario():
    with pytest.raises(ValueError, match="No-Skill"):
        fixture_solver(fixture_tasks()[0], condition="no_skill", skill_text=PARENT_SKILL)
    with pytest.raises(ValueError, match="Unknown fixture"):
        fixture_solver(fixture_tasks()[0], condition="current", skill_text=PARENT_SKILL, scenario="posthoc")


def test_skill_version_is_bound_to_text_not_run_condition():
    row = fixture_tasks()[0]
    current = fixture_solver(row, condition="current", skill_text=PARENT_SKILL)
    candidate = fixture_solver(row, condition="candidate", skill_text=PARENT_SKILL)
    assert current.skill_version == candidate.skill_version
    assert current.skill_version != _artifact(row, "candidate").skill_version


def test_fixture_executor_reports_scripted_state_without_executing_code():
    row = fixture_tasks()[0]
    executor = FixtureExecutor()
    artifact = _artifact(row, "current")
    files = {file.path: file.content for file in artifact.files}
    original = [[4, 2, -1, -3]]
    result = executor.run(files, "solution", "solve", original, {})
    assert result["before_args"] == original == [[4, 2, -1, -3]]
    assert result["after_args"] == [[-3, -1, 2, 4]]
    assert result["actual"] == [-3, -1, 2, 4]
    assert result["fixture_only"] and result["executor_identity"]["real_execution"] is False
    assert result["input_hash"] == digest({"files": files, "module": "solution", "function": "solve", "args": original, "kwargs": {}})
    assert len(executor.calls) == 1


def test_fixture_executor_rejects_unregistered_source_or_new_inputs():
    executor = FixtureExecutor()
    row = fixture_tasks()[0]
    artifact = _artifact(row, "no_skill")
    files = {file.path: file.content for file in artifact.files}
    with pytest.raises(ValueError, match="Unregistered source"):
        executor.run({"solution.py": "def solve(values): return [1]"}, "solution", "solve", [[-3, -1, 2, 4]], {})
    with pytest.raises(ValueError, match="input permutations"):
        executor.run(files, "solution", "solve", [[1, 2, 3, 4]], {})
    with pytest.raises(ValueError, match="registered fixture callables"):
        executor.run(files, "other", "solve", [[-3, -1, 2, 4]], {})
