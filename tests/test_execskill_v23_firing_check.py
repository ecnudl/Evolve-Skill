"""Amendment 2: C6b's exact routing inputs, fault handling and text-free feedback, with authored fake workers."""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from skillopt.execskill import engineer, protocol
from skillopt.execskill.package import FIXTURE, Procedure, empty

SOURCE = "def applies(view):\n    return True\ndef before_call(view, state):\n    return None\n"


class RoutingWorkers:
    def __init__(self, responses):
        self.responses, self.seen = responses, []

    @contextmanager
    def __call__(self, package, item):
        responses, seen = self.responses, self.seen

        class Worker:
            def call(self, procedure, hook, args, *, timeout_s):
                seen.append((package.order, item, procedure, hook, args, timeout_s))
                return responses[item]

        yield Worker()


def context(bench="searchqa", *, items=(), responses=None, mode=engineer.TRAIN, configuration=protocol.MAIN_V2_3):
    base = empty(step="s0", evidence=FIXTURE)
    workers = RoutingWorkers(responses or {})
    ctx = engineer.Context(bench=bench, k=1, step="s1", evidence=FIXTURE, parent=base, trajectories=[],
                           corpora={}, workers=None, roles=None, label="D/s1-%s/engineer-r1" % bench,
                           mode=mode, round=1 if mode == engineer.TRAIN else 0,
                           base=base if mode == engineer.TRAIN else None, configuration=configuration,
                           routing_items=list(items), routing_workers=workers)
    return ctx, workers


def procedure(bench="searchqa", *, excluded=()):
    return Procedure(id="fx-firing", origin=bench, description="Identifies applicable public tasks.",
                     hooks=("applies", "before_call"), source=SOURCE, evidence=FIXTURE,
                     max_note_chars=1000, excluded_benches=excluded)


@pytest.mark.parametrize("bench", ["searchqa", "alfworld"])
def test_firing_uses_every_supplied_run_and_generated_view_and_shows_no_values(bench):
    views = ([{"question": "PRIVATE-SENTINEL-RUN", "context": ["PRIVATE-SENTINEL-CONTEXT"]},
              {"question": "PRIVATE-SENTINEL-GENERATED", "context": []}]
             if bench == "searchqa" else
             [{"initial_observation": "PRIVATE-SENTINEL-RUN", "admissible_commands_at_reset": ["secret action"],
               "task_text": "PRIVATE-SENTINEL-TASK"},
              {"initial_observation": "PRIVATE-SENTINEL-GENERATED", "admissible_commands_at_reset": [],
               "task_text": "PRIVATE-SENTINEL-GENERATED-TASK"}])
    ctx, workers = context(bench, items=list(zip(("run-key", "generated-key"), views)),
                           responses={"run-key": {"ok": True, "value": False},
                                      "generated-key": {"ok": True, "value": True}})
    passed, detail = engineer._firing(procedure(bench), ctx)
    assert passed and detail["fires_on"] == 1 and detail["items"] == 2 and detail["predicate_faults"] == 0
    assert [entry[1] for entry in workers.seen] == ["run-key", "generated-key"]
    assert [entry[4][0] for entry in workers.seen] == views
    assert all(entry[3] == "applies" and entry[5] == protocol.SANDBOX_TIMEOUTS["predicate"]
               for entry in workers.seen)
    assert detail["routing_view_keys"] == sorted(views[0])
    encoded = json.dumps(detail)
    assert all(value not in encoded for value in ("PRIVATE-SENTINEL", "secret action", "run-key", "generated-key"))
    if bench == "alfworld":
        assert set(detail["step_view_keys"]) == {"initial_observation", "observation", "admissible_commands",
                                                "recent_history"}
        assert detail["note"] == "applies() receives the routing view; hooks receive the step view"
    else:
        assert "step_view_keys" not in detail and "note" not in detail


@pytest.mark.parametrize("response,faults", [
    ({"ok": True, "value": False}, 0),
    ({"ok": True, "value": 1}, 1),
    ({"ok": True, "value": "True"}, 1),
    ({"ok": False, "fault": "exception", "exc_type": "ValueError", "message": "SECRET-ITEM-TEXT"}, 1),
])
def test_only_fault_free_boolean_true_fires_and_fault_messages_never_reach_feedback(response, faults):
    ctx, _ = context(items=[("run", {"question": "SECRET-QUESTION"})], responses={"run": response})
    passed, detail = engineer._firing(procedure(), ctx)
    assert not passed and detail["fires_on"] == 0 and detail["predicate_faults"] == faults
    assert "SECRET" not in json.dumps(detail) and "ValueError" not in json.dumps(detail)
    failure = {"check": "C6b", "passed": False, "detail": detail}
    assert engineer._redacted(failure) == failure


def test_one_valid_firing_is_sufficient_even_when_another_item_has_a_predicate_fault():
    ctx, _ = context(items=[("a", {"question": "a"}), ("b", {"question": "b"})],
                     responses={"a": {"ok": False, "fault": "exception"}, "b": {"ok": True, "value": True}})
    passed, detail = engineer._firing(procedure(), ctx)
    assert passed and detail["fires_on"] == 1 and detail["predicate_faults"] == 1 and detail["items"] == 2


def test_procedure_excluded_from_the_current_bench_cannot_count_as_firing():
    ctx, workers = context(items=[("run", {"question": "public"})], responses={"run": {"ok": True, "value": True}})
    passed, detail = engineer._firing(procedure(excluded=("searchqa",)), ctx)
    assert not passed and detail["fires_on"] == 0 and detail["items"] == 1 and not workers.seen


def test_empty_single_smoke_is_explicitly_skipped_but_empty_train_fails_closed():
    smoke, _ = context(mode="single")
    passed, detail = engineer._firing(procedure(), smoke)
    assert passed and detail == {"fires_on": 0, "items": 0, "predicate_faults": 0, "routing_view_keys": [],
                                "skipped": True, "reason": "no_training_items"}
    train, _ = context()
    passed, detail = engineer._firing(procedure(), train)
    assert not passed and detail["items"] == 0 and not detail.get("skipped")


@pytest.mark.parametrize("configuration", protocol.CONFIGURATIONS)
def test_c6b_is_after_c6_and_only_main_v23_changes_check_order(monkeypatch, configuration):
    ctx, _ = context(configuration=configuration, items=[("run", {"question": "public"})],
                     responses={"run": {"ok": True, "value": True}})

    class Worker:
        rejected = {}

        def ping(self):
            return None

    @contextmanager
    def workers(*args, **kwargs):
        yield Worker()

    ctx.workers = workers
    monkeypatch.setattr(engineer.replay, "zero_crash", lambda *a, **k: ({"passed": True}, {}))
    monkeypatch.setattr(engineer, "leak_check", lambda *a, **k: (True, None))
    monkeypatch.setattr(engineer.replay, "registrar_checks", lambda *a, **k: {"passed": True})
    change = engineer.Change(1, "new", {"kind": "new", "description": "Identifies public tasks.",
                                       "hooks": ["applies", "before_call"], "max_note_chars": 1000}, SOURCE, "a" * 64)
    report = engineer.check(change, ctx)
    assert report["passed"]
    expected = ["C1", "C2", "C4", "C3", "C5", "C6", "C4", "C7", "C8", "C9"]
    if configuration == protocol.MAIN_V2_3:
        expected.insert(6, "C6b")
    assert [result["check"] for result in report["checks"]] == expected


def test_c6_failure_does_not_execute_c6b(monkeypatch):
    ctx, _ = context()
    change = engineer.Change(1, "new", {"kind": "new", "description": "Identifies public tasks.",
                                       "hooks": ["applies", "before_call"], "max_note_chars": 1000}, SOURCE, "a" * 64)

    class Worker:
        rejected = {}

        def ping(self):
            return None

    @contextmanager
    def workers(*args, **kwargs):
        yield Worker()

    ctx.workers = workers
    monkeypatch.setattr(engineer.replay, "zero_crash", lambda *a, **k: ({"passed": False}, {}))
    monkeypatch.setattr(engineer, "_firing", lambda *a: pytest.fail("C6b must follow a passed C6"))
    report = engineer.check(change, ctx)
    assert report["failed"] == "C6" and all(entry["check"] != "C6b" for entry in report["checks"])


@pytest.mark.parametrize("stamp", ["engineer", "engineer-v2-3", "engineer-v2-3-a2"])
def test_engineer_reader_preserves_frozen_stamps_and_accepts_amendment2(stamp):
    record = protocol.record(stamp, FIXTURE, {"changes": []})
    assert protocol.verified(record, "engineer") == record


@pytest.mark.parametrize("name", ["procedure", "decision", "acceptance-sealed", "unit"])
def test_amendment2_does_not_create_other_record_aliases(name):
    record = protocol.record(name + "-v2-3-a2", FIXTURE, {})
    with pytest.raises(ValueError, match="another kind"):
        protocol.verified(record, name)
