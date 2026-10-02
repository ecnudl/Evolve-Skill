"""Offline recovery controls; no real model or native environment is used."""
import json
import shutil
import signal
from copy import deepcopy
from pathlib import Path
from threading import Event, Thread

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, runner
from skillopt.continual_eval import truncation_recovery as recovery
from skillopt.continual_eval.core import (
    BENCHMARKS,
    freeze_plan,
    load_checkpoint,
    output_lock,
    panel_tasks,
    read_json,
    write_json,
)
from skillopt.continual_eval.fixtures import fixture_panel
from skillopt.validator_pilot.api import digest


class API:
    model = "fixture"
    service = {"provider": "fixture", "model": "fixture", "reasoning_effort": "low",
               "timeout_seconds": {"connect": 20, "read": 120, "write": 30, "pool": 20}}

    def __init__(self, *, finish="stop", response="[[YES]]", crash=False):
        self.finish, self.response, self.crash, self.calls = finish, response, crash, []

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        self.calls.append((system, user, max_tokens))
        if self.crash:
            raise RuntimeError("Authored interruption")
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        return {"request": request, "request_hash": digest(request), "ok": self.finish == "stop",
                "response": self.response, "finish_reason": self.finish, "status": 200,
                "returned_model": self.model, "error_type": "truncated_content" if self.finish == "length" else None,
                "http_attempt_count": 1, "usage": {"prompt_tokens": 2, "completion_tokens": max_tokens}}

    @staticmethod
    def _initial_ready(receipt):
        return receipt.get("status") == 200


def original(tmp_path, *, benchmark="korbench", count=1, reason="model_response_truncated", finish="length"):
    root = tmp_path / "original"
    panel = fixture_panel(benchmark)
    panel["tasks"][0]["partition"] = "development"
    for index in range(1, count):
        extra = deepcopy(panel["tasks"][0])
        extra.update(task_id=f"extra-{index}", family_id=f"family-{index}")
        panel["tasks"].append(extra)
    path = tmp_path / "panel.json"
    write_json(path, panel)
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
        "panels": {b: str(path) if b == benchmark else None for b in BENCHMARKS}, "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 1,
        "model": {"provider": "fixture", "name": "fixture", "max_tokens": 4096, "reasoning_effort": "low"},
        "runtime": {}, "project_disjoint": False, "exposure_manifest": None}
    plan = freeze_plan(config, root)
    cp = load_checkpoint(root, "no_skill", "h0", 0, plan)
    write_json(root / "model_service.json", seal(API.service))
    for task in panel_tasks(plan, benchmark):
        base, request = runner.position(root, cp, benchmark, task, 0)
        write_json(base / "intent.json", seal(request))
        callback = runner.PositionCalls(API(finish=finish), base, request, 4096, 1)
        if benchmark == "alfworld":
            callback("Frozen action system", "Frozen public state")
            prediction = {"status": "unknown", "output": None, "reason": reason}
        else:
            prediction = backends.solve(benchmark, task["public"], "", callback)
            prediction.update(status="unknown", reason=reason)
        write_json(base / "prediction.json", seal({"request": request, "prediction": prediction,
            "costs": runner._position_costs(base), "evidence_kind": "engineering_fixture",
            "score_feedback_allowed": False}))
    return {"version": "truncation-recovery-spec-v1", "runs": [
        {"kind": "eval", "root": str(root), "source_root": str(Path(__file__).resolve().parents[1])}]}


def score(benchmark, public, private, prediction, *, runtime):
    assert prediction["status"] in {"available", "unknown"}
    unknown = prediction["status"] == "unknown"
    return {"status": "unknown" if unknown else "pass", "score": None if unknown else 1.,
            "reason": prediction["reason"] if unknown else "authored_fixture", "metrics": {}}


def run(root, api, **kwargs):
    return recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score, **kwargs)


def test_exact_prompt_increased_cap_repeat_without_calls_and_old_unchanged(tmp_path):
    spec = original(tmp_path)
    oldroot = Path(spec["runs"][0]["root"])
    before = {str(p): p.read_bytes() for p in oldroot.rglob("*.json")}
    root = tmp_path / "recovery"
    assert recovery.prepare(spec, root)["positions"] == 1
    protocol = read_json(root / "protocol.json", sealed=True)
    old = protocol["positions"][0]["old_request"]
    api = API()
    result = run(root, api)
    assert result["status"] == "completed" and result["counts"]["korbench"]["score_pass"] == 1
    assert api.calls == [(old["system"], old["user"], 8192)]
    assert run(root, api) == result and len(api.calls) == 1
    assert before == {str(p): p.read_bytes() for p in oldroot.rglob("*.json")}
    assert not result["optimizer_resumed"] and not result["whole_benchmark_accuracy_claimed"]


def test_non_truncation_unknown_not_selected(tmp_path):
    spec = original(tmp_path, reason="native_timeout")
    with pytest.raises(ValueError, match="No proven truncated"):
        recovery.prepare(spec, tmp_path / "retry")


def test_reason_without_length_evidence_rejected(tmp_path):
    spec = original(tmp_path, finish="stop")
    with pytest.raises(ValueError, match="Missing or ambiguous truncated"):
        recovery.prepare(spec, tmp_path / "retry")


def test_changed_old_source_rejected(tmp_path, monkeypatch):
    spec = original(tmp_path)
    root = tmp_path / "retry"
    recovery.prepare(spec, root)
    original_sha = recovery._sha
    target = str(Path(spec["runs"][0]["source_root"]) / "skillopt/continual_eval/fixtures.py")
    monkeypatch.setattr(recovery, "_sha", lambda p: "0" * 64 if str(p) == target else original_sha(p))
    with pytest.raises(ValueError, match="Original evidence/source changed"):
        run(root, API())


def test_prompt_mismatch_no_paid_call_and_keeps_unknown(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path), root)
    api = API()
    def wrong(benchmark, public, skill, call, *, runtime):
        return backends.solve(benchmark, {**public, "question": "changed"}, skill, call, runtime=runtime)
    with pytest.raises(ValueError, match="First recovery prompt/call unavailable"):
        recovery.run(root, fixture_api=api, fixture_solve=wrong, fixture_score=score)
    assert api.calls == []
    row = read_json(next(root.glob("positions/*/result.json")), sealed=True)
    assert row["score"]["reason"] == "original_prompt_mismatch" and row["call_hash"] is None


def test_second_truncation_preserved_no_third_call(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path), root)
    api = API(finish="length")
    assert run(root, api)["counts"]["korbench"]["score_unknown"] == 1
    run(root, api)
    assert len(api.calls) == 1


def test_open_intent_fail_closed(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path), root)
    api = API(crash=True)
    with pytest.raises(ValueError, match="retained open intent"):
        run(root, api)
    with pytest.raises(ValueError, match="Interrupted recovery"):
        run(root, API())
    result = recovery.report(root)
    assert result["status"] == "pending" and result["new_costs"]["unclosed_calls"] == 1


def test_alf_only_exact_call_no_solver_or_score(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path, benchmark="alfworld"), root)
    def forbidden(*args, **kwargs):
        raise AssertionError("ALF environment must not be recreated")
    api = API(response="<action>look</action>")
    result = recovery.run(root, fixture_api=api, fixture_solve=forbidden, fixture_score=forbidden)
    assert result["counts"]["alfworld"]["response_available"] == 1
    assert result["counts"]["alfworld"]["score_unknown"] == 1
    assert result["alfworld_episode_scores_recovered"] == 0


def test_service_mismatch_and_budget_tamper_block_calls(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path), root)
    api = API()
    api.service = {**api.service, "changed": True}
    with pytest.raises(ValueError, match="Model service differs"):
        run(root, api)
    assert api.calls == []
    path = root / "protocol.json"
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    value["max_tokens"] = 16000
    # Deliberate test tampering, not a production recovery operation.
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="budget/protocol changed"):
        run(root, API())


def test_completed_first_slot_does_not_bypass_new_health(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path, count=2), root)
    api = API()
    api._initial_ready = lambda receipt: False
    with pytest.raises(ValueError, match="remaining positions not submitted"):
        run(root, api)
    assert len(api.calls) == 1
    second = API()
    result = run(root, second)
    assert len(second.calls) == 1 and result["completed_positions"] == 2


def test_mirrored_original_run_cannot_retry_same_call_twice(tmp_path):
    spec = original(tmp_path)
    copied = tmp_path / "mirror"
    shutil.copytree(spec["runs"][0]["root"], copied)
    spec["runs"].append({**spec["runs"][0], "root": str(copied)})
    with pytest.raises(ValueError, match="Duplicate original logical model call"):
        recovery.prepare(spec, tmp_path / "retry")


def test_learning_keeps_actual_candidate_without_resuming_optimizer(tmp_path):
    from skillopt.continual_learning.contracts import manifest
    from skillopt.continual_learning.gepa import Adapter
    from skillopt.continual_learning.ledger import LearningPending, Ledger
    from skillopt.continual_learning.skillopt import native_sources

    panel = fixture_panel("bigcodebench")
    panel["tasks"][0].update(partition="development", project_id="")
    extra = deepcopy(panel["tasks"][0])
    extra.update(task_id="selection", family_id="selection")
    panel["tasks"].append(extra)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 4096, "reasoning_effort": "low"}
    budget = {"max_metric_calls": 10, "max_reflection_calls": 5, "max_api_calls": 20,
              "max_reported_tokens": 100000, "max_iterations": 2, "minibatch_size": 1,
              "solver_max_tokens": 4096, "reflection_max_tokens": 4096}
    value = manifest(panel, train_families=["fixture-family"], selection_families=["selection"],
                     model=model, budget=budget, method="skillopt")
    source = tmp_path / "learning"
    write_json(source / "identity.json", seal({"manifest": value, "native_sources": native_sources()}))
    write_json(source / "panel.json", panel)
    write_json(source / "model_service.json", seal(API.service))
    candidate = "Keep the public contract intact."
    proposal_identity = seal({"manifest_hash": value["record_hash"], "native_sources": native_sources()})
    write_json(source / "native/0/identity.json", proposal_identity)
    write_json(source / "native/0/result.json", seal({"identity_hash": proposal_identity["record_hash"],
                                                    "candidate_skill": candidate}))
    adapter = Adapter(value, source, Ledger(source, value, API(finish="length")))
    with pytest.raises(LearningPending, match="evaluation_unknown"):
        adapter.evaluate_rows([{"role": "train", "task": panel["tasks"][0]}], {"skill": candidate})
    spec = {"version": "truncation-recovery-spec-v1", "runs": [{"kind": "learning", "root": str(source),
        "source_root": str(Path(__file__).resolve().parents[1])}]}
    output = tmp_path / "retry"
    recovery.prepare(spec, output)
    frozen = read_json(output / "protocol.json", sealed=True)
    assert frozen["positions"][0]["skill_text"] == candidate
    api = API(response="def task_func(): return 1")
    result = run(output, api)
    assert result["counts"]["bigcodebench"]["score_pass"] == 1
    assert candidate in api.calls[0][0] and len(api.calls) == 1
    assert not result["optimizer_resumed"]


@pytest.mark.parametrize("changed", ["returned_model", "service", "error_type"])
def test_receipt_identity_and_actual_truncation_are_required(tmp_path, changed):
    spec = original(tmp_path)
    path = next(Path(spec["runs"][0]["root"]).glob("predictions/*/calls/*.json"))
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    if changed == "returned_model":
        # For real BigModel this is independently checked; fixture models are
        # instead checked through request model and frozen service.
        value["receipt"]["request"]["model"] = "another-model"
    elif changed == "service":
        value["receipt"]["request"]["service"] = {"model": "fixture", "altered": True}
    else:
        value["receipt"]["error_type"] = "timeout"
    value["receipt"]["request_hash"] = digest(value["receipt"]["request"])
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError):
        recovery.prepare(spec, tmp_path / "retry")


def parent_recovery(tmp_path, count=5):
    """Authored v1 evidence under a different frozen source path, not a run."""
    root = tmp_path / "parent"
    recovery.prepare(original(tmp_path, count=count), root)
    value = read_json(root / "protocol.json", sealed=True)
    value.pop("record_hash")
    value["version"] = "truncation-recovery-v1"
    old_source = tmp_path / "frozen-v1.py"
    shutil.copyfile(recovery.__file__, old_source)
    value["recovery_sources"].pop(str(Path(recovery.__file__)))
    value["recovery_sources"][str(old_source)] = recovery._sha(old_source)
    value = seal(value)
    (root / "protocol.json").write_text(json.dumps(value))
    with output_lock(root):
        pass
    return root, value, old_source


def author_parent_position(root, value, index, state):
    slot = value["positions"][index]
    base = root / "positions" / slot["id"]
    expected = recovery._expected(slot)
    if state != "orphan_cache":
        write_json(base / "intent.json", seal({"protocol_hash": value["record_hash"], "position_id": slot["id"]}))
        write_json(base / "call_intent.json", seal(expected))
    if state == "interrupted":
        return
    api = API()
    receipt = api.call(expected["system"], expected["user"], expected["kind"], expected["key"],
                       max_tokens=expected["max_tokens"], repeat=expected["repeat"])
    if state == "timeout":
        receipt.update(ok=False, response="", status=None, finish_reason=None, error_type="timeout", usage={}, http_attempt_count=3)
    write_json(root / "api/calls" / (digest(expected) + ".json"), receipt)
    if state == "orphan_cache":
        return
    call = seal({"receipt": receipt})
    write_json(base / "call.json", call)
    write_json(base / "result.json", seal({"protocol_hash": value["record_hash"], "position_id": slot["id"],
        "call_hash": call["record_hash"], "prediction": {"status": "unknown" if state == "timeout" else "available",
        "output": None if state == "timeout" else "YES", "reason": "fixture"},
        "score": {"status": "unknown" if state == "timeout" else "pass", "score": None if state == "timeout" else 1.,
                  "metrics": {}, "reason": "fixture"}}))


def test_resume_only_never_started_keeps_parent_counts_costs_and_request_ids(tmp_path):
    parent, value, _ = parent_recovery(tmp_path)
    for index, state in enumerate(("complete", "interrupted", "orphan_cache")):
        author_parent_position(parent, value, index, state)
    before = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    child = tmp_path / "child"
    result = recovery.prepare_resume(parent, child)
    assert result["positions"] == 2 and result["inherited_excluded_positions"] == 3
    frozen = read_json(child / "protocol.json", sealed=True)
    assert frozen["positions"] == value["positions"][3:]
    inherited = frozen["inherited"]
    assert inherited["counts"]["korbench"] == {
        "excluded_positions": 3, "completed": 1, "score_pass": 1, "interrupted_unknown": 2}
    assert inherited["retry_costs"]["unclosed_calls"] == 1
    assert not inherited["interrupted_positions_are_model_errors"]
    api = API()
    report = run(child, api)
    assert report["completed_positions"] == report["eligible_positions"] == len(api.calls) == 2
    assert run(child, api) == report and len(api.calls) == 2
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}


@pytest.mark.parametrize("changed", ["receipt", "source", "new_trace"])
def test_resume_parent_evidence_and_source_remain_bound(tmp_path, changed):
    parent, value, source = parent_recovery(tmp_path, count=2)
    author_parent_position(parent, value, 0, "complete")
    child = tmp_path / "child"
    recovery.prepare_resume(parent, child)
    if changed == "receipt":
        path = next(parent.glob("positions/*/call.json"))
        path.write_text(path.read_text() + "\n")
    elif changed == "source":
        source.write_text(source.read_text() + "\n")
    else:
        write_json(parent / "positions" / value["positions"][1]["id"] / "trace.json", {"late": True})
    api = API()
    with pytest.raises(ValueError, match="Original evidence/source changed|Parent recovery evidence roster changed"):
        run(child, api)
    assert not api.calls


def test_resume_refuses_active_parent_writer(tmp_path):
    parent, _, _ = parent_recovery(tmp_path)
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        recovery.prepare_resume(parent, tmp_path / "child")


def test_pause_before_first_call_is_zero_calls_and_cli_returns_three(tmp_path, capsys):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path), root)
    assert recovery.main(["pause", "--output", str(root)]) == 0
    api = API()
    assert run(root, api)["status"] == "paused"
    assert api.calls == [] and not list(root.glob("positions/*/intent.json"))
    assert recovery.main(["report", "--output", str(root)]) == 3
    capsys.readouterr()
    (root / "PAUSE").unlink()  # Explicit operator resume, never automatic in run().
    assert run(root, api)["status"] == "completed" and len(api.calls) == 1


def test_pause_drains_only_inflight_then_resume_skips_completed(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path, count=8), root)
    entered, release = Event(), Event()
    api = API()
    plain = api.call
    def blocking(*args, **kwargs):
        receipt = plain(*args, **kwargs)
        if len(api.calls) > 1:
            if len(api.calls) == 3:
                entered.set()
            assert release.wait(10), "fixture release not received"
        return receipt
    api.call = blocking
    outcome, errors = [], []
    def execute():
        try:
            outcome.append(run(root, api, workers=2))
        except BaseException as exc:
            errors.append(exc)
    thread = Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(10), "two in-flight fixture calls not reached"
        recovery.request_pause(root)
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    assert len(api.calls) == 3 and outcome[0]["status"] == "paused"
    assert len(list(root.glob("positions/*/result.json"))) == 3
    assert outcome[0]["new_costs"]["unclosed_calls"] == 0
    (root / "PAUSE").unlink()
    second = API()
    assert run(root, second, workers=2)["completed_positions"] == 8
    assert len(second.calls) == 5


def test_signal_requests_pause_and_restores_handler(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path, count=2), root)
    api = API()
    plain, before = api.call, signal.getsignal(signal.SIGTERM)
    def interrupted(*args, **kwargs):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return plain(*args, **kwargs)
    api.call = interrupted
    result = run(root, api)
    assert result["status"] == "paused" and len(api.calls) == 1
    assert result["completed_positions"] == 1 and signal.getsignal(signal.SIGTERM) == before


def test_keyboardinterrupt_not_swallowed_and_open_call_cannot_retry(tmp_path):
    root = tmp_path / "retry"
    recovery.prepare(original(tmp_path), root)
    api = API()
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    api.call = interrupted
    with pytest.raises(KeyboardInterrupt):
        run(root, api)
    with pytest.raises(ValueError, match="Interrupted recovery"):
        run(root, API())


def test_timeout_override_keeps_148_never_submitted_and_inherits_timeout_unknown(tmp_path):
    parent, value, _ = parent_recovery(tmp_path, count=149)
    author_parent_position(parent, value, 0, "timeout")
    child = tmp_path / "read300"
    result = recovery.prepare_resume(parent, child, read_timeout_seconds=300)
    frozen = read_json(child / "protocol.json", sealed=True)
    assert result["positions"] == 148 and result["inherited_excluded_positions"] == 1
    assert frozen["transport_override"] == {"read_timeout_seconds": 300}
    assert frozen["inherited"]["counts"]["korbench"] == {"excluded_positions": 1, "completed": 1, "score_unknown": 1}
    for new, old in zip(frozen["positions"], value["positions"][1:]):
        assert {k: v for k, v in new.items() if k != "recovery_service"} == old
        assert new["old_request"]["service"]["timeout_seconds"]["read"] == 120
        assert recovery._expected(new)["service"]["timeout_seconds"]["read"] == 300
        assert recovery._expected(new)["key"] == recovery._expected(old)["key"]
        assert digest(recovery._expected(new)) != digest(recovery._expected(old))
    wrong = API()
    with pytest.raises(ValueError, match="Model service differs"):
        run(child, wrong)
    assert not wrong.calls
    api = API()
    api.service = recovery._with_read_timeout(api.service, 300)
    plain = api.call
    def pause_after_response(*args, **kwargs):
        receipt = plain(*args, **kwargs)
        recovery.request_pause(child)
        return receipt
    api.call = pause_after_response
    report = run(child, api)
    assert report["status"] == "paused" and report["completed_positions"] == 1
    assert len(api.calls) == 1 and report["eligible_positions"] == 148
    assert report["transport_override"] == {"read_timeout_seconds": 300}
    call_record = read_json(next(child.glob("positions/*/call.json")), sealed=True)
    assert call_record["receipt"]["request"] == recovery._expected(frozen["positions"][0])
    grandchild = tmp_path / "continued300"
    assert recovery.prepare_resume(child, grandchild)["positions"] == 147
    continued = read_json(grandchild / "protocol.json", sealed=True)
    assert continued["transport_override"] == {"read_timeout_seconds": 300}
    assert continued["positions"] == frozen["positions"][1:]


def test_undeclared_or_excess_service_changes_are_rejected(tmp_path):
    parent, _, _ = parent_recovery(tmp_path, count=2)
    child = tmp_path / "read300"
    recovery.prepare_resume(parent, child, read_timeout_seconds=300)
    value = read_json(child / "protocol.json", sealed=True)
    value.pop("record_hash")
    value["positions"][0]["recovery_service"]["stream"] = True
    (child / "protocol.json").write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="declared transport override"):
        recovery.report(child)


def test_invalid_timeout_override_does_not_create_child(tmp_path):
    parent, _, _ = parent_recovery(tmp_path, count=2)
    child = tmp_path / "invalid"
    with pytest.raises(ValueError, match="Read timeout"):
        recovery.prepare_resume(parent, child, read_timeout_seconds=601)
    assert not child.exists()


def cache_completed_calls(root):
    """The offline API does not persist its own cache; author that second copy."""
    for path in root.glob("positions/*/call.json"):
        receipt = read_json(path, sealed=True)["receipt"]
        write_json(root / "api/calls" / (receipt["request_hash"] + ".json"), receipt)


def completed_budget_parent(tmp_path, *, states=("length", "complete", "timeout"), version=None, benchmark="korbench"):
    root = tmp_path / "parent8192"
    recovery.prepare(original(tmp_path, count=len(states), benchmark=benchmark), root)
    if version is not None:
        value = read_json(root / "protocol.json", sealed=True)
        value.pop("record_hash")
        value["version"] = version
        (root / "protocol.json").write_text(json.dumps(seal(value)))
    api = API()
    plain = api.call
    def authored(*args, **kwargs):
        state = states[len(api.calls)]
        api.finish = "length" if state == "length" else "stop"
        receipt = plain(*args, **kwargs)
        if state == "timeout":
            receipt.update(ok=False, response="", status=None, finish_reason=None,
                           error_type="timeout", usage={}, http_attempt_count=3)
        return receipt
    api.call = authored
    assert run(root, api)["status"] == "completed"
    cache_completed_calls(root)
    return root, read_json(root / "protocol.json", sealed=True)


@pytest.mark.parametrize("version", ["truncation-recovery-v1", "truncation-recovery-v2"])
def test_budget_selects_only_length_preserves_parent_denominator_and_single_call(tmp_path, version):
    parent, previous = completed_budget_parent(tmp_path, version=version)
    before = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    child = tmp_path / "budget32768"
    prepared = recovery.prepare_budget(parent, child, max_tokens=32768, read_timeout_seconds=600)
    assert prepared["positions"] == 1 and prepared["parent_positions"] == 3 and prepared["excluded_positions"] == 2
    value = read_json(child / "protocol.json", sealed=True)
    assert value["version"] == "truncation-recovery-v3" and value["max_logical_calls"] == 1
    slot = value["positions"][0]
    old = previous["positions"][0]
    assert slot["id"] != old["id"] and slot["parent_retry"]["position_id"] == old["id"]
    assert slot["provenance"] == old["provenance"] and slot["old_request"] == old["old_request"]
    assert slot["old_receipt"] == old["old_receipt"] and slot["skill_text"] == old["skill_text"]
    assert slot["parent_retry"]["receipt"]["request"]["max_tokens"] == 8192
    assert value["budget_parent"]["selected_retry_costs"]["logical_calls"] == 1
    assert value["budget_parent"]["summary"]["new_costs"]["reported_tokens"] is None
    assert value["transport_changed_from_parent"] and not value["pure_token_comparison"]
    api = API(finish="length")
    api.service = recovery._with_read_timeout(api.service, 600)
    result = run(child, api)
    assert result["completed_positions"] == result["eligible_positions"] == 1
    assert result["counts"]["korbench"]["score_unknown"] == 1
    assert api.calls == [(old["old_request"]["system"], old["old_request"]["user"], 32768)]
    assert run(child, api) == result and len(api.calls) == 1
    assert result["budget_parent"]["summary"]["eligible_positions"] == 3
    assert result["new_costs"]["logical_calls"] == result["parent_selected_retry_costs"]["logical_calls"] == 1
    assert result["old_selected_call_costs"]["reported_tokens"] == 4098
    assert result["parent_selected_retry_costs"]["reported_tokens"] == 8194
    assert not result["whole_benchmark_accuracy_claimed"] and not result["causal_token_effect_claimed"]
    assert not result["optimizer_resumed"] and not result["old_scores_replaced"]
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="no repeated escalation"):
        recovery.prepare_budget(child, tmp_path / "third", max_tokens=32768)


@pytest.mark.parametrize("state", ["unsubmitted", "open", "orphan", "partial", "mismatched_cache", "missing_cache", "wrong_model", "false_length"])
def test_budget_rejects_incomplete_or_inconsistent_parent_before_creating_child(tmp_path, state):
    if state in {"unsubmitted", "open"}:
        parent, previous, _ = parent_recovery(tmp_path, count=1)
        if state == "open":
            author_parent_position(parent, previous, 0, "interrupted")
    else:
        parent, previous = completed_budget_parent(tmp_path, states=("length",))
        base = parent / "positions" / previous["positions"][0]["id"]
        if state == "orphan":
            write_json(parent / "api/calls/extra.json", {"unexpected": True})
        elif state == "partial":
            write_json(base / "call.json.tmp", {"partial": True})
        elif state in {"mismatched_cache", "missing_cache"}:
            cache = next((parent / "api/calls").glob("*.json"))
            if state == "missing_cache":
                cache.unlink()
            else:
                receipt = read_json(cache)
                receipt["response"] = "changed"
                cache.write_text(json.dumps(receipt))
        else:
            call = read_json(base / "call.json", sealed=True)
            call.pop("record_hash")
            if state == "wrong_model":
                call["receipt"]["returned_model"] = "another-model"
            else:
                call["receipt"].update(status=503, error_type="timeout")
            call = seal(call)
            (base / "call.json").write_text(json.dumps(call))
            row = read_json(base / "result.json", sealed=True)
            row.pop("record_hash")
            row["call_hash"] = call["record_hash"]
            (base / "result.json").write_text(json.dumps(seal(row)))
            cache = parent / "api/calls" / (call["receipt"]["request_hash"] + ".json")
            cache.write_text(json.dumps(call["receipt"]))  # Deliberately corrupt both authored copies.
    child = tmp_path / "budget32768"
    with pytest.raises(ValueError):
        recovery.prepare_budget(parent, child, max_tokens=32768)
    assert not child.exists()


def test_budget_rejects_active_parent_at_prepare_and_run(tmp_path):
    parent, _ = completed_budget_parent(tmp_path, states=("length",))
    child = tmp_path / "budget32768"
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        recovery.prepare_budget(parent, child, max_tokens=32768)
    recovery.prepare_budget(parent, child, max_tokens=32768)
    api = API()
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        run(child, api)
    assert not api.calls


@pytest.mark.parametrize("changed", ["parent_receipt", "parent_source", "new_trace", "slot_budget", "slot_prompt"])
def test_budget_parent_hashes_roster_and_slot_binding_block_calls(tmp_path, monkeypatch, changed):
    parent, previous = completed_budget_parent(tmp_path, states=("length",))
    child = tmp_path / "budget32768"
    recovery.prepare_budget(parent, child, max_tokens=32768)
    if changed == "parent_receipt":
        path = next(parent.glob("positions/*/call.json"))
        path.write_text(path.read_text() + "\n")
    elif changed == "parent_source":
        original_sha = recovery._sha
        target = next(iter(previous["recovery_sources"]))
        monkeypatch.setattr(recovery, "_sha", lambda p: "0" * 64 if str(p) == target else original_sha(p))
    elif changed == "new_trace":
        write_json(parent / "positions" / previous["positions"][0]["id"] / "extra.json", {"late": True})
    else:
        path = child / "protocol.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        slot = value["positions"][0]
        if changed == "slot_budget":
            slot["recovery_max_tokens"] = 16000
        else:
            slot["old_request"]["system"] = "changed"
            slot["id"] = digest({k: v for k, v in slot.items() if k != "id"})
        path.write_text(json.dumps(seal(value)))
    api = API()
    with pytest.raises(ValueError):
        run(child, api)
    assert not api.calls


def test_budget_abc_lineage_preserves_unknowns_and_locks_all_ancestors(tmp_path):
    parent, previous, _ = parent_recovery(tmp_path, count=5)
    author_parent_position(parent, previous, 0, "complete")
    author_parent_position(parent, previous, 1, "interrupted")
    middle = tmp_path / "B"
    recovery.prepare_resume(parent, middle)
    with output_lock(middle):
        pass
    middle_value = read_json(middle / "protocol.json", sealed=True)
    author_parent_position(middle, middle_value, 0, "timeout")
    latest = tmp_path / "C"
    recovery.prepare_resume(middle, latest, read_timeout_seconds=300)
    api = API(finish="length")
    api.service = recovery._with_read_timeout(api.service, 300)
    assert run(latest, api)["completed_positions"] == 2
    cache_completed_calls(latest)
    child = tmp_path / "D"
    recovery.prepare_budget(latest, child, max_tokens=32768, read_timeout_seconds=600)
    report = recovery.report(child)
    summary = report["budget_parent"]["summary"]
    assert summary["eligible_positions"] == 2
    assert summary["inherited"]["eligible_positions"] == 3
    assert summary["inherited"]["retry_costs"]["reported_tokens"] is None
    assert summary["inherited"]["prior_inherited"]["eligible_positions"] == 5
    assert summary["inherited"]["prior_inherited"]["retry_costs"]["unclosed_calls"] == 1
    api = API()
    api.service = recovery._with_read_timeout(api.service, 600)
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        run(child, api)
    assert not api.calls
    write_json(parent / "positions" / previous["positions"][4]["id"] / "late.json", {"late": True})
    with pytest.raises(ValueError, match="roster changed"):
        run(child, api)
    assert not api.calls


def test_budget_new_round_health_pause_and_resume_keep_budget(tmp_path):
    parent, _ = completed_budget_parent(tmp_path, states=("length", "length", "length"))
    child = tmp_path / "budget32768"
    recovery.prepare_budget(parent, child, max_tokens=32768)
    api = API()
    api._initial_ready = lambda receipt: False
    with pytest.raises(ValueError, match="remaining positions not submitted"):
        run(child, api, workers=3)
    assert len(api.calls) == 1 and api.calls[0][2] == 32768
    continuation = tmp_path / "continued32768"
    recovery.prepare_resume(child, continuation)
    protocol = read_json(continuation / "protocol.json", sealed=True)
    assert protocol["version"] == "truncation-recovery-v3" and protocol["max_tokens"] == 32768
    recovery.request_pause(continuation)
    api = API()
    assert run(continuation, api)["status"] == "paused" and not api.calls
    (continuation / "PAUSE").unlink()
    assert run(continuation, api)["completed_positions"] == 2
    assert len(api.calls) == 2 and all(c[2] == 32768 for c in api.calls)


def test_budget_resume_transport_change_rebinds_slot_without_changing_lineage(tmp_path):
    parent, _ = completed_budget_parent(tmp_path, states=("length", "length"))
    child = tmp_path / "budget32768"
    recovery.prepare_budget(parent, child, max_tokens=32768, read_timeout_seconds=600)
    api = API()
    api.service = recovery._with_read_timeout(api.service, 600)
    api._initial_ready = lambda receipt: False
    with pytest.raises(ValueError, match="remaining positions not submitted"):
        run(child, api)
    continuation = tmp_path / "continued32768"
    recovery.prepare_resume(child, continuation, read_timeout_seconds=120)
    old = read_json(child / "protocol.json", sealed=True)["positions"][1]
    slot = read_json(continuation / "protocol.json", sealed=True)["positions"][0]
    assert slot["id"] != old["id"] and slot["parent_retry"] == old["parent_retry"]
    api = API()
    result = run(continuation, api)
    assert result["completed_positions"] == 1 and api.calls[0][2] == 32768
    assert not result["transport_changed_from_parent"]


@pytest.mark.parametrize("cap", [8192, 16000, 32769, True])
def test_budget_only_explicit_32768_is_allowed(tmp_path, cap):
    parent, _ = completed_budget_parent(tmp_path, states=("length",))
    child = tmp_path / "budget32768"
    with pytest.raises(ValueError, match="max_tokens=32768"):
        recovery.prepare_budget(parent, child, max_tokens=cap)
    assert not child.exists()


def test_budget_cli_flags_are_scoped_and_timeout_checked(tmp_path, capsys):
    parent, _ = completed_budget_parent(tmp_path, states=("length",))
    child = tmp_path / "budget32768"
    with pytest.raises(ValueError, match="Token budget changes require prepare-budget"):
        recovery.main(["run", "--output", str(parent), "--max-tokens", "32768"])
    with pytest.raises(ValueError, match="Read timeout"):
        recovery.prepare_budget(parent, child, max_tokens=32768, read_timeout_seconds=601)
    assert not child.exists()
    assert recovery.main(["prepare-budget", "--parent", str(parent), "--output", str(child),
                          "--max-tokens", "32768", "--read-timeout", "600"]) == 0
    assert json.loads(capsys.readouterr().out)["positions"] == 1


def test_budget_alf_stays_exact_call_only_without_episode_score(tmp_path):
    parent, _ = completed_budget_parent(tmp_path, states=("length",), benchmark="alfworld")
    child = tmp_path / "budget32768"
    recovery.prepare_budget(parent, child, max_tokens=32768)
    def forbidden(*args, **kwargs):
        raise AssertionError("ALF environment must not be recreated")
    api = API(response="<action>look</action>")
    result = recovery.run(child, fixture_api=api, fixture_solve=forbidden, fixture_score=forbidden)
    assert result["alfworld_episode_scores_recovered"] == 0
    assert result["counts"]["alfworld"]["response_available"] == result["counts"]["alfworld"]["score_unknown"] == 1


def completed_environment_parent(tmp_path, *, states=("length", "complete", "timeout")):
    parent, _ = completed_budget_parent(tmp_path, states=("length",) * len(states))
    root = tmp_path / "D"
    recovery.prepare_budget(parent, root, max_tokens=32768, read_timeout_seconds=600)
    api = API()
    api.service = recovery._with_read_timeout(api.service, 600)
    plain = api.call
    def authored(*args, **kwargs):
        state = states[len(api.calls)]
        api.finish = "length" if state == "length" else "stop"
        receipt = plain(*args, **kwargs)
        if state == "timeout":
            receipt.update(ok=False, response="", status=None, finish_reason=None,
                           error_type="timeout", usage={}, http_attempt_count=3)
        return receipt
    api.call = authored
    assert run(root, api)["status"] == "completed"
    cache_completed_calls(root)
    return root, read_json(root / "protocol.json", sealed=True)


@pytest.mark.parametrize("reason, cap", [("length", 65536), ("timeout", 32768)])
def test_environment_split_recovery_preserves_parent_and_actual_budgets(tmp_path, reason, cap):
    parent, previous = completed_environment_parent(tmp_path)
    before = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    child = tmp_path / "E"
    prepared = recovery.prepare_environment(parent, child, reason=reason,
                                             read_timeout_seconds=300, stream_wall_seconds=1800)
    assert prepared["positions"] == 1 and prepared["excluded_positions"] == 2
    frozen = read_json(child / "protocol.json", sealed=True)
    slot = frozen["positions"][0]
    old = previous["positions"][0 if reason == "length" else 2]
    assert slot["parent_retry"] == old["parent_retry"]
    assert slot["environment_retry"]["position_id"] == old["id"]
    assert slot["old_request"] == old["old_request"] and slot["provenance"] == old["provenance"]
    api = API()
    api.service = recovery._environment_service(old["recovery_service"], read_timeout_seconds=300, stream_wall_seconds=1800)
    report = run(child, api)
    assert report["eligible_positions"] == report["completed_positions"] == 1
    assert api.calls[0][2] == cap and len(api.calls) == 1
    assert report["selection"] == "prior_terminal_" + reason
    assert report["environment_parent"]["eligible_positions"] == 3
    assert not report["old_scores_replaced"] and not report["optimizer_resumed"]
    assert run(child, api) == report and len(api.calls) == 1
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    if reason == "timeout":
        assert report["parent_selected_retry_costs"]["reported_tokens"] is None
    with pytest.raises(ValueError, match="same directory"):
        recovery.prepare_resume(child, tmp_path / "forbiddenfork")
    with pytest.raises(ValueError, match="no automatic escalation"):
        recovery.prepare_environment(child, tmp_path / "forbiddenloop", reason=reason,
                                     read_timeout_seconds=300, stream_wall_seconds=1800)


def test_environment_excludes_completed_wrong_answers_and_native_unknowns(tmp_path):
    parent, previous = completed_environment_parent(tmp_path)
    # Change a complete fixture's scorer result to failure; still not eligible.
    slot = previous["positions"][1]
    path = parent / "positions" / slot["id"] / "result.json"
    row = read_json(path, sealed=True)
    row.pop("record_hash")
    row["score"] = {"status": "fail", "score": 0., "metrics": {}, "reason": "authored_wrong_answer"}
    path.write_text(json.dumps(seal(row)))
    child = tmp_path / "E"
    assert recovery.prepare_environment(parent, child, reason="timeout", read_timeout_seconds=300,
                                         stream_wall_seconds=1800)["positions"] == 1
    native = {"prediction": {"status": "unknown", "reason": "native_timeout"}, "score": {"status": "unknown"}}
    receipt = {"ok": False, "error_type": "timeout", "finish_reason": None, "response": "", "http_attempt_count": 3}
    assert not recovery._environment_eligible(native, receipt, "timeout", slot)


@pytest.mark.parametrize("corruption", ["partial", "missing_cache", "open", "prompt", "budget", "service", "ancestor_roster"])
def test_environment_binding_rejects_corruption(tmp_path, corruption):
    parent, previous = completed_environment_parent(tmp_path)
    child = tmp_path / "E"
    if corruption == "partial":
        write_json(parent / "api/calls/partial.json.tmp", {"partial": True})
    if corruption == "missing_cache":
        next((parent / "api/calls").glob("*.json")).unlink()
    if corruption == "open":
        next(parent.glob("positions/*/result.json")).unlink()
    if corruption in {"partial", "missing_cache", "open"}:
        with pytest.raises(ValueError):
            recovery.prepare_environment(parent, child, reason="length", read_timeout_seconds=300, stream_wall_seconds=1800)
        assert not child.exists()
        return
    recovery.prepare_environment(parent, child, reason="length", read_timeout_seconds=300, stream_wall_seconds=1800)
    if corruption == "ancestor_roster":
        ancestor = Path(previous["budget_parent"]["parent_root"])
        write_json(ancestor / "api/calls/unbound.json", {"late": True})
    else:
        path = child / "protocol.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        slot = value["positions"][0]
        if corruption == "prompt":
            slot["old_request"]["system"] = "not the original prompt"
        elif corruption == "budget":
            slot["recovery_max_tokens"] = 131072
        else:
            slot["recovery_service"]["reasoning_effort"] = "max"
        slot["id"] = digest({k: v for k, v in slot.items() if k != "id"})
        path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError):
        recovery.report(child)


def test_environment_pause_and_all_ancestor_locks(tmp_path):
    parent, previous = completed_environment_parent(tmp_path, states=("length", "length"))
    child = tmp_path / "E"
    recovery.prepare_environment(parent, child, reason="length", read_timeout_seconds=300, stream_wall_seconds=1800)
    api = API()
    api.service = recovery._environment_service(previous["positions"][0]["recovery_service"],
                                                read_timeout_seconds=300, stream_wall_seconds=1800)
    ancestor = Path(previous["budget_parent"]["parent_root"])
    with output_lock(ancestor), pytest.raises(ValueError, match="active writer"):
        run(child, api)
    assert not api.calls
    recovery.request_pause(child)
    assert run(child, api)["status"] == "paused" and not api.calls
    (child / "PAUSE").unlink()
    assert run(child, api)["completed_positions"] == 2
    assert all(c[2] == 65536 for c in api.calls)


def test_environment_cli_requires_explicit_transport(tmp_path, capsys):
    parent, _ = completed_environment_parent(tmp_path)
    child = tmp_path / "E"
    with pytest.raises(ValueError, match="requires parent"):
        recovery.main(["prepare-environment", "--parent", str(parent), "--output", str(child)])
    assert recovery.main(["prepare-environment", "--parent", str(parent), "--output", str(child),
                          "--reason", "timeout", "--read-timeout", "300", "--stream-wall", "1800"]) == 0
    assert json.loads(capsys.readouterr().out)["max_tokens"] == 32768


def completed_ceiling_parent(tmp_path, *, reason="length", states=("length", "complete")):
    parent_states = (reason,) * len(states)
    # A real initial timeout stops dispatch, so include a successful D health
    # position before the F stratum; it is excluded when preparing F.
    if reason == "timeout":
        parent_states = ("complete",) + parent_states
    parent, previous = completed_environment_parent(tmp_path, states=parent_states)
    root = tmp_path / "v4"
    recovery.prepare_environment(parent, root, reason=reason, read_timeout_seconds=300, stream_wall_seconds=1800)
    api = API()
    api.service = recovery._environment_service(previous["positions"][0]["recovery_service"],
                                                read_timeout_seconds=300, stream_wall_seconds=1800)
    plain = api.call
    def authored(*args, **kwargs):
        state = states[len(api.calls)]
        api.finish = "length" if state == "length" else "stop"
        receipt = plain(*args, **kwargs)
        receipt["stream_complete"] = True
        return receipt
    api.call = authored
    assert run(root, api)["status"] == "completed"
    cache_completed_calls(root)
    return root, read_json(root / "protocol.json", sealed=True)


@pytest.mark.parametrize("reason,old_cap", [("length", 65536), ("timeout", 32768)])
def test_ceiling_single_escalation_keeps_prompt_receipts_and_closed_results(tmp_path, reason, old_cap):
    parent, previous = completed_ceiling_parent(tmp_path, reason=reason)
    before = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    child = tmp_path / "ceiling"
    prepared = recovery.prepare_ceiling(parent, child)
    assert prepared["positions"] == 1 and prepared["excluded_positions"] == 1
    frozen = read_json(child / "protocol.json", sealed=True)
    assert frozen["version"] == recovery.CEILING_VERSION
    old, new = previous["positions"][0], frozen["positions"][0]
    assert new["old_request"] == old["old_request"] and new["parent_retry"] == old["parent_retry"]
    assert new["environment_retry"]["parent_root"] == str(parent)
    assert frozen["environment_ancestors"][0]["protocol_hash"] == previous["environment_parent"]["protocol_hash"]
    api = API()
    api.service = recovery._environment_service(old["recovery_service"], read_timeout_seconds=300, stream_wall_seconds=3600)
    report = run(child, api)
    assert report["completed_positions"] == 1 and api.calls[0][2] == 131072
    assert report["budget_change"] == {"from": old_cap, "to": 131072}
    assert report["environment_parent"]["eligible_positions"] == 2
    assert not report["old_scores_replaced"] and not report["optimizer_resumed"]
    assert run(child, api) == report and len(api.calls) == 1
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="no repeated escalation"):
        recovery.prepare_ceiling(child, tmp_path / "loop")
    with pytest.raises(ValueError, match="same directory"):
        recovery.prepare_resume(child, tmp_path / "resume_fork")


@pytest.mark.parametrize("corruption", ["open", "missing_cache", "partial", "prompt", "wall", "reason"])
def test_ceiling_fails_closed_for_corrupt_or_unclosed_parent(tmp_path, corruption):
    parent, previous = completed_ceiling_parent(tmp_path)
    child = tmp_path / "ceiling"
    if corruption == "open":
        next(parent.glob("positions/*/result.json")).unlink()
    if corruption == "missing_cache":
        next(parent.glob("api/calls/*.json")).unlink()
    if corruption == "partial":
        write_json(parent / "api/calls/incomplete.json.tmp", {"partial": True})
    if corruption in {"open", "missing_cache", "partial"}:
        with pytest.raises(ValueError):
            recovery.prepare_ceiling(parent, child)
        assert not child.exists()
        return
    recovery.prepare_ceiling(parent, child)
    path = child / "protocol.json"
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    if corruption == "prompt":
        value["positions"][0]["old_request"]["user"] = "different"
        value["positions"][0]["id"] = digest({k: v for k, v in value["positions"][0].items() if k != "id"})
    elif corruption == "wall":
        value["transport_override"]["stream_wall_seconds"] = 1800
    else:
        value["selection_reason"] = "timeout"
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError):
        recovery.report(child)


def test_ceiling_cli_fixed_budget_and_pause_ancestor_locks(tmp_path, capsys):
    parent, previous = completed_ceiling_parent(tmp_path)
    child = tmp_path / "ceiling"
    assert recovery.main(["prepare-ceiling", "--parent", str(parent), "--output", str(child)]) == 0
    assert json.loads(capsys.readouterr().out)["max_tokens"] == 131072
    api = API()
    api.service = recovery._environment_service(previous["positions"][0]["recovery_service"],
                                                read_timeout_seconds=300, stream_wall_seconds=3600)
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        run(child, api)
    recovery.request_pause(child)
    assert run(child, api)["status"] == "paused" and not api.calls
    (child / "PAUSE").unlink()
    assert run(child, api)["completed_positions"] == 1
