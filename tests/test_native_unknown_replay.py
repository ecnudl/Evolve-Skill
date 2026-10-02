"""Offline engineering fixtures: no provider or untrusted program execution."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import native_unknown_worker as worker
from scripts import replay_native_unknowns as replay
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_checkpoint, read_json, write_json
from skillopt.continual_eval.datasets import load_panel
from skillopt.continual_eval.fixtures import fixture_panel
from skillopt.validator_pilot.api import digest


def setup(tmp_path, benchmark="bigcodebench", code="def task_func():\n    return 1", reasons=None):
    parent, source, output = tmp_path / "old", Path(__file__).resolve().parents[1], tmp_path / "new"
    lock = tmp_path / "native.lock"
    lock.touch()
    panel = fixture_panel(benchmark)
    panel["tasks"][0]["partition"] = "development"
    if benchmark == "spreadsheetbench":
        path = tmp_path / "input.xlsx"
        path.write_bytes(b"opaque fixture public workbook; never executed")
        panel["tasks"][0]["public"]["input_files"] = [str(path)]
    path = tmp_path / "panel.json"
    write_json(path, panel)
    panel = load_panel(path)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
        "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                      "initial_health_policy": "completed_response_v1"}}
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 2, "model": model,
        "panels": {b: str(path) if b == benchmark else None for b in BENCHMARKS},
        "runtime": {benchmark: {}}, "project_disjoint": False, "exposure_manifest": None}
    plan = freeze_plan(config, parent)
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    service = {"provider": "fixture", "model": "fixture"}
    write_json(parent / "model_service.json", seal(service))

    class API:
        model = "fixture"

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"system": system, "user": user, "kind": kind, "key": key, "max_tokens": max_tokens,
                "repeat": repeat, "model": self.model, "service": self.service}
            value = {"request": request, "request_hash": digest(request), "ok": True, "status": 200,
                "response": code, "finish_reason": "stop", "stream_complete": True, "returned_model": self.model,
                "http_attempt_count": 1, "usage": {"prompt_tokens": 3, "completion_tokens": 4}}
            write_json(parent / "api/calls" / (value["request_hash"] + ".json"), value)
            return value

    api = API()
    api.service = service
    for repeat in range(2):
        base, request = runner.position(parent, cp, benchmark, panel["tasks"][0], repeat)
        runner.PositionCalls(api, base, request, 65536, 1)("public system", "public input")
    reasons = reasons or ["native_exception:AttributeError", "output.xlsx_not_produced"]
    counter = iter(range(2))

    def solve(*args, **kwargs):
        reason = reasons[next(counter)]
        output_value = code if benchmark == "bigcodebench" else {"code": code, "cases": [
            {"status": "missing_output" if reason == "output.xlsx_not_produced" else "unknown", "reason": reason}]}
        return {"status": "available", "output": output_value, "reason": "fixture"}

    runner.generate(parent, method="no_skill", history="h0", stage=0, benchmark=benchmark, fixture_solve=solve)
    runner.score_checkpoint(parent, method="no_skill", history="h0", stage=0, benchmark=benchmark,
        fixture_score=lambda *a, **k: {"status": "unknown", "score": None, "metrics": {}, "reason": "native_timeout"})
    runner.report(parent)
    return parent, source, output, lock


def test_closed_bcb_replay_once_unchanged_source_artifacts(tmp_path):
    parent, source, output, lock = setup(tmp_path)
    old = {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    protocol = replay.prepare(parent, source, output, lock)
    seen = []

    def execute(benchmark, task, prediction, item, runtime):
        seen.append(prediction["output"])
        return {"status": "fail", "score": 0.0, "reason": "fixture", "metrics": {}}

    result = replay.run(output, lock, fixture_execute=execute)
    assert result["counts"] == {"fail": 2} and result["new_model_calls"] == 0
    assert len(seen) == 2 and len(set(seen)) == 1
    assert replay.run(output, lock, fixture_execute=execute) == result and len(seen) == 2
    assert old == {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    assert "return 1" not in json.dumps(protocol)
    assert result["deployment_authorized"] is False


def test_sheet_selects_generation_only_not_recalc(tmp_path):
    parent, source, output, lock = setup(tmp_path, "spreadsheetbench", reasons=["native_exception:TypeError", "native_timeout"])
    value = replay.prepare(parent, source, output, lock)
    assert len(value["snapshot"]["selected"]) == 1
    seen = []

    def execute(benchmark, task, prediction, item, runtime):
        seen.append(item)
        return {"status": "missing_output", "reason": "output.xlsx_not_produced"}

    result = replay.run(output, lock, fixture_execute=execute)
    assert result["counts"] == {"missing_output": 1} and result["selected_positions"] == 1
    assert seen[0]["case"] == 0


def test_syntax_error_is_static_never_executes(tmp_path):
    parent, source, output, lock = setup(tmp_path, "spreadsheetbench", code="def broken(:\n    pass")
    replay.prepare(parent, source, output, lock)
    result = replay.run(output, lock, fixture_execute=lambda *a: pytest.fail("Syntax error must not execute"))
    assert result["counts"] == {"invalid_program": 2} and result["container_calls"] == 0
    rows = [read_json(p, sealed=True) for p in (output / "records").glob("*.json")]
    assert all(r["result"]["diagnostic"]["line"] == 1 for r in rows)


@pytest.mark.parametrize("target", ["receipt", "score", "source", "open_call", "input"])
def test_preparation_rejects_changed_or_unclosed_evidence(tmp_path, target):
    parent, source, output, lock = setup(tmp_path, "spreadsheetbench")
    if target == "source":
        source = tmp_path / "wrong_source"
    elif target == "open_call":
        write_json(next((parent / "predictions").iterdir()) / "call_intents/extra.json", seal({"test": True}))
    elif target == "input":
        replay.prepare(parent, source, output, lock)
        (tmp_path / "input.xlsx").write_bytes(b"changed")
        with pytest.raises(ValueError, match="Panel changed|Frozen parent"):
            replay.check(output)
        return
    else:
        pattern = "predictions/*/calls/*.json" if target == "receipt" else "host_only/scores/*.json"
        next(parent.glob(pattern)).write_text("{}")
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        replay.prepare(parent, source, output, lock)
    assert not output.exists()


def test_open_execution_is_not_retried(tmp_path):
    parent, source, output, lock = setup(tmp_path)
    protocol = replay.prepare(parent, source, output, lock)
    item = protocol["snapshot"]["selected"][0]
    write_json(output / "intents" / (digest(item) + ".json"), seal({"protocol_hash": protocol["record_hash"], "item": item}))
    with pytest.raises(ValueError, match="do not retry"):
        replay.run(output, lock, fixture_execute=lambda *a: pytest.fail("Retry"))


def test_published_result_cannot_be_resealed(tmp_path):
    parent, source, output, lock = setup(tmp_path)
    replay.prepare(parent, source, output, lock)
    def scorer(*args):
        return {"status": "unknown", "score": None, "metrics": {}, "reason": "fixture"}
    replay.run(output, lock, fixture_execute=scorer)
    path = next((output / "records").glob("*.json"))
    row = read_json(path, sealed=True)
    row.pop("record_hash")
    row["result"].update(status="pass", score=1.0)
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="Published diagnostic"):
        replay.run(output, lock, fixture_execute=scorer)


def test_wrong_lock_and_overlap_blocked(tmp_path):
    parent, source, output, lock = setup(tmp_path)
    with pytest.raises(ValueError, match="independent"):
        replay.prepare(parent, source, parent / "child", lock)
    replay.prepare(parent, source, output, lock)
    with pytest.raises(ValueError, match="Shared native lock"):
        replay.run(output, tmp_path / "typo", fixture_execute=lambda *a: None)
    assert not (tmp_path / "typo").exists()


def test_wrapper_refuses_host(monkeypatch):
    monkeypatch.delenv("NATIVE_UNKNOWN_CONTAINER", raising=False)
    with pytest.raises(SystemExit, match="Container-only"):
        worker.main()


def test_wrapper_filters_private_fields():
    with pytest.raises(ValueError, match="public-input"):
        worker.perform({"operation": "spreadsheet_generate", "code": "pass", "input_base64": "", "test": "HIDDEN"}, None)


def test_exception_diagnostic_omits_messages_paths_locals():
    sentinel = "PRIVATE_LOCAL_SENTINEL"
    try:
        raise TypeError("SECRET_EXCEPTION_MESSAGE " + sentinel)
    except TypeError as exc:
        value = worker.exception_evidence(exc)
    serialized = json.dumps(value)
    assert "PRIVATE_LOCAL_SENTINEL" not in serialized and "SECRET_EXCEPTION_MESSAGE" not in serialized
    assert str(Path(__file__)) not in serialized
    assert value["phase"] == "wrapper_or_input" and value["exception_type"] == "TypeError"
    assert value["messages_and_locals_retained"] is False


def test_wrapper_performs_frozen_entry_once_and_adds_diagnostic():
    calls = []

    def perform(request):
        calls.append(request)
        raise ValueError("should not leak")

    request = {"operation": "spreadsheet_generate", "code": "pass", "input_base64": ""}
    result = worker.perform(request, SimpleNamespace(perform=perform))
    assert calls == [request] and result["status"] == "unknown"
    assert result["diagnostic"]["exception_type"] == "ValueError" and "should not leak" not in json.dumps(result)


def test_wrapper_syntax_diagnostic_without_execution():
    try:
        compile("x = (", "generated.py", "exec")
    except SyntaxError as exc:
        value = worker.exception_evidence(exc)
    assert value["phase"] == "generated_compile" and value["generated_lines"] == [1]


def command_result(**updates):
    return SimpleNamespace(code=0, timed_out=False, overflow=False, unavailable=False, stdout=b"", stderr=b"", **updates)


def test_sheet_launcher_isolated_original_worker_and_cleanup(tmp_path, monkeypatch):
    native = tmp_path / "original_worker.py"
    native.write_text("# authored inert fixture\n")
    image = "sha256:" + "a" * 64
    commands = []
    monkeypatch.setattr(replay.backends, "_image_ready", lambda r: {"status": "ready", "image_id": image})
    monkeypatch.setattr(replay.shutil, "which", lambda _: "/docker")

    def bounded(command, timeout, **kwargs):
        commands.append(command)
        if "run" in command:
            mount = command[command.index("--mount") + 1]
            directory = Path(mount.split("source=", 1)[1].split(",")[0])
            assert (directory / "original_worker.py").read_bytes() == native.read_bytes()
            request = json.loads((directory / "request.json").read_text())
            assert set(request) == {"operation", "code", "input_base64"}
            return SimpleNamespace(code=0, timed_out=False, overflow=False, unavailable=False, stderr=b"",
                stdout=json.dumps({"protocol": replay.WORKER_PROTOCOL,
                    "result": {"status": "missing_output", "reason": "output.xlsx_not_produced"}}).encode())
        return command_result()

    monkeypatch.setattr(replay, "_bounded_command", bounded)
    result = replay.sheet_native({"operation": "spreadsheet_generate", "code": "pass", "input_base64": ""},
                                {"image": image, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}, native)
    assert result["cleanup_confirmed"] and result["status"] == "missing_output"
    assert all(flag in commands[0] for flag in ["--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true", "--memory=4096m", "--pids-limit=128", "--ipc=private"])
    assert commands[1][1:3] == ["rm", "--force"] and len(commands) == 2


def test_cleanup_failure_never_retains_available_result(tmp_path, monkeypatch):
    native = tmp_path / "original_worker.py"
    native.write_text("# fixture")
    image = "sha256:" + "a" * 64
    monkeypatch.setattr(replay.backends, "_image_ready", lambda r: {"status": "ready", "image_id": image})
    monkeypatch.setattr(replay.shutil, "which", lambda _: "/docker")

    def bounded(command, timeout, **kwargs):
        if "rm" in command:
            raise OSError("cleanup failed")
        return SimpleNamespace(code=0, timed_out=False, overflow=False, unavailable=False, stderr=b"",
            stdout=json.dumps({"protocol": replay.WORKER_PROTOCOL, "result": {"status": "available", "reason": "fixture"}}).encode())

    monkeypatch.setattr(replay, "_bounded_command", bounded)
    result = replay.sheet_native({"operation": "spreadsheet_generate", "code": "pass", "input_base64": ""}, {"image": image}, native)
    assert result["status"] == "unknown" and result["reason"] == "container_cleanup_unconfirmed"
    assert result["cleanup_confirmed"] is False


def test_fixture_natural_dispatch_cannot_mix(tmp_path):
    parent, source, output, lock = setup(tmp_path)
    replay.prepare(parent, source, output, lock)
    with pytest.raises(ValueError, match="Fixture dispatch"):
        replay.run(output, lock)
    assert not list((output / "intents").glob("*.json"))


def test_natural_tiny_panel_is_not_formal_data(tmp_path):
    parent, source, output, lock = setup(tmp_path)
    path = parent / "plan.json"
    plan = read_json(path, sealed=True)
    plan.pop("record_hash")
    plan["config"]["model"]["provider"] = "bigmodel"
    path.write_text(json.dumps(seal(plan)))
    with pytest.raises(ValueError, match="Full natural panel"):
        replay.prepare(parent, source, output, lock)
    assert not output.exists()


def test_unavailable_runtime_has_no_host_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(replay.backends, "_image_ready", lambda r: {"status": "unsupported", "reason": "docker_unavailable"})
    monkeypatch.setattr(replay, "_bounded_command", lambda *a, **k: pytest.fail("No execution"))
    result = replay.sheet_native({"code": "raise RuntimeError('must not run')"}, {}, tmp_path / "missing.py")
    assert result["status"] == "unknown" and result["reason"] == "docker_unavailable"
    assert result["execution_costs"]["container_calls"] == 0


@pytest.mark.parametrize("extra", [{}, {"cleanup_confirmed": True}, {"runtime_image_id": "sha256:" + "b" * 64, "cleanup_confirmed": True}])
def test_unverified_native_result_rejected(extra):
    with pytest.raises(ValueError, match="identity|image"):
        replay._validate_result({"status": "pass", "score": 1.0, "metrics": {}, "reason": "fixture", **extra},
                                "bigcodebench", False, {"image": "sha256:" + "a" * 64})
