"""CLI lifecycle and completed replay safeguards without APIs or real tasks."""

import fcntl
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import coevolution_v10 as cli
from skillopt.coevolution_v5 import core


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def environment(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    root = repo / "outputs/coevolution_v10/run"
    monkeypatch.setattr(cli, "REPO", repo)
    calls = []
    value = core.seal({"complete": False, "paused": True, "phase": "confirmation", "private_tasks": "DO_NOT_PRINT"})

    class Study:
        def __init__(self, actual_repo, actual_root, *, design="formal", api_factory=None):
            calls.append(("construct", actual_repo, actual_root, design, api_factory))

        def run(self):
            calls.append(("run",))
            return value

    def pause(path):
        calls.append(("pause", path))
        return value

    def resume(path):
        calls.append(("resume", path))
        return value

    module = SimpleNamespace(Study=Study, request_pause=pause, resume=resume)
    monkeypatch.setattr(cli, "_study_module", lambda: module)
    return repo, root, calls, module


def test_default_new_run_is_smoke_and_output_omits_private_payload(environment, capsys):
    repo, root, calls, _ = environment
    assert cli.main(["--output", str(root)]) == 0
    assert calls == [("construct", repo, root, "smoke", None), ("run",)]
    output = capsys.readouterr().out
    assert "DO_NOT_PRINT" not in output and "private_tasks" not in output
    assert json.loads(output)["paused"] is True


def test_explicit_smoke_run(environment):
    _, root, calls, _ = environment
    cli.main(["--output", str(root), "--design", "smoke"])
    assert calls[0][3] == "smoke"


def test_existing_design_is_inferred_without_changing_protocol(environment):
    _, root, calls, _ = environment
    protocol = core.seal({"design_name": "smoke"})
    put(root / "protocol.json", protocol)
    before = (root / "protocol.json").read_bytes()
    cli.main(["--output", str(root)])
    assert calls[0][3] == "smoke" and (root / "protocol.json").read_bytes() == before


def test_design_change_rejected_before_study_construction(environment):
    _, root, calls, _ = environment
    put(root / "protocol.json", core.seal({"design_name": "smoke"}))
    with pytest.raises(ValueError, match="differs"):
        cli.main(["--output", str(root), "--design", "formal"])
    assert calls == []


def test_pause_only_calls_request_function_not_study(environment):
    _, root, calls, _ = environment
    cli.main(["--output", str(root), "--request-pause"])
    assert calls == [("pause", root)]


def test_resume_calls_resume_before_running_existing_design(environment):
    repo, root, calls, _ = environment
    put(root / "protocol.json", core.seal({"design_name": "smoke"}))
    cli.main(["--output", str(root), "--resume"])
    assert calls == [("resume", root), ("construct", repo, root, "smoke", None), ("run",)]


@pytest.mark.parametrize("flags", [("--request-pause", "--resume"), ("--replay-only", "--resume"),
                                   ("--replay-only", "--request-pause")])
def test_lifecycle_actions_are_mutually_exclusive(environment, flags):
    _, root, calls, _ = environment
    with pytest.raises(SystemExit):
        cli.main(["--output", str(root), *flags])
    assert calls == []


@pytest.mark.parametrize("location", ["outputs/coevolution_v10", "outputs/coevolution_v9/run", "data/run"])
def test_broad_or_wrong_version_roots_rejected(environment, location):
    repo, _, calls, _ = environment
    with pytest.raises(ValueError, match="separate output"):
        cli.main(["--output", str(repo / location)])
    assert calls == []


def test_cli_help_does_not_import_study_or_construct_api(environment, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_study_module", lambda: pytest.fail("study import on help"))
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])
    assert error.value.code == 0
    assert "--replay-only" in capsys.readouterr().out


@pytest.fixture
def completed(environment):
    repo, root, calls, module = environment
    protocol = core.seal({"design_name": "smoke", "source_hashes": {}})
    result = core.seal({"complete": True, "protocol_hash": protocol["record_hash"],
                        "summary": {"n_questions": 4}, "ledger": {"cached_logical_calls": 24}})
    put(root / "protocol.json", protocol)
    put(root / "results.json", result)

    class Study:
        def __init__(self, actual_repo, actual_root, *, design, api_factory):
            assert actual_repo == repo and actual_root == root and design == "smoke"
            assert api_factory is cli.forbidden_api
            calls.append(("offline_construct",))

        def run(self):
            calls.append(("offline_run",))
            return deepcopy(result)

    module.Study = Study
    return repo, root, calls, module, protocol, result


def test_completed_replay_is_exact_zero_write_audit(completed):
    repo, root, calls, _, protocol, result = completed
    before = cli.tree_hashes(root)
    replay = cli.completed_replay(root, repo)
    assert replay["protocol"] == protocol and replay["result"] == result
    assert replay["audit"]["model_api_calls"] == 0 and replay["audit"]["verified_run_files"] == 2
    assert cli.tree_hashes(root) == before
    assert calls == [("offline_construct",), ("offline_run",)]


def test_replay_only_cli_infers_design_and_reports_audit(completed, capsys):
    _, root, calls, _, _, result = completed
    assert cli.main(["--output", str(root), "--replay-only"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["record_hash"] == result["record_hash"] and output["replay_audit"]["model_api_calls"] == 0
    assert calls == [("offline_construct",), ("offline_run",)]


@pytest.mark.parametrize("missing", ["results.json", "protocol.json"])
def test_replay_missing_completion_is_rejected_without_constructing(completed, missing):
    repo, root, calls, _, _, _ = completed
    (root / missing).unlink()
    with pytest.raises(ValueError, match="existing results"):
        cli.completed_replay(root, repo)
    assert calls == []


def test_replay_incomplete_result_cannot_start_an_experiment(completed):
    repo, root, calls, _, protocol, _ = completed
    put(root / "results.json", core.seal({"complete": False, "protocol_hash": protocol["record_hash"]}))
    with pytest.raises(ValueError, match="incomplete"):
        cli.completed_replay(root, repo)
    assert calls == []


def test_replay_protocol_mismatch_rejected_before_import(completed):
    repo, root, calls, _, _, _ = completed
    put(root / "results.json", core.seal({"complete": True, "protocol_hash": "a" * 64}))
    with pytest.raises(ValueError, match="not bound"):
        cli.completed_replay(root, repo)
    assert calls == []


def test_api_factory_is_hard_forbidden(completed):
    with pytest.raises(RuntimeError, match="forbidden"):
        cli.forbidden_api("repo", "root", max_calls=100)


def test_completed_replay_rejects_different_recomputed_result(completed):
    repo, root, _, module, protocol, _ = completed

    class Study:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return core.seal({"complete": True, "protocol_hash": protocol["record_hash"], "different": True})

    module.Study = Study
    with pytest.raises(ValueError, match="differs from"):
        cli.completed_replay(root, repo)


def test_completed_replay_detects_any_write(completed):
    repo, root, _, module, _, result = completed

    class Study:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            put(root / "unexpected.json", {"write": True})
            return result

    module.Study = Study
    with pytest.raises(ValueError, match="changed run artifacts"):
        cli.completed_replay(root, repo)


def test_completed_replay_suppresses_progress_stdout_and_preserves_supervisor_log(completed, capsys):
    from contextlib import redirect_stdout

    repo, root, _, module, _, result = completed
    log = root / "supervisor.log"
    log.write_text("prior log\n")

    class Study:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            print("replay progress must not enter supervisor.log")
            return result

    module.Study = Study
    with log.open("a") as stream, redirect_stdout(stream):
        cli.completed_replay(root, repo)
    assert log.read_text() == "prior log\n"
    assert capsys.readouterr().out == ""


def test_run_symlink_artifact_is_not_silently_audited(completed, tmp_path):
    repo, root, calls, _, _, _ = completed
    target = tmp_path / "outside"
    target.write_text("untrusted")
    (root / "alias.txt").symlink_to(target)
    with pytest.raises(ValueError, match="symlinks"):
        cli.completed_replay(root, repo)
    assert calls == []


def test_output_directory_symlink_rejected(environment, tmp_path):
    repo, root, calls, _ = environment
    target = tmp_path / "outside"
    target.mkdir()
    root.parent.mkdir(parents=True)
    root.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        cli.safe_root(root, repo)
    assert calls == []


def test_active_lock_refuses_second_runner_before_any_resume_mutation(environment):
    _, root, calls, _ = environment
    root.mkdir(parents=True)
    with (root / ".run.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="actively running"):
            cli.main(["--output", str(root), "--resume"])
    assert calls == []


def test_completed_replay_refuses_an_active_writer_without_changing_files(completed):
    repo, root, calls, _, _, _ = completed
    with (root / ".run.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = cli.tree_hashes(root)
        with pytest.raises(ValueError, match="actively running"):
            cli.completed_replay(root, repo)
        assert cli.tree_hashes(root) == before
    assert calls == []


def test_pause_does_not_require_writer_lock_so_running_process_can_drain(environment):
    _, root, calls, _ = environment
    root.mkdir(parents=True)
    with (root / ".run.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        cli.main(["--output", str(root), "--request-pause"])
    assert calls == [("pause", root)]


def test_pause_exit_75_releases_run_lock(environment, capsys):
    _, root, _, module = environment

    class PauseRequested(RuntimeError):
        pass

    class Study:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            raise PauseRequested("drained")

    module.PauseRequested = PauseRequested
    module.Study = Study
    assert cli.main(["--output", str(root)]) == 75
    assert json.loads(capsys.readouterr().out)["paused"] is True
    with cli._run_lock(root):
        pass
