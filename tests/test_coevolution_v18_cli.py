"""CLI/supervisor control-plane tests without model, network or native execution."""

import fcntl
import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import coevolution_v18 as cli
from scripts import launch_coevolution_v18 as launcher
from scripts.coevolution_v17 import tree
from skillopt.coevolution_v12.study import read, save
from skillopt.coevolution_v18 import reporting
from skillopt.coevolution_v18.study import safe_root


@pytest.fixture
def configured(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v18/check"
    calls = []

    class PauseRequested(RuntimeError):
        pass

    class OfflineAPI:
        def call(self, *args, **kwargs):
            pytest.fail("Unexpected real API")

    class Study:
        def __init__(self, repo, output, **kwargs):
            self.root, self.kwargs = output, kwargs
            calls.append(("init", kwargs))

        def prepare(self):
            calls.append(("prepare", None))
            return save(self.root / "protocol.json", {"source_hashes": {"frozen.py": "abc"}})

        def run(self):
            calls.append(("run", None))
            if (self.root / "results.json").exists():
                return read(self.root / "results.json")
            if (self.root / "PAUSE").exists():
                raise PauseRequested("pause")
            protocol = self.prepare()
            return save(self.root / "results.json", {"complete": True,
                         "protocol_hash": protocol["record_hash"]})

    module = SimpleNamespace(Study=Study, read=read, safe_root=safe_root, OfflineAPI=OfflineAPI,
                             source_hashes=lambda repo: {"frozen.py": "abc"}, PauseRequested=PauseRequested)
    monkeypatch.setattr(cli, "_study", lambda: module)
    monkeypatch.setattr(cli, "REPO", tmp_path)
    monkeypatch.setattr(launcher, "REPO", tmp_path)
    monkeypatch.setattr(reporting, "render", lambda root: "# Derived fixture report\n")
    (tmp_path / "docs").mkdir()
    return SimpleNamespace(root=root, repo=tmp_path, module=module, calls=calls,
                           report=tmp_path / "docs/results.md")


def prepare(configured):
    assert cli.main(["--output", str(configured.root), "--prepare-only"]) == 0


def finish(configured):
    prepare(configured)
    return save(configured.root / "results.json", {"complete": True,
                "protocol_hash": read(configured.root / "protocol.json")["record_hash"]})


def test_unprepared_status_is_read_only(configured, capsys):
    assert cli.main(["--output", str(configured.root), "--status"]) == 0
    assert json.loads(capsys.readouterr().out) == {"prepared": False}
    assert not configured.root.exists() and not configured.calls


def test_prepare_does_not_run_or_initialize_api(configured, capsys):
    prepare(configured)
    assert [name for name, _ in configured.calls] == ["init", "prepare"]
    assert json.loads(capsys.readouterr().out)["api_calls"] == 0
    assert not (configured.root / "results.json").exists()


@pytest.mark.parametrize("flag", ["--resume", "--request-pause"])
def test_resume_or_pause_require_prior_registration(configured, flag):
    with pytest.raises(SystemExit):
        cli.main(["--output", str(configured.root), flag])
    assert not configured.root.exists() and not configured.calls


def test_status_counts_explicit_failures_and_preserves_tree(configured, capsys):
    prepare(configured)
    capsys.readouterr()
    for name, ok in (("first", True), ("second", False)):
        path = configured.root / "api/calls" / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ok": ok}))
    save(configured.root / "events/000001.json", {"stage": "development"})
    before = tree(configured.root)
    assert cli.main(["--output", str(configured.root), "--status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["logical_calls"] == 2 and result["terminal_api_errors"] == 1
    assert result["last_event"]["stage"] == "development"
    assert tree(configured.root) == before


def test_pause_marks_only_control_and_unresumed_run_stops(configured):
    prepare(configured)
    before = tree(configured.root)
    configured.calls.clear()
    assert cli.main(["--output", str(configured.root), "--request-pause"]) == 0
    assert configured.calls == []
    assert {key: value for key, value in tree(configured.root).items() if key != "PAUSE"} == before
    assert cli.main(["--output", str(configured.root)]) == 75
    assert (configured.root / "PAUSE").exists()


def test_completed_run_cannot_be_paused(configured):
    finish(configured)
    before = tree(configured.root)
    with pytest.raises(SystemExit):
        cli.main(["--output", str(configured.root), "--request-pause"])
    assert tree(configured.root) == before


def test_resume_source_drift_does_not_clear_pause(configured, monkeypatch):
    prepare(configured)
    (configured.root / "PAUSE").touch()
    monkeypatch.setattr(configured.module, "source_hashes", lambda unused: {"changed": "source"})
    configured.calls.clear()
    with pytest.raises(ValueError, match="changed frozen sources"):
        cli.main(["--output", str(configured.root), "--resume"])
    assert (configured.root / "PAUSE").exists() and not configured.calls


def test_explicit_resume_clears_pause_and_runs_once_then_audits(configured):
    prepare(configured)
    (configured.root / "PAUSE").touch()
    assert cli.main(["--output", str(configured.root), "--resume"]) == 0
    assert not (configured.root / "PAUSE").exists()
    assert read(configured.root / "results.json")["complete"] is True
    assert [name for name, _ in configured.calls].count("run") == 2  # execution then read-only replay


def test_completed_cli_is_read_only_and_report_is_external(configured):
    finish(configured)
    before = tree(configured.root)
    assert cli.main(["--output", str(configured.root), "--report", str(configured.report)]) == 0
    assert tree(configured.root) == before
    assert configured.report.read_text() == "# Derived fixture report\n"


def test_completed_replay_requires_original_locks(configured):
    finish(configured)
    (configured.root / ".audit.lock").unlink()
    with pytest.raises(ValueError, match="locks are required"):
        cli.completed_replay(configured.repo, configured.root)


@pytest.mark.parametrize("operation", ["network", "process", "api", "native", "probe", "factory"])
def test_replay_proactively_forbids_side_effects(configured, monkeypatch, operation):
    from skillopt.coevolution_v11 import executor
    from skillopt.validator_pilot.api import CachedAPI
    finish(configured)
    before = tree(configured.root)
    def bad_run(self):
        if operation == "network":
            socket.create_connection(("localhost", 9))
        elif operation == "process":
            subprocess.Popen(["true"])
        elif operation == "api":
            CachedAPI.call(None, "", "", "", "")
        elif operation == "native":
            executor.run_cases(None, None, None)
        elif operation == "probe":
            executor.sandbox_probe()
        else:
            self.kwargs["api_factory"]()
    monkeypatch.setattr(configured.module.Study, "run", bad_run)
    with pytest.raises(RuntimeError, match="forbids"):
        cli.completed_replay(configured.repo, configured.root)
    assert tree(configured.root) == before


def test_replay_detects_unexpected_write(configured, monkeypatch):
    result = finish(configured)
    def bad_run(self):
        (self.root / "accidental.txt").write_text("changed")
        return result
    monkeypatch.setattr(configured.module.Study, "run", bad_run)
    with pytest.raises(ValueError, match="changed evidence"):
        cli.completed_replay(configured.repo, configured.root)


@pytest.mark.parametrize("target", ["coevolution-v18-protocol.md", "coevolution-v17-protocol.md", "results.json", "../escape.md"])
def test_invalid_reports_rejected_before_execution(configured, target):
    with pytest.raises(ValueError, match="Derived report"):
        cli.main(["--output", str(configured.root), "--report", str(configured.repo / "docs" / target)])
    assert not configured.calls and not configured.root.exists()


def test_symlink_report_is_not_overwritten(configured):
    configured.report.symlink_to(configured.repo / "outside.md")
    with pytest.raises(ValueError, match="Derived report"):
        cli.write_report(configured.root, configured.report)
    assert not (configured.repo / "outside.md").exists()


def test_report_supports_valid_nested_docs_directory(configured):
    target = configured.repo / "docs/new_subdir/report.md"
    assert Path(cli.write_report(configured.root, target)).read_text() == "# Derived fixture report\n"


@pytest.mark.parametrize("wall,mono,expected", [(30, 30, False), (121, 121, True),
    (600, 30, True), (30, 600, True), (-200, 30, True), (120, 120, False)])
def test_suspend_detection_covers_clock_semantics(wall, mono, expected):
    assert launcher.suspend_evidence(1000, 100, 1000 + wall, 100 + mono)["pause_needed"] is expected


def test_completed_launcher_replays_without_supervisor_write_or_process(configured, monkeypatch):
    finish(configured)
    before = tree(configured.root)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: pytest.fail("Duplicate process"))
    assert launcher.main(["--output", str(configured.root), "--report", str(configured.report)]) == 0
    assert tree(configured.root) == before
    assert not (configured.root / "supervisor.log").exists()


def test_supervisor_sleep_drains_inflight_and_never_restarts(configured, monkeypatch):
    prepare(configured)
    started = []
    class Child:
        pid = 1234
        returncode = None
        waits = 0
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            assert timeout == 30
            self.waits += 1
            if self.waits == 1:
                assert not (configured.root / "PAUSE").exists()
                raise subprocess.TimeoutExpired("fake-study", timeout)
            assert (configured.root / "PAUSE").exists()
            self.returncode = 75
            return 75
    child = Child()
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: (started.append(a), child)[1])
    wall, mono = iter([1000, 1600]), iter([100, 700])
    monkeypatch.setattr(launcher.time, "time", lambda: next(wall))
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(mono))
    assert launcher.main(["--output", str(configured.root), "--report", str(configured.report), "--resume"]) == 75
    assert len(started) == 1 and child.waits == 2
    assert "--resume" in started[0][0]
    rows = [json.loads(line) for line in (configured.root / "supervisor.log").read_text().splitlines()]
    assert [row["stage"] for row in rows] == ["started", "suspend_pause_requested", "heartbeat", "paused"]
    assert rows[-1]["automatic_retry"] is False


def test_supervisor_lock_blocks_duplicate_launch(configured, monkeypatch):
    prepare(configured)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: pytest.fail("Duplicate process"))
    with (configured.root / "supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            launcher.main(["--output", str(configured.root), "--report", str(configured.report)])


def test_run_lock_blocks_duplicate_cli_execution(configured):
    prepare(configured)
    configured.calls.clear()
    with (configured.root / ".run.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            cli.main(["--output", str(configured.root)])
    assert not configured.calls
