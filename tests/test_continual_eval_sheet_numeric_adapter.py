"""Authored adapter controls; real Linux qualification is separately archived."""
import json
from pathlib import Path

import pytest

from scripts import replay_sheet_v6 as replay
from scripts import smoke_sheet_learning_numeric as smoke
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval import sheet_numeric_adapter as adapter
from skillopt.continual_eval import sheet_recalc as recalc
from skillopt.continual_eval import sheet_recalc_v7 as numeric
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest
from tests.test_continual_eval_sheet_recalc_adapter import setup
from tests.test_sheet_v6_replay import qualification_fixture


def qualified_fixture(tmp_path, monkeypatch):
    path, _ = qualification_fixture(tmp_path)
    old = read_json(path.parent / "protocol.json", sealed=True)
    old.pop("record_hash")
    old["engine_profile"] = "v7"
    old["engine"] = numeric.Recalculator(old["engine"]["image_id"]).identity
    old["controls"].extend({**old["controls"][0], "name": n} for n in sorted(replay.V7_CONTROLS))
    protocol = seal(old)
    (path.parent / "protocol.json").write_text(json.dumps(protocol))
    q = read_json(path, sealed=True)
    # Rebuild this authored fixture's new-profile receipts/rows separately.
    receipt_path = next((path.parent / "recalculations").glob("*.json"))
    receipt = read_json(receipt_path, sealed=True)
    receipt.pop("record_hash")
    receipt["identity"] = protocol["engine"]
    receipt = seal(receipt)
    receipt_path.write_text(json.dumps(receipt))
    request = {"input": receipt["input_sha256"], "engine": receipt["identity"]}
    receipt_path.replace(receipt_path.with_name(replay.digest(request) + ".json"))
    write_json(path.parent / "intents" / (replay.digest(request) + ".json"), seal(request))
    # Old authored intent is no longer an active fixture request.
    old_intent = next(p for p in (path.parent / "intents").glob("*.json") if p.stem != replay.digest(request))
    old_intent.unlink()
    rows = []
    for control in protocol["controls"]:
        row = seal({"protocol_hash": protocol["record_hash"], "name": control["name"], "qualified": True,
                    "receipt_hash": receipt["record_hash"], "cleanup_confirmed": True})
        (path.parent / "controls" / (control["name"] + ".json")).write_text(json.dumps(row))
        rows.append(row)
    q = seal({**{k: v for k, v in q.items() if k != "record_hash"}, "evidence_kind": "engineering_fixture",
              "engine_profile": "v7", "engine": protocol["engine"], "controls": rows,
              "protocol_hash": protocol["record_hash"]})
    # Explicit authored judgments: no claim that the fixture executes LibreOffice.
    def authored(control, receipt, target):
        return {"name": control["name"], "qualified": True, "receipt_hash": receipt["record_hash"],
                "cleanup_confirmed": True}
    monkeypatch.setattr(replay, "_control_result", authored)
    path.write_text(json.dumps(q))
    runtime = {"spreadsheet_scorer": adapter.VERSION, "recalculation": {
        "image": q["engine"]["image_id"], "timeout_seconds": q["engine"]["timeout_seconds"],
        "qualification_path": str(path), "qualification_sha256": recalc.sha(path),
        "qualification_hash": q["record_hash"]}}
    return runtime, path


def test_complete_qualification_replays_judgments_without_execution(tmp_path, monkeypatch):
    runtime, _ = qualified_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(numeric.Recalculator, "run", lambda *a: pytest.fail("Qualification replay may not run Calc"))
    engine, q = adapter.qualified_engine(runtime)
    assert engine.identity == q["engine"] and len(q["controls"]) == 23


@pytest.mark.parametrize("mutation", ["profile", "source", "missing", "judgment", "receipt", "open_intent"])
def test_stale_or_incomplete_qualification_rejected(tmp_path, monkeypatch, mutation):
    runtime, path = qualified_fixture(tmp_path, monkeypatch)
    q = read_json(path, sealed=True)
    if mutation == "profile":
        runtime["spreadsheet_scorer"] = "qualified_lo_recalc_v5_v1"
    elif mutation == "source":
        q["engine"]["sources"][next(iter(q["engine"]["sources"]))] = "0" * 64
    elif mutation == "missing":
        q["controls"].pop()
    elif mutation == "judgment":
        monkeypatch.setattr(replay, "_control_result", lambda *a: {"qualified": False})
    elif mutation == "receipt":
        q["controls"][0]["receipt_hash"] = "0" * 64
    else:
        write_json(path.parent / "intents/unclosed.json", seal({"authored_unclosed": True}))
    if mutation in {"source", "missing", "receipt"}:
        q.pop("record_hash")
        q = seal(q)
        path.write_text(json.dumps(q))
        runtime["recalculation"].update(qualification_sha256=recalc.sha(path), qualification_hash=q["record_hash"])
    with pytest.raises((ValueError, KeyError)):
        adapter.qualified_engine(runtime)


@pytest.mark.parametrize("value,status", [(5, "pass"), (6, "fail")])
def test_new_profile_dispatch_and_replay_preserve_true_false(tmp_path, monkeypatch, value, status):
    args = setup(tmp_path, monkeypatch, formula="=A1+A2" if value == 5 else "=A1+A2+1", expected=value)
    runtime = args[3]
    runtime["spreadsheet_scorer"] = adapter.VERSION
    engine = numeric.Recalculator(runtime["recalculation"]["image"])
    monkeypatch.setattr(adapter, "qualified_engine", lambda _: (engine, {"engine": engine.identity, "record_hash": "authored"}))
    # The parent setup supplies a fake v5 engine; bypass v6 proof production in
    # this dispatch-only fixture. Numeric view behavior has its own tests.
    monkeypatch.setattr(numeric.Recalculator, "run", recalc.Recalculator.run)
    result = backends.score("spreadsheetbench", *args[:3], runtime=runtime)
    assert result["status"] == status and result["metrics"]["scorer_profile"] == adapter.VERSION
    assert result["execution_costs"]["container_calls"] == 2
    assert adapter.score(*args[:3], runtime=runtime, replay_only=True) == result
    assert len(args[4]) == 2
    assert "output_base64" not in json.dumps(result) and "private-reference" not in json.dumps(result)
    bound = read_json(Path(runtime["_score_context"]["artifact_dir"]) / "result.json", sealed=True)
    assert bound["binding"]["version"] == adapter.VERSION


def test_new_profile_missing_evidence_cannot_replay_or_claim_failure(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    runtime = args[3]
    runtime["spreadsheet_scorer"] = adapter.VERSION
    engine = numeric.Recalculator(runtime["recalculation"]["image"])
    monkeypatch.setattr(adapter, "qualified_engine", lambda _: (engine, {"engine": engine.identity, "record_hash": "authored"}))
    with pytest.raises(ValueError, match="replay cannot execute"):
        adapter.score(*args[:3], runtime=runtime, replay_only=True)
    args[2]["output"]["cases"][0] = {"status": "unknown", "reason": "native_exception:AttributeError"}
    result = backends.score("spreadsheetbench", *args[:3], runtime=runtime)
    assert result["status"] == "unknown" and result["score"] is None and not args[4]


def test_single_learning_replay_uses_frozen_asset_metadata_and_new_output(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    public, private, prediction, runtime = args[:4]
    engine = numeric.Recalculator(runtime["recalculation"]["image"])
    monkeypatch.setattr(adapter, "qualified_engine", lambda _: (engine, {"engine": engine.identity, "record_hash": "authored"}))
    monkeypatch.setattr(numeric.Recalculator, "run", recalc.Recalculator.run)
    task = {"partition": "development", "public": public, "private": private}
    parent = tmp_path / "frozen-stage"
    manifest = seal({"runtime": runtime, "benchmark": "spreadsheetbench",
        "authorized_tasks": {digest(task): "selection"},
        "asset_identity": {str(p): {"status": "ready", "sha256": recalc.sha(p)}
                           for p in tmp_path.glob("*.xlsx")}})
    write_json(parent / "manifest.json", manifest)
    request = {"manifest_hash": manifest["record_hash"], "benchmark": "spreadsheetbench",
               "task_hash": digest(task), "role": "selection"}
    evaluation = parent / "learning/evaluations" / (digest(request) + ".json")
    write_json(evaluation, seal({"request": request, "prediction": prediction,
        "score": {"status": "unknown", "metrics": {"cases": [{"reason": "authored_unknown"}]}}}))
    panel = tmp_path / "panel.json"
    write_json(panel, {"tasks": [task]})
    lock = tmp_path / "native.lock"
    lock.touch()
    result = smoke.run(evaluation, panel, runtime["recalculation"]["qualification_path"], tmp_path / "new-smoke", lock)
    assert result["before"]["status"] == "unknown" and result["after"]["status"] == "pass"
    assert result["cached_replay_equal"] and result["model_api_calls"] == 0
    assert result["execution_costs"]["container_calls"] == 2 and len(args[4]) == 2
    assert read_json(evaluation)["score"]["status"] == "unknown"
    with pytest.raises(ValueError, match="New smoke output"):
        smoke.run(evaluation, panel, runtime["recalculation"]["qualification_path"], tmp_path / "new-smoke", lock)
