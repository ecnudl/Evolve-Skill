"""Offline audit tests; no live artifacts, model calls or unsandboxed candidates."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "audit_scale_quote_contract", Path(__file__).resolve().parents[1] / "scripts/audit_scale_quote_contract.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_exact_fixed_finite_language_without_unplanned_spaces_or_b():
    words = module.words()
    assert len(words) == len(set(words)) == 364
    assert words[0] == ""
    assert set("".join(words)) == {"a", ",", '"'}
    assert max(map(len, words)) == 5
    assert 'a"a"' in words
    assert 'a"b"' not in words
    assert " " not in "".join(words)


def test_reference_crosschecks_include_explicit_omissions_and_support_limits():
    examples = {text: (expected, exception) for text, expected, exception in module.REFERENCE_EXAMPLES}
    assert examples['a"b"'] == (None, "ValueError")
    assert examples['"a'] == (None, "ValueError")
    assert examples['"a"b'] == (None, "ValueError")
    assert examples['""""'] == (['"'], None)
    assert examples["a,"] == (["a", ""], None)
    assert examples[" a , b "] == ([" a ", " b "], None)


def test_candidate_execution_delegates_only_to_existing_sandbox_without_answers(monkeypatch):
    from skillopt.validator_pilot import tasks as oracle

    captured = []

    def fake_run(payload):
        captured.append(payload)
        return 0, json.dumps({"rows": [{"actual": ["x"], "exception": None} for _ in payload["cases"]]}), ""

    monkeypatch.setattr(oracle, "_run_payload", fake_run)
    observed = module.sandbox_observations("def solve(data): return []", ["a", '"'])
    assert len(observed) == 2
    assert set(captured[0]) == {"code", "cases"}
    assert all(set(case) == {"setup", "expr"} for case in captured[0]["cases"])
    assert "expected" not in json.dumps(captured)


def test_sandbox_failure_never_falls_back_to_local_exec(monkeypatch):
    from skillopt.validator_pilot import tasks as oracle

    monkeypatch.setattr(oracle, "_run_payload", lambda payload: (134, "", ""))
    with pytest.raises(RuntimeError, match="sandbox"):
        module.sandbox_observations("def solve(data): return []", ["a"])


def test_real_runner_exception_message_is_accepted(monkeypatch):
    from skillopt.validator_pilot import tasks as oracle

    monkeypatch.setattr(
        oracle,
        "_run_payload",
        lambda payload: (
            0,
            json.dumps({"rows": [{"actual": None, "exception": "ValueError", "message": "invalid quote"}]}),
            "",
        ),
    )
    assert module.sandbox_observations("def solve(data): return []", ['a"a"'])[0]["exception"] == "ValueError"


@pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="frozen reference must run inside existing macOS sandbox",
)
def test_frozen_trusted_reference_passes_contract_crosschecks_and_364_case_generation():
    from skillopt.validator_scale_tasks import build_tasks

    task = next(task for task in build_tasks("holdout") if task.id == module.TASK_ID)
    cases, checks = module.build_expected_cases(task.reference_code)
    assert len(cases) == 364
    assert all(check["passed"] and check["reference_only"] for check in checks)
    assert {case["exception"] for case in cases} == {None, "ValueError"}


def test_reference_disagreement_aborts_before_finite_language_generation(monkeypatch):
    calls = []

    def fake_observations(code, texts):
        calls.append(texts)
        return [{"actual": [], "exception": None} for _ in texts]

    monkeypatch.setattr(module, "sandbox_observations", fake_observations)
    with pytest.raises(ValueError, match="contradicts"):
        module.build_expected_cases("not executed")
    assert len(calls) == 1


def test_expected_cases_do_not_expand_language_with_reference_only_examples(monkeypatch):
    calls = []

    def fake_observations(code, texts):
        calls.append(texts)
        if len(calls) == 1:
            return [
                {"actual": expected, "exception": exception} for text, expected, exception in module.REFERENCE_EXAMPLES
            ]
        return [{"actual": [text], "exception": None} for text in texts]

    monkeypatch.setattr(module, "sandbox_observations", fake_observations)
    cases, checks = module.build_expected_cases("not executed")
    assert len(cases) == 364
    assert len(checks) == len(module.REFERENCE_EXAMPLES)
    assert calls[1] == module.words()
    assert all(
        set(case) == {"label", "setup", "expr", "expected", "exception", "dimension", "public"} for case in cases
    )
    assert all(case["public"] is False for case in cases)


def test_source_must_be_complete_before_reading_frozen_tasks(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "tasks_private.json").write_text("invalid must not be read")
    with pytest.raises(RuntimeError, match="complete"):
        module.verify_source(source)
    (source / "results.json").write_text(json.dumps({"status": "running"}))
    with pytest.raises(RuntimeError, match="complete"):
        module.verify_source(source)


def test_no_output_inside_source_or_overwrite(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="outside"):
        module.validate_output(source, source / "audit.json")
    destination = tmp_path / "audit.json"
    module.validate_output(source, destination)
    destination.write_text("preserve")
    with pytest.raises(FileExistsError):
        module.validate_output(source, destination)
    assert destination.read_text() == "preserve"


def test_missing_code_remains_unavailable_not_fake_pass():
    artifact = {"original_hard": None, "code": None}
    result = module.audit_artifact(None, artifact, [])
    assert result["finite_language_pass"] is None


def test_summary_separates_original_scores_discoveries_and_unavailable():
    rows = [
        {"origin": "natural", "arm": "mechanism_skill", "original_hard": True, "finite_language_pass": outcome}
        for outcome in (True, False, None, True)
    ]
    summary = module.summarize(rows)["mechanism_skill"]
    assert summary == {
        "artifacts": 4,
        "original_hard_pass": 4,
        "finite_language_pass": 2,
        "finite_language_fail": 1,
        "unavailable": 1,
        "original_pass_but_posthoc_failure": 1,
    }
