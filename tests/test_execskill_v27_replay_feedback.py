"""v2.7b ALF replay indexing, missing-hook causes and disclosed-only tracker feedback; authored offline data."""
from copy import deepcopy
from fractions import Fraction
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import replay
from tests.test_execskill_replay import alf_trajectory, fixture
from tests.test_execskill_v24_engineer import Workers
from tests.test_execskill_v27_validation import case
from tests.test_execskill_zpc_pipeline import offline


SOURCE = '''def applies(view):
    return True
def alf_before_step(view, state):
    return {"fields": {"facts": [view["initial_observation"][:100]]}, "discourage": []}
def alf_after_step(event, state):
    return {"facts": {"nothing_happens": 0}, "event_step": event["step"]}
'''


def replayed(*, code=SOURCE, index=12, hook="alf_before_step", malformed=False):
    inputs = replay.inputs_of(alf_trajectory(token="fail"))
    prop = ({"kind": "note_contains", "value": "An unmatched authored claim.", "step": index}
            if hook == "alf_before_step" else {"kind": "state_equals", "key": "event_step", "value": 999, "step": index})
    test = case(cell=inputs["cell"], hook=hook, prop=prop)
    if malformed:
        test["step"] = index
    procedure = fixture("fx-v27-alf-replay", code, ("applies", "alf_before_step", "alf_after_step"),
                        tests=[test], origin="alfworld", state_bytes=4000)
    workers, actual = Workers(), {}
    entries = {inputs["cell"]: inputs}
    outcomes = replay.replay_many(procedure, list(entries.values()), workers, actual=actual)
    return procedure, entries, outcomes, actual, workers


def failure(arguments, *, enhanced=True, shown=True):
    procedure, entries, outcomes, actual, _ = arguments
    kwargs = {} if shown is None else {"shown_cells": set(entries) if shown else set()}
    okay, found = replay.claimed_tests(procedure, entries, outcomes, actual,
                                      validation_feedback=enhanced, **kwargs)
    assert not okay and found["claimed"] == 1
    return found["failed"][0]


def test_limits_show_step_inside_property_and_exact_before_after_indices():
    text = replay.test_format_limits()
    assert "INSIDE property, never at test top level" in text
    assert '{"kind":"note_contains","value":"...","step":3}' in text
    assert "0-based index of the stored step request/view" in text
    assert "for every stored action it equals alfworld_steps[].i" in text
    assert "alf_before_step at i is the note before action i" in text
    assert "alf_after_step at i is state after action i" in text
    assert "1-%d literal fragments" % replay.MAX_FRAGMENTS in text


def test_keys_feedback_lists_missing_unexpected_and_moves_property_fields():
    own = case()
    del own["property"]
    own.update(step=3, value="own", kind="note_contains", key="own-key", name="own-name", extra="own")
    explanation = replay.test_validation_feedback(own, "keys")["validation_explanation"]
    assert 'Missing top-level keys ["property"]' in explanation
    assert 'unexpected top-level keys ["extra", "key", "kind", "name", "step", "value"]' in explanation
    assert 'Move ["key", "kind", "name", "step", "value"] inside property' in explanation
    assert "extra" not in explanation.split("Move ")[1]


def test_stored_step_indices_and_actual_replay_call_positions_match():
    stored = alf_trajectory(token="fail")
    assert [value["i"] for value in stored["alfworld_steps"]] == list(range(len(stored["alfworld_steps"])))
    procedure, entries, outcomes, actual, workers = replayed(index=0)
    cell = next(iter(entries))
    inputs, outcome = entries[cell], outcomes[cell]
    assert len(inputs["steps"]) == len(outcome.steps) == len(stored["alfworld_steps"])
    before = [call for call in actual[cell] if call["hook"] == "alf_before_step"]
    after = [call for call in actual[cell] if call["hook"] == "alf_after_step"]
    assert [call["step"] for call in before] == list(range(len(inputs["steps"])))
    assert [call["step"] for call in after] == list(range(len(inputs["steps"]) - 1))
    for index, item in enumerate(inputs["steps"][:-1]):
        assert item["action"] == stored["alfworld_steps"][index]["action"]
        assert item["event"]["step"] == outcome.steps[index]["state"]["event_step"] == index
        assert item["event"]["action"] == item["action"]
        assert item["event"]["observation"] == inputs["steps"][index + 1]["view"]["observation"]
    assert inputs["steps"][-1]["event"] is None and outcome.steps[-1]["after"] is False


@pytest.mark.parametrize("mode", ["applies_false", "fault", "range"])
def test_specific_missing_hook_reasons_use_existing_replay_and_keep_old_feedback(mode):
    code = SOURCE.replace("return True", "return False") if mode == "applies_false" else SOURCE
    if mode == "fault":
        code = code.replace('return {"facts": {"nothing_happens": 0}, "event_step": event["step"]}',
                            'raise RuntimeError("authored fault " + "x" * 400)')
    arguments = replayed(code=code)
    calls = deepcopy(arguments[-1].calls)
    old = failure(arguments, enhanced=False)
    assert old["actual"] == {"status": "not_called", "reason": "hook_not_reached"}
    new = failure(arguments)
    expected = {"applies_false": "applies_false", "fault": "stopped_by_fault", "range": "step_out_of_range"}[mode]
    assert new["actual"]["reason"] == expected
    assert new["reason"] == old["reason"] == "test_failed"
    assert {key: value for key, value in new.items() if key != "actual"} == {
        key: value for key, value in old.items() if key != "actual"}
    if mode == "fault":
        assert new["actual"]["fault"]["hook"] == "alf_after_step" and new["actual"]["fault"]["step"] == 0
        assert new["actual"]["fault"]["kind"] == "crash:exception"
        assert len(new["actual"]["fault"]["detail"]) <= 200
    elif mode == "range":
        assert new["actual"]["recorded_steps"] == len(next(iter(arguments[2].values())).steps)
    assert failure(arguments, shown=False)["actual"] == {"status": "withheld", "reason": "trajectory_not_shown"}
    assert failure(arguments, shown=None)["actual"] == old["actual"]
    assert arguments[-1].calls == calls


def test_malformed_claim_and_terminal_after_hook_keep_generic_missing_reason():
    malformed = replayed(code=SOURCE.replace("return True", "return False"), malformed=True)
    found = failure(malformed)
    assert found["reason"] == "keys" and found["evaluated"] is False
    assert found["actual"] == {"status": "not_called", "reason": "hook_not_reached"}
    last = len(replay.inputs_of(alf_trajectory(token="fail"))["steps"]) - 1
    terminal = failure(replayed(index=last, hook="alf_after_step"))
    assert terminal["actual"] == {"status": "not_called", "reason": "hook_not_reached"}


def test_future_fault_does_not_explain_missing_earlier_hook_and_actual_call_always_wins():
    arguments = replayed(index=0)
    cell = next(iter(arguments[1]))
    arguments[2][cell].faults = [{"hook": "alf_after_step", "step": 1, "kind": "later-fault", "detail": "own"}]
    assert failure(arguments)["actual"]["status"] == "returned"
    arguments[3][cell] = []
    assert failure(arguments)["actual"] == {"status": "not_called", "reason": "hook_not_reached"}
    arguments[2][cell].faults[0]["step"] = 0
    assert failure(arguments)["actual"]["reason"] == "stopped_by_fault"


def tracker_contract():
    tracker = replay.ReferenceTracker("You see a table 1.")
    assert tracker.facts() == {"reached": [], "carrying": [], "nothing_happens": 0}
    events = [
        ("go to table 1", "You arrive at table 1. On the table 1, you see a mug 1.", ["table 1"], [], 0),
        ("open cabinet 1", "You open cabinet 1. You see nothing.", ["cabinet 1", "table 1"], [], 0),
        ("take mug 1 from table 1", "You pick up the mug 1 from the table 1.", ["cabinet 1", "table 1"], ["mug 1"], 0),
        ("take mug 1 from unseen 1", "You pick up the mug 1 from unseen 1.", ["cabinet 1", "table 1"], ["mug 1", "mug 1"], 0),
        ("put mug 1 in/on shelf 1", "Nothing happens.", ["cabinet 1", "table 1"], ["mug 1", "mug 1"], 1),
        ("put mug 1 in/on shelf 1", "You put the mug 1 in/on shelf 1.", ["cabinet 1", "shelf 1", "table 1"], [], 1),
        ("move mug 1 to table 2", "You move the mug 1 to table 2.", ["cabinet 1", "shelf 1", "table 1", "table 2"], [], 1),
        ("look", "You arrive at unseen 2.", ["cabinet 1", "shelf 1", "table 1", "table 2"], [], 1),
        ("go to unseen 3", "You open unseen 3.", ["cabinet 1", "shelf 1", "table 1", "table 2"], [], 1),
        ("Go to unseen 4", "You arrive at unseen 4.", ["cabinet 1", "shelf 1", "table 1", "table 2"], [], 1),
        ("go to unseen 5", "you arrive at unseen 5.", ["cabinet 1", "shelf 1", "table 1", "table 2"], [], 1),
    ]
    for action, observation, reached, carrying, rejected in events:
        tracker.update(" " + action + " ", " " + observation + " ")
        assert tracker.facts() == {"reached": reached, "carrying": carrying, "nothing_happens": rejected}


def test_tracker_paragraph_matches_fixed_update_rules_and_detects_rule_mutation(monkeypatch):
    tracker_contract()
    text = replay.tracker_format_rules()
    assert text.startswith("Reference tracker (alfworld-v2):")
    for fragment in ("Nothing happens", "go to X", "You arrive at", "open X", "You open", "take X from Y",
                     "You pick up", "move X to Y", "put X in/on Y", "You move", "You put", "retaining duplicates",
                     "removes every X", "does not add Y", "case-sensitive", "compare only keys present", ">= 97%"):
        assert fragment in text
    assert "Missing or failed after hooks are excluded" in text
    monkeypatch.setattr(replay, "TRACKER_AGREEMENT", Fraction(9, 10))
    assert ">= 90%" in replay.tracker_format_rules()
    original = replay.ReferenceTracker.update
    def wrong(self, action, observation):
        original(self, action, observation)
        if observation.strip().startswith("Nothing happens"):
            self.inventory = []
    monkeypatch.setattr(replay.ReferenceTracker, "update", wrong)
    with pytest.raises(AssertionError):
        tracker_contract()


@pytest.mark.parametrize("facts,agree", [
    ({"reached": ["table 1", "shelf 1", "table 1"]}, True),
    ({"carrying": ["mug 1", "apple 1", "mug 1"]}, True),
    ({"nothing_happens": 1}, True), ({"nothing_happens": True}, False),
    ({"carrying": ["mug 1", "apple 1"]}, False), ({"reached": ["Table 1", "shelf 1"]}, False),
    ({"reached": [1]}, False), ({"reached": ("table 1", "shelf 1")}, False),
    ({}, False), ({"unknown": 1}, False), (None, False),
])
def test_tracker_comparison_matches_paragraph_subset_types_and_duplicate_rules(facts, agree):
    reference = {"reached": ["shelf 1", "table 1"], "carrying": ["apple 1", "mug 1", "mug 1"], "nothing_happens": 1}
    assert replay.facts_agree({"facts": facts}, reference) is agree


def tracker_entries(*, count=2, shown=True):
    entries, outcomes = {}, {}
    for number in range(count):
        cell = "cell-%d" % number
        marker = "SHOWN" if number == 0 else "HIDDEN"
        events = [
            {"step": 0, "action": "go to %s-table 1" % marker,
             "observation": "You arrive at %s-table 1. You see nothing." % marker, "admissible_commands": []},
            {"step": 1, "action": "take %s-mug 1 from %s-table 1" % (marker, marker),
             "observation": "You pick up the %s-mug 1." % marker, "admissible_commands": []},
            {"step": 2, "action": "put %s-mug 1 in/on shelf 1" % marker,
             "observation": "Nothing happens. %s" % marker, "admissible_commands": []},
            {"step": 3, "action": "look", "observation": "Nothing happens. %s" % marker, "admissible_commands": []},
        ]
        entries[cell] = {"cell": cell, "item": "alfworld/" + cell, "bench": "alfworld", "token": "fail",
                         "steps": [{"view": {"initial_observation": "You see a %s-table 1." % marker},
                                    "action": event["action"], "event": event} for event in events] +
                                  [{"view": {}, "action": "look", "event": None}]}
        outcomes[cell] = replay.Outcome(cell, "alfworld", applies=True, steps=[
            {"state": {"facts": {"reached": [], "carrying": [], "nothing_happens": -1}}, "after": True}
            for _ in range(5)])
    procedure = SimpleNamespace(hooks=("applies", "alf_before_step", "alf_after_step"))
    return procedure, entries, outcomes


def test_tracker_counts_include_hidden_cells_but_only_first_three_shown_steps_are_disclosed():
    procedure, entries, outcomes = tracker_entries()
    assert replay.reference_tracker_agreement(entries, outcomes) == (0, 8)
    before = deepcopy((entries, outcomes))
    found = replay.tracker_feedback(procedure, entries, outcomes, {"cell-0", "foreign"})
    assert found["tracker_disagreement_counts"] == {"reached": 8, "carrying": 6, "nothing_happens": 8, "facts_shape": 0}
    assert [example["step"] for example in found["tracker_disagreements"]] == [0, 1, 2]
    for example in found["tracker_disagreements"]:
        assert set(example) == {"trajectory", "step", "action", "observation", "procedure_facts", "reference_facts"}
        assert example["trajectory"] == "cell-0"
        assert json.loads(example["procedure_facts"])["nothing_happens"] == -1
        assert "SHOWN" in example["action"] and len(example["observation"]) <= 200
    assert "HIDDEN" not in json.dumps(found)
    reversed_entries = dict(reversed(list(entries.items())))
    assert replay.tracker_feedback(procedure, reversed_entries, outcomes, {"cell-0"}) == found
    assert (entries, outcomes) == before
    hidden = replay.tracker_feedback(procedure, entries, outcomes, set())
    assert hidden["tracker_disagreement_counts"] == found["tracker_disagreement_counts"]
    assert hidden["tracker_disagreements"] == []


def test_tracker_missing_failed_and_terminal_after_steps_are_excluded_from_exact_denominator():
    procedure, entries, outcomes = tracker_entries(count=1)
    outcome = outcomes["cell-0"]
    outcome.steps[0]["after"] = False
    outcome.steps = outcome.steps[:2]
    assert replay.reference_tracker_agreement(entries, outcomes) == (0, 1)
    found = replay.tracker_feedback(procedure, entries, outcomes, {"cell-0"})
    assert found["tracker_disagreement_counts"] == {"reached": 1, "carrying": 1, "nothing_happens": 1, "facts_shape": 0}
    assert [example["step"] for example in found["tracker_disagreements"]] == [1]
    outcome.applies = False
    assert replay.reference_tracker_agreement(entries, outcomes) == (0, 0)
    assert all(value == 0 for value in replay.tracker_feedback(procedure, entries, outcomes, {"cell-0"})[
        "tracker_disagreement_counts"].values())


@pytest.mark.parametrize("facts,counts", [
    ({}, {"facts_shape": 1}), (None, {"facts_shape": 1}), ({"invented": "own"}, {"facts_shape": 1}),
    ({"reached": [], "invented": "own"}, {"facts_shape": 1, "reached": 1}),
    ({"nothing_happens": True}, {"nothing_happens": 1}),
    ({"nothing_happens": 0}, {}),
])
def test_tracker_counts_only_declared_fact_keys_plus_shape_not_absent_optional_keys(facts, counts):
    procedure, entries, outcomes = tracker_entries(count=1)
    outcomes["cell-0"].steps = [{"state": {"facts": facts}, "after": True}]
    found = replay.tracker_feedback(procedure, entries, outcomes, {"cell-0"})
    expected = {key: counts.get(key, 0) for key in (*replay.STATE_FACTS, "facts_shape")}
    assert found["tracker_disagreement_counts"] == expected
    assert len(found["tracker_disagreements"]) == bool(counts)


def test_tracker_examples_bound_actions_observations_and_both_json_fact_texts():
    procedure, entries, outcomes = tracker_entries(count=1)
    long = "long" * 1000
    event = entries["cell-0"]["steps"][0]["event"]
    event.update(action="go to " + long, observation="You arrive at " + long)
    outcomes["cell-0"].steps[0]["state"] = {"facts": {"reached": ["own" * 1000]}}
    found = replay.tracker_feedback(procedure, entries, outcomes, {"cell-0"})
    example = found["tracker_disagreements"][0]
    assert len(example["action"]) == len(example["observation"]) == 200
    assert len(example["procedure_facts"]) == len(example["reference_facts"]) == 1000
    assert json.loads(json.dumps(example)) == example
    assert len(found["tracker_disagreements"]) == 3
