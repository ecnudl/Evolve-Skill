"""Authored real-schema fixtures only; no provider, Docker or task gold scoring."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import diagnose_kor_deliverables as diagnostic
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_checkpoint, read_json, write_json
from skillopt.continual_eval.fixtures import fixture_panel
from skillopt.validator_pilot.api import digest


def setup(tmp_path, *, text="[[PRIVATE_RAW_REPLY]] trailing unchanged", second_finish="network_error"):
    (tmp_path / "native.lock").touch()
    parent = tmp_path / "old"
    panel = fixture_panel("korbench")
    panel["tasks"][0]["partition"] = "development"
    panel["tasks"][0]["private"]["answer"] = "PRIVATE_GOLD_SENTINEL"
    path = tmp_path / "panel.json"
    write_json(path, panel)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                           "initial_health_policy": "completed_response_v1"}}
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 2, "model": model,
        "panels": {b: str(path) if b == "korbench" else None for b in BENCHMARKS},
        "runtime": {"korbench": {}}, "project_disjoint": False, "exposure_manifest": None}
    plan = freeze_plan(config, parent)
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    service = {"provider": "fixture", "model": "fixture"}
    write_json(parent / "model_service.json", seal(service))

    class API:
        model = "fixture"

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"system": system, "user": user, "kind": kind, "key": key,
                "max_tokens": max_tokens, "repeat": repeat, "model": self.model, "service": self.service}
            finish = "length" if repeat == 0 else second_finish
            value = {"request": request, "request_hash": digest(request), "ok": False, "status": 200,
                "response": text if finish == "length" else "", "finish_reason": finish,
                "stream_complete": True, "returned_model": self.model, "http_attempt_count": 1,
                "usage": {"prompt_tokens": 3, "completion_tokens": 65536}}
            write_json(parent / "api/calls" / (value["request_hash"] + ".json"), value)
            return value

    api = API()
    api.service = service
    for repeat in range(2):
        base, request = runner.position(parent, cp, "korbench", panel["tasks"][0], repeat)
        runner.PositionCalls(api, base, request, 65536, 1)("public-system", "public-input")
    index = iter(range(2))

    def solve(*args, **kwargs):
        repeat = next(index)
        finish = "length" if repeat == 0 else second_finish
        return {"status": "unknown", "output": None,
                "reason": "model_response_truncated" if finish == "length" else "model_call_unavailable"}

    runner.generate(parent, method="no_skill", history="h0", stage=0, benchmark="korbench", fixture_solve=solve)
    runner.score_checkpoint(parent, method="no_skill", history="h0", stage=0, benchmark="korbench",
                            fixture_score=lambda *a, **k: pytest.fail("Original unavailable response must stay unknown"))
    runner.report(parent)
    return parent, Path(__file__).resolve().parents[1], tmp_path / "new", text


def test_prepare_binds_all_length_and_never_reads_gold_or_executes(tmp_path, monkeypatch):
    parent, source, output, raw = setup(tmp_path, second_finish="length")
    original = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    monkeypatch.setattr(diagnostic, "load_panel", lambda *a: pytest.fail("Prepare cannot inspect gold"))
    monkeypatch.setattr(diagnostic.backends, "score", lambda *a, **k: pytest.fail("No scorer in prepare"))
    value = diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    assert len(value["snapshot"]["selected"]) == 2
    assert all(r["eligible"] for r in value["snapshot"]["selected"])
    assert value["new_model_calls"] == 0 and value["diagnostic_only"]
    assert "PRIVATE_RAW_REPLY" not in json.dumps(value) and "PRIVATE_GOLD_SENTINEL" not in json.dumps(value)
    assert value["snapshot"]["selected"][0]["raw_response_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert diagnostic.check(output) == value
    assert original == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}


def test_execute_whole_unchanged_reply_once_and_preserve_old_unknown(tmp_path):
    parent, source, output, raw = setup(tmp_path)
    value = diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    seen = []

    def score(benchmark, public, private, prediction, *, runtime):
        seen.append(prediction["output"])
        return {"status": "fail", "score": 0.0, "metrics": {}, "reason": "authored_fixture"}

    result = diagnostic.run(output, tmp_path / "native.lock", fixture_score=score)
    assert result["counts"] == {"fail": 1} and seen == [raw]
    assert value["snapshot"]["excluded_finish_reasons"] == {"network_error": 1}
    assert diagnostic.run(output, tmp_path / "native.lock", fixture_score=score) == result
    assert seen == [raw] and result["new_model_calls"] == 0 and not result["deployment_authorized"]
    assert all(read_json(p)["status"] == "unknown" for p in (parent / "host_only/scores").glob("*.json"))


@pytest.mark.parametrize("raw", ["unfinished [[value", "plain text", "[[   ]]", "x" * 262145 + "[[value]]"])
def test_no_complete_supported_wrapper_stays_unknown_without_native_call(tmp_path, raw):
    parent, source, output, _ = setup(tmp_path, text=raw)
    diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    result = diagnostic.run(output, tmp_path / "native.lock", fixture_score=lambda *a, **k: pytest.fail("Ineligible"))
    assert result["counts"] == {"unknown": 1}


@pytest.mark.parametrize("mutation", ["cache", "receipt", "score", "report", "source", "open_call"])
def test_changed_or_incomplete_old_evidence_rejected_before_new_output(tmp_path, mutation):
    parent, source, output, _ = setup(tmp_path)
    if mutation == "source":
        source = tmp_path / "not-the-frozen-source"
    elif mutation == "open_call":
        write_json(next((parent / "predictions").iterdir()) / "call_intents/extra.json", seal({"test": True}))
    else:
        glob = {"cache": "api/calls/*.json", "receipt": "predictions/*/calls/*.json",
                "score": "host_only/scores/*.json", "report": "host_only/reports/*.json"}[mutation]
        next(parent.glob(glob)).write_text("{}")
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    assert not output.exists()


def test_parent_output_overlap_and_post_prepare_changes_blocked(tmp_path):
    parent, source, output, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="independent"):
        diagnostic.prepare(parent, source, parent / "bad", tmp_path / "native.lock")
    diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    next(parent.glob("api/calls/*.json")).write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        diagnostic.check(output)


def test_unclosed_diagnostic_is_not_retried(tmp_path):
    parent, source, output, _ = setup(tmp_path)
    value = diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    item = value["snapshot"]["selected"][0]
    write_json(output / "intents" / (item["position"] + ".json"), seal({"protocol_hash": value["record_hash"], "item": item}))
    with pytest.raises(ValueError, match="do not retry"):
        diagnostic.run(output, tmp_path / "native.lock", fixture_score=lambda *a, **k: pytest.fail("Retry"))


def test_published_unknown_cannot_be_resealed_as_pass(tmp_path):
    parent, source, output, _ = setup(tmp_path)
    diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    def scorer(*args, **kwargs):
        return {"status": "unknown", "score": None, "reason": "fixture", "metrics": {}}
    diagnostic.run(output, tmp_path / "native.lock", fixture_score=scorer)
    path = next((output / "records").glob("*.json"))
    row = read_json(path, sealed=True)
    row.pop("record_hash")
    row["result"].update(status="pass", score=1.0)
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="Published diagnostic record changed"):
        diagnostic.run(output, tmp_path / "native.lock", fixture_score=scorer)


def test_native_lock_typo_does_not_create_new_unshared_lock(tmp_path):
    parent, source, output, _ = setup(tmp_path)
    diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    lock = tmp_path / "typo.lock"
    with pytest.raises(ValueError, match="Existing external shared"):
        diagnostic.run(output, lock, fixture_score=lambda *a, **k: pytest.fail("Execution"))
    assert not lock.exists()


def test_natural_protocol_cannot_use_tiny_fixture_or_fixture_dispatch(tmp_path):
    parent, source, output, _ = setup(tmp_path)
    value = read_json(parent / "plan.json", sealed=True)
    value.pop("record_hash")
    value["config"]["model"]["provider"] = "bigmodel"
    (parent / "plan.json").write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="500-task"):
        diagnostic.prepare(parent, source, output, tmp_path / "native.lock")


def test_existing_but_wrong_native_lock_rejected(tmp_path):
    parent, source, output, _ = setup(tmp_path)
    diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    wrong = tmp_path / "unrelated.lock"
    wrong.touch()
    with pytest.raises(ValueError, match="Existing external shared"):
        diagnostic.run(output, wrong, fixture_score=lambda *a, **k: pytest.fail("Wrong lock"))


def test_active_original_writer_blocks_prepare_readonly(tmp_path):
    from skillopt.continual_eval.core import output_lock
    parent, source, output, _ = setup(tmp_path)
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        diagnostic.prepare(parent, source, output, tmp_path / "native.lock")
    assert not output.exists()
