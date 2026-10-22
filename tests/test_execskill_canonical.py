"""T-CANON-1..4: the level-1 ALFWorld canonicaliser (registration §2.2, §2.3, §14 #16; plan §1 canonical.py,
§8.1)."""
from __future__ import annotations

import inspect
import json
import re

import pytest

from skillopt.continual_eval import backends
from skillopt.execskill.canonical import HOWS, canonical, level1

ADMISSIBLE = ["go to drawer 1", "go to fridge 1", "open fridge 1", "look", "inventory"]


def frozen_extraction(reply):
    """backends.py:752-753, verbatim."""
    match = re.search(r"<action>(.*?)</action>", reply, re.S)
    return match.group(1).strip() if match else reply.strip()


# ----------------------------------------------------------------------------------------- T-CANON-1 level-1 rules
@pytest.mark.parametrize("reply, expected", [
    ("<action>go to drawer 1</action>", ("go to drawer 1", "tag_exact")),
    ("Thinking...\n<action> look </action>", ("look", "tag_exact")),
    ("<action>Action: go to drawer 1.</action>", ("go to drawer 1", "tag_level1")),
    ("<action> 'Go To Drawer 1' </action>", ("go to drawer 1", "tag_level1")),
    ("<action>“open fridge 1”.</action>", ("open fridge 1", "tag_level1")),
    ("<action>ACTION : Inventory</action>", ("inventory", "tag_level1")),
    ("go to fridge 1", ("go to fridge 1", "whole_exact")),
    ("Action: go to fridge 1", ("go to fridge 1", "whole_level1")),
    ('"open fridge 1."', ("open fridge 1", "whole_level1")),
    ("<action>examine the room</action>", ("examine the room", "unchanged")),
])
def test_level1_rules(reply, expected):
    assert canonical(reply, ADMISSIBLE) == expected


def test_level1_normal_form_repeats_until_stable():
    assert level1(" action: 'go to drawer 1.' ") == "go to drawer 1"
    assert level1("Action: Action: look..") == "look"
    assert level1("go to  drawer 1") == "go to  drawer 1"  # inner whitespace is not normalised
    assert set(HOWS) == {"tag_exact", "tag_level1", "whole_exact", "whole_level1", "unchanged"}


# ------------------------------------------------------------------------------- T-CANON-2 no earliest-admissible
@pytest.mark.parametrize("reply", [
    "I should not go to drawer 1; instead I will open fridge 1.",
    "<action>go to drawer 1 and then open it</action>",
    "<action>not go to drawer 1</action> go to fridge 1",
    "Options: go to drawer 1, look. I choose to look around.",
])
def test_no_search_of_the_reply(reply):
    action, how = canonical(reply, ADMISSIBLE)
    assert how == "unchanged" and action == frozen_extraction(reply)


# ------------------------------------------------------------------------------------- T-CANON-3 edge behaviour
def test_first_tag_only_like_the_frozen_loop():
    assert canonical("<action>look</action><action>inventory</action>", ADMISSIBLE) == ("look", "tag_exact")
    assert canonical("<action>bad</action><action>look</action>", ADMISSIBLE) == ("bad", "unchanged")


def test_ambiguous_case_and_empty_text_stay_unchanged():
    assert canonical("<action>LOOK</action>", ["look", "Look"]) == ("LOOK", "unchanged")
    assert canonical("<action>look</action>", ["look", "Look"]) == ("look", "tag_exact")
    assert canonical("<action></action>", ADMISSIBLE) == ("", "unchanged")
    assert canonical("   ", ADMISSIBLE) == ("", "unchanged")


def test_inputs_are_checked():
    with pytest.raises(ValueError):
        canonical(None, ADMISSIBLE)
    with pytest.raises(ValueError):
        canonical("look", "look")


def test_exact_and_unchanged_execute_the_frozen_text():
    replies = ["<action>look</action>", "go to fridge 1", "<action>x</action>", "Action: look", "no idea"]
    for reply in replies:
        action, how = canonical(reply, ADMISSIBLE)
        if how in ("tag_exact", "whole_exact", "unchanged"):
            assert action == frozen_extraction(reply)
        else:
            assert action in ADMISSIBLE and action != frozen_extraction(reply)


def test_frozen_extraction_is_still_backends_752():
    source = inspect.getsource(backends._solve_alfworld)
    assert 'match = re.search(r"<action>(.*?)</action>", response, re.S)' in source
    assert "action = match.group(1).strip() if match else response.strip()" in source


# ---------------------------------------------------------------- T-CANON-4 divergence from the frozen v3 loop
class ScriptedRoom:
    """A three-command text room: arriving somewhere changes the next observation; any other text does nothing."""

    def __init__(self):
        self.received = []

    def reset(self):
        return (["You are in the middle of a room. Your task is to: put a mug in the fridge."], None,
                [{"admissible_commands": list(ADMISSIBLE), "won": False}])

    def step(self, actions):
        action = actions[0]
        self.received.append(action)
        text = "You arrive at %s." % action[6:] if action in ADMISSIBLE and action.startswith("go to ") else (
            "You see a room." if action in ADMISSIBLE else "Nothing happens.")
        return [text], None, None, [False], [{"admissible_commands": list(ADMISSIBLE), "won": False}]

    def close(self):
        return None


def run_frozen_loop(monkeypatch, replies, transform):
    room, requests = ScriptedRoom(), []
    monkeypatch.setattr(backends, "_new_alfworld", lambda public, runtime: room)

    def call(system, user):
        requests.append(user)
        reply = transform(replies[len(requests) - 1], json.loads(user)["admissible_commands"])
        return {"ok": True, "response": reply, "finish_reason": "stop", "usage": {}}

    runtime = {"max_steps": len(replies), "alfworld_trace_version": backends.ALFWORLD_TRACE_VERSION}
    prediction = backends._solve_alfworld({"game_file": "unused"}, "", call, runtime)
    return room.received, requests, prediction


def test_canonicaliser_divergence_starts_at_the_first_non_exact_step(monkeypatch):
    replies = ["<action>go to drawer 1</action>", "<action>Action: go to fridge 1</action>",
               "<action>look</action>", "<action>open fridge 1</action>"]
    hows = [canonical(r, ADMISSIBLE)[1] for r in replies]
    assert hows == ["tag_exact", "tag_level1", "tag_exact", "tag_exact"]

    raw_actions, raw_requests, raw = run_frozen_loop(monkeypatch, replies, lambda reply, admissible: reply)
    route_actions, route_requests, route = run_frozen_loop(
        monkeypatch, replies, lambda reply, admissible: "<action>%s</action>" % canonical(reply, admissible)[0])

    # v3 executes the raw text, route B the canonical command, from the first non-exact step on
    assert raw_actions == ["go to drawer 1", "Action: go to fridge 1", "look", "open fridge 1"]
    assert route_actions == ["go to drawer 1", "go to fridge 1", "look", "open fridge 1"]
    first = hows.index("tag_level1")
    assert raw_requests[:first + 1] == route_requests[:first + 1]
    assert all(a != b for a, b in zip(raw_requests[first + 1:], route_requests[first + 1:]))
    assert raw["trace"][first]["post_observation"] == "Nothing happens."
    assert route["trace"][first]["post_observation"] == "You arrive at fridge 1."
    assert raw["status"] == route["status"] == "available"
