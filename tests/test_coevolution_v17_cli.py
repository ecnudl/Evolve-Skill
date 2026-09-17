import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import coevolution_v17 as cli
from scripts import launch_coevolution_v17 as launcher
from skillopt.coevolution_v12.study import read, save


@pytest.fixture
def configured(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v17/check"
    calls = []

    class PauseRequested(RuntimeError):
        pass

    def safe_root(repo, output):
        path = Path(output).absolute()
        parent = Path(repo) / "outputs/coevolution_v17"
        if (path == parent or not path.is_relative_to(parent) or ".." in path.parts
                or any(p.is_symlink() for p in (path, *path.parents))):
            raise ValueError("Dedicated nonsymlink V17 run required")
        return path

    class Study:
        def __init__(self, repo, root, **kwargs):
            self.root, self.kwargs = root, kwargs
            calls.append(("init", kwargs))

        def prepare(self):
            calls.append(("prepare", None))
            return save(self.root / "protocol.json", {
                "design": self.kwargs["design"], "source_hashes": {"frozen.py": "abc"},
                "workers": 4, "max_calls": 128, "model": "glm-5.3"})

        def run(self):
            calls.append(("run", None))
            if (self.root / "results.json").exists():
                return read(self.root / "results.json")
            if (self.root / "PAUSE").exists():
                raise PauseRequested("paused")
            protocol = self.prepare()
            return save(self.root / "results.json", {"complete": True,
                "status": "screen_stopped", "protocol_hash": protocol["record_hash"]})

    module = SimpleNamespace(Study=Study, read=read, safe_root=safe_root,
        source_hashes=lambda repo: {"frozen.py": "abc"},
        DESIGNS={"smoke": {}, "pilot": {}}, PauseRequested=PauseRequested)
    monkeypatch.setattr(cli, "_study", lambda: module)
    monkeypatch.setattr(cli, "REPO", tmp_path)
    monkeypatch.setattr(launcher, "REPO", tmp_path)
    return SimpleNamespace(root=root, repo=tmp_path, module=module, calls=calls)


def prepare(configured):
    assert cli.main(["--output", str(configured.root), "--design", "smoke", "--prepare-only"]) == 0


def finish(configured, status="screen_stopped"):
    prepare(configured)
    return save(configured.root / "results.json", {"complete": True, "status": status,
        "protocol_hash": read(configured.root / "protocol.json")["record_hash"]})


def test_status_unprepared_does_not_create_anything(configured, capsys):
    assert cli.main(["--output", str(configured.root), "--status"]) == 0
    assert not configured.root.exists()
    assert json.loads(capsys.readouterr().out)["prepared"] is False
    assert not configured.calls


def test_initial_design_required_and_resume_needs_registration(configured):
    with pytest.raises(SystemExit):
        cli.main(["--output", str(configured.root)])
    with pytest.raises(SystemExit):
        cli.main(["--output", str(configured.root), "--design", "smoke", "--resume"])
    assert not configured.root.exists()


def test_prepare_only_does_not_run(configured):
    prepare(configured)
    assert [name for name, _ in configured.calls] == ["init", "prepare"]
    assert not (configured.root / "results.json").exists()


def test_design_cannot_change(configured):
    prepare(configured)
    before = cli.tree(configured.root)
    with pytest.raises(SystemExit):
        cli.main(["--output", str(configured.root), "--design", "pilot", "--resume"])
    assert cli.tree(configured.root) == before


def test_request_pause_preserves_evidence_and_does_not_run(configured):
    prepare(configured)
    configured.calls.clear()
    before = cli.tree(configured.root)
    assert cli.main(["--output", str(configured.root), "--request-pause"]) == 0
    assert not configured.calls
    assert (configured.root / "PAUSE").exists()
    assert {k: v for k, v in cli.tree(configured.root).items() if k != "PAUSE"} == before
    assert cli.main(["--output", str(configured.root)]) == 75


def test_resume_rejects_drift_before_removing_pause(configured, monkeypatch):
    prepare(configured)
    (configured.root / "PAUSE").touch()
    monkeypatch.setattr(configured.module, "source_hashes", lambda repo: {"changed.py": "def"})
    with pytest.raises(ValueError, match="source drift"):
        cli.main(["--output", str(configured.root), "--resume"])
    assert (configured.root / "PAUSE").exists()


def test_resume_can_finish_at_screen_without_final_stage(configured):
    prepare(configured)
    (configured.root / "PAUSE").touch()
    assert cli.main(["--output", str(configured.root), "--resume"]) == 0
    assert not (configured.root / "PAUSE").exists()
    assert read(configured.root / "results.json")["status"] == "screen_stopped"


@pytest.mark.parametrize("result_status", ["screen_stopped", "completed"])
def test_completed_replay_is_read_only_for_either_terminal_stage(configured, result_status):
    expected = finish(configured, result_status)
    before = cli.tree(configured.root)
    assert cli.completed_replay(configured.repo, configured.root) == expected
    assert cli.tree(configured.root) == before
    assert cli.status(configured.root)["result_status"] == result_status


def test_replay_requires_completion_and_original_locks(configured):
    prepare(configured)
    with pytest.raises(ValueError, match="Completed run"):
        cli.completed_replay(configured.repo, configured.root)
    finish(configured)
    (configured.root / ".audit.lock").unlink()
    with pytest.raises(ValueError, match="original locks"):
        cli.completed_replay(configured.repo, configured.root)


@pytest.mark.parametrize("operation", ["network", "process", "api", "native", "factory"])
def test_replay_forbids_fresh_effects(configured, monkeypatch, operation):
    from skillopt.coevolution_v15 import runtime
    from skillopt.validator_pilot.api import CachedAPI

    finish(configured)

    def bad_run(self):
        if operation == "network":
            socket.create_connection(("localhost", 9))
        elif operation == "process":
            subprocess.Popen(["true"])
        elif operation == "api":
            CachedAPI.call(None, "", "", "", "")
        elif operation == "native":
            runtime.legacy.evaluate(None, None)
        else:
            self.kwargs["api_factory"]()

    monkeypatch.setattr(configured.module.Study, "run", bad_run)
    before = cli.tree(configured.root)
    with pytest.raises(RuntimeError, match="forbids API/network/native"):
        cli.completed_replay(configured.repo, configured.root)
    assert cli.tree(configured.root) == before


def test_replay_detects_evidence_write(configured, monkeypatch):
    original = finish(configured)

    def bad_run(self):
        (self.root / "unwanted.txt").write_text("changed")
        return original

    monkeypatch.setattr(configured.module.Study, "run", bad_run)
    with pytest.raises(ValueError, match="changed evidence"):
        cli.completed_replay(configured.repo, configured.root)


def test_symlink_evidence_is_not_followed(configured):
    finish(configured)
    (configured.root / "escape").symlink_to(configured.repo / "outside")
    with pytest.raises(ValueError, match="Symlink"):
        cli.tree(configured.root)


@pytest.mark.parametrize("target", ["coevolution-v17-protocol.md", "results.json", "../escape.md"])
def test_report_cannot_overwrite_protocol_or_escape_docs(configured, target):
    with pytest.raises(ValueError, match="Derived report"):
        cli.report_path(configured.repo, configured.repo / "docs" / target)


@pytest.mark.parametrize("wall,mono,expected", [(30, 30, False), (121, 121, True),
    (600, 30, True), (30, 600, True), (-200, 30, True), (120, 120, False)])
def test_suspend_detection_covers_both_clock_semantics(wall, mono, expected):
    assert launcher.suspend_evidence(1000, 100, 1000 + wall, 100 + mono)["pause_needed"] is expected


def test_completed_launcher_does_not_write_supervisor_files(configured):
    finish(configured)
    before = cli.tree(configured.root)
    assert launcher.main(["--output", str(configured.root), "--design", "smoke"]) == 0
    assert cli.tree(configured.root) == before
    assert not (configured.root / "supervisor.log").exists()


def test_supervisor_detects_sleep_requests_pause_and_never_restarts(configured, monkeypatch):
    prepare(configured)
    started = []

    class Child:
        pid = 1234
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            assert timeout == 30
            if not (configured.root / "PAUSE").exists():
                raise subprocess.TimeoutExpired("fake-study", timeout)
            self.returncode = 75
            return self.returncode

    def popen(*args, **kwargs):
        started.append(args)
        return Child()

    wall, mono = iter([1000, 1600]), iter([100, 700])
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    monkeypatch.setattr(launcher.time, "time", lambda: next(wall))
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(mono))
    assert launcher.main(["--output", str(configured.root), "--design", "smoke", "--resume"]) == 75
    assert len(started) == 1
    rows = [json.loads(line) for line in (configured.root / "supervisor.log").read_text().splitlines()]
    assert [row["stage"] for row in rows] == ["started",
        "possible_suspend_or_clock_jump_pause_requested", "heartbeat", "paused"]
    assert rows[-1]["automatic_retry"] is False
