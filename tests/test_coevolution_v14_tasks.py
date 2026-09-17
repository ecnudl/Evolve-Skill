"""Fixed V14 data and genuine offline controls; no model API or old task data."""

import ast
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v3.tasks import _schema_valid
from skillopt.coevolution_v14 import tasks
from skillopt.validator_pilot.api import digest


def flatten(panel):
    return [a for batch in panel["train"] for a in batch]+panel["final"]


@pytest.fixture(scope="module")
def panel():
    return tasks.build_panel()


def test_formal_structure_counts_and_unique_disjoint_families(panel):
    assert [len(batch) for batch in panel["train"]] == [4,4]
    assert all(Counter(a.domain for a in batch) == {"coding":2,"spreadsheet":2} for batch in panel["train"])
    assert Counter(a.domain for a in panel["final"]) == {"coding":8,"spreadsheet":8,"rule_reasoning":8}
    train = [tasks.payload(a) for batch in panel["train"] for a in batch]
    final = [tasks.payload(a) for a in panel["final"]]
    assert len({r["id"] for r in train+final}) == 32
    assert len({r["cluster_id"] for r in train}) == 8
    assert len({r["cluster_id"] for r in final}) == 24
    assert not {r["cluster_id"] for r in train}&{r["cluster_id"] for r in final}
    assert all(r["metadata"]["independence_is_design_assumption_not_population_guarantee"] for r in train+final)


def test_tasks_do_not_import_any_prior_task_or_evolution_packages():
    tree = ast.parse(Path(tasks.__file__).read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    assert not any(name and ("coevolution_v12" in name or name.endswith(".tasks")) for name in imports)
    assert tasks.panel_manifest(tasks.build_panel())["host_authored_obligations_and_probes_not_deepresearch_generated"]


def test_repeat_builds_are_immutable_copies(panel):
    assert tasks.panel_manifest(panel) == tasks.panel_manifest(tasks.build_panel())
    copied = tasks.payload(panel["train"][0][0])
    copied["reference_files"]["logic.py"] = "changed"
    assert copied["reference_files"] != panel["train"][0][0].task.reference_files
    challenge = tasks.probe_adapter(panel["train"][0][0])
    challenge.task.files["logic.py"] = "changed"
    assert panel["train"][0][0].task.files["logic.py"] != "changed"


@pytest.mark.parametrize("index",range(32))
def test_public_projections_have_no_reference_probe_pool_or_hidden_gold(panel,index):
    adapter = flatten(panel)[index]
    public = tasks.public_payload(adapter)
    banned = {"reference_files","reference_artifact","private_cases","hidden_cases","metadata","counterexample_probe_pool",
              "mutant","source_task_hash","family","cluster_id","evaluation_group","near_miss"}
    assert not banned&set(public)
    assert public["domain"] == adapter.domain
    assert "obligations" in public if index < 8 else "obligations" not in public
    task = tasks.payload(adapter)
    hidden = task["private_cases" if adapter.domain == "coding" else "hidden_cases"]
    field = "label" if adapter.domain == "coding" else "id"
    assert len(public["public_cases"]) == 2 and len(hidden) >= 6
    assert not {c[field] for c in public["public_cases"]}&{c[field] for c in hidden}
    assert all(identifier not in json.dumps(public) for identifier in (c[field] for c in hidden))


@pytest.mark.parametrize("index",range(8))
def test_dedicated_development_probe_binding_and_input_isolation(panel,index):
    adapter = [a for batch in panel["train"] for a in batch][index]
    source = tasks.payload(adapter)
    obligations = tasks.constraints_for(adapter)
    assert [o["kind"] for o in obligations] == ["unit","boundary","order","dependency"]
    assert all(set(o) == {"id","kind","statement","scope"} for o in obligations)
    challenge = tasks.probe_adapter(adapter)
    row = tasks.payload(challenge)
    assert row["id"] != source["id"] and row["split"] == "development"
    assert row["metadata"]["source_task_id"] == source["id"]
    assert row["metadata"]["source_task_hash"] == digest(source)
    assert row["metadata"]["counterexample_probe_pool"] == []
    assert len(row["public_cases"]) == 4
    private = "private_cases" if adapter.domain == "coding" else "hidden_cases"
    field = "input" if adapter.domain == "coding" else "overrides"
    assert not row[private]
    assert not {digest(c[field]) for c in row["public_cases"]}&{digest(c[field]) for c in source["public_cases"]+source[private]}
    assert len(row["metadata"]["case_obligations"]) == 4
    assert {c["obligation_id"] for c in row["public_cases"]} == {o["id"] for o in obligations}
    with pytest.raises(ValueError,match="recursively"):
        tasks.probe_adapter(challenge)


@pytest.mark.parametrize("index",range(24))
def test_final_cannot_reach_constraint_or_probe_interfaces(panel,index):
    for function in (tasks.constraints_for,tasks.probe_adapter):
        with pytest.raises(ValueError,match="development"):
            function(panel["final"][index])


def test_smoke_never_constructs_formal_final_structures(monkeypatch):
    code,sheet = tasks._coding,tasks._sheet
    def coding(family,*args,**kwargs):
        assert family in tasks.CODING_DEV
        return code(family,*args,**kwargs)
    def spreadsheet(family,*args,**kwargs):
        assert family in tasks.SHEET_DEV
        return sheet(family,*args,**kwargs)
    monkeypatch.setattr(tasks,"_coding",coding)
    monkeypatch.setattr(tasks,"_sheet",spreadsheet)
    monkeypatch.setattr(tasks,"_rule",lambda *args:pytest.fail("Formal Rule materialized in smoke"))
    panel = tasks.build_panel(smoke=True)
    assert [len(b) for b in panel["train"]] == [2] and len(panel["final"]) == 2
    assert len({tasks.payload(a)["id"] for a in flatten(panel)}) == 4
    assert all(tasks.payload(a)["metadata"]["smoke_development_only"] for a in flatten(panel))
    assert all(tasks.payload(a)["split"] == "final" for a in panel["final"])


@pytest.mark.parametrize("value",[None,0,1,[],"false"])
def test_smoke_flag_is_not_truthiness(value):
    with pytest.raises(ValueError,match="boolean"):
        tasks.build_panel(value)


def test_inputs_match_declared_domains_and_independent_oracles(panel):
    for adapter in flatten(panel):
        if adapter.domain != "coding":
            continue
        row = tasks.payload(adapter)
        cases = row["public_cases"]+row["private_cases"]
        for case in cases:
            assert _schema_valid(case["input"],row["input_domain"])
            assert tasks._code_oracle(row["family"],case["input"]) == case["expected"]
        for probe in row["metadata"]["counterexample_probe_pool"]:
            assert _schema_valid(probe["input"],row["input_domain"])
            assert tasks._code_oracle(row["family"],probe["input"]) == probe["expected"]


def test_all_native_reference_starter_and_preservation_controls(panel):
    result = tasks.self_check(panel,coding=False)
    assert result["checked_tasks"] == 20 and result["checked_probe_tasks"] == 4
    assert result["checked_obligation_mutants"] == 16 and result["model_api_calls"] == 0
    assert all(row["controls"]["reference"] == {"passed":True,"available":True} for row in result["records"])
    assert all(not row["controls"]["preservation_mutant"]["passed"] for row in result["records"])


@pytest.mark.parametrize("family",[*tasks.CODING_DEV,*tasks.CODING_FINAL])
def test_each_coding_reference_and_fault_controls_in_os_sandbox(family):
    adapter = tasks._coding(family,"development" if family in tasks.CODING_DEV else "final")
    result = tasks.self_check({"train":[[adapter]] if family in tasks.CODING_DEV else [],
                               "final":[] if family in tasks.CODING_DEV else [adapter]})
    assert result["checked_tasks"] == 1 and result["coding_checked"]
    assert result["checked_obligation_mutants"] == (4 if family in tasks.CODING_DEV else 0)
    assert result["records"][0]["controls"]["starter"] == {"passed":False,"available":True}


def test_near_miss_changes_are_explicit_public_semantics_not_hidden_labels(panel):
    replacements = [a for a in panel["final"] if tasks.public_payload(a)["contract"]["change_scope"] == "full_replacement"]
    assert {a.domain for a in replacements} == {"coding","spreadsheet","rule_reasoning"}
    assert all("NEW POLICY" in tasks.public_payload(a)["prompt"] for a in replacements)
    sheet = next(a for a in replacements if a.domain == "spreadsheet")
    assert any(c["expected"]["B2"] < 0 for c in sheet.task["public_cases"]+sheet.task["hidden_cases"])
    assert all(tasks.public_payload(a)["contract"]["supersedes_old_policy"] for a in replacements)


def test_rule_full_truth_tables_are_cases_not_extra_task_clusters(panel):
    rule_tasks = [a for a in panel["final"] if a.domain == "rule_reasoning"]
    assert len({a.task["cluster_id"] for a in rule_tasks}) == 8
    for adapter in rule_tasks:
        cases = adapter.task["public_cases"]+adapter.task["hidden_cases"]
        assert len(cases) == len({tuple(c["facts"]) for c in cases}) == 64
        assert len(adapter.task["public_cases"]) == 2
        assert all(c["expected"] == tasks._rule_oracle(adapter.task["family"],c["facts"]) for c in cases)


def test_manifest_has_only_identities_and_hashes(panel):
    manifest = tasks.panel_manifest(panel)
    entries = [r for batch in manifest["train"] for r in batch]+manifest["final"]
    assert all(set(r) == {"task_id","domain","family","cluster_id","split","task_hash","public_hash"} for r in entries)
    assert "expected" not in json.dumps(manifest) and "def run" not in json.dumps(manifest)


def test_reference_or_probe_corruption_fails_closed():
    adapter = tasks._sheet(tasks.SHEET_DEV[0])
    adapter.task["metadata"]["counterexample_probe_pool"][0]["mutant"] = deepcopy(adapter.task["reference_artifact"])
    with pytest.raises(ValueError,match="escaped"):
        tasks.self_check({"train":[[adapter]],"final":[]},coding=False)


def test_duplicate_partition_and_relabelled_final_rejected():
    adapter = tasks._sheet(tasks.SHEET_DEV[0])
    with pytest.raises(ValueError,match="Duplicate"):
        tasks.self_check({"train":[[adapter]],"final":[adapter]},coding=False)
    adapter.task["metadata"]["partition"] = "final"
    with pytest.raises(ValueError,match="development"):
        tasks.constraints_for(adapter)


def test_coding_reference_does_not_run_on_host(monkeypatch):
    seen = []
    original = executor.evaluate
    def sandbox(task,*args,**kwargs):
        seen.append(task.id)
        return original(task,*args,**kwargs)
    monkeypatch.setattr(executor,"evaluate",sandbox)
    adapter = tasks._coding(tasks.CODING_DEV[1])
    tasks.self_check({"train":[[adapter]],"final":[]})
    assert len(seen) == 9 and all(name.startswith("repo-v14-") for name in seen)
