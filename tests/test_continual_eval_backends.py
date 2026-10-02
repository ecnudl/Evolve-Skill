"""Offline authored fixtures: native wiring/isolation, NOT method effects."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from skillopt.continual_eval import backends as b


def receipt(text="<answer>Paris</answer>"):
    return {"ok": True, "response": text, "usage": {"total_tokens": 8}}


@pytest.mark.parametrize("benchmark,public", [
    ("searchqa", {"question": "Capital?", "context": ["France"]}),
    ("korbench", {"rule": "A means B", "question": "A?"}),
    ("bigcodebench", {"prompt": "Return one", "entry_point": "f"}),
])
def test_whitelist_keeps_answers_and_metadata_out_of_model(benchmark, public):
    calls = []
    def call(system, user):
        calls.append((system, user))
        return receipt()
    prediction = b.solve(benchmark, {**public, "answers": ["SECRET"], "test": "SECRET", "private": "SECRET"},
                         "FROZEN-SKILL", call)
    assert prediction["status"] == "available"
    assert len(calls) == 1
    assert "SECRET" not in str(calls)
    assert "FROZEN-SKILL" in calls[0][0]
    assert json.loads(calls[0][1]) == public


def test_nested_public_non_text_cannot_smuggle_a_private_record():
    result = b.solve("searchqa", {"question": "Q", "context": {"answer": "SECRET"}}, "", lambda *_: pytest.fail())
    assert result["reason"] == "invalid_public_contract"


@pytest.mark.parametrize("response,reason", [
    ({"ok": False}, "model_call_unavailable"),
    ({"ok": True, "response": "partial", "finish_reason": "length"}, "model_response_truncated"),
    ({"ok": False, "response": "partial", "finish_reason": "length"}, "model_response_truncated"),
    ({"ok": True, "response": ""}, "empty_or_oversized_model_response"),
    (None, "invalid_model_receipt"),
])
def test_failed_calls_retained_unknown(response, reason):
    pred = b.solve("searchqa", {"question": "Q", "context": ""}, "", lambda *_: response)
    assert pred["status"] == "unknown" and pred["reason"] == reason
    assert pred["costs"]["calls"] == 1
    assert b.score("searchqa", {}, {"answers": ["A"]}, pred)["status"] == "unknown"


def test_searchqa_reuses_native_em_f1_no_gold_returned():
    pred = {"status": "available", "output": "reason\n<answer>The Paris!</answer>"}
    result = b.score("searchqa", {}, {"answers": ["Paris"]}, pred)
    assert result["status"] == "pass" and result["score"] == 1
    assert result["metrics"]["em"] == result["metrics"]["f1"] == 1
    assert "answers" not in result["metrics"]
    assert b.score("searchqa", {}, {"answers": ["London"]}, pred)["status"] == "fail"
    assert b.score("searchqa", {}, {"answers": []}, pred)["status"] == "unknown"


def test_bigcode_test_only_enters_isolated_score_not_inference(monkeypatch):
    captured = []
    monkeypatch.setattr(b, "_native", lambda req, runtime: captured.append(req) or
                        {"status": "pass", "score": 1., "metrics": {}, "reason": "fixture"})
    public = {"prompt": "Return one", "entry_point": "f", "test": "HIDDEN"}
    pred = b.solve("bigcodebench", public, "", lambda _, user: receipt("```python\ndef f(): return 1\n```"))
    assert not captured
    result = b.score("bigcodebench", public, {"test": "HIDDEN"}, pred)
    assert result["status"] == "pass"
    assert captured[0]["test"] == "HIDDEN"
    assert captured[0]["code"] == "def f(): return 1"


def test_kor_requires_all_native_identity_and_pinned_source(tmp_path, monkeypatch):
    private = {"answer": "[[B]]", "category": "logic", "rule_id": "1", "upstream_index": "42"}
    pred = {"status": "available", "output": "[[B]]"}
    runtime = {"kor_repo": str(tmp_path)}
    for name, relative in (("eval", "eval/eval_utils.py"), ("common", "utils/common.py"),
                           ("config", "config/config_wrapper.py")):
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("raise RuntimeError('must not import on host')")
        runtime[f"kor_{name}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    captured = []
    monkeypatch.setattr(b, "_native", lambda req, runtime: captured.append(req) or
                        {"status": "pass", "score": 1., "metrics": {}, "reason": "fixture"})
    assert b.score("korbench", {}, private, pred, runtime=runtime)["status"] == "pass"
    assert captured[0]["rule_id"] == "1" and "raise RuntimeError" in captured[0]["eval_source"]
    assert b.score("korbench", {}, {"answer": "B"}, pred, runtime=runtime)["status"] == "unknown"
    runtime["kor_eval_sha256"] = "0" * 64
    assert b.score("korbench", {}, private, pred, runtime=runtime)["status"] == "unknown"


def test_no_digest_or_no_docker_never_falls_back_to_host(monkeypatch):
    monkeypatch.setattr(b.shutil, "which", lambda _: None)
    monkeypatch.setattr(b, "_bounded_command", lambda *args, **kwargs: pytest.fail("no command expected"))
    assert b._native({"operation": "bigcodebench", "code": "raise Exception"}, {})["status"] == "unknown"
    assert b._native({}, {"image": "sha256:" + "0" * 64})["reason"] == "docker_unavailable"


def _command(code=0, stdout=b"", stderr=b"", **extra):
    return SimpleNamespace(code=code, stdout=stdout, stderr=stderr, timed_out=False,
                           overflow=False, unavailable=False, **extra)


def test_native_container_policy_and_exact_cleanup(monkeypatch):
    image = "sha256:" + "a" * 64
    commands = []
    monkeypatch.setattr(b.shutil, "which", lambda _: "/usr/bin/docker")
    def run(args, *limits, **kwargs):
        commands.append(args)
        if args[1:3] == ["image", "inspect"]:
            return _command(stdout=json.dumps([{"Os": "linux", "Config": {}, "Id": image}]).encode())
        if args[1] == "run":
            root = next(arg for arg in args if arg.startswith("type=bind,source=")).split("source=", 1)[1].split(",target=", 1)[0]
            assert json.loads(Path(root, "request.json").read_text()) == {"operation": "probe", "benchmark": "bigcodebench"}
            return _command(stdout=json.dumps({"protocol": b.PROTOCOL, "result": {"status": "ready"}}).encode())
        return _command()
    monkeypatch.setattr(b, "_bounded_command", run)
    result = b._native({"operation": "probe", "benchmark": "bigcodebench"}, {"image": image})
    assert result["cleanup_confirmed"] is True
    assert result["execution_costs"]["container_calls"] == 1
    assert result["execution_costs"]["wall_seconds"] >= 0
    command = commands[1]
    for flag in ("--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL", "--pull=never"):
        assert flag in command
    assert len([a for a in command if a.startswith("type=bind,")]) == 1
    assert commands[-1][-1] == command[command.index("--name") + 1]


def test_container_cleanup_failure_and_malformed_output_are_unknown(monkeypatch):
    monkeypatch.setattr(b, "_image_ready", lambda _: {"status": "ready", "image_id": "fixture"})
    monkeypatch.setattr(b.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(b, "_bounded_command", lambda args, *a, **k:
                        _command(code=1 if args[1] == "rm" else 0, stdout=b"BAD"))
    assert b._native({}, {"image": "fixture"})["reason"] == "container_cleanup_unconfirmed"
    monkeypatch.setattr(b, "_bounded_command", lambda *a, **k: _command(stdout=b"BAD"))
    assert b._native({}, {"image": "fixture"})["reason"] == "invalid_native_receipt"


@pytest.mark.parametrize("failure_stage,exception,reason", [
    ("rm", subprocess.TimeoutExpired("docker rm", 2), "container_cleanup_unconfirmed"),
    ("rm", OSError("fixture"), "container_cleanup_unconfirmed"),
    ("run", subprocess.TimeoutExpired("docker run", 2), "native_timeout"),
    ("run", OSError("fixture"), "native_execution_unavailable"),
])
def test_native_client_reaping_exception_is_unknown_and_cleanup_still_attempted(
        monkeypatch, failure_stage, exception, reason):
    monkeypatch.setattr(b, "_image_ready", lambda _: {"status": "ready", "image_id": "fixture"})
    monkeypatch.setattr(b.shutil, "which", lambda _: "docker")
    commands = []

    def run(args, *a, **k):
        commands.append(args)
        if args[1] == failure_stage:
            raise exception
        return _command(stdout=json.dumps({"protocol": b.PROTOCOL, "result": {
            "status": "pass", "score": 1, "metrics": {}, "reason": "fixture"}}).encode())

    monkeypatch.setattr(b, "_bounded_command", run)
    result = b._native({}, {"image": "fixture"})
    assert result["status"] == "unknown" and result["score"] is None
    assert result["reason"] == reason and result["execution_costs"]["container_calls"] == 1
    assert [c[1] for c in commands] == ["run", "rm"]
    assert commands[-1][-1] == commands[0][commands[0].index("--name") + 1]


def _book(tmp_path, name, value):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active["A1"] = value
    path = tmp_path / name
    workbook.save(path)
    workbook.close()
    return str(path)


def _encoded_case(path):
    return {"status": "available", "output_base64": base64.b64encode(Path(path).read_bytes()).decode()}


def test_sheet_generated_code_never_executed_on_host_or_given_gold(tmp_path, monkeypatch):
    path = _book(tmp_path, "input.xlsx", 7)
    seen = []
    def call(system, user):
        seen.append(json.loads(user))
        return receipt("```python\nraise RuntimeError('container only')\n```")
    native = []
    monkeypatch.setattr(b, "_native", lambda req, runtime: native.append(req) or _encoded_case(path))
    pred = b.solve("spreadsheetbench", {"instruction": "Keep values", "input_files": [path, path],
                                      "test_files": ["SECRET"], "answer_position": "A1"}, "", call)
    assert pred["status"] == "available"
    assert len(seen) == 1 and len(native) == 2
    assert all(set(req) == {"operation", "code", "input_base64"} for req in native)
    assert "SECRET" not in str(seen) + str(native)
    assert seen[0]["required_answer_position"] == "A1"
    assert all(req["code"].startswith("raise RuntimeError") for req in native)


def test_sheet_native_hard_soft_and_unknown_caches(tmp_path):
    gold = _book(tmp_path, "gold.xlsx", 7)
    wrong = _book(tmp_path, "wrong.xlsx", 8)
    formula = _book(tmp_path, "formula.xlsx", "=7")
    private = {"test_files": [gold, gold], "answer_position": "A1"}
    def score(cases):
        return b.score("spreadsheetbench", {"answer_position": "A1"}, private,
                       {"status": "available", "output": {"cases": cases}})
    result = score([_encoded_case(gold), _encoded_case(wrong)])
    assert result["score"] == 0 and result["metrics"]["soft_score"] == .5
    result = score([_encoded_case(gold), _encoded_case(formula)])
    assert result["status"] == "unknown" and result["metrics"]["soft_score"] is None
    assert result["metrics"]["soft_score_lower_bound"] == .5
    assert score([_encoded_case(gold)])["reason"] == "spreadsheet_case_count_mismatch"


def test_sheet_output_contract_cannot_differ_from_scoring_region():
    result = b.score("spreadsheetbench", {"answer_position": "A1"}, {"answer_position": "B1"},
                     {"status": "available", "output": {}})
    assert result["status"] == "unknown" and result["reason"] == "public_scoring_region_mismatch"


def test_alfworld_fresh_environment_public_observations_only_and_closed(monkeypatch):
    envs, prompts = [], []
    class Env:
        closed = False
        def reset(self):
            return ["You are in kitchen"], None, [{"admissible_commands": ["look"], "expert_plan": "SECRET"}]
        def step(self, actions):
            assert actions == ["look"]
            return ["Done"], None, [1], [True], [{"won": True, "expert_plan": "SECRET"}]
        def close(self):
            self.closed = True
    def fresh(*args):
        env = Env()
        envs.append(env)
        return env
    monkeypatch.setattr(b, "_new_alfworld", fresh)
    def call(system, user):
        prompts.append(user)
        return receipt("<action>look</action>")
    for _ in range(2):
        pred = b.solve("alfworld", {"game_file": "fixture", "expert_plan": "SECRET"}, "", call)
        assert b.score("alfworld", {}, {}, pred)["score"] == 1
    assert len(envs) == 2 and all(env.closed for env in envs)
    assert "SECRET" not in str(prompts)


def test_alfworld_retains_public_goal_beyond_history_window_without_cross_episode_leak(monkeypatch):
    prompts, envs = [], []

    class Env:
        def __init__(self, episode):
            self.episode, self.steps, self.closed = episode, 0, False

        def reset(self):
            return [f"Your task is to complete public goal {self.episode}."], None, [
                {"admissible_commands": ["look"], "expert_plan": "HIDDEN_EXPERT"}]

        def step(self, actions):
            assert actions == ["look"]
            self.steps += 1
            return [f"Observation {self.steps}"], None, [0], [self.steps == 8], [
                {"won": self.steps == 8, "admissible_commands": ["look"],
                 "expert_plan": "HIDDEN_EXPERT"}]

        def close(self):
            self.closed = True

    def fresh(*args):
        env = Env(len(envs))
        envs.append(env)
        return env

    def call(system, user):
        prompts.append(json.loads(user))
        return receipt("<action>look</action>")

    monkeypatch.setattr(b, "_new_alfworld", fresh)
    for episode in range(2):
        pred = b.solve("alfworld", {"game_file": "fixture", "expert_plan": "HIDDEN_EXPERT"}, "", call,
                       runtime={"max_steps": 8})
        assert pred["status"] == "available" and pred["output"] == {"won": True, "steps": 8}
        current = prompts[episode * 8:(episode + 1) * 8]
        assert all(p["initial_observation"] == f"Your task is to complete public goal {episode}."
                   for p in current)
        assert all(len(p["recent_history"]) <= 5 for p in current)
        assert "Your task" not in json.dumps(current[-1]["recent_history"])
        assert "HIDDEN_EXPERT" not in json.dumps(current)
        assert f"public goal {1 - episode}" not in json.dumps(current)
    assert all(env.closed for env in envs)


@pytest.mark.parametrize("split,path_key", [
    ("train", "data_path"),
    ("eval_in_distribution", "eval_id_data_path"),
    ("eval_out_of_distribution", "eval_ood_data_path"),
])
def test_alfworld_startup_scans_only_selected_episode_without_mutating_config(monkeypatch, tmp_path, split, path_key):
    root = tmp_path / "data"
    game = root / "scenario" / "trial" / "game.tw-pddl"
    game.parent.mkdir(parents=True)
    game.write_text("{}")
    monkeypatch.setenv("ALFWORLD_DATA", str(root))
    config_file = Path(b.__file__).parents[1] / "envs/alfworld/vendor/config_tw.yaml"
    before = config_file.read_bytes()
    calls = []
    monkeypatch.setattr(b, "_AlfSession", lambda *args: calls.append(args) or "session")
    result = b._new_alfworld({"game_file": str(game)},
                            {"alfworld_data": str(root), "alfworld_split": split, "seed": 73, "max_steps": 150})
    assert result == "session"
    episode_config, selected_game, selected_split, seed, timeout = calls[0]
    assert episode_config["dataset"][path_key] == str(game.parent)
    assert (selected_game, selected_split, seed, timeout) == (str(game), split, 73, 60)
    assert episode_config["logic"]["domain"] == "$ALFWORLD_DATA/logic/alfred.pddl"
    assert episode_config["dagger"]["training"]["max_nb_steps_per_episode"] == 150
    assert episode_config["rl"]["training"]["max_nb_steps_per_episode"] == 150
    assert config_file.read_bytes() == before
    # A second episode receives its own directory, not stale state from the first.
    other = root / "other" / "trial" / "game.tw-pddl"
    other.parent.mkdir(parents=True)
    other.write_text("{}")
    b._new_alfworld({"game_file": str(other)}, {"alfworld_data": str(root), "alfworld_split": split})
    assert calls[1][0]["dataset"][path_key] == str(other.parent)
    assert calls[1][0]["dagger"]["training"]["max_nb_steps_per_episode"] == 50
    assert calls[0][0]["dataset"][path_key] == str(game.parent)


def test_alfworld_refuses_game_outside_frozen_data_root(monkeypatch, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "game.tw-pddl"
    outside.write_text("{}")
    monkeypatch.setenv("ALFWORLD_DATA", str(root))
    monkeypatch.setattr(b, "_AlfSession", lambda *_: pytest.fail("Must not start a worker"))
    with pytest.raises(ValueError, match="outside the frozen data root"):
        b._new_alfworld({"game_file": str(outside)}, {"alfworld_data": str(root)})


@pytest.mark.parametrize("max_steps", [0, 151, True, 1.5])
def test_alfworld_invalid_native_step_budget_never_starts_worker(monkeypatch, tmp_path, max_steps):
    game = tmp_path / "game.tw-pddl"
    game.write_text("{}")
    monkeypatch.setenv("ALFWORLD_DATA", str(tmp_path))
    monkeypatch.setattr(b, "_AlfSession", lambda *_: pytest.fail("Must not start a worker"))
    with pytest.raises(ValueError, match="Invalid ALFWorld step budget"):
        b._new_alfworld({"game_file": str(game)}, {"max_steps": max_steps})


@pytest.mark.parametrize("stuck", [False, True])
def test_alfworld_close_is_bounded_prefers_normal_exit_and_checks_cleanup(stuck):
    events = []
    class Process:
        alive = True
        def is_alive(self):
            return self.alive
        def join(self, timeout):
            events.append(("join", timeout))
            if not stuck:
                self.alive = False
        def terminate(self):
            events.append("terminate")
        def kill(self):
            events.append("kill")
    def queue(name):
        return SimpleNamespace(put=lambda item, timeout: events.append(("put", item, timeout)),
                               cancel_join_thread=lambda: events.append((name, "cancel")),
                               close=lambda: events.append((name, "close")))
    session = object.__new__(b._AlfSession)
    session.process, session.timeout = Process(), 60
    session.commands, session.results = queue("commands"), queue("results")
    if stuck:
        with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
            session.close()
        assert "terminate" in events and "kill" in events
    else:
        session.close()
        assert "terminate" not in events and "kill" not in events
    assert events[0] == ("put", ("close", None), 1)
    assert ("commands", "close") in events and ("results", "close") in events


def test_worker_refuses_direct_host_invocation():
    worker = Path(b.__file__).with_name("native_worker.py")
    result = subprocess.run([sys.executable, str(worker)], capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "Container-only worker" in result.stderr


@pytest.mark.parametrize("native_status,detail,status", [
    ("pass", {}, "pass"), ("fail", {"test_one": "AssertionError"}, "fail"),
    ("timeout", {}, "unknown"),
    ("fail", {"ALL": "ModuleNotFoundError: optional library absent"}, "unknown"),
])
def test_native_bigcode_mapping_without_host_candidate_execution(monkeypatch, native_status, detail, status):
    from skillopt.continual_eval import native_worker
    module = ModuleType("bigcodebench.eval")
    module.PASS, module.FAIL, module.TIMEOUT = "pass", "fail", "timeout"
    calls = []
    def official(*args, **kwargs):
        calls.append((args, kwargs))
        return native_status, detail
    module.untrusted_check = official
    monkeypatch.setitem(sys.modules, "bigcodebench.eval", module)
    result = native_worker.perform({"operation": "bigcodebench", "code": "MUST_NOT_EXECUTE",
                                    "test": "HIDDEN", "entry_point": "f", "memory_mb": 4096,
                                    "test_timeout": 60})
    assert result["status"] == status
    assert calls[0][0] == ("MUST_NOT_EXECUTE", "HIDDEN", "f")
    assert calls[0][1]["max_as_limit"] == 4096


def test_native_kor_uses_exact_official_signature(monkeypatch):
    from skillopt.continual_eval import native_worker
    calls = []
    monkeypatch.setattr(native_worker, "load_kor", lambda _: SimpleNamespace(
        evaluate_response_vs_answer=lambda *args: calls.append(args) or True))
    result = native_worker.perform({"operation": "korbench", "response": "[[B]]", "answer": "[[B]]",
                                    "category": "logic", "rule_id": "1", "upstream_index": "42"})
    assert result["status"] == "pass"
    assert calls == [("[[B]]", "[[B]]", "logic", "1", "42")]


def test_readiness_kor_really_imports_pinned_sources(monkeypatch):
    sources = {"eval_source": "E", "common_source": "C", "config_source": "G"}
    monkeypatch.setattr(b, "_kor_sources", lambda _: sources)
    captured = []
    monkeypatch.setattr(b, "_native", lambda request, runtime: captured.append(request) or
                        {"status": "unknown", "reason": "native_exception:ModuleNotFoundError"})
    result = b.readiness("korbench", {})
    assert result["status"] == "unsupported"
    assert captured[0] == {"operation": "probe", "benchmark": "korbench", **sources}


def test_alfworld_missing_success_signal_is_unknown_and_environment_closes(monkeypatch):
    state = {"closed": False}
    env = SimpleNamespace(
        reset=lambda: (["obs"], None, [{}]),
        step=lambda _: (["obs"], None, [0], [True], [{}]),
        close=lambda: state.update(closed=True))
    monkeypatch.setattr(b, "_new_alfworld", lambda *args: env)
    pred = b.solve("alfworld", {"game_file": "fixture"}, "", lambda *_: receipt("look"))
    assert pred["status"] == "unknown" and pred["reason"] == "native_won_signal_missing"
    assert state["closed"]


def test_alfworld_cleanup_failure_is_unknown_not_a_success_or_uncaught_exception(monkeypatch):
    def fail_close():
        raise RuntimeError("cleanup interrupted")
    env = SimpleNamespace(reset=lambda: (["obs"], None, [{}]),
                          step=lambda _: (["obs"], None, [1], [True], [{"won": True}]), close=fail_close)
    monkeypatch.setattr(b, "_new_alfworld", lambda *args: env)
    pred = b.solve("alfworld", {"game_file": "fixture"}, "", lambda *_: receipt("look"))
    assert pred["status"] == "unknown" and pred["reason"] == "alfworld_cleanup_unconfirmed"
