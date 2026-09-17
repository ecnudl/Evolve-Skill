"""Completed-run post-hoc CLI; evaluators are mocked, no code/API execution."""

from __future__ import annotations

import copy
import json

import pytest

from scripts import validator_artifact_sensitivity as cli
from skillopt.validator_pilot.api import digest


def task():
    return {
        "id": "held-1",
        "split": "holdout",
        "family": "held-family",
        "cluster_id": "held-family",
        "prompt": "Preserve behavior",
        "starter_code": "def f(): return 0",
        "reference_code": "PRIVATE_REFERENCE",
        "public_cases": [],
        "private_cases": [{"expected": "PRIVATE_GOLD"}],
        "metadata": {"upstream_name": "mock"},
    }


def row(
    index=0,
    *,
    raw=None,
    hard=False,
    target_ok=True,
    execution_ok=True,
    origin="natural",
    decision="pass",
    judge_ok=True,
):
    return {
        "id": "held-1",
        "split": "holdout",
        "family": "held-family",
        "cluster_id": "held-family",
        "skill_version": "noskill" if origin == "natural" else "generic_mutant",
        "repeat": index,
        "origin": origin,
        "target_ok": target_ok,
        "execution_ok": execution_ok,
        "hard": hard,
        "response": raw if raw is not None else "```python\ndef f(): return 1\n```",
        "request_hash": digest([index, origin]),
        "evaluation": {},
        "judge_ok": judge_ok,
        "judgment": {"schema_valid": True, "decision": decision},
        "validator_arm": "static_v0",
        "judge_request_hash": "judge-" + str(index),
    }


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_run(tmp_path, rows=None, *, status="complete", arms=None):
    run = tmp_path / "frozen_run"
    rows = rows or [row(), row(1, raw=json.dumps({"code": "def f(): return 1"}), hard=True)]
    arms = arms or {"static_v0": rows}
    manifest = {"held-1": task()}
    protocol = {
        "task_manifest_hash": digest(manifest),
        "source_hashes": {
            path: digest((cli.REPO / path).read_text(encoding="utf-8")) for path in cli.FROZEN_SOURCE_REQUIREMENTS
        },
    }
    write(run / "results.json", {"status": status, "holdout": {arm: {} for arm in arms}})
    write(run / "protocol.json", protocol)
    write(run / "rubrics_frozen.json", {arm: {} for arm in arms})
    write(run / "tasks_private.json", manifest)
    write(run / "targets_frozen_private.json", rows)
    for arm, values in arms.items():
        write(run / "holdout" / (arm + ".json"), values)
    return run


@pytest.fixture
def fake_evaluator(monkeypatch):
    calls = []

    def evaluate(task_object, response):
        calls.append((task_object, response))
        code = response["code"]
        if "INFRA" in code:
            return {"execution_ok": False, "hard": False, "error_category": "infrastructure_failure"}
        if "BEHAVIOR_FAIL" in code:
            return {"execution_ok": True, "hard": False, "private_diagnostics": [{"failure": "private"}]}
        if "AST_FAIL" in code:
            return {"execution_ok": True, "hard": False, "error_category": "candidate_contract_violation"}
        return {"execution_ok": True, "hard": True, "private_diagnostics": []}

    monkeypatch.setattr(cli, "evaluate", evaluate)
    return calls


def test_completed_run_normalizes_and_guards_without_mutating_input(tmp_path, fake_evaluator):
    run = make_run(tmp_path)
    before = {str(p.relative_to(run)): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    output = tmp_path / "posthoc.json"
    report = cli.analyze_run(run, output)
    assert len(fake_evaluator) == 2
    metrics = report["artifact_normalization"]["by_origin"]["natural"]["all"]
    assert metrics["original_strict_pass"] == 1
    assert metrics["normalized_pass"] == 2
    assert metrics["extraction_count"] == 2
    guard = report["strict_public_guard"]
    assert guard["forced_counts"]["static_v0"] == 1
    assert guard["within_arm_paired"]["static_v0"]["main"]["corrected_false_passes"] == 1
    first = guard["rows"]["static_v0"][0]
    assert first["original_judgment"]["decision"] == "pass"
    assert first["judgment"] == {"decision": "fail", "schema_valid": True}
    assert first["judge_ok"] is True and first["original_judge_ok"] is True
    assert first["judgment_source"] == "deterministic_public_guard_not_LLM"
    assert report["model_calls"] == 0 and "POSTHOC" in report["classification"]
    assert report["provenance"]["protocol_sha256"] == cli._sha(run / "protocol.json")
    after = {str(p.relative_to(run)): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    assert before == after
    assert cli.analyze_run(run, output) == report  # Byte-equivalent immutable resume.


def test_completion_barrier_is_before_any_private_manifest_read(tmp_path, monkeypatch):
    run = tmp_path / "unfinished"
    write(run / "tasks_private.json", {"DO_NOT_READ": "private"})
    reads = []
    original = cli._read

    def tracked(path, hashes, root):
        reads.append(path.name)
        return original(path, hashes, root)

    monkeypatch.setattr(cli, "_read", tracked)
    with pytest.raises(ValueError, match="results.json"):
        cli.analyze_run(run, tmp_path / "posthoc.json")
    assert reads == []
    write(run / "results.json", {"status": "running"})
    with pytest.raises(ValueError, match="complete"):
        cli.analyze_run(run, tmp_path / "posthoc.json")
    assert reads == ["results.json"]


def test_output_inside_original_run_is_refused(tmp_path, fake_evaluator):
    run = make_run(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        cli.analyze_run(run, run / "new_report.json")
    assert fake_evaluator == []


def test_infrastructure_and_unextractable_denominators_stay_explicit(tmp_path, fake_evaluator):
    rows = [
        row(0, raw="not valid Python or JSON"),
        row(1, raw="INFRA = 1"),
        row(2, raw="BEHAVIOR_FAIL = 1"),
        row(3, raw="AST_FAIL = 1"),
        row(4, raw="", target_ok=False, execution_ok=False, hard=None),
    ]
    run = make_run(tmp_path, rows)
    report = cli.analyze_run(run, tmp_path / "posthoc.json")
    metrics = report["artifact_normalization"]["by_origin"]["natural"]["all"]
    assert metrics["n_responses"] == 5
    assert metrics["normalized_fail"] == 3
    assert metrics["normalized_unobservable"] == 2
    assert metrics["unextractable"] == 1
    assert metrics["reevaluation_infrastructure_errors"] == 1
    assert metrics["target_api_errors"] == 1
    assert metrics["behavior_or_structural_failures"] == 1
    assert metrics["runtime_ast_contract_failures"] == 1
    assert len(fake_evaluator) == 3


def test_natural_and_controlled_are_never_pooled(tmp_path, fake_evaluator):
    rows = [row(0, hard=False), row(0, origin="controlled", hard=True, raw=json.dumps({"code": "def f(): return 1"}))]
    run = make_run(tmp_path, rows)
    report = cli.analyze_run(run, tmp_path / "posthoc.json")
    origins = report["artifact_normalization"]["by_origin"]
    assert origins["natural"]["all"]["n_responses"] == 1
    assert origins["controlled"]["all"]["n_responses"] == 1
    assert origins["controlled"]["by_split_and_skill"]["holdout"]["generic_mutant"]["normalized_pass"] == 1


def test_guard_never_consults_hard_truth_or_hidden_task(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("oracle/extractor must not be used by strict guard")

    monkeypatch.setattr(cli, "evaluate", forbidden)
    monkeypatch.setattr(cli, "extract_artifact", forbidden)
    a = row(hard=True, judge_ok=False)
    b = row(hard=False, judge_ok=True)
    ga, gb = cli.public_guard(a), cli.public_guard(b)
    assert ga["public_guard_forced"] and gb["public_guard_forced"]
    assert ga["judgment"] == gb["judgment"] == {"decision": "fail", "schema_valid": True}
    assert ga["original_judge_ok"] is False and ga["judge_ok"] is True
    assert a["judge_ok"] is False  # No mutation.


@pytest.mark.parametrize(
    "raw,reason",
    [
        (json.dumps({"code": "def f(:"}), "python_syntax:"),
        (json.dumps({"code": "import os"}), "runtime_AST_contract:"),
        ("```python\nx=1\n```", "response_schema:"),
    ],
)
def test_guard_forces_only_declared_schema_syntax_and_ast(raw, reason):
    result = cli.public_guard(row(raw=raw))
    assert result["public_guard_forced"]
    assert result["guard_reason"].startswith(reason)


def test_guard_keeps_valid_candidate_judgment_even_if_behavior_is_wrong():
    incoming = row(raw=json.dumps({"code": "def f(): return 'wrong'"}), hard=False)
    result = cli.public_guard(incoming)
    assert not result["public_guard_forced"]
    assert result["judgment"] == incoming["judgment"]


def test_syntax_invalid_extraction_remains_a_failure_not_a_behavior_failure(monkeypatch):
    monkeypatch.setattr(
        cli,
        "evaluate",
        lambda *_: {"execution_ok": True, "hard": False, "error_category": "candidate_contract_violation"},
    )
    incoming = row(raw=json.dumps({"code": "def f(:"}))
    normalized = cli.normalize_target(incoming, cli.Task.from_dict(task()))
    assert normalized["normalized_hard"] is False
    assert normalized["normalized_failure_kind"] == "python_syntax_error"
    metrics = cli.artifact_metrics([normalized])
    assert metrics["syntax_errors"] == 1
    assert metrics["behavior_or_structural_failures"] == 0
    assert metrics["normalized_observable"] == 1


@pytest.mark.parametrize(
    "field,value", [("target_ok", 1), ("execution_ok", None), ("hard", "false"), ("repeat", True), ("request_hash", "")]
)
def test_malformed_target_status_fields_do_not_change_denominators(tmp_path, fake_evaluator, field, value):
    rows = [row()]
    rows[0][field] = value
    run = make_run(tmp_path, rows)
    with pytest.raises(ValueError):
        cli.analyze_run(run, tmp_path / "posthoc.json")


def test_guard_does_not_turn_missing_target_into_a_real_rejection():
    incoming = row(raw="", target_ok=False, execution_ok=False, hard=None, judge_ok=False)
    result = cli.public_guard(incoming)
    assert not result["public_guard_forced"]
    assert result["judge_ok"] is False


def test_guard_between_arm_comparison_retains_same_target_pairing(tmp_path, fake_evaluator):
    rows = [row(0), row(1, raw=json.dumps({"code": "def f(): return 1"}), hard=True)]
    revised = copy.deepcopy(rows)
    revised[0]["judgment"]["decision"] = "fail"
    run = make_run(tmp_path, rows, arms={"static_v0": rows, "feedback_repair": revised})
    report = cli.analyze_run(run, tmp_path / "posthoc.json")
    paired = report["strict_public_guard"]["between_arms_guarded"]["feedback_repair"]
    assert paired["n_pairs"] == 2
    assert paired["main"]["decisive_corrections"] == 0


@pytest.mark.parametrize(
    "change", ["task_manifest", "source_hash", "duplicate_target", "grouping", "holdout_response", "arm_set"]
)
def test_corrupt_or_mismatched_frozen_evidence_fails_closed(tmp_path, fake_evaluator, change):
    run = make_run(tmp_path)
    if change == "task_manifest":
        value = json.loads((run / "tasks_private.json").read_text())
        value["held-1"]["prompt"] = "changed"
        write(run / "tasks_private.json", value)
    elif change == "source_hash":
        value = json.loads((run / "protocol.json").read_text())
        value["source_hashes"][cli.FROZEN_SOURCE_REQUIREMENTS[0]] = "bad"
        write(run / "protocol.json", value)
    elif change in ("duplicate_target", "grouping"):
        value = json.loads((run / "targets_frozen_private.json").read_text())
        if change == "duplicate_target":
            value.append(value[0])
        else:
            value[0]["split"] = "train"
        write(run / "targets_frozen_private.json", value)
    elif change == "holdout_response":
        value = json.loads((run / "holdout/static_v0.json").read_text())
        value[0]["response"] = "different"
        write(run / "holdout/static_v0.json", value)
    else:
        write(run / "holdout/extra.json", [])
    with pytest.raises(ValueError):
        cli.analyze_run(run, tmp_path / "posthoc.json")
    assert not (tmp_path / "posthoc.json").exists()


def test_cli_exit_status_and_no_new_report_for_incomplete_run(tmp_path, fake_evaluator, capsys):
    assert cli.main(["--run", str(tmp_path / "missing"), "--output", str(tmp_path / "report.json")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    run = make_run(tmp_path)
    assert cli.main(["--run", str(run), "--output", str(tmp_path / "report.json")]) == 0
    assert json.loads(capsys.readouterr().out)["model_calls"] == 0


def test_existing_different_report_is_not_overwritten(tmp_path, fake_evaluator):
    run = make_run(tmp_path)
    output = tmp_path / "report.json"
    write(output, {"user_content": "preserve"})
    with pytest.raises(ValueError, match="Immutable"):
        cli.analyze_run(run, output)
    assert json.loads(output.read_text()) == {"user_content": "preserve"}
