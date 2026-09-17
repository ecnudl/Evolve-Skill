"""Supervisor invokes the frozen CLI once; no experiments or network calls."""

import fcntl
import sys
from types import SimpleNamespace

import pytest

from scripts import launch_coevolution_v9 as launch


def setup(tmp_path, monkeypatch, *, first_code=0, second_code=0):
    monkeypatch.setattr(launch, "REPO", tmp_path)
    root = tmp_path / "outputs/coevolution_v9/run"
    report = tmp_path / "docs/new.md"
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(returncode=first_code if len(commands) == 1 else second_code)

    monkeypatch.setattr(launch.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["launch", "--output", str(root), "--design", "source", "--report", str(report)])
    return root, report, commands


def test_success_runs_experiment_then_verified_report_once(tmp_path, monkeypatch):
    root, _, commands = setup(tmp_path, monkeypatch)
    assert launch.main() == 0
    assert len(commands) == 2
    assert commands[0][2].endswith("scripts/coevolution_v9.py")
    assert commands[1][2].endswith("scripts/report_coevolution_v9.py")
    assert '"phase": "finished"' in (root / "supervisor.log").read_text()


@pytest.mark.parametrize("code", [1, 17, 130])
def test_failed_experiment_never_retries_or_reports(tmp_path, monkeypatch, code):
    root, _, commands = setup(tmp_path, monkeypatch, first_code=code)
    assert launch.main() == code and len(commands) == 1
    assert '"evidence_preserved": true' in (root / "supervisor.log").read_text()


def test_report_failure_preserves_successful_experiment(tmp_path, monkeypatch):
    root, _, commands = setup(tmp_path, monkeypatch, second_code=5)
    assert launch.main() == 5 and len(commands) == 2
    assert '"phase": "report_stopped"' in (root / "supervisor.log").read_text()


def test_second_supervisor_refused_before_subprocess(tmp_path, monkeypatch):
    root, _, commands = setup(tmp_path, monkeypatch)
    root.mkdir(parents=True)
    with (root / "supervisor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SystemExit):
            launch.main()
    assert commands == []


def test_unsafe_report_path_refused_before_model(tmp_path, monkeypatch):
    _, _, commands = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", sys.argv[:-1] + [str(tmp_path / "skillopt/study.py")])
    with pytest.raises(SystemExit):
        launch.main()
    assert commands == []
