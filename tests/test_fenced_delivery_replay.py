"""Authored closed-panel extraction/once-only execution fixtures."""
import fcntl
import hashlib
import json
from pathlib import Path

import pytest

from scripts import replay_fenced_delivery as replay
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_checkpoint, read_json, write_json
from skillopt.continual_eval.datasets import load_panel
from skillopt.continual_eval.fixtures import fixture_panel
from skillopt.validator_pilot.api import digest

PARSER = Path(__file__).resolve().parents[1] / "skillopt/continual_eval/code_delivery.py"
REPLY = "```excel\n=AVERAGE(A:A)\n```\nWrong prose from old regex\n```python\nprint('new literal')\n```"


def setup(tmp_path, *, reply=REPLY, statuses=("unknown", "unknown")):
    parent, output, source = tmp_path / "old", tmp_path / "new", Path(__file__).resolve().parents[1]
    lock = tmp_path / "native.lock"
    lock.touch()
    panel = fixture_panel("spreadsheetbench")
    panel["tasks"][0]["partition"] = "development"
    asset = tmp_path / "public.xlsx"
    asset.write_bytes(b"opaque authored public workbook")
    panel["tasks"][0]["public"]["input_files"] = [str(asset)]
    path = tmp_path / "panel.json"
    write_json(path, panel)
    panel = load_panel(path)
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 2,
        "model": {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low"},
        "panels": {b: str(path) if b == "spreadsheetbench" else None for b in BENCHMARKS},
        "runtime": {"spreadsheetbench": {}}, "project_disjoint": False, "exposure_manifest": None}
    config["model"]["transport"] = {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                                    "initial_health_policy": "completed_response_v1"}
    plan = freeze_plan(config, parent)
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    service = {"provider": "fixture", "model": "fixture"}
    write_json(parent / "model_service.json", seal(service))

    class API:
        model = "fixture"

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"system": system, "user": user, "kind": kind, "key": key, "max_tokens": max_tokens,
                       "repeat": repeat, "model": self.model, "service": service}
            row = {"request": request, "request_hash": digest(request), "ok": True, "status": 200,
                "response": reply, "finish_reason": "stop", "stream_complete": True, "returned_model": self.model,
                "http_attempt_count": 1, "usage": {"prompt_tokens": 3, "completion_tokens": 4}}
            write_json(parent / "api/calls" / (row["request_hash"] + ".json"), row)
            return row
    api = API()
    api.service = service
    for repeat in range(2):
        base, request = runner.position(parent, cp, "spreadsheetbench", panel["tasks"][0], repeat)
        runner.PositionCalls(api, base, request, 65536, 1)("public system", "public input")
    runner.generate(parent, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
        fixture_solve=lambda *a, **k: {"status": "available", "reason": "fixture", "output": {
            "code": backends._code(reply), "cases": [{"status": "unknown", "reason": "native_exception:SyntaxError"}]}})
    status_iterator = iter(statuses)
    def original_score(*a, **k):
        status = next(status_iterator)
        return {"status": status, "score": None if status == "unknown" else float(status == "pass"),
                "reason": "fixture", "metrics": {}}
    runner.score_checkpoint(parent, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
                            fixture_score=original_score)
    runner.report(parent)
    replay.prepare(parent, source, output, lock, PARSER)
    return parent, output, lock


def execute(request, runtime):
    assert request["code"] == "print('new literal')\n"
    assert set(request) == {"operation", "code", "input_base64"}
    return {"status": "available", "reason": "fixture", "output_base64": "eA==", "cleanup_confirmed": True,
            "execution_costs": {"container_calls": 1, "wall_seconds": 2.}}


def score(*args, **kwargs):
    assert kwargs["runtime"]["_score_context"]["request"]["benchmark"] == "spreadsheetbench"
    return {"status": "pass", "score": 1., "metrics": {}, "reason": "fixture", "cleanup_confirmed": True,
            "execution_costs": {"container_calls": 2, "wall_seconds": 3.}}


def test_full_audit_keeps_known_changes_but_only_old_unknown_is_executed(tmp_path):
    parent, root, _ = setup(tmp_path, statuses=("unknown", "pass"))
    before = {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    result = replay.run(root, fixture_execute=execute, fixture_score=score)
    assert result["original_positions"] == 2 and result["selected"] == result["completed"] == 1
    assert result["extraction_changes_by_original_status"] == {"unknown": 1, "pass": 1}
    assert result["native_container_calls"] == 3 and result["native_wall_seconds"] == 5.
    assert result["semantic_scores"] == {"pass": 1} and result["new_model_calls"] == 0
    assert replay.run(root, fixture_execute=lambda *a: pytest.fail("Repeated execution"), fixture_score=score) == result
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    assert "new literal" not in json.dumps(result)
    assert not result["old_scores_replaced"] and not result["whole_baseline_regraded"]


@pytest.mark.parametrize("reply", ["```python\nprint(1)\n```", "print(1)",
    "```python\nprint(1)\n```\n```python\nprint(2)\n```"])
def test_whitespace_only_same_code_or_ambiguous_never_executed(tmp_path, reply):
    _, root, _ = setup(tmp_path, reply=reply)
    result = replay.run(root, fixture_execute=lambda *a: pytest.fail("Not eligible"), fixture_score=score)
    assert result["selected"] == 0 and result["native_container_calls"] == 0
    if reply.count("```python") == 2:
        assert result["parser_outcomes"] == {"multiple_python_blocks": 2}


def test_generation_and_lo_scoring_share_native_lock(tmp_path):
    _, root, lock = setup(tmp_path)
    seen = []
    def assert_locked():
        with lock.open("rb") as handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    def locked_execute(*args):
        assert_locked()
        seen.append("generation")
        return execute(*args)
    def locked_score(*args, **kwargs):
        assert_locked()
        seen.append("score")
        return score(*args, **kwargs)
    replay.run(root, fixture_execute=locked_execute, fixture_score=locked_score)
    assert seen == ["generation", "score", "generation", "score"]


def test_interrupted_execution_does_not_repeat(tmp_path):
    _, root, _ = setup(tmp_path)
    def broken(*args):
        raise RuntimeError("authored interruption")
    with pytest.raises(RuntimeError):
        replay.run(root, fixture_execute=broken, fixture_score=score)
    with pytest.raises(ValueError, match="Open replay intent"):
        replay.run(root, fixture_execute=execute, fixture_score=score)


def test_cleanup_failure_blocks_future_generation_and_scoring(tmp_path):
    _, root, _ = setup(tmp_path)
    seen = []
    def bad(*args):
        seen.append(True)
        return {"status": "unknown", "reason": "container_cleanup_unconfirmed", "cleanup_confirmed": False,
                "execution_costs": {"container_calls": 1, "wall_seconds": 3.}}
    with pytest.raises(ValueError, match="cleanup unconfirmed"):
        replay.run(root, fixture_execute=bad, fixture_score=lambda *a, **k: pytest.fail("Scorer forbidden"))
    assert seen == [True] and replay.report(root)["status"] == "blocked"
    with pytest.raises(ValueError, match="Prior cleanup"):
        replay.run(root, fixture_execute=execute, fixture_score=score)


def test_saved_case_and_report_bindings_cannot_change(tmp_path):
    _, root, _ = setup(tmp_path)
    replay.run(root, fixture_execute=execute, fixture_score=score)
    path = next(root.glob("cases/*/*.json"))
    value = read_json(path)
    value.pop("record_hash")
    value["output_base64"] = "changed"
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="Case evidence changed"):
        replay.report(root)


def test_parent_evidence_changed_blocks_replay(tmp_path):
    parent, root, _ = setup(tmp_path)
    next(parent.glob("api/calls/*.json")).write_text("{}")
    with pytest.raises(ValueError, match="Receipt cache changed"):
        replay.run(root, fixture_execute=execute, fixture_score=score)


def test_asset_changed_while_waiting_for_native_lock_blocks_before_intent(tmp_path, monkeypatch):
    _, root, _ = setup(tmp_path)
    real_flock = replay.fcntl.flock
    changed = []

    def acquire(fd, operation):
        if operation == fcntl.LOCK_EX:
            (tmp_path / "public.xlsx").write_bytes(b"changed during shared native lock wait")
            changed.append(True)
        return real_flock(fd, operation)

    monkeypatch.setattr(replay.fcntl, "flock", acquire)
    with pytest.raises(ValueError, match="Panel changed"):
        replay.run(root, fixture_execute=lambda *a: pytest.fail("Changed asset executed"), fixture_score=score)
    assert changed == [True]
    assert not list(root.glob("intents/*.json"))


def test_exact_input_read_after_intent_is_bound_to_frozen_bytes(tmp_path, monkeypatch):
    _, root, _ = setup(tmp_path)
    original_write = replay.write_json

    def write(path, value):
        original_write(path, value)
        if path.parent.name == "intents":
            (tmp_path / "public.xlsx").write_bytes(b"changed after final snapshot")

    monkeypatch.setattr(replay, "write_json", write)
    with pytest.raises(ValueError, match="Public workbook changed before execution"):
        replay.run(root, fixture_execute=lambda *a: pytest.fail("Changed asset executed"), fixture_score=score)
    assert len(list(root.glob("intents/*.json"))) == 1
    assert not list(root.glob("cases/*/*.json"))


def test_execution_source_changed_after_intent_is_rejected(tmp_path, monkeypatch):
    _, root, _ = setup(tmp_path)
    original_write = replay.write_json

    def write(path, value):
        original_write(path, value)
        if path.parent.name == "intents":
            monkeypatch.setattr(replay.native, "source_identity", lambda: {"changed.py": "0" * 64})

    monkeypatch.setattr(replay, "write_json", write)
    with pytest.raises(ValueError, match="Frozen execution source changed"):
        replay.run(root, fixture_execute=lambda *a: pytest.fail("Changed source executed"), fixture_score=score)
    assert len(list(root.glob("intents/*.json"))) == 1
    assert not list(root.glob("cases/*/*.json"))


def test_unpinned_public_workbook_is_fixture_only(tmp_path, monkeypatch):
    asset = tmp_path / "public.xlsx"
    asset.write_bytes(b"authored fixture")
    task = {"public": {"input_files": [str(asset)]}, "private": {}}
    monkeypatch.setattr(replay, "panel_tasks", lambda *a: [task])
    expected = hashlib.sha256(asset.read_bytes()).hexdigest()
    assert replay._input_hashes({}, True) == {str(asset): expected}
    with pytest.raises(ValueError, match="Natural public workbook requires frozen asset hash"):
        replay._input_hashes({}, False)
    task["private"]["asset_sha256"] = {str(asset): expected}
    assert replay._input_hashes({}, False) == {str(asset): expected}
    task["private"]["asset_sha256"][str(asset)] = "0" * 64
    for fixture in (False, True):
        with pytest.raises(ValueError, match="Public workbook differs from frozen asset hash"):
            replay._input_hashes({}, fixture)


def test_input_read_is_bounded_before_hashing(tmp_path, monkeypatch):
    asset = tmp_path / "public.xlsx"
    asset.write_bytes(b"oversized authored fixture")
    monkeypatch.setattr(replay.backends, "MAX_WORKBOOK", 5)
    with pytest.raises(ValueError, match="Public workbook size limit"):
        replay._input_bytes({"public_input_sha256": {str(asset): "0" * 64}}, str(asset))
