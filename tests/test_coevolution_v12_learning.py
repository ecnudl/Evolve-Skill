"""Offline checks of matched evidence and phase boundaries."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v12 import learning as l

GOOD = "## When\nApplicable contracts.\n## Procedure\nCheck observations.\n## Avoid\nUnsupported claims."


def row(skill="", phase="development", success=1, available=True):
    return seal({"phase": phase, "task_id": "train-one", "domain": "coding", "artifact": {"a.py": "pass"},
        "skill_hash": l.text_hash(skill), "request_hashes": ["a"*64, "b"*64],
        "score": {"all_attempt_success": success if available else 0, "oracle_available": available,
                  "delivery_valid": available, "semantic_success": success if available else None},
        "private_evaluation": {"case_results": [{"id": "case", "passed": bool(success)}],
            "private_diagnostics": [{"input": {"x": 1}, "actual": 2, "expected": 3}] if not success else []}})


def test_same_raw_evidence_both_arms():
    task = {"id": "train-one", "prompt": "Obey task contract."}
    pair = [(row(), row("old", success=0))]
    fixed = l.messages("old", [task], pair, "independent")
    contrast = l.messages("old", [task], pair, "contrastive")
    assert fixed[0] == contrast[0] and fixed[2] == contrast[2]
    a, b = json.loads(fixed[1]), json.loads(contrast[1])
    assert a["observed_records"] == b["observed_records"]
    assert "pair_diagnostics" not in a
    assert b["pair_diagnostics"][0]["category"] == "repair_observed_regression"
    assert b["observed_records"][1]["executed_checks"]["executed_failure_details"][0]["expected"] == 3


@pytest.mark.parametrize("phase", ["selection", "final", "test"])
def test_no_nontraining_feedback(phase):
    with pytest.raises(ValueError, match="Selection/final"):
        l.messages("", [{"id": "train-one"}], [(row(), row(phase=phase))], "contrastive")


@pytest.mark.parametrize("base,current,category", [(0,1,"preserve_observed_gain"),
    (1,0,"repair_observed_regression"),(0,0,"shared_failure_seek_specific_repair"),
    (1,1,"both_pass_no_new_gain_evidence")])
def test_observed_pair_categories(base, current, category):
    value = l.evidence([{"id":"train-one"}], [(row(success=base), row("old", success=current))])
    assert value["pair_diagnostics"][0]["category"] == category


def test_unknown_not_semantic_failure():
    value = l.evidence([{"id":"train-one"}], [(row(), row("old", available=False))])
    assert value["pair_diagnostics"][0]["category"] == "unknown_do_not_infer_behavior"


def test_parse_text_success():
    assert l.parse_skill({"ok":True,"response":GOOD}, "old")["skill"] == GOOD


@pytest.mark.parametrize("response", ["", "```markdown\n"+GOOD+"\n```", "## Procedure\nOnly one.", "x"*6001])
def test_parse_invalid_keeps_parent(response):
    result = l.parse_skill({"ok":True,"response":response}, "parent")
    assert not result["valid"] and result["skill"] == "parent"


def test_api_unknown_keeps_parent():
    assert l.parse_skill({"ok":False}, "parent")["reason"] == "api_unknown"


def test_evidence_inputs_not_modified():
    tasks, pairs = [{"id":"train-one"}], [(row(), row("old",success=0))]
    before = deepcopy((tasks,pairs))
    l.messages("old",tasks,pairs,"contrastive")
    assert (tasks,pairs) == before


def test_selection_is_not_scope_approval():
    decision = l.choose_selected("old","new",[row(phase="selection",success=0)],
                                  [row("new",phase="selection")])
    assert decision["accept"] and decision["skill"] == "new"
    assert not decision["scope_approval"] and not decision["safety_certified"]


def test_tie_retains_selected_not_new_raw():
    decision = l.choose_selected("old","new",[row(phase="selection")],[row("new",phase="selection")])
    assert not decision["accept"] and decision["skill"] == "old"


def test_final_cannot_select():
    with pytest.raises(ValueError, match="selection"):
        l.choose_selected("old","new",[row(phase="final")],[row("new",phase="final")])
