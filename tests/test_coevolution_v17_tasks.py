"""No API: authored task contracts, host-oracle consistency and heldout closure."""

import itertools
import json
import random
from collections import Counter
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v8.feedback_study import evaluate, score
from skillopt.coevolution_v15.runtime import task_public as runtime_public
from skillopt.coevolution_v17 import tasks as t
from skillopt.validator_pilot.api import digest


def flat(panel):
    return [a for group in panel.values() for a in group]


@pytest.mark.parametrize("smoke,counts", [(False,[6,6,6,8,24]),(True,[1,1,1,4,3])])
def test_counts_domains_family_separation(smoke,counts):
    panel = t.build_panel(smoke)
    assert list(panel) == ["source","source_extra","transfer","confirmation","final"]
    assert [len(group) for group in panel.values()] == counts
    assert {a.domain for a in panel["source"]+panel["source_extra"]} == {"coding"}
    assert {a.domain for a in panel["transfer"]} == {"spreadsheet"}
    assert Counter(a.domain for a in panel["final"]) == dict.fromkeys(("coding","spreadsheet","rule_reasoning"),1 if smoke else 8)
    all_ids,partitions = set(),{}
    for phase,group in panel.items():
        for a in group:
            row = t.payload(a)
            assert row["id"] not in all_ids
            all_ids.add(row["id"])
            assert row["metadata"]["version"] == t.VERSION
            assert row["metadata"]["smoke_only"] is smoke
            expected_split = "final" if phase == "final" else "calibration" if phase == "confirmation" else "development"
            assert row["split"] == row["metadata"]["partition"] == expected_split
            family = row["metadata"]["structural_family"]
            assert partitions.setdefault(family,phase) == phase
    if not smoke:
        for domain in ("coding","spreadsheet","rule_reasoning"):
            families = Counter(t.payload(a)["family"] for a in panel["final"] if a.domain == domain)
            assert len(families) == 4 and set(families.values()) == {2}


@pytest.mark.parametrize("smoke", [False,True])
def test_confirmation_has_four_cells_and_replacement_is_public_semantic_obligation(smoke):
    panel = t.build_panel(smoke)
    assert {(a.domain,t.payload(a)["metadata"]["mechanism_cell"]) for a in panel["confirmation"]} == {
        (domain,cell) for domain in ("coding","spreadsheet") for cell in ("same_mechanism","near_miss")}
    for a in flat(panel):
        row = t.payload(a)
        public = t.public_task(a)
        if row["metadata"]["mechanism_cell"] == "near_miss":
            assert "EXPLICIT FULL POLICY REPLACEMENT" in public["prompt"]
            assert public["contract"]["supersedes_old_policy"] is True
        else:
            assert public["contract"]["supersedes_old_policy"] is False
    if not smoke:
        assert {a.domain for a in panel["final"] if t.payload(a)["metadata"]["mechanism_cell"] == "near_miss"} == {
            "coding","spreadsheet","rule_reasoning"}


def test_smoke_does_not_consume_full_panel_structures_or_references():
    panels = [flat(t.build_panel(flag)) for flag in (False,True)]
    families = [{t.payload(a)["family"] for a in panel} for panel in panels]
    references = [{digest(t.artifacts(a)["reference"]) for a in panel} for panel in panels]
    assert families[0].isdisjoint(families[1])
    assert references[0].isdisjoint(references[1])
    for wrong in (None,0,1,"false"):
        with pytest.raises(ValueError):
            t.build_panel(wrong)


@pytest.mark.parametrize("smoke", [False,True])
def test_public_projection_and_runtime_never_expose_host_labels_or_gold(smoke):
    forbidden = {"metadata","mechanism_cell","structural_family","variant","private_cases","hidden_cases","reference_files","reference_artifact"}
    for a in flat(t.build_panel(smoke)):
        for projection in (t.public_task(a),runtime_public(a)):
            assert forbidden.isdisjoint(projection)
            assert len(projection["public_cases"]) == 2
        row = t.payload(a)
        cases = row["public_cases"] + row["private_cases" if a.domain == "coding" else "hidden_cases"]
        assert len(cases) >= 8
        if a.domain == "coding":
            assert all(a._input_valid(case["input"]) for case in cases)
        elif a.domain == "rule_reasoning":
            assert len(cases) == len({tuple(case["facts"]) for case in cases}) == 256


@pytest.mark.parametrize("smoke", [False,True])
def test_manifest_is_stable_and_has_no_answers(smoke):
    panel = t.build_panel(smoke)
    manifest = t.manifest(panel)
    assert manifest == t.panel_manifest(t.build_panel(smoke))
    assert manifest["synthetic_not_public_benchmark"] is True
    serialized = json.dumps(manifest)
    for forbidden in ("expected", "reference_artifact", "reference_files", "public_cases", "hidden_cases", "private_cases"):
        assert forbidden not in serialized


@pytest.mark.parametrize("smoke,total", [(False,50),(True,10)])
def test_all_authored_references_pass_and_starters_fail_native_oracles(smoke,total):
    result = t.self_check(t.build_panel(smoke))
    assert result["all_checked"] is True
    assert result["checked_tasks"] == total
    assert result["model_api_calls"] == 0
    assert result["internal_consistency_not_model_efficacy"] is True


def test_coding_independent_oracles_on_additional_seeded_inputs():
    rng = random.Random(17001)
    for adapter in flat(t.build_panel()):
        if adapter.domain != "coding":
            continue
        row = t.payload(adapter)
        family,variant = row["family"],row["metadata"]["variant"]
        lower = row["input_domain"]["properties"]["values"]["items"]["minimum"]
        examples = [{"values":[rng.randint(lower,6) for _ in range(rng.randrange(9))],"k":rng.randrange(7)} for _ in range(24)]
        cases = [{"label":f"independent-{i}","input":x,"expected":t._code_oracle(family,variant,x),
                  "exception":None,"public":i<2,"dimension":"requested_behavior"} for i,x in enumerate(examples)]
        probe = CodingAdapter(replace(adapter.task,public_cases=cases[:2],private_cases=cases[2:]))
        reference = t.artifacts(adapter)["reference"]
        result = score(probe,reference,evaluate(probe,reference,public_only=False))
        assert result["all_attempt_success"] == 1, (row["id"],result)


def test_self_check_rejects_partition_family_leakage():
    panel = t.build_panel(True)
    panel["source_extra"] = list(panel["source"])
    with pytest.raises(ValueError,match="duplication"):
        t.self_check(panel)


@pytest.mark.parametrize("variant", [0,1])
def test_weighted_palindrome_matching_equal_endpoints_is_not_forced(variant):
    adapter = next(a for a in t.build_panel()["final"] if t.payload(a)["family"] == t.CODE_FINAL[1]
                   and t.payload(a)["metadata"]["variant"] == variant)
    examples = [{"values":list(a),"k":0} for a in itertools.product((0,1,2),repeat=4)]
    examples += [{"values":[1,1,2,1],"k":0}]
    assert t._code_oracle(t.CODE_FINAL[1],0,examples[-1])["result"] == 1
    cases = [{"label":f"palindrome-oracle-{i}","input":x,"expected":t._code_oracle(t.CODE_FINAL[1],variant,x),
              "exception":None,"public":i<2,"dimension":"requested_behavior"} for i,x in enumerate(examples)]
    probe = CodingAdapter(replace(adapter.task,public_cases=cases[:2],private_cases=cases[2:]))
    artifact = t.artifacts(adapter)["reference"]
    result = score(probe,artifact,evaluate(probe,artifact,public_only=False))
    assert result["all_attempt_success"] == 1


def test_exact_circular_cover_empty_input_is_infeasible_for_positive_k():
    assert t._code_oracle(t.CODE_CONFIRM[0],0,{"values":[],"k":1})["result"] == 0
    assert t._code_oracle(t.CODE_CONFIRM[0],1,{"values":[],"k":0})["result"] == 0
    assert t._code_oracle(t.CODE_CONFIRM[0],1,{"values":[],"k":1})["result"] is None
    adapter = next(a for a in t.build_panel()["confirmation"] if t.payload(a)["family"] == t.CODE_CONFIRM[0]
                   and t.payload(a)["metadata"]["variant"] == 1)
    assert "exactly-k requires k=0" in t.public_task(adapter)["prompt"]
