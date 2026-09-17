"""V12 immutable authored data, oracle and projection tests; zero model calls."""

import json
from collections import Counter
from copy import deepcopy

import pytest

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v3.tasks import _schema_valid
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v12 import tasks
from skillopt.validator_pilot.api import digest


def flatten(panel):
    return [a for part in ("train", "selection") for batch in panel[part] for a in batch] + panel["final"]


@pytest.fixture(scope="module")
def panel():
    return tasks.build_panel()


def test_fixed_formal_counts_and_domain_assignment(panel):
    assert [len(batch) for batch in panel["train"]] == [4, 4, 4]
    assert [len(batch) for batch in panel["selection"]] == [4, 4, 4]
    for batch in panel["train"] + panel["selection"]:
        assert Counter(a.domain for a in batch) == {"coding": 2, "spreadsheet": 2}
    assert Counter(a.domain for a in panel["final"]) == {"coding": 12, "spreadsheet": 12, "rule_reasoning": 12}
    assert len({tasks.payload(a)["id"] for a in flatten(panel)}) == 60


def test_final_families_disjoint_and_parameter_instances_do_not_inflate_clusters(panel):
    development = {tasks.payload(a)["cluster_id"] for batch in panel["train"] + panel["selection"] for a in batch}
    final = Counter(tasks.payload(a)["cluster_id"] for a in panel["final"])
    assert len(development) == 6 and len(final) == 12 and set(final.values()) == {3}
    assert not development.intersection(final)
    for domain in ("coding", "spreadsheet", "rule_reasoning"):
        assert len({tasks.payload(a)["cluster_id"] for a in panel["final"] if a.domain == domain}) == 4


def test_selection_is_development_family_not_unseen_family_certification(panel):
    for training, selected in zip(panel["train"], panel["selection"]):
        assert {tasks.payload(a)["cluster_id"] for a in training} == {tasks.payload(a)["cluster_id"] for a in selected}
        assert all(tasks.payload(a)["split"] == "selection" for a in selected)
        def inputs(adapters, domain):
            result = set()
            for adapter in adapters:
                if adapter.domain != domain:
                    continue
                row = tasks.payload(adapter)
                cases = row["public_cases"] + row["private_cases" if domain == "coding" else "hidden_cases"]
                result.update(digest(case["input" if domain == "coding" else "overrides"]) for case in cases)
            return result
        for domain in ("coding", "spreadsheet"):
            assert not inputs(training, domain).intersection(inputs(selected, domain))


def test_smoke_never_constructs_formal_final_families(monkeypatch):
    coding, sheet = tasks._coding, tasks._sheet
    def development_coding(family, *args):
        assert family not in tasks.CODING_FINAL
        return coding(family, *args)
    def development_sheet(family, *args):
        assert family not in tasks.SHEET_FINAL
        return sheet(family, *args)
    monkeypatch.setattr(tasks, "_coding", development_coding)
    monkeypatch.setattr(tasks, "_sheet", development_sheet)
    monkeypatch.setattr(tasks, "_rule", lambda *args: pytest.fail("Formal Rule final materialized during smoke"))
    panel = tasks.build_panel(smoke=True)
    assert [len(x) for x in panel["train"]] == [2] and [len(x) for x in panel["selection"]] == [2]
    assert len(panel["final"]) == 2
    assert len({tasks.payload(a)["id"] for a in flatten(panel)}) == 6
    for part in ("train", "selection", "final"):
        batch = panel[part][0] if part != "final" else panel[part]
        for adapter in batch:
            row = tasks.payload(adapter)
            assert row["split"] == ("development" if part == "train" else part)
            assert row["metadata"]["smoke_development_only"] is True
            assert row["metadata"]["origin"] == "development_family_smoke_control_not_formal_heldout"


@pytest.mark.parametrize("value", [None, 0, 1, "false", []])
def test_smoke_argument_must_be_boolean(value):
    with pytest.raises(ValueError, match="boolean"):
        tasks.build_panel(value)


def test_deterministic_fresh_construction_and_no_alias_mutation(panel):
    assert tasks.panel_manifest(panel) == tasks.panel_manifest(tasks.build_panel())
    other = tasks.build_panel()
    other["train"][0][0].task.metadata["extra"] = True
    assert "extra" not in panel["train"][0][0].task.metadata
    copied = tasks.payload(panel["train"][0][0])
    copied["reference_files"]["logic.py"] = "changed"
    assert tasks.payload(panel["train"][0][0])["reference_files"]["logic.py"] != "changed"


@pytest.mark.parametrize("index", range(60))
def test_public_projection_has_no_hidden_cases_reference_controls_or_scope_labels(panel, index):
    adapter = flatten(panel)[index]
    public = tasks.public_payload(adapter)
    prohibited = {"reference_files", "reference_artifact", "hidden_cases", "private_cases", "controls", "metadata",
                  "family", "cluster_id", "evaluation_group", "same_mechanism", "near_miss"}
    assert not prohibited.intersection(public)
    assert public["domain"] == adapter.domain
    assert public["contract"]["preserve_obligations"]
    assert public["contract"]["change_scope"] == "partial_update"
    row = tasks.payload(adapter)
    private = row["private_cases" if adapter.domain == "coding" else "hidden_cases"]
    key = "label" if adapter.domain == "coding" else "id"
    assert not {c[key] for c in private}.intersection(c[key] for c in public["public_cases"])
    assert all(c.get("public", True) is True for c in public["public_cases"])


def test_identity_manifest_contains_no_task_or_gold_bodies(panel):
    result = tasks.panel_manifest(panel)
    assert result["synthetic_not_public_benchmark"] is True
    assert result["development_selection_shares_family_not_unseen_family_evidence"] is True
    fields = {"task_id", "domain", "family", "cluster_id", "split", "task_hash", "public_hash"}
    rows = [a for part in ("train", "selection") for batch in result[part] for a in batch] + result["final"]
    assert all(set(row) == fields for row in rows)
    assert all(len(row["task_hash"]) == len(row["public_hash"]) == 64 for row in rows)
    assert "expected" not in json.dumps(result) and "def run" not in json.dumps(result)


def test_coding_inputs_obey_public_schema_and_public_private_do_not_overlap(panel):
    for adapter in flatten(panel):
        if not isinstance(adapter, CodingAdapter):
            continue
        row = tasks.payload(adapter)
        for case in row["public_cases"] + row["private_cases"]:
            assert _schema_valid(case["input"], row["input_domain"])
            assert case["dimension"] == "requested_behavior"
            assert case["exception"] is None
            assert tasks._coding_oracle(row["family"], case["input"]) == case["expected"]


def test_native_reference_and_semantic_preservation_controls_exhaustively(panel):
    result = tasks.self_check(panel, coding=False)
    assert result["checked_tasks"] == 36 and result["model_api_calls"] == 0
    assert result["coding_checked"] is False
    for row in result["records"]:
        assert row["controls"]["reference"]["passed"] is True
        assert row["controls"]["starter"] == {"passed": False, "available": True}
        assert row["controls"]["semantic_mutant"] == {"passed": False, "available": True}
        assert row["controls"]["preservation_mutant"]["passed"] is False


@pytest.mark.parametrize("family", [*tasks.CODING_DEV, *tasks.CODING_FINAL])
def test_each_coding_family_four_controls_in_actual_os_sandbox(family):
    adapter = tasks._coding(family, 0, "development")
    result = tasks.self_check({"train": [[adapter]], "selection": [], "final": []})
    assert result["checked_tasks"] == 1 and result["coding_checked"]
    assert result["records"][0]["controls"]["reference"] == {"passed": True, "available": True}


@pytest.mark.parametrize("family", [*tasks.CODING_DEV, *tasks.CODING_FINAL])
def test_three_prespecified_starter_faults_each_fail_independently(family):
    adapter = tasks._coding(family, 0, "development")
    assert adapter.task.metadata["authored_starter_fault_count"] == 3
    assert len(set(adapter.task.metadata["starter_fault_roles"])) == 3
    reference = adapter.task.reference_files["logic.py"]
    original = tasks._PROGRAMS[family]
    mutations = [(original[2], original[3]), *((a, b) for a, b, _ in tasks._EXTRA_STARTER_FAULTS[family])]
    assert len(mutations) == 3
    for before, after in mutations:
        assert reference.count(before) == 1
        result = executor.evaluate(adapter.task, {"files": {"logic.py": reference.replace(before, after, 1)}})
        assert result["execution_ok"] is True
        assert result["hard"] is False


def test_preflight_fails_closed_for_wrong_reference_without_api():
    adapter = tasks._sheet(tasks.SHEET_DEV[0], 0, "development")
    first = adapter.task["editable_cells"][0]
    adapter.task["reference_artifact"]["formulas"][first] = "=999999"
    with pytest.raises(ValueError, match="preflight failed"):
        tasks.self_check({"train": [[adapter]], "selection": [], "final": []}, coding=False)


def test_preflight_rejects_duplicate_partitions():
    adapter = tasks._sheet(tasks.SHEET_DEV[0], 0, "development")
    with pytest.raises(ValueError, match="Duplicate task ID"):
        tasks.self_check({"train": [[adapter]], "selection": [[adapter]], "final": []}, coding=False)


def test_public_feedback_accepts_new_development_projection_without_private_data():
    from skillopt.coevolution_v5.adapters import _public_feedback
    from skillopt.coevolution_v8 import feedback

    panel = tasks.build_panel(smoke=True)
    for adapter in panel["train"][0]:
        public = tasks.public_payload(adapter)
        artifact = tasks.artifact_controls(adapter)["starter"]
        if isinstance(adapter, CodingAdapter):
            evaluation = executor.evaluate(adapter.task, {"files": {k: artifact[k] for k in adapter.task.editable_paths}},
                                           public_only=True)
            receipt = _public_feedback(adapter.task, evaluation)
        else:
            receipt = adapter.evaluate(artifact, public_only=True)
        report = feedback.execution_feedback(public, receipt, request_hash="a" * 64, artifact=artifact,
                                             task_split="development")
        packet = feedback.skill_feedback([report])
        assert packet["no_final_feedback"] is True
        assert packet["semantic_failures"] == 1


def test_final_and_selection_provenance_cannot_be_relabelled_as_development_feedback(panel):
    from skillopt.coevolution_v8 import feedback

    for adapter in (panel["selection"][0][2], panel["final"][12]):
        public = tasks.public_payload(adapter)
        artifact = tasks.artifact_controls(adapter)["reference"]
        receipt = adapter.evaluate(artifact, public_only=True)
        with pytest.raises(ValueError, match="development"):
            feedback.execution_feedback(public, receipt, request_hash="b" * 64, artifact=artifact,
                                         task_split=adapter.task["split"])


def test_rule_full_truth_tables_and_reference_ids_are_complete(panel):
    for adapter in panel["final"]:
        if adapter.domain != "rule_reasoning":
            continue
        row = tasks.payload(adapter)
        cases = row["public_cases"] + row["hidden_cases"]
        assert len(cases) == len({tuple(c["facts"]) for c in cases}) == 256
        assert len(row["public_cases"]) == 3 and len(row["hidden_cases"]) == 253
        assert len(row["editable_rule_ids"]) == 4
        reference = tasks.artifact_controls(adapter)["reference"]["rules"]
        assert {r["id"] for r in reference} == {r["id"] for r in row["rules"]}
        assert all(len(c["expected"]) <= len(row["answer_facts"]) for c in cases)


def test_development_literal_oracle_sanity_and_input_immutability():
    value = {"base": {"a": 2, "b": 3, "c": -1}, "ops": [{"key": "a", "kind": "add", "value": 4},
             {"key": "b", "kind": "delete", "value": 0}, {"key": "b", "kind": "add", "value": 5}]}
    before = deepcopy(value)
    assert tasks._coding_oracle(tasks.CODING_DEV[0], value) == {
        "settings": [["a", 6], ["b", 5], ["c", -1]], "total": 10, "applied": 3}
    assert value == before
    sheet = {"A1": 10, "A2": 20, "A3": 1, "A4": 5, "A5": 3, "A6": 0.2, "A7": 2}
    assert tasks._sheet_oracle(tasks.SHEET_DEV[0], sheet) == {
        "B1": 10, "B2": 0, "B3": 3, "B4": 0, "C1": 3, "C2": 16}
