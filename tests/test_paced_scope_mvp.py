"""Offline transport tests; synthetic clocks avoid real rate-limit sleeps."""

from __future__ import annotations

import math
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import paced_scope_mvp as launcher


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        assert duration > 0
        self.sleeps.append(duration)
        self.now += duration


def test_first_call_immediate_and_minimum_spacing_without_burst_credit():
    clock = Clock()
    pacer = launcher.StartPacer(2, clock=clock.monotonic, sleep=clock.sleep)
    assert [pacer.wait(), pacer.wait(), pacer.wait()] == [0, 2, 4]
    clock.now = 50
    assert [pacer.wait(), pacer.wait()] == [50, 52]
    assert clock.sleeps == [2, 2, 2]


def test_short_sleep_is_rechecked_until_the_monotonic_deadline():
    clock = Clock()

    def short_first_sleep(duration):
        clock.sleep(duration / 2 if not clock.sleeps else duration)

    pacer = launcher.StartPacer(2, clock=clock.monotonic, sleep=short_first_sleep)
    assert [pacer.wait(), pacer.wait()] == [0, 2]
    assert clock.sleeps == [1, 1]


def test_thread_safe_start_admissions_share_one_interval():
    clock = Clock()
    pacer = launcher.StartPacer(2, clock=clock.monotonic, sleep=clock.sleep)
    with ThreadPoolExecutor(max_workers=6) as pool:
        starts = list(pool.map(lambda _: pacer.wait(), range(24)))
    assert sorted(starts) == list(range(0, 48, 2))


def test_wrapper_forwards_arguments_and_restores_exact_original():
    clock = Clock()
    calls = []
    result = ("original response", {"total_tokens": 7})

    def original(*args, **kwargs):
        calls.append((clock.now, args, kwargs))
        return result

    backend = SimpleNamespace(_chat_messages_impl=original)
    messages = [{"role": "system", "content": "unchanged prompt"}]
    kwargs = {"role": "target", "deployment": "gpt-5.5", "timeout": 90,
              "tools": None, "tool_choice": None, "return_message": False}
    with launcher.paced_backend(backend, 2, clock=clock.monotonic, sleep=clock.sleep):
        assert backend._chat_messages_impl(messages, 16384, 3, "stage", **kwargs) is result
        assert backend._chat_messages_impl(messages, 16384, 3, "stage", **kwargs) is result
    assert backend._chat_messages_impl is original
    assert calls == [(0, (messages, 16384, 3, "stage"), kwargs),
                     (2, (messages, 16384, 3, "stage"), kwargs)]


def test_backend_io_is_not_held_under_the_pacing_lock():
    clock = Clock()
    first_entered, second_entered = threading.Event(), threading.Event()

    def original(index):
        if index == 0:
            first_entered.set()
            assert second_entered.wait(timeout=1)
        else:
            second_entered.set()
        return index

    backend = SimpleNamespace(_chat_messages_impl=original)
    with launcher.paced_backend(backend, 2, clock=clock.monotonic, sleep=clock.sleep), ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(backend._chat_messages_impl, 0)
        assert first_entered.wait(timeout=1)
        second = pool.submit(backend._chat_messages_impl, 1)
        assert first.result(timeout=1) == 0
        assert second.result(timeout=1) == 1
    assert clock.sleeps == [2]


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_exception_exit_restores_original_without_logging(error_type, capsys):
    clock = Clock()

    def original():
        raise error_type("synthetic-private-session")

    backend = SimpleNamespace(_chat_messages_impl=original)
    with pytest.raises(error_type):
        with launcher.paced_backend(backend, 2, clock=clock.monotonic, sleep=clock.sleep):
            backend._chat_messages_impl()
    assert backend._chat_messages_impl is original
    assert capsys.readouterr() == ("", "")


def test_internal_retries_are_not_wrapped_individually():
    clock = Clock()
    internal_attempts = []

    def original():
        # Models one logical backend call containing its own retry loop.
        for _ in range(3):
            internal_attempts.append(clock.now)
        return "success"

    backend = SimpleNamespace(_chat_messages_impl=original)
    with launcher.paced_backend(backend, 2, clock=clock.monotonic, sleep=clock.sleep):
        backend._chat_messages_impl()
        backend._chat_messages_impl()
    assert internal_attempts == [0, 0, 0, 2, 2, 2]
    assert clock.sleeps == [2]


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, True])
def test_invalid_interval_is_rejected(bad):
    with pytest.raises(ValueError, match="positive finite"):
        launcher.StartPacer(bad)


@pytest.mark.parametrize("entry", ["source", "routing"])
@pytest.mark.parametrize("separator", [[], ["--"]])
def test_session_preload_import_order_and_cli_passthrough(entry, separator, monkeypatch, capsys):
    events = []

    def original():
        return "not called"

    backend = SimpleNamespace(_chat_messages_impl=original)
    phase = "pilot" if entry == "source" else "route-calibration"
    forwarded = ["--phase", phase, "--out", "outputs/scope_evolution_v2/example", "--workers", "6"]

    def preload(repo):
        events.append("preload-session")
        return "synthetic-private-session"

    def delegated(arguments):
        assert backend._chat_messages_impl is not original
        events.append(("delegate", arguments))
        return 23

    helper = SimpleNamespace(preload_session_environment=preload, main=delegated)

    def fake_import(name):
        if name == "scripts.source_retention_session_mvp":
            events.append("import-session-helper")
            return helper
        if name == "skillopt.model.openai_compatible_backend":
            assert events[-1] == "preload-session"
            events.append("import-backend")
            return backend
        assert name == "scripts.retention_routing_mvp"
        events.append("import-routing-cli")
        return SimpleNamespace(main=delegated)

    monkeypatch.setattr(launcher.importlib, "import_module", fake_import)
    assert launcher.main(["--entry", entry, "--min-interval", "2", *separator, *forwarded]) == 23
    assert events[-1] == ("delegate", forwarded)
    assert backend._chat_messages_impl is original
    assert capsys.readouterr() == ("", "")


def test_delegate_exception_restores_backend(monkeypatch):
    def original():
        return "unused"

    backend = SimpleNamespace(_chat_messages_impl=original)

    def delegated(arguments):
        assert backend._chat_messages_impl is not original
        raise RuntimeError("synthetic delegate failure")

    helper = SimpleNamespace(preload_session_environment=lambda repo: "existing-session", main=delegated)
    monkeypatch.setattr(launcher.importlib, "import_module",
                        lambda name: backend if name == "skillopt.model.openai_compatible_backend" else helper)
    with pytest.raises(RuntimeError, match="synthetic delegate"):
        launcher.main(["--entry", "source", "--phase", "pilot"])
    assert backend._chat_messages_impl is original


def test_import_alone_is_model_free_and_help_discloses_retry_limit():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.paced_scope_mvp; import sys; "
         "assert 'skillopt.model.openai_compatible_backend' not in sys.modules"],
        cwd=repo, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    help_result = subprocess.run([sys.executable, "scripts/paced_scope_mvp.py", "--help"],
                                 cwd=repo, check=False, capture_output=True, text=True)
    assert help_result.returncode == 0
    assert "Internal retries are NOT separately paced" in help_result.stdout
