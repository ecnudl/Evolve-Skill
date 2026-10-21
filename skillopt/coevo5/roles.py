"""Method-role calls (registration §4, §6-§9, §13.5).

Every method role -- analyst, rubric judge, diagnosis, rubric reviser, researcher, rewriter, forward-item writer and
checker, leakage adjudicator, the pre-launch instruction and rubric writers -- is GLM-5.3 (reasoning low, temperature
0) behind the call wrapper of its unit attempt (``calls.Endpoint``: reservation, settlement, identical resends of a call
that delivered nothing). A role's reply must be one JSON object -- the whole reply, or the whole reply inside one
```json fence -- that the role's validator accepts; anything else is an invalid reply: it is recorded and the role's
registered fallback applies (§4). A stop of the run -- a budget stop, a broken reservation assumption, a ledger
failure, a receipt that is not a mapping -- is raised and pauses the unit; it is never mistaken for an invalid reply.
"""
from __future__ import annotations

import json
import re

from skillopt.continual_eval.core import require

from .calls import _request_hash
from .outcomes import ConfigurationError

FENCE = re.compile(r"```(?:json)?[ \t]*\n(.*)\n[ \t]*```", re.S)
NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")


class Invalid(ValueError):
    """A reply that is not what the role must return."""


def parse(text):
    """The JSON object a role replied: the whole reply, or the whole reply inside one fence."""
    if type(text) is not str:
        raise Invalid("no_text")
    body = text.strip()
    fenced = FENCE.fullmatch(body)
    if fenced is not None:
        body = fenced.group(1).strip()
    try:
        value = json.loads(body)
    except ValueError:
        raise Invalid("not_json") from None
    if type(value) is not dict:
        raise Invalid("not_an_object")
    return value


def fields(value, required, optional=()):
    """``value`` has exactly the ``required`` keys and, possibly, some of the ``optional`` ones."""
    if type(value) is not dict or not set(required) <= set(value) or not set(value) <= set(required) | set(optional):
        raise Invalid("fields")
    return value


def text(value, *, limit, empty=False):
    if type(value) is not str or (not empty and not value.strip()) or len(value) > limit:
        raise Invalid("text")
    return value


def message_bytes(user):
    """The UTF-8 size of ``user`` as ``Roles.ask`` sends it."""
    return len(json.dumps(user, ensure_ascii=False, sort_keys=True).encode())


def fit(user, key, budget):
    """v3 §6: leave out the last entries of ``user[key]`` (a list, in its shown order) until the message has at most
    ``budget`` bytes; ``user[key + "_omitted"]`` says how many were left out. Deterministic; returns ``user``. A message
    whose other fields alone exceed the budget is never sent: ValueError (the unit pauses)."""
    entries = list(user[key])
    user[key + "_omitted"] = 0
    while entries and message_bytes(user) > budget:
        entries.pop()
        user[key], user[key + "_omitted"] = list(entries), user[key + "_omitted"] + 1
    if message_bytes(user) > budget:
        raise ValueError("A role input exceeds its bound with no example left")
    return user


def items(value, *, limit, low=0):
    if type(value) is not list or not low <= len(value) <= limit:
        raise Invalid("list")
    return value


class Roles:
    """The method roles of one unit attempt. ``endpoint``: the attempt's GLM-5.3 endpoint for method roles. ``calls``:
    the record of every role call (kept in the unit's record): role, label, request hash, sends with their receipts,
    and whether the reply was valid (else why not)."""

    def __init__(self, endpoint):
        self.endpoint, self.calls = endpoint, []

    def ask(self, role, system, user, *, label, check=None):
        """The validated reply of one call, or None when it is invalid. ``user``: a JSON-serializable payload, sent as
        compact JSON; ``check(value)`` returns the accepted value or raises ``Invalid`` (or ``ValueError``)."""
        require(NAME.fullmatch(role) is not None and type(system) is str and system.strip(), "Invalid role call")
        message = json.dumps(user, ensure_ascii=False, sort_keys=True)
        recorder = self.endpoint.recorder(label=label)
        record = {"role": role, "label": label, "request_sha256": _request_hash(system, message), "sends": None,
                  "valid": False, "reason": None}
        self.calls.append(record)
        try:
            receipt = recorder(system, message)  # a stop of the run is raised from here
        finally:
            record["sends"] = recorder.sends
        if recorder.invalid:
            raise ConfigurationError("invalid_model_receipt")
        if receipt.get("ok") is not True or receipt.get("finish_reason") != "stop":
            record["reason"] = "no_reply:" + str(receipt.get("error_type") or receipt.get("finish_reason"))[:40]
            return None
        try:
            value = parse(receipt.get("response"))
            value = check(value) if check is not None else value
        except (Invalid, ValueError, TypeError, KeyError) as error:
            record["reason"] = "invalid:" + (str(error)[:80] if isinstance(error, Invalid) else type(error).__name__)
            return None
        record["valid"] = True
        return value

    def plain(self, role, system, user, *, label):
        """The text of one call whose reply is plain text (the pre-launch instruction writer, whose user message is
        the plain text of the existing generator), or None when no complete reply arrived."""
        require(NAME.fullmatch(role) is not None and type(user) is str and user.strip(), "Invalid role call")
        recorder = self.endpoint.recorder(label=label)
        record = {"role": role, "label": label, "request_sha256": _request_hash(system, user), "sends": None,
                  "valid": False, "reason": None}
        self.calls.append(record)
        try:
            receipt = recorder(system, user)
        finally:
            record["sends"] = recorder.sends
        if recorder.invalid:
            raise ConfigurationError("invalid_model_receipt")
        if receipt.get("ok") is not True or receipt.get("finish_reason") != "stop" or type(receipt.get("response")) \
                is not str:
            record["reason"] = "no_reply:" + str(receipt.get("error_type") or receipt.get("finish_reason"))[:40]
            return None
        record["valid"] = True
        return receipt["response"]

    def count(self, prefix):
        """Calls whose label starts with ``prefix`` (the per-request ceilings of §7 and §8)."""
        return sum(1 for record in self.calls if record["label"].startswith(prefix))
