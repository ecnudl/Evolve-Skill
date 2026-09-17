"""Bounded CLI/supervisor/status tests using fake studies and subprocesses."""

import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import coevolution_v14 as cli
from scripts import launch_coevolution_v14 as launch
from scripts import status_coevolution_v14 as progress
from skillopt.coevolution_v5.core import seal, verify


def put(path, value, *, sealed=True):
    value = seal(value) if sealed else value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return value


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v14/run"
    state = {"runs": 0, "constructors": [], "action": None, "processes": []}
    def safe_root(repo, output):
        output = Path(output).absolute()
        if (any(p.is_symlink() for p in (output, *output.parents))
                or not output.is_relative_to(Path(repo) / "outputs/coevolution_v14")
                or output == Path(repo) / "outputs/coevolution_v14"):
            raise ValueError("Unsafe output")
        if output.exists() and any(p.is_symlink() for p in output.rglob("*")):
            raise ValueError("Unsafe symlink entry")
        return output
    class PauseRequested(RuntimeError):
        pass
    class OfflineAPI:
        def call(self):
            pytest.fail("Unexpected model access")
    class Study:
        def __init__(self, repo, output, **kwargs):
            self.complete = (output / "results.json").exists()
            self.api_factory = kwargs.get("api_factory")
            state["constructors"].append(kwargs)
        def run(self):
            state["runs"] += 1
            if state["action"]:
                return state["action"](self)
            if self.complete:
                return verify(json.loads((root / "results.json").read_text()))
            return seal({"complete": True, "learning": {}, "summary": {}, "ledger": {}})
    module = SimpleNamespace(safe_root=safe_root, read=lambda path: verify(json.loads(path.read_text())),
                             source_hashes=lambda repo: {}, Study=Study, OfflineAPI=OfflineAPI,
                             PauseRequested=PauseRequested)
    for target in (cli, launch, progress):
        monkeypatch.setattr(target, "REPO", tmp_path)
        monkeypatch.setattr(target, "study_module", lambda: module)
    def subprocess_run(command, **kwargs):
        state["processes"].append((command, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(launch.subprocess, "run", subprocess_run)
    return {"repo": tmp_path, "root": root, "module": module, "state": state}


def prepared(f, *, complete=False):
    root = f["root"]
    root.mkdir(parents=True, exist_ok=True)
    (root / ".run.lock").touch()
    protocol = put(root / "protocol.json", {"design": "smoke", "max_calls": 64, "workers": 4,
        "model": "glm-5.3", "source_hashes": {}})
    if complete:
        put(root / "results.json", {"complete": True, "protocol_hash": protocol["record_hash"],
                                   "summary": {}, "learning": {}, "ledger": {}})
    return protocol


def test_new_cli_passes_explicit_bounded_configuration(fixture, capsys):
    f = fixture
    assert cli.main(["--output", str(f["root"]), "--design", "formal", "--max-calls", "640", "--workers", "4"]) == 0
    assert f["state"]["constructors"] == [{"design": "formal", "max_calls": 640, "workers": 4}]
    assert json.loads(capsys.readouterr().out)["complete"]


def test_pause_writes_only_explicit_marker_without_running(fixture):
    prepared(fixture)
    before = cli.tree(fixture["root"])
    assert cli.main(["--output", str(fixture["root"]), "--request-pause"]) == 0
    after = cli.tree(fixture["root"])
    assert set(after) - set(before) == {"PAUSE"} and fixture["state"]["runs"] == 0
    assert cli.main(["--output", str(fixture["root"]), "--request-pause"]) == 0


def test_pause_request_is_possible_while_writer_holds_run_lock(fixture):
    prepared(fixture)
    with (fixture["root"] / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cli.main(["--output", str(fixture["root"]), "--request-pause"]) == 0
    assert fixture["state"]["runs"] == 0


@pytest.mark.parametrize("flag", ["--resume", "--request-pause"])
def test_no_prepare_no_resume_or_pause_mutations(fixture, flag):
    with pytest.raises(SystemExit):
        cli.main(["--output", str(fixture["root"]), flag])
    assert not fixture["root"].exists()


def test_resume_consumes_only_validated_marker(fixture):
    prepared(fixture)
    (fixture["root"] / "PAUSE").touch()
    (fixture["root"] / "keep.txt").write_text("keep")
    before = cli.tree(fixture["root"])
    assert cli.main(["--output", str(fixture["root"]), "--resume"]) == 0
    after = cli.tree(fixture["root"])
    assert set(before) - set(after) == {"PAUSE"}
    assert all(after[k] == before[k] for k in after)


def test_source_drift_does_not_consume_pause(fixture):
    prepared(fixture)
    (fixture["root"] / "PAUSE").touch()
    fixture["module"].source_hashes = lambda _: {"drift": True}
    with pytest.raises(ValueError, match="Cannot resume"):
        cli.main(["--output", str(fixture["root"]), "--resume"])
    assert (fixture["root"] / "PAUSE").exists() and fixture["state"]["runs"] == 0


def test_pause_exception_is_75_without_retry(fixture):
    def pause(_):
        raise fixture["module"].PauseRequested()
    fixture["state"]["action"] = pause
    assert cli.main(["--output", str(fixture["root"])]) == 75
    assert fixture["state"]["runs"] == 1


def test_completed_cli_replay_zero_writes_and_explicit_factory_guard(fixture, capsys):
    prepared(fixture, complete=True)
    before = cli.tree(fixture["root"])
    assert cli.main(["--output", str(fixture["root"]), "--replay-only"]) == 0
    assert cli.tree(fixture["root"]) == before
    assert fixture["state"]["constructors"][0]["api_factory"] is cli.forbidden
    assert json.loads(capsys.readouterr().out)["replay_files_unchanged"]


def test_already_completed_normal_entry_is_also_guarded_replay(fixture):
    prepared(fixture, complete=True)
    assert cli.main(["--output", str(fixture["root"])]) == 0
    assert fixture["state"]["constructors"][0]["api_factory"] is cli.forbidden


def test_missing_completed_result_cannot_create_run(fixture):
    with pytest.raises(ValueError, match="Completed results"):
        cli.main(["--output", str(fixture["root"]), "--replay-only"])
    assert not fixture["root"].exists()


@pytest.mark.parametrize("action", ["factory", "offline_api", "native"])
def test_replay_api_and_execution_tripwires(fixture, action):
    prepared(fixture, complete=True)
    def attempt(study):
        if action == "factory":
            study.api_factory()
        elif action == "offline_api":
            fixture["module"].OfflineAPI.call(None)
        else:
            from skillopt.coevolution_v14 import runtime
            runtime.legacy.evaluate(None)
    fixture["state"]["action"] = attempt
    with pytest.raises(ValueError, match="model access or native execution"):
        cli.main(["--output", str(fixture["root"]), "--replay-only"])


def test_completed_readout_still_protects_tree(fixture):
    prepared(fixture, complete=True)
    with pytest.raises(ValueError, match="readout changed"):
        with cli.completed_replay(fixture["repo"], fixture["root"]):
            (fixture["root"] / "changed.txt").write_text("mutation")


def test_completed_replay_rejects_active_run_writer(fixture):
    prepared(fixture, complete=True)
    with (fixture["root"] / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            cli.main(["--output", str(fixture["root"]), "--replay-only"])


@pytest.mark.parametrize("extra", [["--design", "formal"], ["--max-calls", "63"], ["--workers", "2"]])
def test_frozen_config_cannot_change(fixture, extra):
    prepared(fixture)
    with pytest.raises(ValueError, match="Cannot change"):
        cli.main(["--output", str(fixture["root"]), *extra])
    assert fixture["state"]["runs"] == 0


@pytest.mark.parametrize("kwargs", [{"max_calls": 0}, {"max_calls": 641}, {"workers": 0}, {"workers": 5},
    {"max_calls": True}, {"workers": True}, {"design": "other"}, {"workers": 3},
    {"max_calls": 63}, {"design": "formal", "max_calls": 64}])
def test_new_config_bounds(kwargs):
    with pytest.raises(ValueError):
        cli.configuration(**kwargs)


def test_launcher_has_one_run_then_one_offline_report(fixture):
    target = fixture["repo"] / "docs/test.md"
    assert launch.main(["--output", str(fixture["root"]), "--design", "smoke", "--report", str(target)]) == 0
    calls = fixture["state"]["processes"]
    assert len(calls) == 2 and "coevolution_v14.py" in calls[0][0][3]
    assert "report_coevolution_v14.py" in calls[1][0][2]
    assert "--max-calls" in calls[0][0] and "64" in calls[0][0]
    assert "automatic_retry" not in (fixture["root"] / "supervisor.log").read_text()


@pytest.mark.parametrize("returncode", [75, 1])
def test_launcher_never_restarts_failed_or_paused_run(fixture, monkeypatch, returncode):
    def process(command, **kwargs):
        fixture["state"]["processes"].append(command)
        return SimpleNamespace(returncode=returncode)
    monkeypatch.setattr(launch.subprocess, "run", process)
    assert launch.main(["--output", str(fixture["root"]), "--design", "formal",
                        "--report", str(fixture["repo"] / "docs/test.md")]) == returncode
    assert len(fixture["state"]["processes"]) == 1
    assert '"automatic_retry": false' in (fixture["root"] / "supervisor.log").read_text()


def test_launcher_report_cannot_overwrite_frozen_source(fixture):
    fixture["module"].source_hashes = lambda _: {"docs/protocol.md": "hash"}
    with pytest.raises(SystemExit):
        launch.main(["--output", str(fixture["root"]), "--design", "smoke",
                     "--report", str(fixture["repo"] / "docs/protocol.md")])
    assert not fixture["root"].exists()


@pytest.mark.parametrize("path", ["outside.md", "docs/report.txt"])
def test_launcher_report_scope(fixture, path):
    with pytest.raises(ValueError, match="Markdown"):
        launch.main(["--output", str(fixture["root"]), "--design", "smoke",
                     "--report", str(fixture["repo"] / path)])
    assert not fixture["root"].exists()


def test_status_readonly_no_score_or_body_leak_and_ignores_pending_atomic_files(fixture):
    prepared(fixture)
    h = "a" * 64
    put(fixture["root"] / "api/calls" / (h + ".json"), {"request_hash": h, "ok": True,
        "request": {"kind": "v14_solve_generation", "user": "SECRET_PROMPT"}, "response": "SECRET_REPLY",
        "http_attempt_count": 1, "usage": {"total_tokens": 10}}, sealed=False)
    put(fixture["root"] / "events/001.json", {"stage": "inflight", "score": .2, "skill": "SECRET_SKILL"})
    put(fixture["root"] / "learning/h0-r0-independent.json", {"valid": True, "skill": "SECRET_SKILL"})
    for directory in ("api/calls", "events", "learning", "runtime/request_intents", "runtime/stages"):
        path = fixture["root"] / directory / ".pending-incomplete.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{")
    before = cli.tree(fixture["repo"])
    result = progress.status(fixture["root"], repo=fixture["repo"])
    assert result["closed_logical_calls"] == result["skill_proposals"] == 1
    assert result["last_event"] == {"stage": "inflight"}
    assert result["read_only"] and result["final_scores_not_exposed"]
    assert "SECRET" not in json.dumps(result) and cli.tree(fixture["repo"]) == before
    assert fixture["state"]["runs"] == 0


def test_status_no_prepared_run_does_not_create_files(fixture):
    assert not progress.status(fixture["root"], repo=fixture["repo"])["prepared"]
    assert not fixture["root"].exists()
