"""Shared fakes for the coevo5 batch-2 tests: a scripted GLM-5.3 client behind the real call wrapper, so role calls go
through ``calls.Endpoint`` exactly as in a run (no ledger: the free route's path; the ledger has its own tests)."""
from __future__ import annotations

import json

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.roles import Roles

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def reply(value, *, finish="stop"):
    """A delivered receipt whose reply is ``value`` (a dict is sent as JSON text)."""
    text = value if isinstance(value, str) else json.dumps(value)
    return {"ok": finish == "stop", "response": text, "finish_reason": finish, "usage": dict(USAGE),
            "usage_valid": True, "status": 200, "attempts": [{"status": 200}], "returned_model": "glm-5.3",
            **({} if finish == "stop" else {"error_type": "finish_" + finish})}


def undelivered():
    return {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "transport",
            "attempts": [{"error": "ReadTimeout"}]}


class Script:
    """``call(system, user)`` answers from ``replies``: a list (in order) or a function ``(system, payload) ->
    receipt or value`` (a value is wrapped by ``reply``). Every request is kept in ``seen`` as (system, payload)."""

    def __init__(self, replies):
        self.replies, self.seen = replies, []

    def call(self, system, user):
        try:
            payload = json.loads(user)
        except ValueError:  # a plain-text user message (``Roles.plain``)
            payload = user
        self.seen.append((system, payload))
        if callable(self.replies):
            value = self.replies(system, payload)
        else:
            if not self.replies:
                raise AssertionError("No scripted reply left")
            value = self.replies.pop(0)
        return value if isinstance(value, dict) and "finish_reason" in value else reply(value)


def roles(tmp_path, replies, *, model="glm-5.3"):
    """(Roles, Script) over a real ``Endpoint`` without a ledger and without resend cooldowns."""
    script = Script(replies)
    endpoint = Endpoint(script, model=model, max_tokens=16384, slots=Slots(tmp_path / "slots", "glm-5.3", 4),
                        cooldown=0, sleep=lambda _: None)
    return Roles(endpoint), script
