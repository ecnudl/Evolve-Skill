"""Offline fixture replay controls, never evidence of real benchmark gains."""
import base64
import json
from pathlib import Path

import openpyxl
import pytest

from scripts import replay_sheet_frozen_gold as replay
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json


def workbook(path, value):
    book = openpyxl.Workbook()
    book.active.title = "S"
    book.active["B1"] = value
    book.save(path)
    book.close()
    return path


class FixtureEngine:
    calls = []
    def __init__(self, image="sha256:" + "a" * 64, timeout=120):
        self.identity = {"image_id": image, "timeout_seconds": timeout, "version": "engineering-fixture"}

    def run(self, path):
        assert path.name.endswith(".xlsx") and "frozen-gold-prediction-" in str(path)
        self.calls.append(replay.recalc.sha(path))
        return seal({"input_sha256": replay.recalc.sha(path), "identity": self.identity,
            "status": "available", "reason": "fixture", "output_sha256": replay.recalc.sha(path),
            "output_base64": base64.b64encode(path.read_bytes()).decode(),
            "cleanup_confirmed": True, "model_api_calls": 0, "container_execution_attempted": False,
            "duration_seconds": 0})


def mini_panel(tmp_path, monkeypatch):
    FixtureEngine.calls = []
    monkeypatch.setattr(replay.replay.v8, "Recalculator", FixtureEngine)
    root, previous, original = (tmp_path / x for x in ("replay", "previous", "original"))
    for path in (root, previous, original):
        path.mkdir()
        (path / ".writer.lock").touch()
    lock = tmp_path / "native.lock"
    lock.touch()
    reference = workbook(tmp_path / "reference.xlsx", 2)
    prediction = workbook(tmp_path / "candidate.xlsx", 3)
    slots, inventory = [], replay.replay._files([reference])
    for index, condition in enumerate(("correct", "wrong", "truncated", "disputed")):
        key = str(index)
        content = (reference if condition == "correct" else prediction).read_bytes()
        available = {"status": "available", "output": {"cases": [
            {"status": "available", "output_base64": base64.b64encode(content).decode()}]}}
        record = seal({"prediction": {"status": "unknown", "reason": "model_response_truncated"}
                       if condition == "truncated" else available})
        predpath = original / (key + ".json")
        write_json(predpath, record)
        h = replay.scoring.freeze_reference(reference, replay.recalc.sha(reference), "S!B1",
            provenance={"source_protocol_hash": "fixture", "task_id": key, "evidence_kind": "engineering_fixture"},
            dispute=condition == "disputed")
        hpath = root / "host_only/references" / (key + ".json")
        write_json(hpath, h)
        inventory.update(replay.replay._files([predpath, hpath]))
        slots.append({"id": key, "prediction_path": str(predpath), "prediction_hash": record["record_hash"],
            "old_status": "unknown", "previous_status": "unknown", "references": [str(reference)],
            "reference_manifests": [key], "answer_position": "S!B1"})
    protocol = seal({"version": replay.VERSION, "kind": "replay", "root": str(root),
        "sources": replay._sources(), "inventory": inventory, "engine": FixtureEngine().identity,
        "native_lock": str(lock), "previous_replay": str(previous), "original_source": str(original),
        "slots": slots, "truth_basis": "frozen_benchmark_label_not_independent_oracle"})
    write_json(root / "protocol.json", protocol)
    return root, protocol


def test_candidate_only_replay_preserves_unknown_and_is_idempotent(tmp_path, monkeypatch):
    root, protocol = mini_panel(tmp_path, monkeypatch)
    result = replay.run(root)
    assert result["status"] == "complete" and result["positions"] == 4
    assert result["counts"] == {"pass": 1, "fail": 1, "unknown": 2}
    assert result["delivery_evaluation_axes"] == {"delivered->pass": 1, "delivered->fail": 1,
                                                "undelivered->unknown": 1, "delivered->unknown": 1}
    assert result["reference_engine_calls"] == result["model_api_calls"] == 0
    assert len(FixtureEngine.calls) == 2
    assert replay.run(root) == result and len(FixtureEngine.calls) == 2
    assert read_json(root / "protocol.json", sealed=True) == protocol


def test_replay_pause_retains_all_slots_then_resumes_without_reexecution(tmp_path, monkeypatch):
    root, _ = mini_panel(tmp_path, monkeypatch)
    (root / "PAUSE").touch()
    result = replay.run(root)
    assert result["status"] == "pending" and result["positions"] == 4 and result["completed"] == 0
    assert not FixtureEngine.calls
    (root / "PAUSE").unlink()
    assert replay.run(root)["completed"] == 4 and len(FixtureEngine.calls) == 2


@pytest.mark.parametrize("damage", ["reference", "manifest", "source_identity", "published_result"])
def test_frozen_evidence_or_published_result_cannot_change(tmp_path, monkeypatch, damage):
    root, protocol = mini_panel(tmp_path, monkeypatch)
    if damage == "reference":
        Path(protocol["slots"][0]["references"][0]).write_bytes(b"fixture corruption")
    elif damage == "manifest":
        (root / "host_only/references/0.json").write_text("{}")
    elif damage == "source_identity":
        protocol.pop("record_hash")
        protocol["sources"] = {}
        (root / "protocol.json").write_text(json.dumps(seal(protocol)))
    else:
        replay.run(root)
        record = read_json(root / "positions/0.json", sealed=True)
        record.pop("record_hash")
        record["status"] = "fail"
        (root / "positions/0.json").write_text(json.dumps(seal(record)))
    with pytest.raises(ValueError, match="changed"):
        replay.run(root)


def test_open_intent_never_silently_reruns_a_workbook(tmp_path, monkeypatch):
    root, protocol = mini_panel(tmp_path, monkeypatch)
    intent = seal({"input": "a" * 64, "engine": protocol["engine"]})
    key = replay.digest({k: v for k, v in intent.items() if k != "record_hash"})
    write_json(root / "intents" / (key + ".json"), intent)
    with pytest.raises(ValueError, match="Unclosed"):
        replay.run(root)
    assert not FixtureEngine.calls


def test_missing_score_qualification_blocks_preparation(tmp_path, monkeypatch):
    path = tmp_path / "qualification.json"
    write_json(path, seal({"status": "rejected"}))
    with pytest.raises(ValueError, match="Independent scoring qualification"):
        replay._score_qualification(path, FixtureEngine())


def test_incomplete_historical_panel_is_not_promoted(tmp_path, monkeypatch):
    previous = tmp_path / "previous"
    previous.mkdir()
    protocol = seal({"version": replay.replay.VERSION, "kind": "replay", "root": str(previous),
        "engine_profile": "v8", "engine": {"version": replay.replay.v8.VERSION, "sources": {}},
        "script_sha256": replay.recalc.sha(replay.replay.__file__), "inventory": {}, "slots": []})
    write_json(previous / "protocol.json", protocol)
    with pytest.raises(ValueError, match="160-position"):
        replay._previous(previous)


def test_cli_prepare_requires_both_independent_qualifications(tmp_path):
    with pytest.raises(ValueError, match="Preparation arguments"):
        replay.main(["prepare", "--output", str(tmp_path / "new")])


@pytest.mark.parametrize("corrupt", [False, True])
def test_prepare_freezes_h_and_quarantines_prior_reference_dispute(tmp_path, monkeypatch, corrupt):
    previous, original = tmp_path / "previous", tmp_path / "original"
    for path in (previous, original):
        path.mkdir()
        (path / ".writer.lock").touch()
    reference = workbook(tmp_path / "reference.xlsx", 2)
    inventory = replay.replay._files([reference])
    slots = [{"id": str(index), "task_id": "task", "repeat": index, "old_status": "unknown",
              "references": [str(reference)], "answer_position": "S!B1"} for index in range(2)]
    prior = seal({"source": str(original), "inventory": inventory, "slots": slots, "engine": {"sources": {}}})
    rows = {s["id"]: seal({"status": "unknown", "cases": [
        {"reason": "reference_native_cache_drift_or_unavailable"}]}) for s in slots}
    monkeypatch.setattr(replay, "_previous", lambda path: (prior, rows))
    monkeypatch.setattr(replay, "_engine_qualification", lambda path:
                        (seal({"status": "qualified"}), FixtureEngine(), {}))
    monkeypatch.setattr(replay, "_score_qualification", lambda *args:
                        (seal({"status": "qualified"}), {}))
    lock = tmp_path / "native.lock"
    lock.touch()
    output = tmp_path / "new"
    if corrupt:
        reference.write_bytes(b"fixture changed")
        with pytest.raises(ValueError, match="reference inventory changed"):
            replay.prepare(previous, tmp_path / "eq/q.json", tmp_path / "sq/q.json", output, lock)
        assert not output.exists()
        return
    result = replay.prepare(previous, tmp_path / "eq/q.json", tmp_path / "sq/q.json", output, lock)
    assert result["reference_manifests"] == result["disputed_references"] == 1
    protocol = read_json(output / "protocol.json", sealed=True)
    assert len(protocol["slots"]) == 2
    assert protocol["slots"][0]["reference_manifests"] == protocol["slots"][1]["reference_manifests"]
    manifests = list((output / "host_only/references").glob("*.json"))
    h = read_json(manifests[0], sealed=True)
    assert h["known_reference_dispute"] and h["status"] == "unknown" and not h["reference_recalculated"]
