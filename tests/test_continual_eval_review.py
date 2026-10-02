"""Independent, offline review regressions; no paid calls or benchmark effects."""
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import cli, runner
from skillopt.continual_eval.core import freeze_plan, read_json, write_json
from skillopt.continual_eval.fixtures import fixture_config, fixture_score, fixture_solve
from skillopt.validator_pilot.api import digest


def _run(tmp_path, *, two_tasks=False):
    root = tmp_path / "review-run"
    config = fixture_config(root)
    if two_tasks:
        path = config["panels"]["searchqa"]
        panel = read_json(path)
        second = deepcopy(panel["tasks"][0])
        second["task_id"] = "searchqa/second"
        second["family_id"] = "second-family"
        second["public"]["question"] = "What color is the other square?"
        second["private"]["answers"] = ["red"]
        panel["tasks"].append(second)
        from pathlib import Path
        Path(path).write_text(json.dumps(panel), encoding="utf-8")
    freeze_plan(config, root)
    return root


def _generate(root, solve=fixture_solve):
    return runner.generate(root, method="no_skill", history="h0", stage=0,
                           benchmark="searchqa", fixture_solve=solve)


def _score(root, score=fixture_score):
    return runner.score_checkpoint(root, method="no_skill", history="h0", stage=0,
                                   benchmark="searchqa", fixture_score=score)


def test_terminal_unknown_is_scored_without_invoking_native_or_becoming_fail(tmp_path):
    root = _run(tmp_path)
    _generate(root, lambda *args, **kwargs: {"status": "unknown", "output": "", "reason": "network_unavailable"})
    _score(root, lambda *args, **kwargs: pytest.fail("An unavailable prediction must not invoke a native scorer"))
    cell = runner.report(root)["summary"]["runs"][0]["matrix"]["0"]["searchqa"]
    assert cell["counts"] == {"pass": 0, "fail": 0, "unknown": 1}
    assert cell["score_evaluable"]["value"] is None
    assert cell["score_all_attempt_lower_bound"] == 0


def test_terminal_prediction_replay_cannot_invoke_solver_again(tmp_path):
    root = _run(tmp_path)
    _generate(root)
    assert _generate(root, lambda *args, **kwargs: pytest.fail("resampled"))["new_positions"] == 0


def test_score_interruption_does_not_repeat_native_execution(tmp_path):
    root = _run(tmp_path)
    _generate(root)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        _score(root, interrupt)
    with pytest.raises(ValueError, match="Interrupted native score"):
        _score(root, lambda *args, **kwargs: pytest.fail("rescored"))


def test_score_adapter_cannot_override_host_position_identity(tmp_path):
    root = _run(tmp_path)
    _generate(root)
    def misplaced(*args, **kwargs):
        return {"status": "pass", "score": 1.0, "reason": "fixture", "metrics": {},
                "task_id": "unrelated-task"}
    with pytest.raises(ValueError):
        _score(root, misplaced)


def test_report_rejects_score_task_identity_swapped_between_valid_predictions(tmp_path):
    root = _run(tmp_path, two_tasks=True)
    _generate(root)
    _score(root)
    paths = sorted((root / "host_only" / "scores").glob("*.json"))
    scores = [read_json(path, sealed=True) for path in paths]
    identities = [{field: row[field] for field in ("task_id", "family_id")} for row in scores]
    # Model a host bookkeeping bug: valid receipt/hash, but a wrong task label.
    # Checksums authenticate bytes, not the relation to the prediction request.
    for path, row, identity in zip(paths, scores, reversed(identities)):
        row.pop("record_hash")
        row.update(identity)
        path.write_text(json.dumps(seal(row)), encoding="utf-8")
    with pytest.raises(ValueError):
        runner.report(root)


def test_nested_model_receipt_must_match_position_call_not_just_outer_wrapper(tmp_path):
    class WrongReceiptAPI:
        model = "glm-5.3"
        service = {"model": "glm-5.3", "provider": "fixture"}

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"model": self.model, "service": self.service, "system": system,
                       "user": "another task's prompt", "kind": kind, "key": key,
                       "max_tokens": max_tokens, "repeat": repeat}
            return {"request": request, "request_hash": digest(request), "ok": True,
                    "response": "somebody else's answer", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "http_attempt_count": 1}
    call = runner.PositionCalls(WrongReceiptAPI(), tmp_path, {"repeat": 0}, 100, 1)
    with pytest.raises(ValueError):
        call("system", "this task's prompt")


def test_call_accounting_rejects_unmatched_intent_and_terminal_names(tmp_path):
    write_json(tmp_path / "call_intents" / "a.json", seal({"request": "A"}))
    write_json(tmp_path / "calls" / "b.json", seal({"request": "B", "receipt": {
        "request_hash": "b", "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "http_attempt_count": 1}}))
    with pytest.raises(ValueError):
        runner._position_costs(tmp_path)


def test_cli_import_uses_requested_bigcode_variant_and_never_exposes_test(tmp_path, capsys):
    source, output = tmp_path / "source.json", tmp_path / "panel.json"
    source.write_text(json.dumps([{"task_id": "BigCodeBench/review", "instruct_prompt": "instruction",
        "complete_prompt": "completion", "entry_point": "task_func", "test": "HOST_ONLY_TEST"}]), encoding="utf-8")
    assert cli.main(["prepare", "--benchmark", "bigcodebench", "--source", str(source),
                     "--revision", "fixture-revision", "--variant", "complete", "--output", str(output)]) == 0
    panel = read_json(output)
    assert panel["tasks"][0]["public"] == {"prompt": "completion", "entry_point": "task_func"}
    assert "HOST_ONLY_TEST" not in capsys.readouterr().out
