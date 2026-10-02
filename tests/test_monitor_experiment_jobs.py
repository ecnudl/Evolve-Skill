"""Observer fixtures never execute experiments or read model text into reports."""
import json
from pathlib import Path

import pytest

from scripts.monitor_experiment_jobs import VERSION, main, observe


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_pending_learning_not_completed_and_private_text_not_emitted(tmp_path):
    put(tmp_path / "result.json", {"status": "pending", "reason": "native_reflection_parse_incomplete",
                                  "candidate_skill": "PRIVATE", "record_hash": "hash"})
    put(tmp_path / "calls/one.json", {"receipt": {"ok": True, "response": "PRIVATE", "request": {"system": "SECRET"},
        "finish_reason": "stop", "http_attempt_count": 1, "usage": {"prompt_tokens": 5, "completion_tokens": 7}}})
    row = observe({"kind": "learning", "label": "learner", "root": str(tmp_path)})
    assert row["status"] == "pending"
    assert row["reported_tokens_known"] == 12
    assert row["terminal_reason"] == "native_reflection_parse_incomplete"
    assert "PRIVATE" not in json.dumps(row) and "SECRET" not in json.dumps(row)


def test_eval_uses_host_only_scores_and_preserves_unknown(tmp_path):
    put(tmp_path / "host_only/scores/a.json", {"status": "pass"})
    put(tmp_path / "host_only/scores/b.json", {"status": "unknown", "reason": "native_timeout"})
    row = observe({"kind": "eval", "label": "base", "root": str(tmp_path), "expected_positions": 2})
    assert row["status"] == "complete"
    assert row["score_counts"] == {"pass": 1, "unknown": 1}
    assert row["unknown_reasons"] == {"native_timeout": 1}
    assert not row["can_authorize_deployment"]


def test_recovery_and_observation_errors_are_not_silent(tmp_path):
    put(tmp_path / "positions/a/result.json", {"score": {"status": "fail"}})
    put(tmp_path / "positions/a/call.json", {"receipt": {"ok": True, "finish_reason": "length", "usage": {}, "http_attempt_count": 2}})
    bad = tmp_path / "positions/b/result.json"
    bad.parent.mkdir()
    bad.write_text("malformed")
    row = observe({"kind": "recovery", "label": "diagnostic", "root": str(tmp_path), "expected_positions": 2})
    assert row["status"] == "incomplete"
    assert row["observation_errors"] == {"JSONDecodeError": 1}
    assert row["missing_usage_calls"] == 1


@pytest.mark.parametrize("kind,prefix", [("full_delivery_recovery", "positions/a"),
                                       ("single_delivery_recovery", "")])
def test_new_delivery_layouts_preserve_inflight_and_close_without_api_double_count(tmp_path, kind, prefix):
    base = tmp_path / prefix
    put(base / "intent.json", {"system": "SECRET"})
    target = {"kind": kind, "label": "recovery", "root": str(tmp_path), "expected_positions": 1}
    pending = observe(target)
    assert pending["unclosed_calls"] == 1 and pending["closed_calls"] == 0
    assert pending["status"] == "incomplete" and not pending["usage_complete"]
    receipt = {"receipt": {"ok": True, "response": "PRIVATE", "http_attempt_count": 1,
        "finish_reason": "stop", "usage": {"prompt_tokens": 7, "completion_tokens": 9}}}
    put(base / "call.json", receipt)
    put(tmp_path / "api/calls/cache.json", receipt["receipt"])
    put(base / "result.json", {"prediction": {"output": "PRIVATE"}, "score": {"status": "unknown", "reason": "native_timeout"}})
    closed = observe(target)
    assert closed["status"] == "complete" and closed["closed_calls"] == closed["call_intents"] == 1
    assert closed["unclosed_calls"] == closed["receipts_without_intents"] == 0
    assert closed["reported_tokens_known"] == 16 and closed["score_counts"] == {"unknown": 1}
    assert "PRIVATE" not in json.dumps(closed) and "SECRET" not in json.dumps(closed)


def test_unknown_unstarted_is_not_failure(tmp_path):
    row = observe({"kind": "learning", "label": "gepa", "root": str(tmp_path / "absent")})
    assert row["status"] == "not_started" and row["score_counts"] == {}


def test_monitor_cannot_write_inside_or_over_experiment(tmp_path):
    experiment = tmp_path / "experiment"
    config = tmp_path / "config.json"
    put(config, [{"kind": "eval", "root": str(experiment), "label": "base"}])
    for output in (experiment, experiment / "monitor", tmp_path):
        with pytest.raises(SystemExit):
            main(["--config", str(config), "--output", str(output), "--once"])


def test_once_writes_only_monitor_area(tmp_path):
    config = tmp_path / "config.json"
    experiment = tmp_path / "experiment"
    put(config, [{"kind": "learning", "root": str(experiment), "label": "base"}])
    output = tmp_path / "monitor"
    assert main(["--config", str(config), "--output", str(output), "--once"]) == 0
    assert not experiment.exists()
    row = json.loads((output / "latest.json").read_text())
    assert row["actions_taken"] == [] and row["model_calls"] == 0
    assert len((output / "observations.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("kind", ["shell", "unknown"])
def test_no_action_target_kind(tmp_path, kind):
    with pytest.raises(ValueError):
        observe({"kind": kind, "label": "bad", "root": str(tmp_path)})


def test_eval_uses_position_receipts_and_retains_unclosed_calls(tmp_path):
    put(tmp_path / "predictions/a/call_intents/one.json", {"user": "SECRET"})
    put(tmp_path / "predictions/b/call_intents/two.json", {"user": "SECRET"})
    put(tmp_path / "predictions/a/calls/one.json", {"receipt": {"ok": True, "response": "PRIVATE", "finish_reason": "stop",
        "http_attempt_count": 1, "usage": {"prompt_tokens": 5, "completion_tokens": 7}}})
    # The API cache is not a second logical call and is not counted again.
    put(tmp_path / "api/calls/one.json", {"usage": {"prompt_tokens": 5, "completion_tokens": 7}})
    row = observe({"kind": "eval", "label": "base", "root": str(tmp_path)})
    assert row["closed_calls"] == 1 and row["unclosed_calls"] == 1
    assert row["reported_tokens_known"] == 12 and not row["usage_complete"]
    assert not row["retry_inclusive_usage_known"]
    assert "PRIVATE" not in json.dumps(row) and "SECRET" not in json.dumps(row)


def test_malformed_nested_records_do_not_crash_or_claim_completion(tmp_path):
    put(tmp_path / "positions/a/result.json", {"score": {"status": ["pass"]}})
    put(tmp_path / "positions/a/call.json", {"receipt": {"usage": []}})
    row = observe({"kind": "recovery", "label": "base", "root": str(tmp_path), "expected_positions": 1})
    assert row["status"] == "incomplete"
    assert row["observation_errors"] == {"invalid_score_record": 1, "invalid_call_record": 1}
    assert not row["usage_complete"]


def test_unrecognized_reason_and_bad_hash_never_exported(tmp_path):
    put(tmp_path / "result.json", {"status": "pending", "reason": "sk-secret", "record_hash": {"secret": "PRIVATE"}})
    row = observe({"kind": "learning", "label": "base", "root": str(tmp_path)})
    assert row["status"] == "pending" and row["terminal_reason"] == "not_exported"
    assert row["terminal_hash"] is None
    assert "sk-secret" not in json.dumps(row) and "PRIVATE" not in json.dumps(row)


@pytest.mark.parametrize("linked_name", ["observer.lock", "observations.jsonl"])
@pytest.mark.parametrize("hardlink", [False, True])
def test_existing_output_links_cannot_modify_experiment(tmp_path, linked_name, hardlink):
    experiment = tmp_path / "experiment"
    protected = experiment / "receipt.json"
    put(protected, {"preserve": True})
    previous = protected.read_bytes()
    config = tmp_path / "config.json"
    put(config, [{"kind": "learning", "root": str(experiment), "label": "base"}])
    output = tmp_path / "monitor"
    output.mkdir()
    link = output / linked_name
    if hardlink:
        link.hardlink_to(protected)
    else:
        link.symlink_to(protected)
    with pytest.raises((OSError, ValueError)):
        main(["--config", str(config), "--output", str(output), "--once"])
    assert protected.read_bytes() == previous


def test_symlinked_evidence_parent_cannot_escape_experiment(tmp_path):
    experiment = tmp_path / "experiment"
    experiment.mkdir()
    private = tmp_path / "private"
    put(private / "one.json", {"receipt": {"finish_reason": "stop", "usage": {}}})
    (experiment / "calls").symlink_to(private, target_is_directory=True)
    row = observe({"kind": "learning", "label": "base", "root": str(experiment)})
    assert row["closed_calls"] == 0
    assert row["observation_errors"] == {"ValueError": 1}


def test_orphan_receipt_cannot_cancel_unclosed_intent(tmp_path):
    put(tmp_path / "call_intents/a.json", {})
    put(tmp_path / "calls/b.json", {"receipt": {"ok": True, "http_attempt_count": 1, "finish_reason": "stop", "usage": {}}})
    row = observe({"kind": "learning", "label": "base", "root": str(tmp_path)})
    assert row["unclosed_calls"] == row["receipts_without_intents"] == 1
    assert not row["usage_complete"]


@pytest.mark.parametrize("missing", ["ok", "http_attempt_count"])
def test_incomplete_receipt_cannot_close_intent_or_complete_panel(tmp_path, missing):
    put(tmp_path / "predictions/a/call_intents/one.json", {})
    put(tmp_path / "host_only/scores/a.json", {"status": "pass"})
    receipt = {"ok": True, "http_attempt_count": 1, "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
    del receipt[missing]
    put(tmp_path / "predictions/a/calls/one.json", {"receipt": receipt})
    row = observe({"kind": "eval", "label": "base", "root": str(tmp_path), "expected_positions": 1})
    assert row["status"] == "incomplete" and row["unclosed_calls"] == 1
    assert row["closed_calls"] == 0 and not row["usage_complete"]
    assert row["observation_errors"] == {"invalid_call_record": 1}


def test_valid_temporary_records_and_intents_do_not_double_count(tmp_path):
    receipt = {"receipt": {"ok": True, "finish_reason": "stop", "http_attempt_count": 1,
                           "usage": {"prompt_tokens": 5, "completion_tokens": 7}}}
    put(tmp_path / "predictions/a/call_intents/one.json", {})
    put(tmp_path / "predictions/a/calls/one.json", receipt)
    put(tmp_path / "host_only/scores/a.json", {"status": "pass"})
    # A live hardlink name is a realistic duplicate created during publication.
    (tmp_path / "predictions/a/calls/.pending-copy.json").hardlink_to(tmp_path / "predictions/a/calls/one.json")
    put(tmp_path / "predictions/a/call_intents/.pending-copy.json", {})
    put(tmp_path / "host_only/scores/.pending-copy.json", {"status": "pass"})
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    row = observe({"kind": "eval", "label": "base", "root": str(tmp_path), "expected_positions": 1})
    assert row["status"] == "complete" and row["closed_calls"] == row["call_intents"] == row["scored_positions"] == 1
    assert row["reported_tokens_known"] == 12 and row["unclosed_calls"] == row["receipts_without_intents"] == 0
    assert row["observation_errors"] == {} and row["usage_complete"]
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}


@pytest.mark.parametrize("pattern", ["predictions/*/calls/*.json", "predictions/*/call_intents/*.json",
                                    "host_only/scores/*.json"])
def test_temporary_file_vanishing_after_glob_is_not_missing_evidence(tmp_path, monkeypatch, pattern):
    folders = {"predictions/*/calls/*.json": "predictions/a/calls",
               "predictions/*/call_intents/*.json": "predictions/a/call_intents",
               "host_only/scores/*.json": "host_only/scores"}
    temporary = tmp_path / folders[pattern] / ".pending-vanishes.json"
    put(temporary, {"private": "not a published artifact"})
    original = Path.glob

    def glob(path, selected):
        values = list(original(path, selected))
        if path == tmp_path and selected == pattern:
            temporary.unlink()
        yield from values

    monkeypatch.setattr(Path, "glob", glob)
    row = observe({"kind": "eval", "label": "base", "root": str(tmp_path)})
    assert row["closed_calls"] == row["call_intents"] == row["scored_positions"] == 0
    assert row["observation_errors"] == {} and row["unclosed_calls"] == row["receipts_without_intents"] == 0
    assert "not a published artifact" not in json.dumps(row)


def test_new_monitor_version_keeps_old_log_semantics_separate(tmp_path):
    config = tmp_path / "config.json"
    put(config, [{"kind": "learning", "root": str(tmp_path / "experiment"), "label": "base"}])
    main(["--config", str(config), "--output", str(tmp_path / "observer-v4"), "--once"])
    assert VERSION == "experiment-observer-v4"
    assert json.loads((tmp_path / "observer-v4/latest.json").read_text())["version"] == VERSION
