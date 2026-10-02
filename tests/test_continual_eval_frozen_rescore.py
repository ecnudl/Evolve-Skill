"""Authored all-roster fixtures only; no model, network or Docker execution."""
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import frozen_rescore as f
from skillopt.continual_eval import reference_qualification as q
from skillopt.continual_eval import runner
from skillopt.continual_eval.core import load_checkpoint, output_lock, read_json, write_json
from skillopt.validator_pilot.api import digest
from tests import test_continual_eval_reference_qualification as fixtures


def result(status="pass", *, missing=False):
    return {"status": status, "score": None if status == "unknown" else float(status == "pass"),
            "reason": "native_timeout" if status == "unknown" else "official_bigcodebench_untrusted_check",
            "metrics": {"details": {"fixture": [{"traceback": "Resource \x1b[93mpunkt\x1b[0m not found"}]
                                                   if missing else "PRIVATE_CANARY"}},
            "cleanup_confirmed": True, "execution_costs": {"container_calls": 1, "wall_seconds": 0.1}}


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rescore-fixture")
    oldq, parent, raw, lock = fixtures.setup(tmp)
    _, data = q._load(oldq)
    q.run(oldq, fixture_score=lambda task, code: result("fail" if int(task["task_id"].split("-")[-1]) < 7 else "pass",
             missing=int(task["task_id"].split("-")[-1]) < 5))
    plan = read_json(parent / "plan.json", sealed=True)
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)

    class FakeAPI:
        model = "fixture"
        service = {"fixture_service": True}
        truncated = False

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = dict(model=self.model, system=system, user=user, kind=kind, key=key,
                           max_tokens=max_tokens, repeat=repeat, service=self.service)
            receipt = dict(request=request, request_hash=digest(request),
                           response="" if self.truncated else "FROZEN_CODE_NOT_EXECUTED_ON_HOST",
                           ok=not self.truncated, finish_reason="length" if self.truncated else "stop",
                           usage={"prompt_tokens": 1, "completion_tokens": 1}, http_attempt_count=1)
            write_json(parent / "api/calls" / (receipt["request_hash"] + ".json"), receipt)
            return receipt

    api = FakeAPI()
    write_json(parent / "model_service.json", seal(api.service))
    for ref in data["references"]:
        for repeat in range(2):
            base, request = runner.position(parent, cp, "bigcodebench", ref["task"], repeat)
            write_json(base / "intent.json", seal(request))
            api.truncated = ref["task"]["task_id"] == "fixture-0" and repeat == 1
            call = runner.PositionCalls(api, base, request, 4096, 1)
            receipt = call("PUBLIC_SYSTEM", "PUBLIC_USER")
            prediction = {"status": "unknown" if api.truncated else "available", "output": receipt["response"],
                          "reason": "model_response_truncated" if api.truncated else "fixture"}
            write_json(base / "prediction.json", seal({"request": request, "prediction": prediction,
                       "costs": runner._costs([receipt]), "evidence_kind": "engineering_fixture"}))

    def oldscore(benchmark, public, private, prediction, *, runtime):
        i = int(public["prompt"].split()[-1].rstrip("."))
        return result("unknown" if i == 0 else "fail" if i < 5 else "pass", missing=0 < i < 5)

    runner.score_checkpoint(parent, method="no_skill", history="h0", stage=0, benchmark="bigcodebench", fixture_score=oldscore)
    runner.report(parent)
    overlay = tmp / "overlay"
    manifest = seal({"version": "bcb-nltk-data-overlay-v2", "base_image": data["runtime"]["image"]})
    receipt = seal({"status": "built_not_qualified", "manifest_hash": manifest["record_hash"],
                    "base_image": manifest["base_image"], "image_id": "sha256:" + "b" * 64, "base_configuration_preserved": True})
    write_json(overlay / "manifest.json", manifest)
    write_json(overlay / "build-receipt.json", receipt)
    oldreport = read_json(oldq / "result.json", sealed=True)
    metadata = deepcopy(plan)
    metadata.pop("record_hash")
    metadata["config"]["runtime"]["bigcodebench"]["image"] = receipt["image_id"]
    metadata["checkpoints"] = []
    metadata["environment_qualification"] = {"parent_plan_path": str(parent / "plan.json"),
        "parent_plan_hash": plan["record_hash"], "parent_plan_file_sha256": q._sha(parent / "plan.json"),
        "original_reference_report_path": str(oldq / "result.json"), "original_reference_report_hash": oldreport["record_hash"],
        "original_reference_report_file_sha256": q._sha(oldq / "result.json"),
        "overlay_manifest": manifest, "overlay_manifest_path": str(overlay / "manifest.json"),
        "overlay_manifest_file_sha256": q._sha(overlay / "manifest.json"),
        "overlay_build_receipt": receipt, "overlay_receipt_path": str(overlay / "build-receipt.json"),
        "overlay_receipt_file_sha256": q._sha(overlay / "build-receipt.json"),
        "acceptance_frozen_before_execution": {"target_task_hashes": [r["identity"]["task_hash"] for r in data["references"][:5]]}}
    with output_lock(tmp / "metadata"):
        write_json(tmp / "metadata/plan.json", seal(metadata))
    newq = tmp / "new-qualification"
    q.prepare(tmp / "metadata/plan.json", raw, newq, native_lock=lock)
    q.run(newq, fixture_score=lambda task, code: result("fail" if int(task["task_id"].split("-")[-1]) in (5, 6) else "pass"))
    template = tmp / "rescore-template"
    protocol = f.prepare(newq, template)
    return template, protocol, parent, newq


@pytest.fixture
def runroot(tmp_path, frozen):
    template, protocol, _, _ = frozen
    root = tmp_path / "new-output"
    write_json(root / "protocol.json", protocol)
    return root


def test_qualification_and_full800_frozen_output_replay(frozen, runroot):
    _, protocol, parent, _ = frozen
    before = {str(p): q._sha(p) for p in parent.rglob("*.json")}
    seen = []

    def score(benchmark, public, private, prediction, *, runtime):
        assert benchmark == "bigcodebench" and private["test"] == "HIDDEN_TEST_CANARY"
        assert prediction["output"] == "FROZEN_CODE_NOT_EXECUTED_ON_HOST"
        assert runtime == protocol["runtime"] and runtime["timeout_seconds"] == 300
        seen.append(1)
        return result("unknown" if len(seen) == 1 else "pass")

    partial = f.run(runroot, max_new_positions=2, fixture_score=score)
    assert partial["counts"] == {"unknown": 2} and partial["unsubmitted"] == 798
    complete = f.run(runroot, fixture_score=score)
    assert complete["status"] == "completed" and complete["closed"] == 800 and len(seen) == 799
    assert complete["model_calls"] == 0 and complete["counts"] == {"unknown": 2, "pass": 798}
    assert complete["predeclared_environment_diagnostic_strata"]["old_explicit_nltk_missing"]["positions"] == 8
    assert complete["predeclared_environment_diagnostic_strata"]["all_other_original_positions"]["positions"] == 792
    assert f.run(runroot, fixture_score=score) == complete and len(seen) == 799
    assert not complete["old_scores_replaced"] and not complete["skill_gate_allowed"]
    assert all(x not in json.dumps(complete) for x in ("PRIVATE_CANARY", "HIDDEN_TEST_CANARY", "FROZEN_CODE"))
    assert before == {str(p): q._sha(p) for p in parent.rglob("*.json")}


def test_open_native_execution_not_retried(runroot):
    seen = []

    def crash(*args, **kwargs):
        seen.append(1)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        f.run(runroot, fixture_score=crash)
    report = f.run(runroot, fixture_score=crash)
    assert len(seen) == report["unclosed"] == 1 and report["closed"] == 0 and not report["costs_complete"]


def test_closed_unknown_cannot_be_resealed_to_pass(runroot):
    f.run(runroot, max_new_positions=1, fixture_score=lambda *a, **k: result("unknown"))
    path = next((runroot / "records").glob("*.json"))
    row = read_json(path, sealed=True)
    row.pop("record_hash")
    row["score"] = result("pass")
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="published rescore changed"):
        f.run(runroot, fixture_score=lambda *a, **k: pytest.fail("No resampling"))


def test_source_change_blocks_before_scoring(runroot, monkeypatch):
    changed = f.source_identity()
    changed["continual_eval/native_worker.py"] = "0" * 64
    monkeypatch.setattr(f, "source_identity", lambda: changed)
    with pytest.raises(ValueError, match="source changed"):
        f.run(runroot, fixture_score=lambda *a, **k: pytest.fail("Changed code must not execute"))


@pytest.mark.parametrize("kind", ["old_retained_regression", "target_not_repaired"])
def test_qualification_gate_rejects_regression_or_unrepaired_target(frozen, monkeypatch, kind):
    _, _, _, newq = frozen
    original = f._reference

    def changed(root):
        protocol, data, report, rows = original(root)
        if root == newq:
            rows = deepcopy(rows)
            h = data["references"][10 if kind == "old_retained_regression" else 0]["identity"]["task_hash"]
            rows[h]["score"] = result("fail")
        return protocol, data, report, rows

    monkeypatch.setattr(f, "_reference", changed)
    with pytest.raises(ValueError, match="regression or unrepaired"):
        f._qualified(newq)


def test_pause_does_not_call_native(runroot):
    (runroot / "PAUSE").touch()
    assert f.run(runroot, fixture_score=lambda *a, **k: pytest.fail("Paused"))["closed"] == 0
    (runroot / "PAUSE").unlink()
    seen = []
    assert f.run(runroot, max_new_positions=1, fixture_score=lambda *a, **k: seen.append(1) or result())["closed"] == 1
    assert seen == [1]


@pytest.mark.parametrize("kind", ["wrong_image", "missing_cleanup", "exception"])
def test_natural_dispatch_bad_receipts_stop_unknown(runroot, monkeypatch, kind):
    original = f._load

    def natural(root):
        protocol, data = original(root)
        data = deepcopy(data)
        data["fixture"] = False  # Test-only native dispatch emulation, not natural evidence.
        return protocol, data

    monkeypatch.setattr(f, "_load", natural)
    calls = []

    def score(*args, **kwargs):
        calls.append(1)
        if kind == "exception":
            raise RuntimeError("PRIVATE_EXCEPTION")
        value = result("unknown" if kind == "missing_cleanup" else "pass")
        value["runtime_image_id"] = "wrong" if kind == "wrong_image" else kwargs["runtime"]["image"]
        if kind == "missing_cleanup":
            value.pop("cleanup_confirmed")
        return value

    monkeypatch.setattr(f.backends, "score", score)
    report = f.run(runroot)
    assert calls == [1] and report["status"] == "pending" and report["counts"] == {"unknown": 1}
    assert not report["costs_complete"] and "PRIVATE_EXCEPTION" not in json.dumps(report)
    assert f.run(runroot) == report and calls == [1]


def test_no_fixture_callback_on_natural_or_missing_callback_on_fixture(runroot):
    with pytest.raises(ValueError, match="Fixture boundary"):
        f.run(runroot)


@pytest.mark.parametrize("kind", ["wrong_returned_model", "non_boolean_outcome", "zero_attempts",
                                  "boolean_attempts", "wrong_old_image", "missing_old_cleanup"])
def test_original_natural_response_and_native_identity_are_required(kind):
    plan = {"config": {"model": {"name": "glm-5.3"}, "runtime": {"bigcodebench": {"image": "original-image"}}}}
    receipt = {"ok": True, "returned_model": "glm-5.3", "http_attempt_count": 1}
    score = {**result(), "runtime_image_id": "original-image"}
    f._validate_original(receipt, score, plan, fixture=False)
    if kind == "wrong_returned_model":
        receipt["returned_model"] = "other"
    elif kind == "non_boolean_outcome":
        receipt["ok"] = 1
    elif kind == "zero_attempts":
        receipt["http_attempt_count"] = 0
    elif kind == "boolean_attempts":
        receipt["http_attempt_count"] = True
    elif kind == "wrong_old_image":
        score["runtime_image_id"] = "new-image"
    else:
        score.pop("cleanup_confirmed")
    with pytest.raises(ValueError):
        f._validate_original(receipt, score, plan, fixture=False)


def test_nested_ansi_details_use_values_not_serialized_repr_or_keys():
    details = {"Resource stopwords not found": False,
               "details": [None, 42, {"traceback": "Resource \x1b[93mpunkt\x1b[0m not found"}]}
    text = f._detail_text(details)
    assert "Resource punkt not found" in text and "stopwords" not in text
    assert "\\x1b" not in text and "\x1b" not in text
    assert f._detail_text("Resource stopwords not found") == "Resource stopwords not found"
