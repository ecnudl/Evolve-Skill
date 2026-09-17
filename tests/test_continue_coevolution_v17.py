"""One-shot queue tests: no API, real subprocess, or blocking waiting."""

import json
from copy import deepcopy

import pytest

from scripts import continue_coevolution_v17 as q
from skillopt.coevolution_v12.study import save
from skillopt.coevolution_v17 import study


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    base = repo / "outputs/coevolution_v17"
    smoke, pilot, queue = (base / name for name in ("smoke", "pilot", "queue_test"))
    hashes = {"fixture.py": "fixed-source-hash"}
    for root, design in ((smoke, "smoke"), (pilot, "pilot")):
        panel = save(root / "private_panel.json", {"groups": {}})
        snapshot = save(root / "source_snapshot.json", {"files": {}})
        preflight = save(root / "task_preflight.json", {"all_checked": True})
        save(root / "protocol.json", {"design": design, "source_hashes": hashes,
             "panel_hash": panel["record_hash"], "source_snapshot_hash": snapshot["record_hash"],
             "preflight_hash": preflight["record_hash"], "max_calls": 123})
    monkeypatch.setattr(q, "REPO", repo)
    monkeypatch.setattr(study, "source_hashes", lambda unused: deepcopy(hashes))
    monkeypatch.setattr(q.time, "sleep", lambda unused: pytest.fail("Unexpected real waiting"))
    monkeypatch.setattr(q.subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected real process launch"))
    args = ["--smoke", str(smoke), "--pilot", str(pilot), "--queue", str(queue),
            "--report", str(repo / "docs/results.md")]
    result = {"complete": True, "design": "smoke",
              "protocol_hash": study.read(smoke / "protocol.json")["record_hash"],
              "ledger": {"cached_logical_calls": 20, "terminal_errors": 0},
              "learning": {"valid": 1}, "scientific_score": 0, "accepted": 0}
    return {"repo": repo, "smoke": smoke, "pilot": pilot, "queue": queue,
            "args": args, "result": result, "hashes": hashes}


def finish(config, *, result=None, audit=True, code=0):
    record = save(config["smoke"] / "results.json", result or config["result"])
    rows = [{"stage": "started", "child_pid": 123}]
    if audit:
        rows.append({"complete": True, "offline_verified": True, "result_hash": record["record_hash"]})
    rows.append({"stage": "finished" if code == 0 else "paused" if code == 75 else "stopped", "returncode": code})
    (config["smoke"] / "supervisor.log").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return record


def test_ready_ignores_scientific_scores_and_gate_acceptance(setup):
    finish(setup)
    assert q.ready(setup["repo"], setup["smoke"])[0] == "ready"


@pytest.mark.parametrize("audit,code", [(False, 0), (True, 1), (True, 75)])
def test_missing_audit_or_failed_supervisor_cannot_authorize(setup, audit, code):
    finish(setup, audit=audit, code=code)
    assert q.ready(setup["repo"], setup["smoke"])[0] == "stop"


@pytest.mark.parametrize("errors,valid,expected", [(2, 1, "ready"), (3, 1, "stop"), (0, 0, "stop")])
def test_operational_health_thresholds(setup, errors, valid, expected):
    result = deepcopy(setup["result"])
    result["ledger"]["terminal_errors"] = errors
    result["learning"]["valid"] = valid
    finish(setup, result=result)
    assert q.ready(setup["repo"], setup["smoke"])[0] == expected


def test_stale_audit_and_source_drift_fail_closed(setup, monkeypatch):
    finish(setup)
    path = setup["smoke"] / "supervisor.log"
    path.write_text(path.read_text().replace(study.read(setup["smoke"] / "results.json")["record_hash"], "stale"))
    assert q.ready(setup["repo"], setup["smoke"])[1] == "missing_result_bound_offline_audit"
    monkeypatch.setattr(study, "source_hashes", lambda unused: {"changed": "source"})
    assert q.ready(setup["repo"], setup["smoke"])[1] == "smoke_identity_or_frozen_source_mismatch"


def test_new_supervisor_session_invalidates_old_success(setup):
    finish(setup)
    with (setup["smoke"] / "supervisor.log").open("a") as handle:
        handle.write('{"stage":"started","child_pid":456}\n')
    assert q.last_supervisor_terminal(setup["smoke"]) is None
    assert q.ready(setup["repo"], setup["smoke"])[0] == "wait"


def test_prepared_pilot_rejects_started_activity(setup):
    assert q.prepared_pilot(setup["repo"], setup["pilot"])["design"] == "pilot"
    path = setup["pilot"] / "api/calls/attempt.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="prior runtime"):
        q.prepared_pilot(setup["repo"], setup["pilot"])


def test_valid_queue_launches_once_with_durable_intent_and_no_resume(setup, monkeypatch):
    finish(setup)
    launched = []
    def launch(command, **kwargs):
        assert (setup["queue"] / "launch_intent.json").is_file()
        assert "--resume" not in command and "--report" in command
        launched.append(command)
        return 0
    monkeypatch.setattr(q, "_monitor_pilot", launch)
    assert q.main(setup["args"]) == 0
    assert len(launched) == 1
    intent = study.read(setup["queue"] / "launch_intent.json")
    assert intent["scientific_score_selection"] is False and intent["queue_script_sha256"]
    assert q.main(setup["args"]) == 75
    assert len(launched) == 1


def test_process_creation_failure_keeps_launch_intent(setup, monkeypatch):
    finish(setup)
    def fail(*args, **kwargs):
        raise OSError("synthetic spawn failure")
    monkeypatch.setattr(q, "_monitor_pilot", fail)
    with pytest.raises(OSError):
        q.main(setup["args"])
    assert (setup["queue"] / "launch_intent.json").is_file()
    assert q.main(setup["args"]) == 75


@pytest.mark.parametrize("target", ["smoke", "pilot", "queue"])
def test_explicit_pause_prevents_launch(setup, target):
    finish(setup)
    setup[target].mkdir(parents=True, exist_ok=True)
    (setup[target] / "PAUSE").touch()
    assert q.main(setup["args"]) == 75
    assert not (setup["queue"] / "launch_intent.json").exists()


def test_missing_supervisor_stops_without_retry(setup):
    assert q.main(setup["args"]) == 1
    assert not (setup["queue"] / "launch_intent.json").exists()


def test_wait_timeout_is_bounded(setup, monkeypatch):
    monkeypatch.setattr(q, "_smoke_lock_held", lambda unused: True)
    clock = [1000.0]
    monkeypatch.setattr(q.time, "time", lambda: clock[0])
    monkeypatch.setattr(q.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(q.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    assert q.main(setup["args"]) == 75
    assert clock[0] == 1000 + q.WAIT_SECONDS
    assert not (setup["queue"] / "launch_intent.json").exists()
    assert "smoke_wait_timeout" in (setup["queue"] / "queue.log").read_text()


def test_monitor_forwards_pause_without_restart(setup, monkeypatch, tmp_path):
    setup["queue"].mkdir()
    (setup["queue"] / "PAUSE").touch()
    class Child:
        pid = 123
        returncode = None
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            assert (setup["pilot"] / "PAUSE").is_file()
            self.returncode = 75
            return 75
    calls = []
    monkeypatch.setattr(q.subprocess, "Popen", lambda *a, **k: (calls.append(a), Child())[1])
    events = []
    with (tmp_path / "log").open("a") as log:
        result = q._monitor_pilot(["fake"], repo=setup["repo"], smoke=setup["smoke"],
                                  pilot=setup["pilot"], queue=setup["queue"], log=log,
                                  event=lambda stage, **kw: events.append((stage, kw)))
    assert result == 75 and len(calls) == 1
    assert events[-1][0] == "paused"


def test_queue_lock_blocks_concurrent_operator(setup):
    import fcntl
    finish(setup)
    setup["queue"].mkdir()
    with (setup["queue"] / "queue.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            q.main(setup["args"])


def test_disjoint_roots_required(setup):
    args = list(setup["args"])
    args[args.index("--queue") + 1] = str(setup["pilot"])
    with pytest.raises(SystemExit):
        q.main(args)


@pytest.mark.parametrize("analysis_code", [0, 1])
def test_optional_analysis_only_after_pilot_success_and_failure_propagates(setup, monkeypatch, analysis_code):
    finish(setup)
    script = setup["repo"] / "scripts/analyze_coevolution_v17.py"
    script.parent.mkdir()
    script.write_text("# synthetic read-only analyzer\n")
    seen = []
    monkeypatch.setattr(q, "_monitor_pilot", lambda *a, **k: 0)
    monkeypatch.setattr(q, "_analysis", lambda *a, **k: (seen.append(a), analysis_code)[1])
    args = setup["args"] + ["--analysis-report", str(setup["repo"] / "docs/analysis.md")]
    assert q.main(args) == analysis_code
    assert len(seen) == 1
    assert study.read(setup["queue"] / "launch_intent.json")["analysis_script_sha256"]


def test_failed_pilot_never_starts_analysis(setup, monkeypatch):
    finish(setup)
    script = setup["repo"] / "scripts/analyze_coevolution_v17.py"
    script.parent.mkdir()
    script.write_text("# synthetic analyzer\n")
    monkeypatch.setattr(q, "_monitor_pilot", lambda *a, **k: 75)
    monkeypatch.setattr(q, "_analysis", lambda *a, **k: pytest.fail("Must not analyze failed pilot"))
    args = setup["args"] + ["--analysis-report", str(setup["repo"] / "docs/analysis.md")]
    assert q.main(args) == 75


@pytest.mark.parametrize("changed,expected", [(False, 0), (True, 1)])
def test_analysis_helper_checks_script_hash_and_bound_pilot_audit(setup, monkeypatch, tmp_path, changed, expected):
    import hashlib
    from types import SimpleNamespace
    script = setup["repo"] / "scripts/analyze_coevolution_v17.py"
    script.parent.mkdir()
    script.write_text("# synthetic analyzer\n")
    script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    result = {**setup["result"], "design": "pilot",
              "protocol_hash": study.read(setup["pilot"] / "protocol.json")["record_hash"]}
    finish({**setup, "smoke": setup["pilot"]}, result=result)
    if changed:
        script.write_text("# changed operational script\n")
    calls, events = [], []
    monkeypatch.setattr(q.subprocess, "run", lambda command, **kw:
                        (calls.append(command), SimpleNamespace(returncode=0))[1])
    with (tmp_path / "analysis.log").open("a") as log:
        code = q._analysis(setup["repo"], setup["pilot"], setup["repo"] / "docs/analysis.md",
                           script_hash, log, lambda stage, **kw: events.append((stage, kw)))
    assert code == expected
    assert len(calls) == (0 if changed else 1)
    if calls:
        assert "--output" in calls[0] and "--report" in calls[0]
