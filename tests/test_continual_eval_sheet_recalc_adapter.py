"""Offline authored qualification/execution controls, not real LO/effect data."""
import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, runner
from skillopt.continual_eval import sheet_recalc as recalc
from skillopt.continual_eval import sheet_recalc_adapter as adapter
from skillopt.continual_eval import spreadsheet_compat as compat
from skillopt.continual_eval.core import freeze_plan, read_json, write_json
from skillopt.continual_eval.fixtures import fixture_config
from skillopt.validator_pilot.api import digest
from tests.test_continual_eval_sheet_recalc import workbook

IMAGE = "sha256:" + "a" * 64


def setup(tmp_path, monkeypatch, *, formula="=A1+A2", expected=5):
    gold = workbook(tmp_path / "private-reference.xlsx", cache=5)
    pred = workbook(tmp_path / "prediction.xlsx", formula)
    converted = workbook(tmp_path / "converted.xlsx", formula, cache=expected)
    mapping = {recalc.sha(gold): gold, recalc.sha(pred): converted}
    calls = []

    def execute(self, path):
        key = recalc.sha(path)
        calls.append(key)
        raw = mapping[key].read_bytes()
        return seal({"status": "available", "reason": "authored_fixture", "identity": self.identity,
            "input_sha256": key, "output_sha256": hashlib.sha256(raw).hexdigest(),
            "output_base64": base64.b64encode(raw).decode(), "cleanup_confirmed": True,
            "model_api_calls": 0, "container_execution_attempted": True, "duration_seconds": 0.25})

    monkeypatch.setattr(recalc.Recalculator, "run", execute)
    engine = recalc.Recalculator(IMAGE)
    folder = tmp_path / "qualification-fixture"
    controls = []
    for name in sorted(adapter.CONTROLS):
        receipt = seal({"identity": engine.identity, "cleanup_confirmed": True, "model_api_calls": 0,
                        "fixture_control": name})
        write_json(folder / "receipts" / (name + ".json"), receipt)
        controls.append({"name": name, "qualified": True, "cleanup_confirmed": True, "receipt_hash": receipt["record_hash"]})
    q = seal({"version": recalc.VERSION, "status": "qualified", "engine": engine.identity,
              "controls": controls, "model_api_calls": 0, "evidence_kind": "engineering_fixture"})
    path = folder / "qualification.json"
    write_json(path, q)
    runtime = {"spreadsheet_scorer": adapter.VERSION, "image": "sha256:" + "b" * 64,
        "recalculation": {"image": IMAGE, "timeout_seconds": 120, "qualification_path": str(path),
                          "qualification_hash": q["record_hash"], "qualification_sha256": recalc.sha(path)}}
    request = {"plan_hash": "plan", "checkpoint_hash": "cp", "benchmark": "spreadsheetbench",
               "task_hash": "task", "repeat": 0}
    key = digest(request)
    runtime["_score_context"] = {"artifact_dir": str(tmp_path / "run/host_only/scorer_artifacts" / key),
        "request": request, "position": key, "prediction_hash": "f" * 64}
    public = {"answer_position": "B1", "instruction": "Preserve values", "input_files": [str(pred)]}
    private = {"answer_position": "B1", "test_files": [str(gold)], "asset_sha256": {str(gold): recalc.sha(gold)}}
    prediction = {"status": "available", "output": {"code": "AUTHORED_UNEXECUTED_CODE",
        "cases": [{"status": "available", "output_base64": base64.b64encode(pred.read_bytes()).decode()}]}}
    return public, private, prediction, runtime, calls, mapping


def _score(args):
    public, private, prediction, runtime = args[:4]
    return backends.score("spreadsheetbench", public, private, prediction, runtime=runtime)


@pytest.mark.parametrize("formula,value,status", [("=A1+A2", 5, "pass"), ("=A1+A2+1", 6, "fail")])
def test_backend_recalculates_both_inputs_replays_without_new_calls(tmp_path, monkeypatch, formula, value, status):
    args = setup(tmp_path, monkeypatch, formula=formula, expected=value)
    originals = {str(p): p.read_bytes() for p in tmp_path.glob("*.xlsx")}
    result = _score(args)
    assert result["status"] == status and result["score"] == float(status == "pass")
    assert result["metrics"]["model_api_calls"] == 0 and result["execution_costs"]["container_calls"] == 2
    assert result["runtime_image_id"] == IMAGE and len(args[4]) == 2
    assert _score(args) == result and len(args[4]) == 2
    assert originals == {str(p): p.read_bytes() for p in tmp_path.glob("*.xlsx")}
    root = Path(args[3]["_score_context"]["artifact_dir"])
    assert (root / "result.json").exists() and len(list((root / "recalculations").glob("*.json"))) == 2
    assert "output_base64" not in json.dumps(result) and "private-reference.xlsx" not in json.dumps(result)
    assert not (tmp_path / "run/predictions").exists()


@pytest.mark.parametrize("mutation", ["hash", "image", "source", "version", "missing_control", "rejected_control", "receipt", "cleanup"])
def test_qualification_mismatch_blocks_before_execution(tmp_path, monkeypatch, mutation):
    args = setup(tmp_path, monkeypatch)
    runtime = args[3]
    spec = runtime["recalculation"]
    path = Path(spec["qualification_path"])
    q = read_json(path, sealed=True)
    q.pop("record_hash")
    if mutation == "hash":
        spec["qualification_sha256"] = "0" * 64
    elif mutation == "image":
        spec["image"] = "sha256:" + "c" * 64
    elif mutation == "source":
        q["engine"]["sources"][next(iter(q["engine"]["sources"]))] = "0" * 64
    elif mutation == "version":
        q["version"] = "unreviewed_version"
    elif mutation == "missing_control":
        q["controls"].pop()
    elif mutation == "rejected_control":
        q["controls"][0]["qualified"] = False
    elif mutation == "receipt":
        q["controls"][0]["receipt_hash"] = "0" * 64
    else:
        q["controls"][0]["cleanup_confirmed"] = False
    if mutation not in {"hash", "image"}:
        q = seal(q)
        path.write_text(json.dumps(q))
        spec.update(qualification_sha256=recalc.sha(path), qualification_hash=q["record_hash"])
    assert _score(args)["status"] == "unknown" and args[4] == []


@pytest.mark.parametrize("change", ["reference", "position", "outside", "wrong_prediction", "cache", "interrupt"])
def test_asset_position_and_replay_guards(tmp_path, monkeypatch, change):
    args = setup(tmp_path, monkeypatch)
    if change in {"wrong_prediction", "cache"}:
        assert _score(args)["status"] == "pass"
    root = Path(args[3]["_score_context"]["artifact_dir"])
    if change == "reference":
        Path(args[1]["test_files"][0]).write_bytes(b"changed reference")
    elif change == "position":
        args[3]["_score_context"]["request"]["repeat"] = 1
    elif change == "outside":
        args[3]["_score_context"]["artifact_dir"] = str(tmp_path / "workspace" / root.name)
    elif change == "wrong_prediction":
        args[3]["_score_context"]["prediction_hash"] = "0" * 64
    elif change == "cache":
        next((root / "recalculations").glob("*.json")).write_text("{}")
    else:
        write_json(root / "started.json", seal({"interrupted": True}))
    previous = len(args[4])
    assert _score(args)["status"] == "unknown" and len(args[4]) == previous


@pytest.mark.parametrize("states,expected", [(["pass", "pass"], "pass"), (["pass", "fail"], "fail"),
    (["pass", "unknown"], "unknown"), (["fail", "unknown"], "fail")])
def test_hard_all_cases_and_deduplicated_receipts(tmp_path, monkeypatch, states, expected):
    args = setup(tmp_path, monkeypatch)
    args[1]["test_files"] *= 2
    args[2]["output"]["cases"] *= 2
    real = recalc.evaluate_pair
    def pair(*a, **kw):
        result = real(*a, **kw)
        result["status"] = states.pop(0)
        return result
    monkeypatch.setattr(recalc, "evaluate_pair", pair)
    result = _score(args)
    assert result["status"] == expected and len(args[4]) == 2
    assert result["metrics"]["receipt_reuses"] == 2


def test_cleanup_failure_overrides_even_another_confirmed_failure(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch, formula="=A1+A2+1", expected=6)
    args[1]["test_files"] *= 2
    args[2]["output"]["cases"] *= 2
    real = recalc.evaluate_pair
    count = 0
    def pair(*a, **kw):
        nonlocal count
        count += 1
        if count == 1:
            return real(*a, **kw)
        write_json(a[4] / "cleanup-failure.json", seal({"cleanup_confirmed": False,
            "container_execution_attempted": True, "duration_seconds": 1}))
        return {"status": "unknown", "reason": "container_cleanup_unconfirmed"}
    monkeypatch.setattr(recalc, "evaluate_pair", pair)
    result = _score(args)
    assert result["status"] == "unknown" and result["score"] is None and not result["cleanup_confirmed"]
    assert result["metrics"]["case_failed"] == 1 and result["execution_costs"]["container_calls"] == 3


def test_unavailable_case_and_model_prediction_remain_unknown_without_engine(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    args[2]["output"]["cases"][0] = {"status": "unknown", "reason": "native_exception:SyntaxError"}
    result = _score(args)
    assert result["status"] == "unknown" and result["metrics"]["case_unknown"] == 1 and not args[4]
    args[2]["status"] = "unknown"
    args[2]["reason"] = "model_response_truncated"
    assert _score(args)["reason"] == "model_response_truncated" and not args[4]


def test_empty_string_formula_cache_is_a_real_pass(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch, formula='=IF(A1=2,"",1)')
    gold = workbook(tmp_path / "empty-gold.xlsx", '=IF(1,"",2)', cache="", cache_type="str")
    converted = workbook(tmp_path / "empty-converted.xlsx", '=IF(A1=2,"",1)', cache="", cache_type="str")
    args[1].update(test_files=[str(gold)], asset_sha256={str(gold): recalc.sha(gold)})
    args[5][recalc.sha(gold)] = gold
    args[5][recalc.sha(tmp_path / "prediction.xlsx")] = converted
    assert _score(args)["status"] == "pass" and len(args[4]) == 2


def test_unsupported_formula_result_stays_unknown(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch, formula="=UNSUPPORTED(A1)")
    converted = workbook(tmp_path / "unsupported.xlsx", "=UNSUPPORTED(A1)", cache="#NAME?", cache_type="e")
    args[5][recalc.sha(tmp_path / "prediction.xlsx")] = converted
    result = _score(args)
    assert result["status"] == "unknown" and "unsupported_formula_result" in result["metrics"]["cases"][0]["reason"]


def test_cleanup_failure_stops_remaining_cases_and_no_replay_execution(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    args[1]["test_files"] *= 3
    args[2]["output"]["cases"] *= 3
    calls = []
    def pair(*a, **kw):
        calls.append(True)
        write_json(a[4] / "cleanup.json", seal({"cleanup_confirmed": False,
            "container_execution_attempted": True, "duration_seconds": 1}))
        return {"status": "unknown", "reason": "reference:container_cleanup_unconfirmed"}
    monkeypatch.setattr(recalc, "evaluate_pair", pair)
    result = _score(args)
    assert result["status"] == "unknown" and result["metrics"]["case_unknown"] == 3 and len(calls) == 1
    assert _score(args) == result and len(calls) == 1
    other = deepcopy(args[3])
    other["_score_context"]["artifact_dir"] = str(tmp_path / "other/host_only/scorer_artifacts" / other["_score_context"]["position"])
    with pytest.raises(ValueError, match="replay cannot execute"):
        adapter.score(*args[:3], runtime=other, replay_only=True)
    assert len(calls) == 1


def test_reference_drift_and_unsupported_do_not_fall_back(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    changed = workbook(tmp_path / "reference-calc.xlsx", cache=6)
    args[5][recalc.sha(args[1]["test_files"][0])] = changed
    monkeypatch.setattr(backends, "_score_sheet", lambda *a, **k: pytest.fail("No legacy fallback"))
    result = _score(args)
    assert result["status"] == "unknown" and "drift" in result["metrics"]["cases"][0]["reason"]


def test_legacy_profiles_are_still_the_original_dispatch(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    calls = []
    expected = {"status": "pass", "score": 1.0, "reason": "unchanged", "metrics": {}}
    monkeypatch.setattr(backends, "_score_sheet", lambda *a, **k: calls.append(k) or expected)
    monkeypatch.setattr(adapter, "score", lambda *a, **k: pytest.fail("Legacy must not use new adapter"))
    for profile in (None, compat.VERSION):
        args[3]["spreadsheet_scorer"] = profile
        assert _score(args) is expected
    assert calls == [{"scorer_profile": None}, {"scorer_profile": compat.VERSION}]


def test_readiness_checks_distinct_recalc_image_then_original_generator(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    images, native = [], []
    monkeypatch.setattr(backends, "_image_ready", lambda runtime: images.append(runtime["image"]) or {"status": "ready"})
    monkeypatch.setattr(backends, "_native", lambda request, runtime: native.append(runtime["image"]) or {"status": "ready"})
    assert backends.readiness("spreadsheetbench", args[3])["status"] == "ready"
    assert images == [IMAGE] and native == [args[3]["image"]] and not args[4]


def test_runner_supplies_host_context_only_at_scoring_and_keeps_reference_private(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    root = tmp_path / "runner"
    config = fixture_config(root)
    runtime = deepcopy(args[3])
    runtime.pop("_score_context")
    config["runtime"]["spreadsheetbench"] = runtime
    panel_path = Path(config["panels"]["spreadsheetbench"])
    panel = read_json(panel_path)
    panel["tasks"][0].update(public=args[0], private=args[1])
    panel_path.write_text(json.dumps(panel))
    freeze_plan(config, root)
    seen = []
    def solver(benchmark, public, skill, call, *, runtime):
        seen.append(public)
        assert "_score_context" not in runtime and "test_files" not in public
        return {**args[2], "reason": "authored_fixture"}
    runner.generate(root, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench", fixture_solve=solver)
    runner.score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
                            fixture_score=backends.score)
    scores = list((root / "host_only/scores").glob("*.json"))
    assert len(scores) == 1 and read_json(scores[0], sealed=True)["status"] == "pass"
    assert len(list((root / "host_only/scorer_artifacts").glob("*/result.json"))) == 1
    assert "private-reference.xlsx" not in json.dumps(seen)
    assert not list((root / "predictions").glob("*/workspace/*"))
    runner.score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
                            fixture_score=lambda *a, **k: pytest.fail("Existing score must replay"))
    assert len(args[4]) == 2
    # Cached host scores must not bypass verification of retained private proof.
    next((root / "host_only/scorer_artifacts").glob("*/recalculations/*.json")).write_text("{}")
    with pytest.raises(ValueError, match="evidence changed"):
        runner.score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
                                fixture_score=backends.score)
    assert len(args[4]) == 2


def test_operator_cannot_configure_host_evidence_context(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    config = fixture_config(tmp_path / "config")
    config["runtime"]["spreadsheetbench"] = args[3]
    with pytest.raises(ValueError, match="host-owned"):
        freeze_plan(config, tmp_path / "forbidden")
