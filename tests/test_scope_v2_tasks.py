"""Oracle, executable-artifact, protocol and interpreter-safety tests for v2."""
from __future__ import annotations

import json
from collections import Counter

import pytest

from skillopt.scope_evolution_v2.tasks import (
    DEFAULT_DOMAINS,
    SPLITS,
    Task,
    _apply,
    _artifact,
    _eval,
    _execute,
    _reference_patch,
    build_tasks,
    evaluate_answer,
)


@pytest.mark.parametrize("difficulty", ["medium", "hard"])
@pytest.mark.parametrize("split", SPLITS)
def test_gold_patch_matches_independent_oracle_in_every_artifact_domain(split, difficulty):
    # These are interpreter/oracle unit checks, not model-based test evaluation.
    for task in build_tasks(seed=17, split=split, n_per_cell=2, difficulty=difficulty):
        result = evaluate_answer(task, json.dumps({"answer": task.gold}))
        assert result["correct"], (task.id, result)
        assert result["artifact_valid"]
        assert result["passed_tests"] == result["total_tests"]
        assert result["soft"] == 1.0
        assert not result["failure_examples"]


def test_determinism_balance_serialization_and_subset_generation():
    for split in SPLITS:
        tasks = build_tasks(42, split, 2, mechanisms=["constraint_preservation"])
        assert tasks == build_tasks(42, split, 2, mechanisms=["constraint_preservation"])
        assert len(tasks) == len(DEFAULT_DOMAINS[split]) * 3 * 2
        assert {task.mechanism for task in tasks} == {"constraint_preservation", "none"}
        assert set(Counter((t.domain, t.mechanism, t.group) for t in tasks).values()) == {2}
        for task in tasks:
            assert Task.from_dict(json.loads(json.dumps(task.to_dict()))) == task
        larger = {t.id: t for t in build_tasks(42, split, 3, mechanisms=["constraint_preservation"])}
        assert all(larger[t.id] == t for t in tasks)


def test_split_structural_variants_and_held_out_domain():
    tasks = {split: build_tasks(42, split, 1) for split in SPLITS}
    for i, split in enumerate(SPLITS):
        for other in SPLITS[i + 1:]:
            assert not {t.id for t in tasks[split]} & {t.id for t in tasks[other]}
            assert not {t.family for t in tasks[split]} & {t.family for t in tasks[other]}
    assert {t.domain for t in tasks["train"]} == {"coding"}
    assert {t.domain for t in tasks["dev"]} == {"coding"}
    assert "rule_reasoning" not in {t.domain for t in tasks["validation"]}
    with pytest.raises(ValueError, match="held-out"):
        build_tasks(split="train", domains=["rule_reasoning"])


def test_prompts_have_explicit_schemas_and_no_hidden_test_payload_or_labels():
    for split in SPLITS:
        for task in build_tasks(4, split, 1):
            assert "OUTPUT SCHEMA (exact nesting and field names)" in task.prompt
            assert '"answer"' in task.prompt
            assert task.id not in task.prompt
            for key in ["constraint_preservation", "evidence_verification", "near_miss", '"tests":', '"gold":', '"expected":']:
                assert key not in task.prompt
            # The prompt displays an original artifact, never a reference patch.
            assert '"reference_patch"' not in task.prompt


def test_noop_patch_has_no_artifact_success_shortcut():
    for task in build_tasks(31, "validation", 2):
        key = next(iter(task.gold))
        result = evaluate_answer(task, json.dumps({"answer": {key: {}}}))
        assert not result["correct"], task.id
        assert result["format_valid"]
        assert result["artifact_valid"]


def test_credit_boundary_requires_both_requested_outputs():
    task = next(t for t in build_tasks(42, "train", 1, mechanisms=["constraint_preservation"])
                if t.group == "positive")
    patch = {"replace": {"amount_due": task.gold["replace"]["amount_due"]}}
    result = evaluate_answer(task, json.dumps({"answer": patch}))
    assert not result["correct"]
    assert result["dimensions"]["requested_behavior"]["passed"] < result["total_tests"]
    assert result["dimensions"]["preserved_behavior"]["passed"] == result["total_tests"]
    assert any("credit_used" in f["failed_outputs"] for f in result["failure_examples"])


def test_historical_exports_are_real_regression_tests():
    task = next(t for t in build_tasks(42, "train", 1, mechanisms=["constraint_preservation"])
                if t.group == "positive")
    patch = json.loads(json.dumps(task.gold))
    patch["replace"]["audit_code"] = "0"
    result = evaluate_answer(task, json.dumps({"answer": patch}))
    assert not result["correct"]
    assert result["dimensions"]["requested_behavior"]["passed"] == result["total_tests"]
    assert result["dimensions"]["preserved_behavior"]["passed"] < result["total_tests"]


def test_cp_oracle_known_credit_and_quote_fixture():
    task = next(t for t in build_tasks(7, "train", 1, mechanisms=["constraint_preservation"], difficulty="hard")
                if t.group == "positive")
    p = task.metadata["parameters"]
    case = {"price": 10, "qty": 10, "credit": 10000, "member": True, "remote": False,
            "rush": False, "campaign": True, "fragile": True, "priority": True}
    artifact = _apply(task.metadata["artifact"], task.gold)
    actual = _execute(artifact, case)
    gross = 100
    bulk = min(p["bulk_cap"], 100 // p["bulk_div"])
    goods = max(0, gross - bulk - p["member_rate"] * 10)
    packing = p["packing_rate"] * 10
    quote = goods + p["local_fee"] + packing + goods // p["tax_div"]
    rebate = min(goods, p["rebate_rate"] * 10 + p["priority_bonus"])
    subtotal = max(0, goods - rebate + packing + max(0, goods - rebate) // p["tax_div"])
    assert actual["amount_due"] == 0
    assert actual["credit_used"] == subtotal
    assert actual["quoted_total"] == quote
    assert actual["zone_quote"] == p["local_fee"]
    assert actual["tax_quote"] == goods // p["tax_div"]
    assert actual["audit_code"] == quote * 3 + p["local_fee"] * 5 + bulk


def test_ev_replay_is_covered_by_positive_regression_tests():
    task = next(t for t in build_tasks(13, "train", 1, mechanisms=["evidence_verification"])
                if t.group == "positive")
    patch = json.loads(json.dumps(task.gold))
    patch["replace"]["use_active"] = "True"
    result = evaluate_answer(task, json.dumps({"answer": patch}))
    assert not result["correct"]
    assert result["dimensions"]["preserved_behavior"]["passed"] < result["total_tests"]
    assert any("use_active" in f["failed_outputs"] for f in result["failure_examples"])


def test_ev_near_miss_requires_legacy_flag_bypass():
    task = next(t for t in build_tasks(21, "train", 1, mechanisms=["evidence_verification"])
                if t.group == "near_miss")
    result = evaluate_answer(task, '{"answer":{"replace":{}}}')
    assert not result["correct"]
    assert result["dimensions"]["preserved_behavior"]["passed"] == result["total_tests"]


@pytest.mark.parametrize("split", ["train", "dev", "validation", "test"])
def test_hard_ev_emergency_requirement_is_independently_tested(split):
    task = next(t for t in build_tasks(42, split, 1, domains=["coding"],
                                     mechanisms=["evidence_verification"], difficulty="hard")
                if t.group == "positive")
    patch = json.loads(json.dumps(task.gold))
    predicate = patch["replace"]["eligible"]
    assert " and (not emergency or emergency_authorized)" in predicate
    patch["replace"]["eligible"] = predicate.replace(" and (not emergency or emergency_authorized)", "")
    result = evaluate_answer(task, json.dumps({"answer": patch}))
    assert not result["correct"]
    assert any("eligible_ids" in f["failed_outputs"] for f in result["failure_examples"])


def test_cp_tests_include_numeric_range_and_exact_credit_boundaries():
    task = next(t for t in build_tasks(9, "train", 1, mechanisms=["constraint_preservation"])
                if t.group == "positive")
    cases = task.metadata["tests"]
    assert any(c["inputs"]["price"] == 100 and c["inputs"]["qty"] == 30 for c in cases)
    assert any(c["inputs"]["credit"] == 10000 for c in cases)
    assert any(c["inputs"]["credit"] > 0 and c["expected"]["amount_due"] == 0
               and c["expected"]["credit_used"] == c["inputs"]["credit"] for c in cases)
    assert any(c["expected"]["amount_due"] == 1 for c in cases)


def test_domains_have_genuine_execution_semantics_differences():
    # Forward references are valid in spreadsheet recalculation but invalid in
    # a sequential expression program (and in ordered rule stages).
    nodes = {"first": "1", "second": "x + 2"}
    program = _artifact("coding", ["x"], nodes)
    spreadsheet = _artifact("spreadsheet", ["x"], nodes)
    rules = _artifact("rule_reasoning", ["x"], nodes)
    for artifact in [program, rules]:
        patched = _apply(artifact, _reference_patch(artifact, {"first": "second + 1"}))
        with pytest.raises(KeyError):
            _execute(patched, {"x": 3})
    patched = _apply(spreadsheet, _reference_patch(spreadsheet, {"first": "second + 1"}))
    assert _execute(patched, {"x": 3}) == {"first": 6, "second": 5}


def test_spreadsheet_cycle_is_rejected_without_execution():
    artifact = _artifact("spreadsheet", ["x"], {"a": "x + 1", "b": "a + 1"})
    patched = _apply(artifact, _reference_patch(artifact, {"a": "b + 1"}))
    with pytest.raises(ValueError, match="cyclic"):
        _execute(patched, {"x": 1})


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo unsafe')", "open('/tmp/file')", "x.__class__", "x[0]",
    "[x for x in [1]]", "lambda: 1", "2 ** 100000", "IF(False, open('unused'), 1)",
])
def test_arbitrary_code_and_unknown_functions_rejected(expression):
    with pytest.raises((ValueError, SyntaxError)):
        _eval(expression, {"x": 1})


@pytest.mark.parametrize("response", [
    '```json\n{"answer":{"replace":{}}}\n```', '{"answer":[],"extra":1}',
    '{"answer":{"replace":{}},"answer":{"replace":{}}}', '{"answer":{"replace":{"unknown":"1"}}}',
    '{"answer":{"replace":{"amount_due":42}}}', '{"answer":{"replace":{"amount_due":"open(1)"}}}',
])
def test_invalid_patch_contract_is_scored_as_failure(response):
    task = next(t for t in build_tasks(3, "train", 1, mechanisms=["constraint_preservation"]) if t.group == "positive")
    result = evaluate_answer(task, response)
    assert not result["correct"]
    assert not result["artifact_valid"]


@pytest.mark.parametrize("kwargs", [
    {"split": "bad"}, {"difficulty": "unknown"}, {"n_per_cell": 0}, {"n_per_cell": True},
    {"mechanisms": []}, {"mechanisms": ["bad"]}, {"domains": []},
    {"domains": ["coding", "coding"]},
])
def test_invalid_generator_parameters(kwargs):
    with pytest.raises(ValueError):
        build_tasks(**kwargs)
