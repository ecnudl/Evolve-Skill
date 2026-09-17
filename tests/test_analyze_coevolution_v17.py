"""Derived interpretation must not invent efficacy after an early stop."""

import pytest

from scripts.analyze_coevolution_v17 import interpret
from skillopt.coevolution_v17.core import analyze


def result(status="screen_stopped"):
    return {"complete": True, "status": status, "design": "pilot", "record_hash": "a" * 64,
        "screen": {"passed": 12, "tasks": 12, "semantic_failures": 0,
                   "failure_families": [], "oracle_unknown": 0},
        "ledger": {"cached_logical_calls": 24, "http_attempts_from_cached_records": 24,
                   "terminal_errors": 0, "total_tokens": 100}}


def test_screen_stop_has_no_invented_final_or_success_claim():
    text = interpret(result())
    assert "12/12" in text and "没有运行 Skill 分叉" in text
    assert "没有发现可执行语义错误" in text
    assert "原始 Skill：" not in text


def test_unknown_is_not_semantic_headroom():
    row = result()
    row["screen"]["oracle_unknown"] = 1
    text = interpret(row)
    assert "不可用结果" in text and "没有发现可执行语义错误" not in text


def test_complete_ceiling_and_fallback_not_called_generalization():
    row = result("completed")
    arms = ("no_skill", "parent", "local_feedback", "cross_raw_feedback", "cross_structured_feedback")
    rows = [{"phase": "final", "task_id": domain, "domain": domain, "structural_family": domain,
             "history": 0, "arm": arm, "cell": "same_mechanism", "artifact_valid": True,
             "oracle_available": True, "passed": True}
            for domain in ("coding", "spreadsheet", "rule_reasoning") for arm in arms]
    row["summary"] = analyze(rows)
    row["deployment_coverage"] = {"gated_x": {"positions": 3, "candidate_positions": 0}}
    text = interpret(row)
    assert "尚不能声称获得泛化增益" in text and "最终 No-Skill 满分" in text
    assert "所有经验准入策略均回退 Base" in text
    assert "区间包含零" in text


def test_incomplete_run_cannot_be_interpreted():
    row = result()
    row["complete"] = False
    with pytest.raises(ValueError):
        interpret(row)
