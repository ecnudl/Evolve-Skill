"""coevo5 call path (registration §5.4 row 4, §13.2-13.5): the global token ledger shared by every process, the
concurrency slots, and the call wrapper -- reservation before sending, per-attempt settlement, identical re-sends of a
call that delivered nothing, and what a cell's recorder hands to the decision table."""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from skillopt.coevo5 import budget as budget_module
from skillopt.coevo5.budget import OVERALL, Budget, chain_scope, step_scope
from skillopt.coevo5.calls import BREACH, Endpoint, Slots
from skillopt.coevo5.ledger import reservation
from skillopt.coevo5.outcomes import AssumptionBroken, BudgetStop, LedgerFailure, classify
from skillopt.coevo5.protocol import MAX_RESENDS, RESEND_COOLDOWN_SECONDS
from skillopt.continual_eval import backends

STEP = step_scope("E-glm", 1, "learning")
SCOPES = (OVERALL, chain_scope("E-glm"), STEP)
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def _budget(tmp_path, caps=None, **kwargs):
    ledger = Budget(tmp_path / "ledger", poll=0, **kwargs)
    ledger.declare(caps or {OVERALL: 10 ** 9, chain_scope("E-glm"): 10 ** 8, STEP: 10 ** 7})
    return ledger


def _events(tmp_path):
    return [json.loads(line) for line in (tmp_path / "ledger" / "events.jsonl").read_text().splitlines()]


# ------------------------------------------------------------------------------------------------- the ledger
def test_a_reservation_fits_every_scope_and_settles_at_most_its_amount(tmp_path):
    ledger = _budget(tmp_path)
    rid = ledger.reserve(SCOPES, 1000, label="cell", generation=0)
    assert ledger.snapshot()[STEP] == {"cap": 10 ** 7, "settled": 0, "open": 1000}
    ledger.settle(rid, 400, detail={})
    assert ledger.snapshot()[OVERALL] == {"cap": 10 ** 9, "settled": 400, "open": 0}
    assert [e["event"] for e in _events(tmp_path)][-2:] == ["reserve", "settle"]


@pytest.mark.parametrize("case", ["beyond the amount", "settled twice", "unknown"])
def test_a_refused_settlement_is_a_ledger_failure_that_halts_the_ledger(tmp_path, case):
    ledger = _budget(tmp_path)
    rid = ledger.reserve(SCOPES, 1000, label="cell", generation=0)
    if case == "settled twice":
        ledger.settle(rid, 400, detail={})
    with pytest.raises(LedgerFailure) as failure:
        ledger.settle(rid if case != "unknown" else "no-such-id", 1001 if case == "beyond the amount" else 0,
                      detail={})
    assert failure.value.quarantined and str(failure.value) == "ledger_failure:ValueError"
    view = ledger.snapshot()
    assert view["halted"] == {"reason": "ledger_failure:ValueError", "label": "settle:%s" % (
        rid if case != "unknown" else "no-such-id")}
    assert view[STEP]["open"] == (0 if case == "settled twice" else 1000)  # an unsettled call is charged in full later
    with pytest.raises(AssumptionBroken):
        ledger.reserve(SCOPES, 10, label="next", generation=0)


def test_caps_are_fixed_once_declared_and_raised_only_as_a_recorded_deviation(tmp_path):
    ledger = _budget(tmp_path)
    with pytest.raises(ValueError):
        ledger.declare({STEP: 5})
    ledger.raise_cap(STEP, 2 * 10 ** 7, deviation="owner raised the SearchQA learning cap")
    assert ledger.snapshot()[STEP]["cap"] == 2 * 10 ** 7 and _events(tmp_path)[-1]["event"] == "raise"
    ledger.declare({OVERALL: 10 ** 9, chain_scope("E-glm"): 10 ** 8, STEP: 10 ** 7})  # a restarted runner
    assert ledger.snapshot()[STEP]["cap"] == 2 * 10 ** 7  # the raise stays in force
    with pytest.raises(ValueError):
        ledger.declare({STEP: 2 * 10 ** 7})  # the registered cap is still the declared one
    with pytest.raises(ValueError):
        ledger.reserve((STEP,), 10, label="no overall scope", generation=0)
    with pytest.raises(ValueError):
        ledger.reserve((OVERALL,), 10, label="no generation", generation=None)
    with pytest.raises(LedgerFailure, match="ValueError"):  # a configuration error found under the lock halts
        ledger.reserve((OVERALL, "step:unknown"), 10, label="undeclared", generation=0)
    assert ledger.snapshot()["halted"]["label"] == "undeclared"


def test_a_call_that_cannot_fit_with_nothing_open_is_a_budget_stop(tmp_path):
    ledger = _budget(tmp_path, {OVERALL: 1000, STEP: 500})
    ledger.settle(ledger.reserve((OVERALL, STEP), 400, label="a", generation=0), 400, detail={})
    with pytest.raises(BudgetStop):
        ledger.reserve((OVERALL, STEP), 101, label="b", generation=0)
    assert _events(tmp_path)[-1]["event"] == "refuse" and _events(tmp_path)[-1]["exceeded"] == [STEP]
    ledger.reserve((OVERALL,), 600, label="other step", generation=0)  # only the step is exhausted


def test_a_call_waits_while_a_live_reservation_is_open_in_an_exceeded_scope(tmp_path):
    turns = []

    def sleep(_):  # the in-flight call settles while the new one waits
        turns.append(1)
        ledger.settle(first, 100, detail={})

    ledger = _budget(tmp_path, {OVERALL: 1000}, sleep=sleep)
    first = ledger.reserve((OVERALL,), 900, label="in flight", generation=0)
    second = ledger.reserve((OVERALL,), 800, label="waits", generation=0)
    assert turns == [1] and ledger.snapshot()[OVERALL] == {"cap": 1000, "settled": 100, "open": 800} and second


def test_a_reservation_of_an_ended_process_keeps_its_whole_amount(tmp_path):
    ledger = _budget(tmp_path, {OVERALL: 1000})
    rid = ledger.reserve((OVERALL,), 700, label="crashed", generation=0)
    state = json.loads((tmp_path / "ledger" / "state.json").read_text())
    state["open"][rid]["pid"] = 2 ** 22 + 12345  # no such process
    (tmp_path / "ledger" / "state.json").write_text(json.dumps(state))
    with pytest.raises(BudgetStop):
        ledger.reserve((OVERALL,), 400, label="new", generation=0)
    orphan = [e for e in _events(tmp_path) if e["event"] == "orphan"]
    assert orphan and orphan[0]["charged"] == 700 and ledger.snapshot()[OVERALL]["settled"] == 700
    ledger.reserve((OVERALL,), 300, label="fits", generation=0)


def test_a_reused_pid_or_an_unreaped_process_is_not_taken_for_the_reserving_process(tmp_path, monkeypatch):
    ledger = _budget(tmp_path, {OVERALL: 1000})
    entry = {"pid": ledger.owner["pid"], "host": ledger.owner["host"], "start": "123"}
    monkeypatch.setattr(budget_module, "_process", lambda pid: ("S", "456"))
    assert not ledger._alive(entry) and ledger._alive({**entry, "start": None})
    assert ledger._alive({**entry, "host": "another-machine"})
    monkeypatch.setattr(budget_module, "_process", lambda pid: ("Z", "123"))
    assert not ledger._alive(entry)


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="Linux process table")
def test_an_exited_child_that_was_not_reaped_releases_its_reservation(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        while budget_module._process(child.pid)[0] not in ("Z", "X", None):
            pass
        ledger = _budget(tmp_path, {OVERALL: 1000})
        assert not ledger._alive({"pid": child.pid, "host": ledger.owner["host"],
                                  "start": budget_module._process(child.pid)[1]})
    finally:
        child.wait()


class _Crash(BaseException):
    """The process dies here (nothing below it runs)."""


def test_a_crash_between_the_log_and_the_state_is_repaired_from_the_log(tmp_path, monkeypatch):
    ledger = _budget(tmp_path, {OVERALL: 1000})
    real = budget_module.os.replace

    def crash(*args):
        raise _Crash

    monkeypatch.setattr(budget_module.os, "replace", crash)
    with pytest.raises(_Crash):
        ledger.reserve((OVERALL,), 300, label="logged, state not replaced", generation=0)
    monkeypatch.setattr(budget_module.os, "replace", real)
    reopened = Budget(tmp_path / "ledger", poll=0)
    assert reopened.snapshot()[OVERALL] == {"cap": 1000, "settled": 0, "open": 300}
    assert [e["event"] for e in _events(tmp_path)] == ["declare", "reserve"]
    assert not list((tmp_path / "ledger").glob(".state-*"))  # no temporary state left behind


def test_a_breach_is_settled_and_halts_the_ledger_in_one_journal_event(tmp_path):
    ledger = _budget(tmp_path)
    rid = ledger.reserve(SCOPES, 1000, label="cell", generation=0)
    log, state = tmp_path / "ledger" / "events.jsonl", tmp_path / "ledger" / "state.json"
    before, cached = log.read_bytes(), state.read_bytes()
    ledger.settle(rid, 1500, detail={}, breach=BREACH)  # beyond the reservation: allowed for a breach only
    after = log.read_bytes()
    assert after.count(b"\n") == before.count(b"\n") + 1
    for cut in range(len(before), len(after) + 1):  # a crash at any byte of that line: both or neither
        log.write_bytes(after[:cut])
        state.write_bytes(cached)
        view = Budget(tmp_path / "ledger", poll=0).snapshot()
        done = cut == len(after)
        assert ("halted" in view) is done and view[STEP]["open"] == (0 if done else 1000)
        assert view[STEP]["settled"] == (1500 if done else 0)


def test_a_call_waiting_across_a_halt_and_a_resume_is_refused(tmp_path):
    def sleep(_):  # while the call waits: a breach elsewhere settles low and halts; the owner resumes
        ledger.settle(first, 100, detail={}, breach=BREACH)
        ledger.resume(decision="owner: resume after reviewing the receipt")

    ledger = _budget(tmp_path, {OVERALL: 1000}, sleep=sleep)
    first = ledger.reserve((OVERALL,), 900, label="in flight", generation=0)
    with pytest.raises(AssumptionBroken, match="since_the_attempt_began"):  # it would fit now: 100 + 800 <= 1000
        ledger.reserve((OVERALL,), 800, label="waits", generation=0)
    assert _events(tmp_path)[-1]["event"] == "refuse" and ledger.generation() == 1
    assert ledger.reserve((OVERALL,), 800, label="a new attempt's call", generation=1)


def test_a_torn_last_line_is_a_change_that_never_happened(tmp_path):
    ledger = _budget(tmp_path, {OVERALL: 1000})
    ledger.settle(ledger.reserve((OVERALL,), 300, label="a", generation=0), 100, detail={})
    log = tmp_path / "ledger" / "events.jsonl"
    size = log.stat().st_size
    with log.open("ab") as handle:
        handle.write(b'{"event": "reserve", "id": "torn')
    assert Budget(tmp_path / "ledger", poll=0).snapshot()[OVERALL] == {"cap": 1000, "settled": 100, "open": 0}
    assert log.stat().st_size == size
    state = json.loads((tmp_path / "ledger" / "state.json").read_text())
    state["offset"] = size + 1
    (tmp_path / "ledger" / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError):
        ledger.snapshot()


# -------------------------------------------------------------------------------------------------- the slots
def test_slots_admit_at_most_their_count_across_holders(tmp_path):
    def stuck(_):
        raise TimeoutError  # a holder that would have to wait

    slots, other = Slots(tmp_path / "slots", "glm-5.3", 1), Slots(tmp_path / "slots", "glm-5.3", 1, sleep=stuck)
    with slots.hold() as index:
        assert index == 0
        with pytest.raises(TimeoutError):
            with other.hold():
                pass
    with other.hold():  # released
        pass


def test_a_gatherer_takes_slots_as_they_free_while_single_holders_wait(tmp_path):
    root = tmp_path / "slots"
    first, second = Slots(root, "glm-5.3", 3).hold(), Slots(root, "glm-5.3", 3).hold()
    first.__enter__(), second.__enter__()  # two single holders are busy
    seen = []

    def stuck(_):
        raise TimeoutError

    def turn(_):  # while the gatherer waits, single holders take no slot; then one busy slot frees per turn
        seen.append(Slots(root, "glm-5.3", 3)._gathering())
        with pytest.raises(TimeoutError):
            with Slots(root, "glm-5.3", 3, sleep=stuck).hold():
                pass
        (first if len(seen) == 1 else second).__exit__(None, None, None)

    with Slots(root, "glm-5.3", 3, sleep=turn).hold_many(3) as held:
        assert held == [0, 1, 2] and seen == [True, True]
        assert not Slots(root, "glm-5.3", 3)._gathering()  # gathered: single holders would wait only for a slot
        with pytest.raises(TimeoutError):
            with Slots(root, "glm-5.3", 3, sleep=stuck).hold():
                pass
    with Slots(root, "glm-5.3", 3, sleep=stuck).hold():  # all released
        pass


def test_one_gatherer_per_pool_and_never_more_than_the_pool(tmp_path):
    root = tmp_path / "slots"
    with pytest.raises(ValueError):
        with Slots(root, "glm-5.3", 2).hold_many(3):
            pass
    with Slots(root, "glm-5.3", 4).hold_many(2) as held:
        assert held == [0, 1]
        with Slots(root, "glm-5.3", 4).hold() as index:  # the rest of the pool stays shared
            assert index in (2, 3)
        blocked = []

        def gather():
            with Slots(root, "glm-5.3", 4).hold_many(1):
                blocked.append("gathered")
        worker = threading.Thread(target=gather)
        worker.start()
        worker.join(0.3)
        assert blocked == []  # a second gatherer waits for the first one's gate
    worker.join(5)
    assert blocked == ["gathered"]


# ---------------------------------------------------------------------------------------------- the wrapper
class _Client:
    def __init__(self, *receipts):
        self.queue, self.requests = list(receipts), []

    def call(self, system, user):
        self.requests.append((system, user))
        reply = self.queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def _delivered(text="<answer>x</answer>", usage=USAGE):
    return {"ok": True, "response": text, "finish_reason": "stop", "error_type": None, "usage": usage,
            "attempts": [{"status": 200}], "returned_model": "glm-5.3"}


TRANSPORT = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "transport",
             "attempts": [{"error": "ReadTimeout"}] * 4}
REFUSED_429 = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "http_429",
               "attempts": [{"status": 429}] * 4}


def _endpoint(tmp_path, client, *, ledger=None, slept=None, max_tokens=100):
    return Endpoint(client, model="glm-5.3", max_tokens=max_tokens, slots=Slots(tmp_path / "slots", "glm-5.3", 2),
                    budget=ledger, scopes=SCOPES if ledger else (),
                    sleep=(slept.append if slept is not None else lambda _: None))


def test_a_delivered_reply_is_settled_at_its_reported_usage(tmp_path):
    ledger = _budget(tmp_path)
    recorder = _endpoint(tmp_path, _Client(_delivered()), ledger=ledger).recorder(label="cell")
    assert recorder("sys", "user")["ok"] is True
    (send,) = recorder.sends
    assert send["reserved"] == reservation(7, 100) and send["charged"] == 15 and not send["assumption_broken"]
    assert ledger.snapshot()[STEP] == {"cap": 10 ** 7, "settled": 15, "open": 0}
    assert recorder.receipts == [send["receipt"]] and not (recorder.refused or recorder.invalid or recorder.broken)


def test_a_call_that_delivered_nothing_is_resent_identically_after_the_cooldown(tmp_path):
    slept, ledger = [], _budget(tmp_path)
    client = _Client(TRANSPORT, REFUSED_429, _delivered())
    recorder = _endpoint(tmp_path, client, ledger=ledger, slept=slept).recorder(label="cell")
    assert recorder("sys", "user")["ok"] is True
    assert slept == [RESEND_COOLDOWN_SECONDS] * 2 and len(set(client.requests)) == 1 and len(client.requests) == 3
    assert [s["charged"] for s in recorder.sends] == [4 * (7 + 512 + 100), 0, 15]
    assert len(recorder.receipts) == 1  # the solver received one reply


def test_resends_stop_after_the_registered_number_and_the_last_receipt_is_returned(tmp_path):
    slept = []
    recorder = _endpoint(tmp_path, _Client(*[TRANSPORT] * (MAX_RESENDS + 1)), slept=slept).recorder(label="cell")
    assert recorder("sys", "user")["error_type"] == "transport"
    assert len(recorder.sends) == MAX_RESENDS + 1 and len(slept) == MAX_RESENDS


def test_a_noncompletion_is_a_delivered_reply_and_never_resent(tmp_path):
    truncated = {**_delivered(), "ok": False, "finish_reason": "length", "error_type": "finish_length"}
    recorder = _endpoint(tmp_path, _Client(truncated)).recorder(label="cell")
    assert recorder("sys", "user") is truncated and len(recorder.sends) == 1


def test_a_refused_call_raises_a_budget_stop_and_the_cell_is_a_stop_whatever_the_backend_reports(tmp_path):
    ledger = _budget(tmp_path, {OVERALL: 100, chain_scope("E-glm"): 100, STEP: 100})
    client = _Client(_delivered())
    recorder = _endpoint(tmp_path, client, ledger=ledger).recorder(label="cell")
    prediction = backends.solve("searchqa", {"question": "Q", "context": ["c"]}, "", recorder)
    assert prediction["reason"] == "model_call_exception:BudgetStop" and client.requests == []
    assert recorder.refused and recorder.sends[0]["refused"].startswith("budget_stop:")
    with pytest.raises(BudgetStop):
        classify("searchqa", prediction, receipts=recorder.receipts, refused=recorder.refused)


def test_a_receipt_beyond_the_bound_is_recorded_settled_as_reported_and_stops_every_call(tmp_path):
    ledger = _budget(tmp_path)
    over = _delivered(usage={"prompt_tokens": 7 + 513, "completion_tokens": 1, "total_tokens": 521})
    client = _Client(over, _delivered())
    endpoint = _endpoint(tmp_path, client, ledger=ledger)
    recorder = endpoint.recorder(label="cell")
    with pytest.raises(AssumptionBroken):
        recorder("sys", "user")
    assert recorder.broken and recorder.receipts == [] and recorder.sends[0]["receipt"] is over
    assert recorder.sends[0]["charged"] == 521 and ledger.snapshot()["halted"]["label"] == "cell"
    with pytest.raises(AssumptionBroken):  # this endpoint sends nothing more
        endpoint.recorder(label="next").__call__("sys", "user")
    assert len(client.requests) == 1
    with pytest.raises(AssumptionBroken):  # no unit attempt begins in any process while the ledger is halted
        _endpoint(tmp_path, _Client(_delivered()), ledger=Budget(tmp_path / "ledger", poll=0))
    ledger.resume(decision="owner: continue after reviewing the receipt")
    with pytest.raises(AssumptionBroken):  # the halted attempt is never continued, even after the resume
        endpoint.recorder(label="after")("sys", "user")
    other = _endpoint(tmp_path, _Client(_delivered()), ledger=Budget(tmp_path / "ledger", poll=0))
    assert other.recorder(label="a new attempt")("sys", "user")["ok"] is True and len(client.requests) == 1


def test_a_four_attempt_receipt_beyond_the_bound_settles_its_overrun(tmp_path):
    ledger = _budget(tmp_path)
    receipt = _delivered(usage={"prompt_tokens": 520, "completion_tokens": 100, "total_tokens": 620})
    receipt["attempts"] = [{"error": "ReadTimeout"}] * 3 + [{"status": 200}]
    recorder = _endpoint(tmp_path, _Client(receipt), ledger=ledger).recorder(label="cell")
    with pytest.raises(AssumptionBroken):
        recorder("sys", "user")
    (send,) = recorder.sends
    assert (send["reserved"], send["charged"]) == (4 * 619, 3 * 619 + 620)
    assert ledger.snapshot()[STEP] == {"cap": 10 ** 7, "settled": 3 * 619 + 620, "open": 0}
    settle = _events(tmp_path)[-1]
    assert (settle["event"], settle["overrun"], settle["breach"]) == ("settle", 1, BREACH)
    assert ledger.snapshot()["halted"] == {"reason": BREACH, "label": "cell"}


def test_a_breach_latches_the_endpoint_before_the_ledger_can_fail(tmp_path, monkeypatch):
    ledger = _budget(tmp_path)
    over = _delivered(usage={"prompt_tokens": 7 + 513, "completion_tokens": 1, "total_tokens": 521})
    client = _Client(over, _delivered())
    endpoint = _endpoint(tmp_path, client, ledger=ledger)

    def unwritable(self, *args, **kwargs):
        raise OSError("disk")

    monkeypatch.setattr(Budget, "settle", unwritable)
    recorder = endpoint.recorder(label="cell")
    with pytest.raises(OSError):
        recorder("sys", "user")
    assert recorder.broken == BREACH and recorder.failed == "ledger_failure:OSError"
    assert recorder.sends[0]["receipt"] is over  # recorded before the ledger was touched
    with pytest.raises(LedgerFailure):
        endpoint.recorder(label="next")("sys", "user")
    assert len(client.requests) == 1 and ledger.snapshot()["halted"]["reason"] == "ledger_failure:OSError"


def test_a_reservation_whose_commit_failed_is_released_unsent_and_the_ledger_halts(tmp_path, monkeypatch):
    ledger = _budget(tmp_path)
    real, failures = budget_module.os.replace, []
    client = _Client(_delivered())
    endpoint = _endpoint(tmp_path, client, ledger=ledger)
    competitor, outcome = Budget(tmp_path / "ledger", poll=0), []

    def compete():
        try:
            outcome.append(competitor.reserve(SCOPES, 10, label="another process", generation=0))
        except AssumptionBroken as stop:
            outcome.append(stop)

    def once(*args):
        if not failures:  # the reservation is logged; its state is not replaced. Another process asks meanwhile.
            failures.append(threading.Thread(target=compete))
            failures[0].start()
            time.sleep(0.2)
            raise OSError("state not replaced")
        return real(*args)

    monkeypatch.setattr(budget_module.os, "replace", once)
    recorder = endpoint.recorder(label="cell")
    with pytest.raises(LedgerFailure) as failure:
        recorder("sys", "user")
    failures[0].join()
    assert failure.value.quarantined and client.requests == []
    assert recorder.failed == "ledger_commit_failed:OSError" == recorder.sends[0]["ledger_failure"]
    assert isinstance(outcome[0], AssumptionBroken)  # admitted neither before nor after the quarantine
    reserve, quarantine, refused = _events(tmp_path)[-3:]
    assert (reserve["event"], quarantine["event"], refused["event"]) == ("reserve", "halt", "refuse")
    assert quarantine["close"] == [{"event": "release", "id": reserve["id"], "charged": 0,
                                    "reason": "not_sent_after_ledger_failure"}]
    view = ledger.snapshot()
    assert view[STEP]["open"] == 0 and view[STEP]["settled"] == 0
    assert view["halted"] == {"reason": "ledger_commit_failed:OSError", "label": "cell"}
    with pytest.raises(LedgerFailure):  # this endpoint sends nothing more
        endpoint.recorder(label="next")("sys", "user")


def test_a_quarantine_releases_nothing_unless_it_also_halts(tmp_path, monkeypatch):
    ledger = _budget(tmp_path)
    real, failures = budget_module.os.replace, []

    def once(*args):
        if not failures:
            failures.append(1)
            raise OSError("state not replaced")
        return real(*args)

    monkeypatch.setattr(budget_module.os, "replace", once)
    with pytest.raises(LedgerFailure):
        ledger.reserve(SCOPES, 1000, label="cell", generation=0)
    log, state = tmp_path / "ledger" / "events.jsonl", tmp_path / "ledger" / "state.json"
    after = log.read_bytes()
    before = after[:after.rstrip(b"\n").rfind(b"\n") + 1]  # up to the quarantine line
    assert [json.loads(line)["event"] for line in after.splitlines()][-2:] == ["reserve", "halt"]
    for cut in range(len(before), len(after) + 1):  # a crash at any byte of that line: both or neither
        log.write_bytes(after[:cut])
        state.unlink(missing_ok=True)  # replayed from the log
        view = Budget(tmp_path / "ledger", poll=0).snapshot()
        done = cut == len(after)
        assert ("halted" in view) is done and view[STEP]["open"] == (0 if done else 1000)


def test_a_settlement_the_ledger_did_not_record_is_applied_by_its_quarantine(tmp_path, monkeypatch):
    ledger = _budget(tmp_path)
    real, failures = Budget._commit, []

    def once(self, state, events):
        if not failures and events[0]["event"] == "settle":
            failures.append(1)
            raise OSError("log not written")  # nothing reached the log
        return real(self, state, events)

    monkeypatch.setattr(Budget, "_commit", once)
    client = _Client(_delivered(), _delivered())
    endpoint = _endpoint(tmp_path, client, ledger=ledger)
    recorder = endpoint.recorder(label="cell")
    with pytest.raises(LedgerFailure):
        recorder("sys", "user")
    assert recorder.failed == "ledger_commit_failed:OSError" and recorder.sends[0]["receipt"]["ok"] is True
    view = ledger.snapshot()
    assert view[STEP] == {"cap": 10 ** 7, "settled": 15, "open": 0} and view["halted"]["label"].startswith("settle:")
    (quarantine,) = [e for e in _events(tmp_path) if e["event"] == "halt"]
    assert [c["event"] for c in quarantine["close"]] == ["settle"] and len(client.requests) == 1


def _halt_and_resume(path):
    other = Budget(path, poll=0)
    other.halt("another process failed", label="elsewhere")
    other.resume(decision="owner: resume after reviewing the failure")


def test_a_resend_after_a_halt_and_a_resume_during_its_cooldown_is_refused(tmp_path):
    ledger = _budget(tmp_path)
    client = _Client(REFUSED_429, _delivered())
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 2),
                        budget=ledger, scopes=SCOPES, sleep=lambda _: _halt_and_resume(tmp_path / "ledger"))
    recorder = endpoint.recorder(label="cell")
    with pytest.raises(AssumptionBroken, match="since_the_attempt_began"):
        recorder("sys", "user")
    assert len(client.requests) == 1 and recorder.broken == "ledger_halted_since_the_attempt_began"
    assert [("halted" in s) for s in recorder.sends] == [False, True]
    with pytest.raises(AssumptionBroken):  # latched: the attempt is redone with a new endpoint, never continued
        endpoint.recorder(label="next")("sys", "user")


def test_a_call_that_waited_for_a_slot_across_a_halt_and_a_resume_is_refused(tmp_path):
    ledger = _budget(tmp_path)
    holder = Slots(tmp_path / "slots", "glm-5.3", 1).hold()
    holder.__enter__()  # the only slot is busy

    def wait(_):  # meanwhile another process halts the ledger and the owner resumes; then the slot is freed
        _halt_and_resume(tmp_path / "ledger")
        holder.__exit__(None, None, None)

    client = _Client(_delivered())
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 1,
                                                                              sleep=wait),
                        budget=ledger, scopes=SCOPES, sleep=lambda _: None)
    with pytest.raises(AssumptionBroken, match="since_the_attempt_began"):
        endpoint.recorder(label="cell")("sys", "user")
    assert client.requests == [] and ledger.snapshot()[STEP]["open"] == 0


def test_receipts_that_break_the_receipt_form_are_flagged(tmp_path):
    ledger = _budget(tmp_path)
    malformed = {**_delivered(), "attempts": []}
    recorder = _endpoint(tmp_path, _Client(malformed), ledger=ledger).recorder(label="cell")
    recorder("sys", "user")
    assert recorder.invalid and recorder.sends[0]["charged"] == recorder.sends[0]["reserved"]
    recorder = _endpoint(tmp_path, _Client(["not a mapping"]), ledger=ledger).recorder(label="cell")
    recorder("sys", "user")
    assert recorder.invalid


def test_a_client_exception_is_recorded_charged_its_reservation_and_raised(tmp_path):
    ledger = _budget(tmp_path)
    recorder = _endpoint(tmp_path, _Client(RuntimeError("bug")), ledger=ledger).recorder(label="cell")
    with pytest.raises(RuntimeError):
        recorder("sys", "user")
    (send,) = recorder.sends
    assert send["exception"] == "RuntimeError" and send["charged"] == send["reserved"]
    assert ledger.snapshot()[STEP]["open"] == 0


def test_the_ledger_keeps_fixed_categories_and_numbers_of_a_receipt_only(tmp_path):
    ledger = _budget(tmp_path)
    odd = {**_delivered(), "ok": False, "finish_reason": "SEALED", "error_type": "finish_SEALED",
           "usage": {**USAGE, "note": "SEALED", "completion_tokens": "5"},
           "attempts": [{"error": "SEALED text"}, {"status": 503}, {"error": "ReadTimeout"}, "SEALED"]}
    _endpoint(tmp_path, _Client(odd), ledger=ledger).recorder(label="cell")("sys", "user")
    (settle,) = [e for e in _events(tmp_path) if e["event"] == "settle"]
    assert settle["detail"] == {"error_type": "other", "attempts": ["other", 503, "ReadTimeout", "other"],
                                "usage": {"prompt_tokens": 10, "completion_tokens": None, "total_tokens": 15}}
    assert "SEALED" not in (tmp_path / "ledger" / "events.jsonl").read_text()


def test_an_uncharged_endpoint_never_touches_the_ledger(tmp_path):
    recorder = _endpoint(tmp_path, _Client(_delivered())).recorder(label="deepseek cell")
    recorder("sys", "user")
    assert "reserved" not in recorder.sends[0] and not (tmp_path / "ledger").exists()


def test_on_reply_runs_after_every_delivered_call(tmp_path):
    seen = []
    recorder = _endpoint(tmp_path, _Client(_delivered())).recorder(label="cell", on_reply=lambda: seen.append(1))
    recorder("sys", "user")
    assert seen == [1]


def test_v3_a_call_is_charged_to_one_overall_scope_and_only_its_model_s(tmp_path):
    """v3 §9: the deepseek solver's calls go to deepseek's own scopes, never to a GLM-5.3 scope (and vice versa)."""
    from skillopt.coevo5 import chain
    from skillopt.coevo5.budget import DEEPSEEK, deepseek_scope, rooted

    assert rooted(SCOPES) and rooted(chain.deepseek_scopes("I-ds", 1, "learning")) and rooted([DEEPSEEK])
    for mixed in ([chain_scope("I-ds")], [deepseek_scope("I-ds")], [OVERALL, DEEPSEEK],
                  [OVERALL, deepseek_scope("I-ds")], [DEEPSEEK, chain_scope("I-ds")]):
        assert not rooted(mixed)
    ledger = Budget(tmp_path / "ledger", poll=0)
    ledger.declare(chain.caps("I-ds", 10 ** 9))
    scopes = chain.deepseek_scopes("I-ds", 1, "learning")
    endpoint = Endpoint(_Client(_delivered(usage=USAGE)), model="deepseek-v4-flash", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "deepseek-v4-flash", 2), budget=ledger, scopes=scopes,
                        sleep=lambda _: None)
    recorder = endpoint.recorder(label="I-ds/s1/train")
    endpoint.send("system", "user", recorder)
    found = ledger.snapshot()
    assert {s: found[s]["settled"] for s in scopes} == {s: 15 for s in scopes}
    assert found[OVERALL]["settled"] == 0 and found[chain_scope("I-ds")]["settled"] == 0
    with pytest.raises(ValueError, match="one overall scope"):
        ledger.reserve((OVERALL, deepseek_scope("I-ds")), 10, label="mixed", generation=0)
    with pytest.raises(ValueError, match="one overall scope"):
        Endpoint(_Client(), model="deepseek-v4-flash", max_tokens=100, slots=Slots(tmp_path / "slots", "x", 1),
                 budget=ledger, scopes=(deepseek_scope("I-ds"),))
