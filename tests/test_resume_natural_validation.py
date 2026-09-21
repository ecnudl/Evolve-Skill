"""Offline recovery engineering checks; no real API calls or benchmark evidence."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from scripts.resume_natural_validation import RecoveryControl, RecoveryPause
from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest, write_immutable_json


def test_cli_rejects_unvalidated_transport_switch(monkeypatch, capsys):
    from scripts.resume_natural_validation import main

    monkeypatch.setattr("sys.argv", [
        "resume_natural_validation", "--output", "unused", "--pause", "unused",
        "--remote-repo", "/unused", "--reuse-from", "unused",
        "--public-preflight", "unused", "--health-summary", "unused",
        "--session", "fixture", "--local-docker",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "unrecognized arguments: --local-docker" in capsys.readouterr().err


class API:
    model = "fixture-model"
    service = {"fixture": True, "model": model}

    def __init__(self, root):
        self.root, self.sent, self.ok = root, 0, True
        self.lock, self.active, self.peak = threading.Lock(), 0, 0

    def call(self, system, user, kind, key, max_tokens=2048, repeat=0):
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "repeat": repeat, "max_tokens": max_tokens, "service": self.service}
        identifier = digest(request)
        path = self.root / "calls" / (identifier + ".json")
        if path.exists():
            return json.loads(path.read_text())
        with self.lock:
            self.sent += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(.01)
        with self.lock:
            self.active -= 1
        record = {"request_hash": identifier, "request": request, "ok": self.ok,
                  "response": "fixture" if self.ok else "", "usage": {}, "http_attempt_count": 1}
        write_immutable_json(path, record)
        return record


def fixture(tmp_path, *, max_new=24):
    protocol = seal({"service": API.service})
    write_immutable_json(tmp_path / "protocol.json", protocol)
    args = {"system": "s", "user": "interrupted", "kind": "natural-solver", "repeat": 0, "max_tokens": 2048}
    request = {"model": API.model, **args, "service": API.service,
               "key": digest({"protocol": protocol["record_hash"], **args})}
    identifier = digest(request)
    write_immutable_json(tmp_path / "model_budget/intents" / (identifier + ".json"), seal({
        "request_hash": identifier, "protocol_hash": protocol["record_hash"], "kind": "natural-solver", "repeat": 0}))
    pause = seal({"protocol_hash": protocol["record_hash"], "unclosed_requests": [
        {"request": request, "request_hash": identifier}]})
    write_immutable_json(tmp_path / "pause.json", pause)
    api = API(tmp_path / "api")
    calls = BoundedCalls(api, tmp_path / "model_budget", protocol["record_hash"], 100)
    return RecoveryControl(tmp_path, tmp_path / "pause.json", max_new=max_new), calls, identifier


def test_interrupted_unknown_is_local_and_replays_without_fake_receipt(tmp_path):
    control, calls, identifier = fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    with control.active():
        result = calls.call("s", "interrupted", "natural-solver")
        assert result == calls.call("s", "interrupted", "natural-solver")
    assert not result["ok"] and not result["provider_reply_observed"]
    assert result["usage"] is result["http_attempt_count"] is None
    assert calls.api.sent == 0 and not list((calls.api.root / "calls").glob("*.json"))
    assert (tmp_path / "resume_control/local_unknown" / (identifier + ".json")).exists()
    assert all(p.read_bytes() == b for p, b in before.items())
    with pytest.raises(ValueError, match="Interrupted API request"):
        calls.call("s", "interrupted", "natural-solver")


def test_existing_failed_receipt_unchanged_new_failure_trips_breaker(tmp_path):
    control, calls, _ = fixture(tmp_path)
    calls.api.ok = False
    old = calls.call("s", "old failure", "natural-solver")
    terminal = calls.api.root / "calls" / (old["request_hash"] + ".json")
    before = terminal.read_bytes()
    with control.active():
        assert calls.call("s", "old failure", "natural-solver") == old
        assert not control.stopped.is_set()
        assert not calls.call("s", "new failure", "natural-solver")["ok"]
        assert control.stopped.is_set()
        with pytest.raises(RecoveryPause):
            calls.call("s", "not sent", "natural-solver")
        assert calls.call("s", "old failure", "natural-solver") == old
    assert terminal.read_bytes() == before and calls.api.sent == 2
    assert len(control.started) == len(control.failures) == 1


def test_chunk_limit_and_concurrency_without_phantom_intents(tmp_path):
    control, calls, _ = fixture(tmp_path, max_new=4)
    with control.active(), ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(calls.call, "s", str(i), "natural-solver") for i in range(8)]
        results, paused = [], 0
        for future in futures:
            try:
                results.append(future.result())
            except RecoveryPause:
                paused += 1
    assert len(results) == calls.api.sent == 4 and paused == 4 and calls.api.peak <= 2
    assert len(list((calls.root / "intents").glob("*.json"))) == 5  # includes original interruption


def test_aliases_count_once_and_graceful_stop_allows_cached_replay(tmp_path):
    control, calls, _ = fixture(tmp_path)
    with control.active(), ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: calls.call("s", "one", "natural-solver"), range(6)))
        control.stop("requested_graceful_stop")
        assert calls.call("s", "one", "natural-solver") == results[0]
        with pytest.raises(RecoveryPause):
            calls.call("s", "two", "natural-solver")
    assert calls.api.sent == len(control.started) == 1 and results == [results[0]] * 6


def test_unrecognized_interruption_is_not_resampled(tmp_path):
    control, calls, _ = fixture(tmp_path)
    extra = calls.root / "intents" / ("a" * 64 + ".json")
    write_immutable_json(extra, seal({"unknown": True}))
    with pytest.raises(ValueError, match="Additional interruption"):
        RecoveryControl(tmp_path, tmp_path / "pause.json")
    assert calls.api.sent == 0


@pytest.mark.parametrize("damage", ["wrong_request", "wrong_protocol", "late_terminal"])
def test_invalid_resolution_rejected(tmp_path, damage):
    _, calls, identifier = fixture(tmp_path)
    pause_path = tmp_path / "pause.json"
    pause = json.loads(pause_path.read_text())
    pause.pop("record_hash")
    if damage == "wrong_request":
        pause["unclosed_requests"][0]["request"]["user"] = "changed"
    elif damage == "wrong_protocol":
        pause["protocol_hash"] = "0" * 64
    else:
        write_immutable_json(calls.api.root / "calls" / (identifier + ".json"), {"ok": True})
    pause_path.write_text(json.dumps(seal(pause)))
    with pytest.raises(ValueError):
        RecoveryControl(tmp_path, pause_path)


def test_no_updater_or_probe_permitted(tmp_path):
    control, calls, _ = fixture(tmp_path)
    with control.active(), pytest.raises(ValueError, match="only permits solver"):
        calls.call("s", "u", "natural-skill-update")
    assert calls.api.sent == 0


def test_paced_recovery_waits_only_before_new_requests(tmp_path):
    _, calls, _ = fixture(tmp_path)
    control = RecoveryControl(tmp_path, tmp_path / "pause.json", concurrency=1, min_idle_seconds=30)
    with control.active(), patch.object(control.stopped, "wait", return_value=False) as wait:
        calls.call("s", "interrupted", "natural-solver")
        first = calls.call("s", "one", "natural-solver")
        assert calls.call("s", "one", "natural-solver") == first
        calls.call("s", "two", "natural-solver")
    assert wait.call_count == calls.api.sent == 2
    assert all(c.args == (30,) for c in wait.call_args_list)
    assert control.summary()["minimum_idle_seconds_between_logical_calls"] == 30


def test_stop_during_cooldown_does_not_reserve_or_send(tmp_path):
    _, calls, _ = fixture(tmp_path)
    control = RecoveryControl(tmp_path, tmp_path / "pause.json", concurrency=1, min_idle_seconds=30)

    def stop_during_wait(_):
        control.stop("requested_graceful_stop")
        return True

    with control.active(), patch.object(control.stopped, "wait", side_effect=stop_during_wait):
        with pytest.raises(RecoveryPause):
            calls.call("s", "not sent", "natural-solver")
    assert not control.started and calls.api.sent == 0
    assert len(list((calls.root / "intents").glob("*.json"))) == 1


@pytest.mark.parametrize("concurrency,idle", [(2, 30), (1, -1), (1, 61), (1, True), (1, .5)])
def test_invalid_pacing_rejected(tmp_path, concurrency, idle):
    fixture(tmp_path)
    with pytest.raises(ValueError):
        RecoveryControl(tmp_path, tmp_path / "pause.json", concurrency=concurrency, min_idle_seconds=idle)


def test_window_limits_new_calls_not_cached_replays(tmp_path):
    _, calls, _ = fixture(tmp_path)
    now = [0.]
    with patch("scripts.resume_natural_validation.time.monotonic", side_effect=lambda: now[0]):
        control = RecoveryControl(tmp_path, tmp_path / "pause.json", concurrency=4, launch_window_seconds=20)

        def elapse(seconds):
            now[0] += seconds
            return False

        with control.active(), patch.object(control.stopped, "wait", side_effect=elapse) as wait:
            for i in range(9):
                result = calls.call("s", str(i), "natural-solver")
                assert calls.call("s", str(i), "natural-solver") == result
        assert wait.call_count == 2 and now[0] == 40
        assert calls.api.sent == len(control.started) == 9


def test_window_wait_can_be_stopped_without_an_intent(tmp_path):
    _, calls, _ = fixture(tmp_path)
    with patch("scripts.resume_natural_validation.time.monotonic", return_value=0.):
        control = RecoveryControl(tmp_path, tmp_path / "pause.json", concurrency=2, launch_window_seconds=20)

        def stop_wait(_):
            control.stop("requested_graceful_stop")
            return True

        with control.active(), patch.object(control.stopped, "wait", side_effect=stop_wait):
            calls.call("s", "one", "natural-solver")
            calls.call("s", "two", "natural-solver")
            with pytest.raises(RecoveryPause):
                calls.call("s", "not sent", "natural-solver")
        assert calls.api.sent == len(control.started) == 2
        assert len(list((calls.root / "intents").glob("*.json"))) == 3


def test_four_workers_do_not_exceed_chunk_cap(tmp_path):
    _, calls, _ = fixture(tmp_path)
    control = RecoveryControl(tmp_path, tmp_path / "pause.json", concurrency=4, max_new=3)
    with control.active(), ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(calls.call, "s", str(i), "natural-solver") for i in range(12)]
        completed = 0
        for job in jobs:
            try:
                job.result()
                completed += 1
            except RecoveryPause:
                pass
    assert completed == calls.api.sent == len(control.started) == 3 and calls.api.peak <= 4
