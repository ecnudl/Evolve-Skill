"""New authored task/oracle consistency; no API, sandbox-only Python controls."""

import json
import math
from collections import Counter

import pytest

from skillopt.coevolution_v15 import tasks as t
from skillopt.validator_pilot.api import digest


def flat(panel):
    return [a for batch in panel["train"] + panel["calibration"] for a in batch] + panel["final"]


@pytest.mark.parametrize("smoke,total,rounds,calibration", [(False,32,[2,2,2,2],[2,2,2]),(True,7,[1,1],[2])])
def test_panel_counts_partitions_and_unique_families(smoke, total, rounds, calibration):
    panel = t.build_panel(smoke=smoke)
    assert [len(x) for x in panel["train"]] == rounds
    assert [len(x) for x in panel["calibration"]] == calibration
    assert [x[0].domain for x in panel["train"]] == (["coding","spreadsheet"] if smoke else ["coding","spreadsheet"]*2)
    rows = [t.payload(a) for a in flat(panel)]
    assert len(rows) == total == len({x["id"] for x in rows}) == len({x["cluster_id"] for x in rows})
    assert len({x["family"] for x in rows}) == total
    assert Counter(a.domain for a in panel["final"]) == {"coding":1 if smoke else 6,"spreadsheet":1 if smoke else 6,"rule_reasoning":1 if smoke else 6}
    assert all(x["metadata"]["partition"] == x["split"] for x in rows)
    assert all(x["metadata"]["smoke_only"] is smoke for x in rows)
    assert t.panel_manifest(panel) == t.panel_manifest(t.build_panel(smoke=smoke))
    assert t.panel_manifest(panel)["synthetic_not_public_benchmark"] is True


def test_smoke_structures_do_not_consume_pilot_families_or_references():
    sets = [{t.payload(a)["family"] for a in flat(t.build_panel(smoke=s))} for s in (False,True)]
    assert sets[0].isdisjoint(sets[1])
    refs = [{digest(t.calibration_artifacts(a)["reference"]) for a in flat(t.build_panel(smoke=s))} for s in (False,True)]
    assert refs[0].isdisjoint(refs[1])
    with pytest.raises(ValueError):
        t.build_panel(smoke=1)


@pytest.mark.parametrize("smoke", [False,True])
def test_all_fixed_cases_obey_declared_public_domain(smoke):
    for adapter in flat(t.build_panel(smoke=smoke)):
        row = t.payload(adapter)
        assert len(row["public_cases"]) == 2
        if adapter.domain == "rule_reasoning":
            assert len(row["hidden_cases"]) == 254
            continue
        cases = row["public_cases"] + row["private_cases" if adapter.domain == "coding" else "hidden_cases"]
        assert len(cases) == 8
        field = "input" if adapter.domain == "coding" else "overrides"
        assert all(t.validate_probe_input(adapter, case[field]) for case in cases)
        assert len({digest(case[field]) for case in cases}) == 8


@pytest.mark.parametrize("value", [None,True,[],{}, {"values":[],"k":False}, {"values":[True],"k":0},
    {"values":[1]*9,"k":0},{"values":[21],"k":0},{"values":[],"k":13},
    {"values":[],"k":0,"expected":0},{"values":[math.nan],"k":0}, {"values":(),"k":0}])
def test_coding_closed_schema_rejects_invalid_inputs(value):
    adapter = t.build_panel(smoke=True)["train"][0][0]
    assert t.validate_probe_input(adapter,value) is False


@pytest.mark.parametrize("value", [False,math.nan,math.inf,-math.inf,10**1000,"=1",[],{}])
def test_sheet_numbers_are_finite_bounded_not_bools_or_code(value):
    adapter = t.build_panel(smoke=True)["train"][1][0]
    example = t.canonical_inputs(adapter)[0]
    example["A1"] = value
    assert t.validate_probe_input(adapter,example) is False


@pytest.mark.parametrize("smoke", [False,True])
def test_canonical_and_controls_partition_input_boundaries(smoke):
    panel = t.build_panel(smoke=smoke)
    for adapter in [a for batch in panel["train"]+panel["calibration"] for a in batch]:
        canonical, ordinary = t.canonical_inputs(adapter),t.control_inputs(adapter)
        assert len(canonical) == 4 and len(ordinary) == 8
        assert {digest(x) for x in canonical}.isdisjoint(digest(x) for x in ordinary)
        assert len({digest(x) for x in canonical}) == 4
        assert all(t.validate_probe_input(adapter,x) for x in canonical+ordinary)
    for adapter in panel["final"]:
        for function in (t.canonical_inputs,t.control_inputs,t.constraints_for):
            with pytest.raises(ValueError):
                function(adapter)


@pytest.mark.parametrize("domain,phase", [("coding","development"),("spreadsheet","development"),
                                        ("coding","calibration"),("spreadsheet","calibration")])
def test_probe_has_independent_expected_and_bound_source_not_model_oracle(domain,phase):
    panel = t.build_panel(smoke=True)
    pool = [a for batch in panel["train"] if phase == "development" for a in batch] if phase == "development" else panel["calibration"][0]
    adapter = next(a for a in pool if a.domain == domain)
    original = t.payload(adapter)
    inputs = t.canonical_inputs(adapter)
    probe = t.probe_adapter(adapter,inputs)
    row = t.payload(probe)
    assert row["split"] == phase and row["cluster_id"] == original["cluster_id"]
    assert row["metadata"]["source_task_hash"] == digest(original)
    assert row["metadata"]["source_task_id"] == original["id"]
    assert row["metadata"]["ordinary_overlap"] == 0
    assert not row["private_cases" if domain == "coding" else "hidden_cases"]
    assert len(row["public_cases"]) == 4
    field = "input" if domain == "coding" else "overrides"
    oracle = t._code_oracle if domain == "coding" else t._sheet_oracle
    for case in row["public_cases"]:
        assert case["expected"] == oracle(original["family"],case[field])
    assert t.payload(adapter) == original
    inputs[0].clear()
    assert t.payload(probe) == row
    with pytest.raises(ValueError):
        t.public_task(probe)
    with pytest.raises(ValueError):
        t.probe_adapter(probe,t.canonical_inputs(adapter))


@pytest.mark.parametrize("invalid", [[],[{}],[{}, {}, {}, {}, {}],"inputs"])
def test_illegal_probe_requests_cannot_materialize(invalid):
    adapter = t.build_panel(smoke=True)["train"][0][0]
    with pytest.raises(ValueError):
        t.probe_adapter(adapter,invalid)


def test_duplicate_probe_and_attempted_expected_injection_rejected():
    adapter = t.build_panel(smoke=True)["train"][0][0]
    value = t.canonical_inputs(adapter)[0]
    for bad in ([value,value],[{**value,"expected":{"result":999}}]):
        with pytest.raises(ValueError):
            t.probe_adapter(adapter,bad)
    ordinary = t.control_inputs(adapter)[:4]
    assert t.payload(t.probe_adapter(adapter,ordinary))["metadata"]["ordinary_overlap"] == 4


def test_model_public_view_contains_no_private_or_reference_fields():
    forbidden = {"private_cases","hidden_cases","reference_files","reference_artifact","metadata","calibration_artifacts"}
    for adapter in flat(t.build_panel(smoke=False)):
        public = t.public_task(adapter)
        assert forbidden.isdisjoint(public)
        json.dumps(public,allow_nan=False)
        if adapter.domain == "spreadsheet":
            assert "==" in public["runtime"]
        elif adapter.domain == "rule_reasoning":
            assert "audit_rule unchanged" in public["runtime"]
        else:
            assert public["contract"]["change_scope"] == "partial_update"


@pytest.mark.parametrize("smoke", [False,True])
def test_all_controls_actual_native_or_os_sandbox_and_canonical_oracles(smoke):
    report = t.self_check(t.build_panel(smoke=smoke))
    assert report["checked_tasks"] == (7 if smoke else 32)
    assert report["all_checked"] and report["model_api_calls"] == 0
    for record in report["records"]:
        assert {name for name,result in record["controls"].items() if result["passed"]} == {"reference","equivalent"}
        assert all(result["available"] for result in record["controls"].values())


def test_reference_oracle_hand_calculated_interactions_not_reference_execution():
    assert t._code_oracle("prefix-lower-medians",{"values":[4,1,4,0],"k":0})["result"] == [4,1,4,1]
    assert t._code_oracle("stable-top-k-indices",{"values":[2,5,5,2],"k":3})["result"] == [1,2,0]
    assert t._code_oracle("earliest-palindromic-slice",{"values":[1,2,1,3,1],"k":0})["result"] == [0,3]
    assert t._code_oracle("circular-nonadjacent-profit",{"values":[3,1,1,3],"k":0})["result"] == 4
    assert t._code_oracle("minimum-forward-jumps",{"values":[1,0,3],"k":0})["result"] == -1
    assert t._code_oracle("kth-missing-positive",{"values":[1,2,2,4,-2],"k":2})["result"] == 5


def test_all_native_equivalent_controls_are_parse_valid_not_delivery_mutants():
    from skillopt.coevolution_v15.runtime import _parse
    for adapter in flat(t.build_panel(smoke=False)):
        if adapter.domain == "coding":
            continue
        public = t.public_task(adapter)
        for artifact in t.calibration_artifacts(adapter).values():
            assert _parse(public,json.dumps(artifact),adapter.domain,None,"generation") == artifact


def test_oracle_tampering_is_detected_by_preflight():
    panel = t.build_panel(smoke=True)
    panel["train"][1][0].task["hidden_cases"][0]["expected"]["B1"] += 99
    with pytest.raises(ValueError,match="independent oracle"):
        t.self_check(panel)


def test_partition_relabeling_or_family_duplicate_cannot_pass_preflight():
    panel = t.build_panel(smoke=True)
    panel["calibration"][0][1].task["metadata"]["partition"] = "development"
    with pytest.raises(ValueError,match="partition"):
        t.self_check(panel)
