"""Authored reference-qualification fixtures; no reference execution or APIs."""
import copy
import json

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import reference_qualification as q
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, read_json, write_json
from skillopt.continual_eval.datasets import import_bigcodebench


def setup(tmp_path):
    raw = tmp_path / "raw"
    rows = [{"task_id": f"fixture-{i}", "entry_point": "task_func", "instruct_prompt": f"Authored fixture {i}.",
             "complete_prompt": "raise RuntimeError('NEVER_EXECUTE_ON_HOST')\ndef task_func():\n",
             "canonical_solution": "    return 1\n", "test": "HIDDEN_TEST_CANARY"} for i in range(400)]
    write_json(raw / "rows.json", rows)
    (raw / "v0.1.4.parquet").write_bytes(b"authored fixture, not actual parquet")
    write_json(raw / "download-receipt.json", {"repository": "fixture", "revision": "fixture", "version_split": "fixture",
               "rows_sha256": q._sha(raw / "rows.json"), "source_parquet_sha256": q._sha(raw / "v0.1.4.parquet")})
    panel = import_bigcodebench(rows, revision="authored-reference-fixture",
                               family_map={r["task_id"]: f"family-{i if i != 399 else 0}" for i, r in enumerate(rows)})
    panel["provenance"] = "fixture"
    panel_path = tmp_path / "data/panel.json"
    write_json(panel_path, panel)
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
              "panels": {b: str(panel_path) if b == "bigcodebench" else None for b in BENCHMARKS},
              "partition": "development", "methods": ["no_skill"], "histories": ["h0"], "repeats": 2,
              "model": {"provider": "fixture", "name": "fixture", "reasoning_effort": "low", "max_tokens": 4096},
              "runtime": {"bigcodebench": {"image": "sha256:" + "a" * 64, "timeout_seconds": 300, "memory_mb": 8192,
                                           "cpus": 1}}, "project_disjoint": False, "exposure_manifest": None}
    plan_root = tmp_path / "baseline"
    freeze_plan(config, plan_root)
    native_lock = tmp_path / "native.lock"
    native_lock.touch()
    output = tmp_path / "qualification"
    q.prepare(plan_root / "plan.json", raw, output, native_lock=native_lock)
    return output, plan_root, raw, native_lock


def score(task, code):
    assert code.startswith("raise RuntimeError('NEVER_EXECUTE_ON_HOST')")
    assert task["private"]["test"] == "HIDDEN_TEST_CANARY"
    i = int(task["task_id"].split("-")[-1])
    status = ("pass", "fail", "unknown")[i % 3]
    return {"status": status, "score": None if status == "unknown" else float(status == "pass"),
            "reason": "native_timeout" if status == "unknown" else "official_bigcodebench_untrusted_check",
            "metrics": {"private": "HIDDEN_TEST_CANARY"}, "cleanup_confirmed": True,
            "execution_costs": {"container_calls": 1, "wall_seconds": 0.25}}


def test_full_roster_resume_unknown_no_retry_no_host_exec_no_api(tmp_path):
    output, baseline, raw, _ = setup(tmp_path)
    before = {str(p): p.read_bytes() for root in (baseline, raw) for p in root.rglob("*") if p.is_file()}
    visited = []

    def record(task, code):
        visited.append(task["task_id"])
        return score(task, code)

    first = q.run(output, max_new_tasks=17, fixture_score=record)
    assert first["closed"] == 17 and first["unsubmitted"] == 383 and first["status"] == "pending"
    result = q.run(output, fixture_score=record)
    assert result["status"] == "completed" and result["closed"] == 400
    assert (result["pass"], result["fail"], result["unknown"]) == (134, 133, 133)
    assert len(visited) == len(set(visited)) == 400
    assert result["container_calls_known_subtotal"] == 400 and result["container_wall_seconds_known_subtotal"] == 100
    assert result["cleanup_confirmed"] == 400 and result["execution_costs_complete_for_submitted_positions"]
    assert result["evidence_kind"] == "engineering_fixture" and result["model_calls"] == 0
    assert not result["baseline_scores_replaced"] and not result["skill_gate_allowed"] and not result["score_feedback_allowed"]
    assert all(x not in json.dumps(result) for x in ("HIDDEN_TEST_CANARY", "NEVER_EXECUTE_ON_HOST", "return 1"))
    assert q.run(output, fixture_score=record) == result and len(visited) == 400
    assert before == {str(p): p.read_bytes() for root in (baseline, raw) for p in root.rglob("*") if p.is_file()}


def test_open_execution_blocks_resume_instead_of_rerun_or_zero_cost(tmp_path):
    output, _, _, _ = setup(tmp_path)
    visited = []

    def interrupted(task, code):
        visited.append(task["task_id"])
        if len(visited) == 3:
            raise KeyboardInterrupt
        return score(task, code)

    with pytest.raises(KeyboardInterrupt):
        q.run(output, fixture_score=interrupted)
    result = q.run(output, fixture_score=interrupted)
    assert result["closed"] == 2 and result["unclosed"] == 1 and result["unsubmitted"] == 397
    assert result["status"] == "pending" and not result["execution_costs_complete_for_submitted_positions"]
    assert len(visited) == 3


@pytest.mark.parametrize("kind", ["cleanup", "host_exception"])
def test_uncertain_cleanup_stops_new_containers_and_remains_unknown(tmp_path, kind):
    output, _, _, _ = setup(tmp_path)
    visited = []

    def uncertain(task, code):
        visited.append(task["task_id"])
        if kind == "host_exception":
            raise RuntimeError("Do not export private exception text")
        return {"status": "unknown", "score": None, "reason": "container_cleanup_unconfirmed", "metrics": {}}

    result = q.run(output, fixture_score=uncertain)
    assert result["closed"] == result["unknown"] == 1 and result["unsubmitted"] == 399
    assert not result["execution_costs_complete_for_submitted_positions"]
    assert q.run(output, fixture_score=uncertain) == result and len(visited) == 1
    assert "private exception" not in json.dumps(result)


def test_boundary_pause_can_resume_and_does_not_reopen_unknown(tmp_path):
    output, _, _, _ = setup(tmp_path)
    pause = output / "PAUSE"
    pause.touch()
    assert q.run(output, fixture_score=score)["closed"] == 0
    pause.unlink()
    assert q.run(output, max_new_tasks=3, fixture_score=score)["unknown"] == 1
    assert q.run(output, max_new_tasks=1, fixture_score=score)["closed"] == 4


@pytest.mark.parametrize("change", ["raw", "source", "runtime", "roster", "reference_identity"])
def test_changed_inputs_cannot_execute(tmp_path, monkeypatch, change):
    output, baseline, raw, _ = setup(tmp_path)
    if change == "raw":
        rows = read_json(raw / "rows.json")
        rows[0]["canonical_solution"] = "    return 9\n"
        (raw / "rows.json").write_text(json.dumps(rows))
    elif change == "source":
        changed = q.source_identity()
        changed["continual_eval/native_worker.py"] = "0" * 64
        monkeypatch.setattr(q, "source_identity", lambda: changed)
    elif change == "roster":
        plan = read_json(baseline / "plan.json", sealed=True)
        plan.pop("record_hash")
        plan["tasks"] = plan["tasks"][:399]
        (baseline / "plan.json").write_text(json.dumps(seal(plan)))
    else:
        value = read_json(output / "protocol.json", sealed=True)
        value.pop("record_hash")
        if change == "runtime":
            value["runtime"]["timeout_seconds"] = 600
        else:
            value["reference_roster"][0]["reference_sha256"] = "0" * 64
        (output / "protocol.json").write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError):
        q.run(output, fixture_score=lambda *args: pytest.fail("Changed inputs must not execute"))


def test_prior_report_binds_closed_unknown_across_resumptions(tmp_path):
    output, _, _, _ = setup(tmp_path)
    q.run(output, max_new_tasks=3, fixture_score=score)
    path = next(p for p in (output / "records").glob("*.json") if read_json(p)["score"]["status"] == "unknown")
    row = read_json(path, sealed=True)
    row.pop("record_hash")
    row["score"].update(status="pass", score=1.0)
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="closed evidence changed"):
        q.run(output, fixture_score=score)


def test_natural_dispatch_uses_existing_score_and_original_runtime_only(tmp_path, monkeypatch):
    output, _, _, _ = setup(tmp_path)
    protocol, data = q._load(output)
    data = copy.deepcopy(data)
    data["fixture"] = False  # Authored mock of dispatch, never natural-effect evidence.
    monkeypatch.setattr(q, "_load", lambda root: (protocol, data))
    monkeypatch.setattr(q.backends, "_image_ready", lambda runtime: {"status": "ready"})
    called = []

    def native(benchmark, public, private, prediction, *, runtime):
        called.append(benchmark)
        assert runtime == data["runtime"] and runtime["timeout_seconds"] == 300
        assert prediction["reason"] == "official_reference_not_model" and prediction["status"] == "available"
        assert prediction["output"] == data["references"][0]["code"]
        assert public == data["references"][0]["task"]["public"]
        assert private == data["references"][0]["task"]["private"]
        return {**score(data["references"][0]["task"], prediction["output"]), "runtime_image_id": runtime["image"]}

    monkeypatch.setattr(q.backends, "score", native)
    result = q.run(output, max_new_tasks=1)
    assert called == ["bigcodebench"] and result["model_calls"] == 0 and result["pass"] == 1


def test_cli_check_is_read_only_and_no_execution(tmp_path, capsys):
    output, _, _, _ = setup(tmp_path)
    assert q.main(["check", "--output", str(output)]) is None
    result = json.loads(capsys.readouterr().out)
    assert result["model_calls"] == 0 and result["status"] == "validated_not_executed"
    assert not (output / "records").exists()


def test_fixture_scorer_cannot_inject_real_run_or_missing_fixture_callback(tmp_path):
    output, _, _, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="Fixture scorer boundary"):
        q.run(output)


@pytest.mark.parametrize("mutation", ["image", "cleanup", "cost_image"])
def test_natural_native_identity_or_cleanup_mismatch_is_not_known_success(tmp_path, monkeypatch, mutation):
    output, _, _, _ = setup(tmp_path)
    protocol, data = q._load(output)
    data["fixture"] = False
    monkeypatch.setattr(q, "_load", lambda root: (protocol, data))
    monkeypatch.setattr(q.backends, "_image_ready", lambda runtime: {"status": "ready"})
    value = {**score(data["references"][0]["task"], data["references"][0]["code"]),
             "runtime_image_id": data["runtime"]["image"]}
    if mutation == "image":
        value["runtime_image_id"] = "sha256:" + "b" * 64
    elif mutation == "cleanup":
        value.pop("cleanup_confirmed")
    else:
        value["execution_costs"]["image_id"] = "sha256:" + "b" * 64
    monkeypatch.setattr(q.backends, "score", lambda *args, **kwargs: value)
    result = q.run(output, max_new_tasks=2)
    assert result["status"] == "pending" and result["pass"] == result["fail"] == 0
    assert result["unknown"] == 1 and result["unsubmitted"] == 399
    assert not result["execution_costs_complete_for_submitted_positions"]
    with pytest.raises(ValueError, match="native image|image differs"):
        q._validated_score(value, data)


def test_natural_unknown_can_lack_outer_timeout_image_but_cannot_forge_one(tmp_path):
    output, _, _, _ = setup(tmp_path)
    _, data = q._load(output)
    data["fixture"] = False
    value = {"status": "unknown", "score": None, "reason": "native_timeout", "metrics": {}}
    assert q._validated_score(value, data) == value
    with pytest.raises(ValueError, match="image differs"):
        q._validated_score({**value, "runtime_image_id": "sha256:" + "b" * 64}, data)
