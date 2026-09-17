"""The V12 supervisor never retries failures or starts an unrequested experiment."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import launch_coevolution_v12 as launch


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "REPO", tmp_path)
    root = tmp_path / "outputs/coevolution_v12/fixture"
    report = tmp_path / "docs/result.md"
    (tmp_path / "docs").mkdir()
    calls, codes = [], [0, 0]
    def fake(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=codes[len(calls)-1])
    monkeypatch.setattr(launch.subprocess, "run", fake)
    arguments = ["--output", str(root), "--design", "smoke", "--report", str(report)]
    return root, report, arguments, calls, codes


@pytest.mark.parametrize("code", [75, 1, 2, -9])
def test_pause_and_failure_preserved_without_retry_or_report(fixture, code):
    root, _, arguments, calls, codes = fixture
    codes[0] = code
    assert launch.main(arguments) == code
    assert len(calls) == 1
    events = [json.loads(line) for line in (root / "supervisor.log").read_text().splitlines()]
    assert events[-1]["phase"] == ("paused" if code == 75 else "stopped")
    assert events[-1]["automatic_retry"] is False and events[-1]["evidence_preserved"] is True
    assert not any("report_coevolution_v12.py" in value for value in calls[0]["command"])


def test_success_runs_exact_experiment_then_verified_report(fixture):
    root, report, arguments, calls, _ = fixture
    assert launch.main(arguments) == 0
    assert len(calls) == 2
    first, second = (row["command"] for row in calls)
    assert first[1:3] == ["-B", "-u"]
    assert Path(first[3]).name == "coevolution_v12.py"
    assert first[first.index("--output") + 1] == str(root)
    assert first[first.index("--design") + 1] == "smoke"
    assert Path(second[2]).name == "report_coevolution_v12.py"
    assert second[second.index("--report") + 1] == str(report)
    assert all(row["cwd"] == launch.REPO for row in calls)


def test_explicit_resume_is_forwarded_only_to_experiment(fixture):
    _, _, arguments, calls, _ = fixture
    assert launch.main(arguments + ["--resume"]) == 0
    assert "--resume" in calls[0]["command"]
    assert "--resume" not in calls[1]["command"]


def test_report_failure_does_not_repeat_completed_experiment(fixture):
    root, _, arguments, calls, codes = fixture
    codes[1] = 7
    assert launch.main(arguments) == 7 and len(calls) == 2
    assert json.loads((root / "supervisor.log").read_text().splitlines()[-1])["phase"] == "report_stopped"


@pytest.mark.parametrize("target", ["outside.md", "docs/report.txt", "docs/sub/../../outside.md"])
def test_invalid_report_path_refused_before_subprocess(fixture, target):
    _, _, arguments, calls, _ = fixture
    arguments[-1] = str(launch.REPO / target)
    with pytest.raises(SystemExit):
        launch.main(arguments)
    assert calls == []


def test_symlink_report_refused(fixture):
    _, report, arguments, calls, _ = fixture
    destination = launch.REPO / "docs/real.md"
    destination.write_text("existing user artifact")
    report.symlink_to(destination)
    with pytest.raises(SystemExit):
        launch.main(arguments)
    assert calls == [] and destination.read_text() == "existing user artifact"


@pytest.mark.parametrize("target", ["outputs/coevolution_v12", "outputs/other/run", "outside"])
def test_out_of_scope_run_directory_refused(fixture, target):
    _, _, arguments, calls, _ = fixture
    arguments[1] = str(launch.REPO / target)
    with pytest.raises(ValueError):
        launch.main(arguments)
    assert calls == []


def test_active_supervisor_lock_refused_without_subprocess(fixture, monkeypatch):
    _, _, arguments, calls, _ = fixture
    def locked(*args):
        raise BlockingIOError("synthetic occupied lock")
    monkeypatch.setattr(launch.fcntl, "flock", locked)
    with pytest.raises(SystemExit):
        launch.main(arguments)
    assert calls == []


def test_design_is_required_and_closed(fixture):
    _, _, arguments, calls, _ = fixture
    arguments[3] = "new_unregistered_design"
    with pytest.raises(SystemExit):
        launch.main(arguments)
    assert calls == []
