"""Adversarial v2.4 fix-prompt isolation using authored hooks and the actual engineer fix loop.

Generated routing items are synthetic; their questions must not reach any role request or
feedback record, even when a hook returns or raises that question verbatim.
"""
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import GOOD, PUBLIC, Roles, change, claim, context, detail
from tests.test_execskill_zpc_pipeline import offline


GENERATED = "GENERATEDQUESTIONFORBIDDENZSENTINEL"
RUN_MESSAGE = "VERIFIEDRUNEXCEPTIONVISIBLEZSENTINEL"
RUN_EXAMPLE = "VERIFIEDRUNOUTPUTEXAMPLEVISIBLEZSENTINEL"
OPENING = "There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street."
GENERATED_VIEW = {"question": OPENING + "\n" + GENERATED, "columns": ["Name", "Color"]}


class WireRoles(Roles):
    """Capture the actual serialized request rather than just a selected feedback field."""
    def __init__(self, replies=()):
        super().__init__(replies)
        self.wire = []

    def plain(self, role, system, user, *, label, **options):
        self.wire.append({"role": role, "system": system, "user": user, "label": label, "options": options})
        return super().plain(role, system, user, label=label, **options)


def add_generated(ctx):
    # This is an admitted routing item, not a stored run trajectory. It precedes the
    # verified run item so an unguarded first-exception slot captures it.
    ctx.routing_items.insert(0, ("gen:unshown", dict(GENERATED_VIEW)))


def with_run_example(ctx):
    run = ctx.trajectories[0]
    feedback = {"adopted": False, "reason": "gain:fixed_over_broken", "items": 1,
        "fixed": 0, "broken": 0, "net": "0/1", "need": 1, "p_sign": 1.0,
        "guards": {"own_faults": True, "predicate_faults": True, "format": True},
        "generated": {"items": 1, "fixed": 0, "broken": 0}, "procedures": [],
        "identical_items": [run["task_id"]], "unfixed_examples": [{
            "task_id": run["task_id"], "cell": run["cell"], "token": "fail",
            "source": "identical_current", "notes": RUN_EXAMPLE, "answer": "Authored failed run answer.",
            "reference": "reference unavailable"}]}
    return replace(ctx, round=2, current=[run], training=feedback, analysed=frozenset({run["task_id"]}))


def assert_no_generated_content(ctx, record, *, extra=None):
    # Include every request (propose and fix), its system message, every recorded
    # check and lint detail, and the next-round examples/sample payload. Checking
    # only C6c.sample would miss the exception feedback defect.
    serialized = json.dumps({"requests": ctx.roles.wire, "record": record,
                             "payload": engineer.payload(ctx), "extra": extra}, ensure_ascii=False)
    assert GENERATED not in serialized
    assert GENERATED_VIEW["question"] not in serialized
    return serialized


@pytest.mark.parametrize("action", [
    'raise ValueError(view["question"])',
    'return view["question"]',
    'return {"facts": view["question"]}',
], ids=["raised-question", "returned-question", "invalid-facts-question"])
def test_entire_actual_fix_prompt_keeps_generated_questions_out_of_every_feedback_channel(action):
    ctx, workers = context()
    ctx = with_run_example(ctx)
    add_generated(ctx)
    source = ('def applies(view):\n    return True\ndef before_call(view, state):\n'
              '    if "House 1 |" in view["question"]:\n        return {}\n    ' + action + '\n')
    claimed = change(ctx, source, tests=[claim(ctx)])
    without_claim = change(ctx, source)
    corrected = change(ctx, GOOD, tests=[claim(ctx)])
    ctx.roles = WireRoles([engineer_reply({"findings": []}, [])] + [
        engineer_reply({"changes": [candidate.entry]}, [candidate.source])
        for candidate in (claimed, without_claim, corrected)])

    package, record = engineer.run_train(ctx)

    serialized = assert_no_generated_content(ctx, record)
    assert package is not None
    attempts = record["changes"][0]["attempts"]
    assert [attempt["failed"] for attempt in attempts] == ["C5b", "C6c", None]
    c5b = detail(attempts[0], "C5b")
    assert c5b["failed"][0]["actual"] == {"status": "returned", "value": "returned nothing ({})"}
    c6c = detail(attempts[1], "C6c")
    assert c6c["fired"] == 2 and c6c["nonempty"] == 0
    assert c6c["exceptions"] == (1 if action.startswith("raise") else 0)
    assert c6c["first_exception"] is None
    fixes = [json.loads(request["user"]) for request in ctx.roles.wire
             if json.loads(request["user"]).get("request") == "fix"]
    assert [request["failed"]["check"] for request in fixes] == ["C5b", "C6c"]
    assert all(request["hook_views"]["hook_view"] == PUBLIC for request in fixes)
    assert any(hook == "before_call" and args[0]["question"] == GENERATED_VIEW["question"]
               for _, hook, args in workers.calls)
    assert RUN_EXAMPLE in serialized  # the example channel is present, not silently omitted


def test_verified_run_exception_remains_visible_in_actual_c5b_fix_request():
    run_view = {**PUBLIC, "question": PUBLIC["question"].replace(OPENING, OPENING + "\n" + RUN_MESSAGE)}
    ctx, _ = context(views=[run_view])
    add_generated(ctx)
    throwing = change(ctx, 'def applies(view):\n    return True\ndef before_call(view, state):\n'
                           '    raise LookupError(view["question"])\n', tests=[claim(ctx)])
    corrected = change(ctx, GOOD, tests=[claim(ctx)])
    ctx.roles = WireRoles([engineer_reply({"changes": [candidate.entry]}, [candidate.source])
                           for candidate in (throwing, corrected)])

    package, record = engineer.run_train(ctx)

    assert package is not None
    first = record["changes"][0]["attempts"][0]
    assert first["failed"] == "C5b"
    actual = detail(first, "C5b")["failed"][0]["actual"]
    assert actual == {"status": "raised", "exc_type": "LookupError", "message": run_view["question"][:300]}
    fix = next(json.loads(request["user"]) for request in ctx.roles.wire
               if json.loads(request["user"]).get("request") == "fix")
    assert fix["failed"]["detail"]["failed"][0]["actual"] == actual
    assert RUN_MESSAGE in assert_no_generated_content(ctx, record)


def test_generated_exception_cannot_take_the_verified_run_exception_slot_or_fix_feedback():
    run_view = {**PUBLIC, "question": PUBLIC["question"].replace(OPENING, OPENING + "\n" + RUN_MESSAGE)}
    ctx, workers = context(views=[run_view])
    add_generated(ctx)
    source = ('def applies(view):\n    return True\ndef before_call(view, state):\n'
              '    if "House 1 |" in view["question"]:\n        raise LookupError(view["question"])\n'
              '    raise ValueError(view["question"])\n')
    candidate = change(ctx, source)
    engineer._build(candidate, ctx)
    routed = engineer._routing_checks(candidate.procedure, ctx)
    passed, c6c = routed["C6c"]
    assert not passed and c6c["exceptions"] == c6c["fired"] == 2
    assert c6c["first_exception"] == {"status": "raised", "exc_type": "LookupError",
                                       "message": run_view["question"][:300]}
    assert len(workers.opened) == 1
    assert [args[0]["question"] for _, hook, args in workers.calls if hook == "before_call"] == [
        GENERATED_VIEW["question"], run_view["question"]]
    # A crashing stored run would stop at C6 in the full chain. Exercise the C6c
    # result's real fix serializer directly to cover its separate exception slot.
    report = {"checks": [{"check": "C6c", "passed": passed, "detail": c6c}], "failed": "C6c"}
    ctx.roles = WireRoles()
    engineer._fix(ctx, candidate, report, attempt=1)
    fix = json.loads(ctx.roles.wire[0]["user"])
    assert fix["failed"]["detail"]["first_exception"] == c6c["first_exception"]
    assert RUN_MESSAGE in assert_no_generated_content(ctx, report, extra=routed)
