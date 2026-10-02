"""Offline binding/no-resampling controls for the one-position sidecar."""
import base64
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import replay_fenced_with_frozen_h as cli
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json


def fixtures(tmp_path, monkeypatch):
    c, f, original, source, qroot = [tmp_path / name for name in ("c", "f", "original", "source", "q")]
    for path in (c, f, original, source, qroot):
        path.mkdir()
        (path / ".writer.lock").touch()
    lock = tmp_path / "native.lock"
    lock.touch()
    candidate, reference = tmp_path / "saved.xlsx", tmp_path / "gold.xlsx"
    cli.scoring._fixture_book(candidate, {"C4": 3})
    cli.scoring._fixture_book(reference, {"C4": 3})
    h = cli.scoring.freeze_reference(reference, cli.recalc.sha(reference), "C4:C200",
        provenance={"source_protocol_hash": "fixture", "task_id": "56786", "evidence_kind": "engineering_fixture"})
    case = seal({"status": "available", "reason": "fixture", "cleanup_confirmed": True,
                 "output_base64": base64.b64encode(candidate.read_bytes()).decode()})
    monkeypatch.setattr(cli, "CASE_HASH", case["record_hash"])
    item = {"position": cli.POSITION, "repeat": 1, "prediction_hash": "p", "score_hash": "s",
            "eligible": True, "closed_stop": True}
    fp = seal({"version": "frozen-fenced-delivery-replay-v1", "output": str(f), "parent": str(original),
               "source": str(source), "audit": [item]})
    record = seal({"identity": {"protocol_hash": fp["record_hash"], "item": item},
                   "case_record_hashes": [case["record_hash"]], "cases": [
                       {k: v for k, v in case.items() if k not in {"record_hash", "output_base64"}}],
                   "score": {"status": "unknown"}, "cleanup_unconfirmed": False, "new_model_calls": 0})
    fr = seal({"status": "completed", "cleanup_unconfirmed": False, "new_model_calls": 0,
               "protocol_hash": fp["record_hash"], "record_hashes": {cli.POSITION: record["record_hash"]}})
    class Engine:
        identity = {"version": "offline-fixture"}
        calls = 0

        def run(self, path):
            self.calls += 1
            return seal({"status": "available", "reason": "fixture", "identity": self.identity,
                         "input_sha256": cli.recalc.sha(path), "output_sha256": cli.recalc.sha(path),
                         "output_base64": base64.b64encode(path.read_bytes()).decode(),
                         "cleanup_confirmed": True, "model_api_calls": 0, "duration_seconds": 0.,
                         "container_execution_attempted": False})
    engine = Engine()
    q = seal({"status": "qualified", "engine": engine.identity})
    slot = {"id": cli.POSITION, "task_id": "56786", "repeat": 1, "reference_manifests": [cli.REFERENCE_ID],
            "references": [str(reference)], "answer_position": "C4:C200", "prediction_hash": "p", "old_score_hash": "s"}
    cp = seal({"version": cli.frozen.VERSION, "root": str(c), "slots": [slot], "original_source": str(original),
               "engine": engine.identity, "engine_qualification_hash": q["record_hash"],
               "score_qualification_hash": "fixture-score-qualified", "truth_basis": "engineering_fixture"})
    c_row = seal({"protocol_hash": cp["record_hash"], "slot_id": cli.POSITION, "status": "unknown"})
    cr = seal({"status": "complete", "completed": 160, "positions": 160, "protocol_hash": cp["record_hash"],
               "result_hashes": {cli.POSITION: c_row["record_hash"]}})
    for path, value in ((f / "protocol.json", fp), (c / "protocol.json", cp),
                        (f / "records" / (cli.POSITION + ".json"), record),
                        (f / "intents" / (cli.POSITION + ".json"), seal(record["identity"])),
                        (f / "cases" / cli.POSITION / "0.json", case),
                        (c / "host_only/references" / (cli.REFERENCE_ID + ".json"), h),
                        (c / "positions" / (cli.POSITION + ".json"), c_row),
                        (c / "reports" / (cr["record_hash"] + ".json"), cr)):
        write_json(path, value)
    monkeypatch.setattr(cli.frozen, "report", lambda root: cr)
    monkeypatch.setattr(cli, "_fenced_report", lambda *args: fr)
    monkeypatch.setattr(cli.frozen, "_engine_qualification", lambda path: (q, engine, {}))
    args = {"fenced_root": f, "fenced_script": "unused", "fenced_python": "unused", "c_root": c,
            "engine_qualification": qroot / "qualification.json", "output": tmp_path / "out", "native_lock": lock}
    return args, engine, (cp, cr, c_row, fp, fr, record, case, h)


def test_one_candidate_only_and_completed_replay_does_not_reexecute(tmp_path, monkeypatch):
    args, engine, _ = fixtures(tmp_path, monkeypatch)
    before = {str(p): p.read_bytes() for root in (args["fenced_root"], args["c_root"]) for p in root.rglob("*") if p.is_file()}
    result = cli.run(**args)
    assert result["status"] == "complete" and result["score"]["status"] == "pass"
    assert result["positions"] == 1 and result["new_model_calls"] == result["reference_engine_calls"] == 0
    assert not result["historical_scores_replaced"] and not result["is_method_effect"]
    assert engine.calls == 1
    assert cli.run(**args) == result and engine.calls == 1
    assert all(Path(path).read_bytes() == value for path, value in before.items())


@pytest.mark.parametrize("mutation", ["repeat", "reference", "prediction", "case", "cleanup", "unclosed", "manifest"])
def test_identity_or_delivery_changes_rejected_before_engine(tmp_path, monkeypatch, mutation):
    _, engine, inputs = fixtures(tmp_path, monkeypatch)
    values = deepcopy(inputs)
    cp, cr, _, _, _, record, case, h = values
    if mutation == "repeat":
        cp["slots"][0]["repeat"] = 0
    elif mutation == "reference":
        cp["slots"][0]["reference_manifests"] = ["other"]
    elif mutation == "prediction":
        record["identity"]["item"]["prediction_hash"] = "foreign"
    elif mutation == "case":
        case["record_hash"] = "foreign"
    elif mutation == "cleanup":
        case["cleanup_confirmed"] = False
    elif mutation == "unclosed":
        cr["status"] = "pending"
    else:
        h["answer_position"] = "A1"
    with pytest.raises(ValueError):
        cli._bind(*values)
    assert engine.calls == 0


def test_original_fenced_report_uses_own_source_and_preserves_python_path(tmp_path, monkeypatch):
    source, root = tmp_path / "source", tmp_path / "fenced"
    source.mkdir()
    root.mkdir()
    script = tmp_path / "fenced.py"
    script.write_text("# untouched fixture script\n")
    result = seal({"status": "completed"})
    write_json(root / "reports" / (result["record_hash"] + ".json"), result)
    calls = []
    def process(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(result))
    monkeypatch.setattr(cli.subprocess, "run", process)
    assert cli._fenced_report(root, sys.executable, script,
                             {"source": str(source), "script_sha256": cli.recalc.sha(script)}) == result
    assert calls[0][0][0] == sys.executable
    assert calls[0][1]["env"]["PYTHONPATH"] == str(source)
    assert calls[0][1]["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert calls[0][0][-3:] == ["report", "--output", str(root)]


def test_tampered_saved_candidate_blocks_replay(tmp_path, monkeypatch):
    args, engine, _ = fixtures(tmp_path, monkeypatch)
    cli.run(**args)
    (args["output"] / "candidate.xlsx").write_bytes(b"changed")
    with pytest.raises(ValueError, match="candidate bytes"):
        cli.run(**args)
    assert engine.calls == 1


def test_open_native_intent_never_reexecutes(tmp_path, monkeypatch):
    args, engine, _ = fixtures(tmp_path, monkeypatch)
    result = cli.run(**args)
    write_json(args["output"] / "intents/unclosed.json", seal({"fixture": "open"}))
    with pytest.raises(ValueError, match="Unclosed"):
        cli.run(**args)
    assert result["status"] == "complete" and engine.calls == 1
    assert read_json(args["output"] / "result.json", sealed=True) == result
